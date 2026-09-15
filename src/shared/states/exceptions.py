"""Exception / edge-case states — STOP, OOH, IDLE, ARCH, FALLBACK, HUMAN_REQUEST, PERSONHOOD.

Also holds the S2.99 opt-out confirmation which is technically a campaign
state but is reached via the STOP path.
"""

from __future__ import annotations

import answering
import consent
import copy_library
import crm
import llm
import templates
import wa_client


# ─── STOP → S2.99 opt-out ────────────────────────────────────────────────────

def handle_stop(ctx) -> str:
    """Log opt-out, set DND for the whatsapp channel, send confirmation."""
    consent.set_dnd_whatsapp(
        ctx.contact_id,
        trigger=f"stop_keyword:{ctx.text_body.strip()[:40]}",
        source_state=ctx.current_state,
    )
    try:
        wa_client.send_text(ctx.wa_id, copy_library.get("S2.99", "body"), state_id="S2.99")
    except Exception as exc:  # noqa: BLE001
        # If the send fails (e.g. window closed and no template approved yet),
        # the opt-out itself is already persisted — that's what matters.
        print(f"exceptions.handle_stop: confirmation send failed: {exc!r}")
    crm.write_event(ctx.contact_id, "S2_99_SENT", {"source_state": ctx.current_state})
    return "X.ARCH"


def handle_optout_confirmation(ctx) -> str:
    """S2.99 is terminal — any further inbound is silently archived."""
    return "X.ARCH"


# ─── X.OOH out-of-hours ──────────────────────────────────────────────────────

def send_ooh_ack(ctx) -> None:
    """Send the OOH template acknowledgement.

    Called from the router pre-dispatch when `is_business_hours()` is False.
    The template must be approved; if not, this raises and the router logs it.
    """
    templates.send("OOH_ACK", to_wa_id=ctx.wa_id)
    crm.write_event(ctx.contact_id, "OOH_ACK_SENT", {"source_state": ctx.current_state})


def handle_ooh(ctx) -> str:
    send_ooh_ack(ctx)
    return "X.OOH"


# ─── X.IDLE ──────────────────────────────────────────────────────────────────

def handle_idle(ctx) -> str:
    # If we land here on an inbound, the contact has resumed — bounce them
    # back to welcome so the menu is re-shown.
    from states import welcome  # local import to avoid cycle
    return welcome.handle(ctx)


# ─── X.ARCH archived ─────────────────────────────────────────────────────────

def handle_archive(ctx) -> str:
    """Inbound to an archived thread: log; answer if it is an FAQ; else silent."""
    crm.write_event(
        ctx.contact_id,
        "ARCHIVED_INBOUND",
        {"msg_type": ctx.message_type, "text": ctx.text_body[:200]},
    )
    if ctx.message_type == "text" and ctx.intent == "FAQ" and llm.is_enabled():
        answering.answer_or_fallback(
            ctx,
            contact_kind=_infer_contact_kind(ctx),
            fallback_state_id="X.ARCH",
            fallback_copy_state_id="X.FALLBACK",
        )
    return "X.ARCH"


# ─── X.FALLBACK ──────────────────────────────────────────────────────────────

def fallback(ctx) -> str:
    # If the LLM classified this as an answerable FAQ, try to answer before
    # falling back to the menu re-show. The scripted funnel remains the anchor;
    # the LLM only fills the gap when the user asks something the state
    # machine has no branch for.
    if ctx.message_type == "text" and ctx.intent == "FAQ" and llm.is_enabled():
        answered = answering.answer_or_fallback(
            ctx,
            contact_kind=_infer_contact_kind(ctx),
            fallback_state_id=ctx.current_state,
            fallback_copy_state_id="X.FALLBACK",
        )
        # answer_or_fallback returns the current state when the LLM path
        # succeeded and sent a reply. Only re-show the menu when it fell back.
        if answered == ctx.current_state:
            return ctx.current_state

    wa_client.send_text(ctx.wa_id, copy_library.get("X.FALLBACK", "body"), state_id="X.FALLBACK")
    # Also re-show the welcome menu so the user has a way forward.
    from states import welcome
    return welcome.handle(ctx)


def _infer_contact_kind(ctx) -> str:
    """Rough contact-kind inference from current state for LLM system prompt."""
    s = ctx.current_state or ""
    if s.startswith("S1.20"):
        return "vendor"
    if s.startswith("S1.40"):
        return "career"
    if s.startswith("S1.50") or s.startswith("S1.51"):
        return "press"
    if s.startswith("S1.1") or s.startswith("S1.14") or s.startswith("S1.17") or s.startswith("S1.19"):
        return "client"
    return "unknown"


# ─── X.HUMAN_REQUEST ─────────────────────────────────────────────────────────

def handle_human_request(ctx) -> str:
    wa_client.send_text(ctx.wa_id, copy_library.get("X.HUMAN_REQUEST", "body"), state_id="X.HUMAN_REQUEST")
    crm.write_event(ctx.contact_id, "HUMAN_REQUESTED", {"source_state": ctx.current_state})
    return "X.HUMAN_REQUEST"


# ─── X.PERSONHOOD_QUERY ──────────────────────────────────────────────────────

def handle_personhood(ctx) -> str:
    wa_client.send_text(ctx.wa_id, copy_library.get("X.PERSONHOOD_QUERY", "body"), state_id="X.PERSONHOOD_QUERY")
    return ctx.current_state  # stay put; user will try again
