"""S1.14 → S1.14a → S1.14.GATE → S1.14b → S1.15 → S1.16 — complimentary Discovery Call.

Discovery Call is 10-min, no fee, no crediting. On slot pick we create the
calendar event directly (no payment gate) and confirm.
"""

from __future__ import annotations

import calendar_client as gcal
import copy_library
import crm
import flows
import slots
import wa_client

_DURATION_MIN = 10
_MEETING_TYPE = "discovery_call"

_S114_ACCEPT_ID = "S1.14.ACCEPT"
_S114_SKIP_ID = "S1.14.SKIP"
_S114A_DONE_ID = "S1.14a.DONE"

_S114_GATE_ITEMS = [
    {"id": "S1.14.GATE.CLIENT",  "title": "Client / owner"},
    {"id": "S1.14.GATE.BROKER",  "title": "Broker / consultant"},
    {"id": "S1.14.GATE.VENDOR",  "title": "Vendor / firm"},
    {"id": "S1.14.GATE.OTHER",   "title": "Other"},
]


# ─── S1.14 offer ─────────────────────────────────────────────────────────────

def handle_s114(ctx) -> str:
    if ctx.button_id == _S114_ACCEPT_ID:
        crm.write_event(ctx.contact_id, "STATE_TRANSITION", {"from": "S1.14", "to": "S1.14a"})
        return "S1.14a"
    if ctx.button_id == _S114_SKIP_ID:
        return "S1.14.GATE"

    interactive = {
        "type": "button",
        "body": {"text": copy_library.get("S1.14", "body")},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": _S114_ACCEPT_ID, "title": "Book Discovery Call"}},
                {"type": "reply", "reply": {"id": _S114_SKIP_ID,   "title": "Skip additional details"}},
            ]
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.14")
    return "S1.14"


# ─── S1.14a additional details capture ───────────────────────────────────────

