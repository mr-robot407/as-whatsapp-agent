"""S1.17 → S1.18.step_b (payment link) — Project Discussion (paid, 30 min, Meet).

S1.18.step_c (payment confirmation) fires from the Razorpay webhook in
`src/funnel/app.py` — not driven by an inbound message.
"""

from __future__ import annotations

import calendar_client as gcal
import copy_library
import crm
import razorpay
import slots
import wa_client

_DURATION_MIN = 30
_MEETING_TYPE = "project_discussion"
_AMOUNT_INR = 1770
_STATE_OFFER = "S1.17"
_STATE_SLOT = "S1.17.SLOT"
_STATE_WAIT = "S1.18.step_b"

_S117_ACCEPT_ID = "S1.17.ACCEPT"
_S117_DECLINE_ID = "S1.17.DECLINE"


# ─── S1.17 offer ─────────────────────────────────────────────────────────────

def handle_s117(ctx) -> str:
    if ctx.button_id == _S117_ACCEPT_ID:
        crm.write_event(ctx.contact_id, "STATE_TRANSITION", {"from": _STATE_OFFER, "to": _STATE_SLOT})
        return _STATE_SLOT
    if ctx.button_id == _S117_DECLINE_ID:
        return "E.00"

    interactive = {
        "type": "button",
        "body": {"text": copy_library.get("S1.17", "body")},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": _S117_ACCEPT_ID,  "title": "Book — Rs 1,770"}},
                {"type": "reply", "reply": {"id": _S117_DECLINE_ID, "title": "Not now"}},
            ]
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.17")
    return _STATE_OFFER


# ─── S1.17.SLOT slot selection → S1.18.step_b payment link ──────────────────

def handle_s117_slot(ctx) -> str:
    if ctx.button_id.startswith("SLOT_"):
        try:
            start, end = slots.decode(ctx.button_id)
        except ValueError:
            wa_client.send_text(ctx.wa_id, copy_library.get("X.FALLBACK", "body"), state_id="S1.17.slot.bad")
            return _STATE_SLOT

        ctx.session["slot_iso_start"] = start.isoformat()
        ctx.session["slot_iso_end"] = end.isoformat()
        ctx.session["slot_human"] = start.strftime("%a %d %b · %H:%M IST")
        ctx.session["meeting_type"] = _MEETING_TYPE

        # Generate Razorpay Payment Link.
        try:
            link = razorpay.create_payment_link(
                amount_inr=_AMOUNT_INR,
                description=f"Project Discussion — {ctx.session['slot_human']} — Atelier Shreenu",
                contact_name=ctx.session.get("contact_name", "Client"),
                contact_phone_e164="+" + ctx.wa_id,
                reference_id=f"pd-{ctx.contact_id}-{start.strftime('%Y%m%d%H%M')}",
                expire_by_unix=_expire_by_unix(),
                contact_email=ctx.session.get("contact_email", ""),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"S1.17.SLOT: razorpay link creation failed: {exc!r}")
            wa_client.send_text(
                ctx.wa_id,
                "The payment gateway is momentarily unreachable — kindly retry in a few minutes.",
                state_id="S1.17.slot.retry",
            )
            return _STATE_SLOT

        ctx.session["razorpay_link_id"] = link.get("id", "")
        ctx.session["razorpay_short_url"] = link.get("short_url", "")

        wa_client.send_text(ctx.wa_id, copy_library.get("S1.18.step_b", "body"), state_id="S1.18.step_b")
        wa_client.send_text(ctx.wa_id, link.get("short_url", ""), state_id="S1.18.step_b.link")

        crm.write_event(
            ctx.contact_id,
            "PAYMENT_LINK_SENT",
            {
                "meeting_type": _MEETING_TYPE,
                "amount_inr": _AMOUNT_INR,
                "razorpay_link_id": link.get("id", ""),
                "short_url": link.get("short_url", ""),
                "slot_iso_start": start.isoformat(),
            },
        )
        return _STATE_WAIT

    # First entry: generate & present slots.
    try:
        busy = gcal.freebusy(*_lookahead_bounds())
    except Exception:
        busy = []
    candidates = slots.generate(duration_minutes=_DURATION_MIN, busy=busy)
    if not candidates:
        wa_client.send_text(
            ctx.wa_id,
            "The partner's calendar has no openings in the immediate window. Kindly try again shortly.",
            state_id="S1.17.slot.empty",
        )
        return _STATE_SLOT

    interactive = {
        "type": "list",
        "body": {"text": copy_library.get("S1.15", "body")},
        "action": {
            "button": "Choose a slot",
            "sections": [{"title": "Next openings", "rows": [s.to_list_row() for s in candidates]}],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.17.slot")
    return _STATE_SLOT


# ─── S1.18.step_b waiting for payment ────────────────────────────────────────

def handle_s118_step_b(ctx) -> str:
    """Contact messaged while we're waiting on Razorpay. Re-send the link."""
    short_url = ctx.session.get("razorpay_short_url", "")
    if not short_url:
        wa_client.send_text(
            ctx.wa_id,
            "The payment link is being re-issued — kindly wait a moment.",
            state_id="S1.18.step_b.stub",
        )
        return _STATE_WAIT
    wa_client.send_text(
        ctx.wa_id,
        f"The payment link for the Project Discussion is still open:\n{short_url}",
        state_id="S1.18.step_b.remind",
    )
    return _STATE_WAIT


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _lookahead_bounds() -> tuple[str, str]:
    import ist_time
    from datetime import timedelta
    now = ist_time.now_ist()
    return now.isoformat(), (now + timedelta(days=14)).isoformat()


def _expire_by_unix() -> int:
    """Payment link expires in 30 minutes per S1.18.step_b copy."""
    import time
    return int(time.time() + 30 * 60)
