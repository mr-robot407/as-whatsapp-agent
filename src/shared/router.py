"""Message router — the single dispatch point for every inbound WhatsApp message.

Order of checks (short-circuit):
  1. Killswitch (SSM) — if off, do nothing.
  2. DND — silent drop (contact opted out).
  3. Human takeover — a partner is handling this thread manually; ingest the
     inbound (for the audit log) but suppress every agent-generated reply.
  4. STOP keyword → S2.99 opt-out flow + set_dnd_whatsapp + write OPT_OUT event.
  5. RESTART keyword → S1.00 welcome, session cleared.
  6. LLM intent classifier (if enabled) — free-text messages get classified.
     PERSONHOOD_QUERY / HUMAN_REQUEST / OPT_OUT / BOOKING_CHANGE / OFF_TOPIC
     short-circuit to their scripted state before the funnel dispatcher runs.
     FAQ intents fall through to the state handler, which decides whether to
     answer via LLM or continue the scripted flow.
  7. Out-of-hours → X.OOH ack (template) + let the current state also process.
  8. Dispatch to state handler based on `current_state`.

State handlers live in `src/shared/states/*.py` and expose `handle(ctx)` returning
the next state_id. The router persists that transition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import consent
import ist_time
import killswitch
import llm
import state_machine
from states import (
    career,
    discovery,
    engagement,
    exceptions,
    other,
    project_discussion,
    project_nature,
    subscribe,
    vendor,
    walkthrough,
    welcome,
)

# ─── Router context ──────────────────────────────────────────────────────────

@dataclass
class RouterContext:
    contact_id: str
    wa_id: str
    message: dict
    current_state: str = "S1.00"
    session: dict = field(default_factory=dict)
    intent: str = ""  # populated by the LLM classifier on free-text inputs

    # Convenience accessors -------------------------------------------------
    @property
    def message_type(self) -> str:
        return self.message.get("type", "unknown")

    @property
    def text_body(self) -> str:
        return self.message.get("text", {}).get("body", "")

    @property
    def button_id(self) -> str:
        """For interactive button_reply / list_reply, return the reply id."""
        interactive = self.message.get("interactive", {})
        itype = interactive.get("type", "")
        if itype == "button_reply":
            return interactive.get("button_reply", {}).get("id", "")
        if itype == "list_reply":
            return interactive.get("list_reply", {}).get("id", "")
        return ""


# ─── State registry ──────────────────────────────────────────────────────────

# Only the states implemented in Phase 2a are wired. States without an entry
# fall through to `exceptions.fallback` (X.FALLBACK) which re-shows the welcome
# menu. Phase 2b adds S1.10, S1.14 flow, S1.17/S1.18, S1.19, S1.20, S1.40, S1.50.

STATE_REGISTRY: dict[str, Callable[[RouterContext], str]] = {
    # Root
    "S1.00": welcome.handle,
    # Qualification path
    "S1.10":  project_nature.handle_s110,
    "S1.11":  project_nature.handle_s111,
    "S1.12":  project_nature.handle_s112,
    "S1.12a": project_nature.handle_s112a,
    "S1.13a": project_nature.handle_s113a,
    "S1.13b": project_nature.handle_s113b,
    # Discovery Call (complimentary)
    "S1.14":       discovery.handle_s114,
    "S1.14a":      discovery.handle_s114a,
    "S1.14.GATE":  discovery.handle_s114_gate,
    "S1.14b":      discovery.handle_s114b,
    "S1.15":       discovery.handle_s115,
    "S1.16":       discovery.handle_s116,
    # Project Discussion (paid)
    "S1.17":        project_discussion.handle_s117,
    "S1.17.SLOT":   project_discussion.handle_s117_slot,
    "S1.18.step_b": project_discussion.handle_s118_step_b,
    # Site & Vision Walkthrough (paid)
    "S1.19":        walkthrough.handle_s119,
    "S1.19.CAP":    walkthrough.handle_s119_cap,
    "S1.19a.tier":  walkthrough.handle_s119a_tier,
    "S1.19a.slot":  walkthrough.handle_s119a_slot,
    "S1.19a.step_b": walkthrough.handle_s119a_step_b,
    # Vendor
    "S1.20a": vendor.handle_s120a,
    "S1.20b": vendor.handle_s120b,
    "S1.20c": vendor.handle_s120c,
    # Career
    "S1.40":  career.handle_s140,
    "S1.40b": career.handle_s140b,
    # Other / Press
    "S1.50":  other.handle_s150,
    "S1.51":  other.handle_s151,
    # Post-menu engagement
    "E.00":   engagement.handle_post_menu,
    "E.IG":   engagement.handle_instagram,
    "E.WEB":  engagement.handle_website,
    "E.EMAIL": engagement.handle_email,
    "E.VC":   engagement.handle_vcard,
    "E.RECO": engagement.handle_recommend,
    "E.SUB.step_a": subscribe.handle_step_a,
    "E.SUB.step_b": subscribe.handle_step_b,
    # Terminal / edge cases
    "S2.99":               exceptions.handle_optout_confirmation,
    "X.OOH":               exceptions.handle_ooh,
    "X.IDLE":              exceptions.handle_idle,
    "X.ARCH":              exceptions.handle_archive,
    "X.FALLBACK":          exceptions.fallback,
    "X.HUMAN_REQUEST":     exceptions.handle_human_request,
    "X.PERSONHOOD_QUERY":  exceptions.handle_personhood,
}


# ─── Entry point ─────────────────────────────────────────────────────────────

# Intent labels that short-circuit the normal state dispatch. Order matters:
# OPT_OUT is checked before anything else; PERSONHOOD_QUERY and HUMAN_REQUEST
# jump to their scripted handlers regardless of current_state.
_INTENT_JUMP: dict[str, str] = {
    "PERSONHOOD_QUERY": "X.PERSONHOOD_QUERY",
    "HUMAN_REQUEST":    "X.HUMAN_REQUEST",
}


def route(contact_id: str, wa_id: str, message: dict) -> str:
    """Handle one inbound message end-to-end. Return the state we ended in."""
    if not killswitch.is_enabled():
        print(f"router: killswitch off — dropped inbound for {contact_id}")
        return "SKIPPED_KILLSWITCH"

    if consent.is_dnd_whatsapp(contact_id):
        print(f"router: DND set — dropped inbound for {contact_id}")
        return "DROPPED_DND"

    if consent.is_human_takeover_active(contact_id):
        # A partner is handling this thread manually — record the inbound but
        # do not emit any agent reply. The inbound has already been written by
        # the webhook handler; nothing more to do here.
        print(f"router: human takeover active for {contact_id} — muting agent")
        return "MUTED_HUMAN_TAKEOVER"

    current_state, session = state_machine.get_state(contact_id)
    ctx = RouterContext(
        contact_id=contact_id,
        wa_id=wa_id,
        message=message,
        current_state=current_state,
        session=session,
    )

    # STOP keyword wins over everything.
    if state_machine.is_stop_keyword(ctx.text_body):
        print(f"router: STOP keyword from {contact_id} — routing to S2.99")
        next_state = exceptions.handle_stop(ctx)
        state_machine.set_state(contact_id, next_state)
        return next_state

    # RESTART = drop to root, clear session.
    if state_machine.is_restart_keyword(ctx.text_body):
        print(f"router: RESTART keyword from {contact_id} — reset to S1.00")
        state_machine.clear_session(contact_id)
        next_state = welcome.handle(ctx)
        state_machine.set_state(contact_id, next_state)
        return next_state

    # Classify intent on free-text inbounds. Button/list replies are structured
    # inputs — the state handler consumes them directly, no LLM call needed.
    if ctx.message_type == "text" and ctx.text_body.strip():
        ctx.intent = llm.classify_intent(ctx.text_body, current_state=current_state)
        if ctx.intent == "OPT_OUT":
            # Conversational STOP — treat identically to the keyword path.
            print(f"router: LLM intent OPT_OUT for {contact_id} — routing to S2.99")
            next_state = exceptions.handle_stop(ctx)
            state_machine.set_state(contact_id, next_state)
            return next_state
        jump = _INTENT_JUMP.get(ctx.intent)
        if jump:
            print(f"router: LLM intent {ctx.intent!r} for {contact_id} — jump to {jump}")
            handler = STATE_REGISTRY.get(jump, exceptions.fallback)
            next_state = handler(ctx)
            if next_state and next_state != current_state:
                state_machine.set_state(contact_id, next_state)
            return next_state

    # Out-of-hours: X.OOH runs its template ack THEN we still dispatch normally
    # so the user's message is not lost — the state handler queues its own reply.
    if not ist_time.is_business_hours():
        try:
            exceptions.send_ooh_ack(ctx)
        except Exception as exc:  # noqa: BLE001
            print(f"router: OOH ack failed for {contact_id}: {exc!r}")

    handler = STATE_REGISTRY.get(current_state, exceptions.fallback)
    try:
        next_state = handler(ctx)
    except Exception as exc:  # noqa: BLE001
        print(f"router: state handler {current_state!r} failed: {exc!r}")
        next_state = exceptions.fallback(ctx)

    if next_state and next_state != current_state:
        state_machine.set_state(contact_id, next_state)
    return next_state
