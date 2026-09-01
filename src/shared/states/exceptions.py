"""Exception / edge-case states — STOP, OOH, IDLE, ARCH, FALLBACK, HUMAN_REQUEST, PERSONHOOD.

Also holds the S2.99 opt-out confirmation which is technically a campaign
state but is reached via the STOP path.
"""

from __future__ import annotations

import consent
import copy
import crm
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
    """Any inbound to an archived thread is silently absorbed — no reply."""
    crm.write_event(
        ctx.contact_id,
        "ARCHIVED_INBOUND",
        {"msg_type": ctx.message_type, "text": ctx.text_body[:200]},
    )
    return "X.ARCH"


# ─── X.FALLBACK ──────────────────────────────────────────────────────────────

def fallback(ctx) -> str:
    wa_client.send_text(ctx.wa_id, copy_library.get("X.FALLBACK", "body"), state_id="X.FALLBACK")
    # Also re-show the welcome menu so the user has a way forward.
    from states import welcome
    return welcome.handle(ctx)


# ─── X.HUMAN_REQUEST ─────────────────────────────────────────────────────────

def handle_human_request(ctx) -> str:
    wa_client.send_text(ctx.wa_id, copy_library.get("X.HUMAN_REQUEST", "body"), state_id="X.HUMAN_REQUEST")
    crm.write_event(ctx.contact_id, "HUMAN_REQUESTED", {"source_state": ctx.current_state})
    return "X.HUMAN_REQUEST"


# ─── X.PERSONHOOD_QUERY ──────────────────────────────────────────────────────

def handle_personhood(ctx) -> str:
    wa_client.send_text(ctx.wa_id, copy_library.get("X.PERSONHOOD_QUERY", "body"), state_id="X.PERSONHOOD_QUERY")
    return ctx.current_state  # stay put; user will try again
