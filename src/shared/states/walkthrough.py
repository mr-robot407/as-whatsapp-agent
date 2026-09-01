"""S1.19 → S1.19.CAP → S1.19a.tier → S1.19a.step_b — Site & Vision Walkthrough (paid).

Tier NCR (Rs 3,540, 60 min) or Outside NCR (Rs 7,080, 120 min). Site address
captured via a Flow. S1.19a.step_c is fired from the Razorpay webhook.
"""

from __future__ import annotations

import copy_library
import crm
import flows
import razorpay
import slots
import wa_client
import calendar_client as gcal

_STATE_OFFER = "S1.19"
_STATE_CAP = "S1.19.CAP"
_STATE_TIER = "S1.19a.tier"
_STATE_SLOT = "S1.19a.slot"
_STATE_WAIT = "S1.19a.step_b"

_S119_ACCEPT_ID = "S1.19.ACCEPT"
_S119_DECLINE_ID = "S1.19.DECLINE"

_TIERS = {
    "S1.19a.NCR":     {"label": "Within NCR",  "amount_inr": 3540, "duration_min": 60,  "code": "ncr"},
    "S1.19a.OUTSIDE": {"label": "Outside NCR", "amount_inr": 7080, "duration_min": 120, "code": "outside_ncr"},
}


# ─── S1.19 offer ─────────────────────────────────────────────────────────────

def handle_s119(ctx) -> str:
    if ctx.button_id == _S119_ACCEPT_ID:
        crm.write_event(ctx.contact_id, "STATE_TRANSITION", {"from": _STATE_OFFER, "to": _STATE_CAP})
        return _STATE_CAP
    if ctx.button_id == _S119_DECLINE_ID:
        return "E.00"

    interactive = {
        "type": "button",
        "body": {"text": copy_library.get("S1.19", "body")},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": _S119_ACCEPT_ID,  "title": "Book — see tiers"}},
                {"type": "reply", "reply": {"id": _S119_DECLINE_ID, "title": "Not now"}},
            ]
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.19")
    return _STATE_OFFER


# ─── S1.19.CAP site location Flow ────────────────────────────────────────────

def handle_s119_cap(ctx) -> str:
    interactive = ctx.message.get("interactive", {})
    if interactive.get("type") == "nfm_reply":
        import json
        try:
            data = json.loads(interactive.get("nfm_reply", {}).get("response_json", "{}"))
        except Exception:  # noqa: BLE001
            data = {}
        ctx.session["site_address"] = data.get("site_address", "")
        ctx.session["contact_phone_e164"] = data.get("contact_phone_e164", "+" + ctx.wa_id)
        crm.write_event(
            ctx.contact_id,
            "SITE_LOCATION_CAPTURED",
            {"address": ctx.session["site_address"], "phone": ctx.session["contact_phone_e164"]},
        )
        return _STATE_TIER

    try:
        flows.send(
            "SITE_LOCATION_CAPTURE",
            to_wa_id=ctx.wa_id,
            header_text="Site details",
            body_text=copy_library.get("S1.19.CAP", "body"),
            footer_text="Atelier Shreenu",
            cta_label="Share site details",
            flow_token=flows.new_flow_token(),
            autofill={
                "site_address": "",
                "contact_phone_e164": "+" + ctx.wa_id,
            },
            state_id="S1.19.CAP",
        )
    except RuntimeError as exc:
        print(f"S1.19.CAP: flow not published — freeform fallback: {exc!r}")
        wa_client.send_text(
            ctx.wa_id,
            copy_library.get("S1.19.CAP", "body")
            + "\n\nReply with the full site address on one line.",
            state_id="S1.19.CAP.fallback",
        )
    return _STATE_CAP


# ─── S1.19a tier selection ───────────────────────────────────────────────────

def handle_s119a_tier(ctx) -> str:
    if ctx.button_id in _TIERS:
        tier = _TIERS[ctx.button_id]
        ctx.session["walkthrough_tier"] = tier["code"]
        ctx.session["walkthrough_amount_inr"] = tier["amount_inr"]
        ctx.session["walkthrough_duration_min"] = tier["duration_min"]
        return _STATE_SLOT

    body = (
        "Kindly select the tier that matches the site location:\n"
        f"• Within NCR — Rs 3,540 (incl. GST) · 60 min\n"
        f"• Outside NCR — Rs 7,080 (incl. GST) · 120 min · travel and accommodation billed at actuals"
    )
    interactive = {
        "type": "button",
        "body": {"text": body},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": "S1.19a.NCR",     "title": "Within NCR"}},
                {"type": "reply", "reply": {"id": "S1.19a.OUTSIDE", "title": "Outside NCR"}},
            ]
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.19a.tier")
    return _STATE_TIER