def handle_s114a(ctx) -> str:
    if ctx.button_id == _S114A_DONE_ID:
        return "S1.14.GATE"
    if ctx.message_type in ("text", "image", "video", "audio", "document"):
        # Record whatever landed (text or media id).
        payload = {"msg_type": ctx.message_type}
        if ctx.message_type == "text":
            payload["text"] = ctx.text_body[:2000]
        crm.write_event(ctx.contact_id, "PROJECT_DETAILS_CAPTURE", payload)

    body = copy_library.get("S1.14a", "body")
    interactive = {
        "type": "button",
        "body": {"text": body},
        "action": {
            "buttons": [{"type": "reply", "reply": {"id": _S114A_DONE_ID, "title": "Done — proceed"}}]
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.14a")
    return "S1.14a"


# ─── S1.14.GATE relationship confirm ─────────────────────────────────────────

def handle_s114_gate(ctx) -> str:
    if ctx.button_id in [b["id"] for b in _S114_GATE_ITEMS]:
        rel = ctx.button_id.split(".")[-1]
        ctx.session["gate_relationship"] = rel
        if rel == "VENDOR":
            return "S1.20a"
        crm.write_event(
            ctx.contact_id,
            "STATE_TRANSITION",
            {"from": "S1.14.GATE", "to": "S1.14b", "relationship": rel},
        )
        return "S1.14b"

    interactive = {
        "type": "list",
        "body": {"text": copy_library.get("S1.14.GATE", "body")},
        "action": {
            "button": "Confirm",
            "sections": [{"title": "Relationship", "rows": _S114_GATE_ITEMS}],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.14.GATE")
    return "S1.14.GATE"


# ─── S1.14b contact confirmation Flow ────────────────────────────────────────

def handle_s114b(ctx) -> str:
    # If a flow response landed, extract email + phone and advance.
    interactive = ctx.message.get("interactive", {})
    if interactive.get("type") == "nfm_reply":
        response_json = interactive.get("nfm_reply", {}).get("response_json", "{}")
        import json
        try:
            data = json.loads(response_json)
        except Exception:  # noqa: BLE001
            data = {}
        ctx.session["contact_email"] = data.get("contact_email", "")
        ctx.session["contact_name"] = data.get("contact_name", "")
        ctx.session["contact_phone_e164"] = data.get("contact_phone_e164", "")
        crm.write_event(
            ctx.contact_id,
            "CONTACT_CONFIRMED",
            {
                "email": ctx.session["contact_email"],
                "name": ctx.session["contact_name"],
                "phone": ctx.session["contact_phone_e164"],
            },
        )
        return "S1.15"

    # Otherwise: send the Flow message.
    try:
        flows.send(
            "CONTACT_CONFIRMATION",
            to_wa_id=ctx.wa_id,
            header_text="Confirm contact details",
            body_text=copy_library.get("S1.14b", "body"),
            footer_text="Atelier Shreenu",
            cta_label="Confirm details",
            flow_token=flows.new_flow_token(),
            autofill={
                "contact_phone_e164": "+" + ctx.wa_id,
                "contact_name": "",
                "contact_email": "",
            },
            state_id="S1.14b",
        )
    except RuntimeError as exc:
        # Flow not published yet — fall back to freeform text capture.
        print(f"S1.14b: flow not published, using freeform fallback: {exc!r}")
        wa_client.send_text(
            ctx.wa_id,
            copy_library.get("S1.14b", "body") + "\n\nReply as: NAME | EMAIL",
            state_id="S1.14b.fallback",
        )
    return "S1.14b"


# ─── S1.15 slot selection ────────────────────────────────────────────────────

def handle_s115(ctx) -> str:
    if ctx.button_id.startswith("SLOT_"):
        try:
            start, end = slots.decode(ctx.button_id)
        except ValueError as exc:
            print(f"S1.15: bad slot id {ctx.button_id!r}: {exc!r}")
            wa_client.send_text(ctx.wa_id, copy_library.get("X.FALLBACK", "body"), state_id="S1.15.bad")
            return "S1.15"

        ctx.session["slot_iso_start"] = start.isoformat()
        ctx.session["slot_iso_end"] = end.isoformat()
        ctx.session["slot_human"] = start.strftime("%a %d %b · %H:%M IST")
        ctx.session["meeting_type"] = _MEETING_TYPE

        # Discovery Call is complimentary — book and confirm now.
        try:
            event = gcal.create_event(
                summary="Discovery Call — Atelier Shreenu",
                start_iso=start.isoformat(),
                end_iso=end.isoformat(),
                attendee_phone_e164="+" + ctx.wa_id,
                attendee_name=ctx.session.get("contact_name", ""),
                description=_describe_call(ctx.session),
            )
            crm.write_event(
                ctx.contact_id,
                "BOOKING_CREATED",
                {
                    "meeting_type": _MEETING_TYPE,
                    "slot_iso_start": start.isoformat(),
                    "slot_iso_end": end.isoformat(),
                    "cal_event_id": event.get("id", ""),
                    "cal_event_link": event.get("htmlLink", ""),
                },
            )
        except Exception as exc:  # noqa: BLE001
            print(f"S1.15: calendar create failed: {exc!r}")
            wa_client.send_text(
                ctx.wa_id,
                "The studio's calendar is momentarily unreachable — kindly resend the choice in a few minutes.",
                state_id="S1.15.retry",
            )
            return "S1.15"

        # Confirmation copy at S1.16.
        return "S1.16"

    # First entry: generate slots and present.
    try:
        busy = gcal.freebusy(_lookahead_bounds()[0], _lookahead_bounds()[1])
    except Exception as exc:  # noqa: BLE001
        print(f"S1.15: freebusy failed, offering unfiltered slots: {exc!r}")
        busy = []

    candidates = slots.generate(duration_minutes=_DURATION_MIN, busy=busy)
    if not candidates:
        wa_client.send_text(
            ctx.wa_id,
            "The partner's calendar has no openings in the immediate window. Kindly try again shortly.",
            state_id="S1.15.empty",
        )
        return "S1.15"

    rows = [s.to_list_row() for s in candidates]
    interactive = {
        "type": "list",
        "body": {"text": copy_library.get("S1.15", "body")},
        "action": {
            "button": "Choose a slot",
            "sections": [{"title": "Next openings", "rows": rows}],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.15")
    return "S1.15"


# ─── S1.16 confirmation ──────────────────────────────────────────────────────

def handle_s116(ctx) -> str:
    slot_human = ctx.session.get("slot_human", "")
    body = copy_library.render("S1.16", {"slot_human": slot_human})
    wa_client.send_text(ctx.wa_id, body, state_id="S1.16")
    # Present the post-menu.
    return "E.00"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _describe_call(session: dict) -> str:
    parts = ["WhatsApp Discovery Call — 10 minutes."]
    if session.get("project_type"):
        parts.append(f"Project type: {session['project_type']}")
    if session.get("project_location"):
        parts.append(f"Location: {session['project_location']}")
    if session.get("project_area_band"):
        parts.append(f"Area band: {session['project_area_band']}")
    if session.get("contact_email"):
        parts.append(f"Client email: {session['contact_email']}")
    return "\n".join(parts)


def _lookahead_bounds() -> tuple[str, str]:
    import ist_time
    from datetime import timedelta
    now = ist_time.now_ist()
    return now.isoformat(), (now + timedelta(days=14)).isoformat()