# ─── S1.19a slot → payment link ──────────────────────────────────────────────

def handle_s119a_slot(ctx) -> str:
    duration = int(ctx.session.get("walkthrough_duration_min", 60))
    amount = int(ctx.session.get("walkthrough_amount_inr", 3540))
    tier_code = ctx.session.get("walkthrough_tier", "ncr")

    if ctx.button_id.startswith("SLOT_"):
        try:
            start, end = slots.decode(ctx.button_id)
        except ValueError:
            wa_client.send_text(ctx.wa_id, copy_library.get("X.FALLBACK", "body"), state_id="S1.19a.slot.bad")
            return _STATE_SLOT

        ctx.session["slot_iso_start"] = start.isoformat()
        ctx.session["slot_iso_end"] = end.isoformat()
        ctx.session["slot_human"] = start.strftime("%a %d %b · %H:%M IST")
        ctx.session["meeting_type"] = "site_walkthrough"

        try:
            link = razorpay.create_payment_link(
                amount_inr=amount,
                description=f"Site & Vision Walkthrough ({tier_code}) — {ctx.session['slot_human']} — Atelier Shreenu",
                contact_name=ctx.session.get("contact_name", "Client"),
                contact_phone_e164=ctx.session.get("contact_phone_e164", "+" + ctx.wa_id),
                reference_id=f"sw-{ctx.contact_id}-{start.strftime('%Y%m%d%H%M')}",
                expire_by_unix=_expire_by_unix(),
                contact_email=ctx.session.get("contact_email", ""),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"S1.19a.slot: razorpay link failed: {exc!r}")
            wa_client.send_text(
                ctx.wa_id,
                "The payment gateway is momentarily unreachable — kindly retry in a few minutes.",
                state_id="S1.19a.slot.retry",
            )
            return _STATE_SLOT

        ctx.session["razorpay_link_id"] = link.get("id", "")
        ctx.session["razorpay_short_url"] = link.get("short_url", "")

        wa_client.send_text(ctx.wa_id, copy_library.get("S1.19a.step_b", "body"), state_id="S1.19a.step_b")
        wa_client.send_text(ctx.wa_id, link.get("short_url", ""), state_id="S1.19a.step_b.link")

        crm.write_event(
            ctx.contact_id,
            "PAYMENT_LINK_SENT",
            {
                "meeting_type": "site_walkthrough",
                "tier": tier_code,
                "amount_inr": amount,
                "razorpay_link_id": link.get("id", ""),
                "short_url": link.get("short_url", ""),
                "slot_iso_start": start.isoformat(),
                "site_address": ctx.session.get("site_address", ""),
            },
        )
        return _STATE_WAIT

    try:
        busy = gcal.freebusy(*_lookahead_bounds())
    except Exception:
        busy = []
    candidates = slots.generate(duration_minutes=duration, busy=busy)
    if not candidates:
        wa_client.send_text(
            ctx.wa_id,
            "The partner's calendar has no openings in the immediate window. Kindly try again shortly.",
            state_id="S1.19a.slot.empty",
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
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.19a.slot")
    return _STATE_SLOT


# ─── S1.19a.step_b waiting for payment ───────────────────────────────────────

def handle_s119a_step_b(ctx) -> str:
    short_url = ctx.session.get("razorpay_short_url", "")
    if not short_url:
        wa_client.send_text(
            ctx.wa_id,
            "The payment link is being re-issued — kindly wait a moment.",
            state_id="S1.19a.step_b.stub",
        )
        return _STATE_WAIT
    wa_client.send_text(
        ctx.wa_id,
        f"The payment link for the Site & Vision Walkthrough is still open:\n{short_url}",
        state_id="S1.19a.step_b.remind",
    )
    return _STATE_WAIT


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _lookahead_bounds() -> tuple[str, str]:
    import ist_time
    from datetime import timedelta
    now = ist_time.now_ist()
    return now.isoformat(), (now + timedelta(days=14)).isoformat()


def _expire_by_unix() -> int:
    import time
    return int(time.time() + 30 * 60)
