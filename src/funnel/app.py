"""Funnel Lambda — scheduler-driven sweeps + Razorpay webhook.

Message routing lives in `src/inbound/app.py` (fast-path for Meta's 5s window).
This Lambda owns everything that doesn't happen inside an inbound webhook:

  * `/webhook/razorpay` — payment_link.paid → create calendar event → send
    S1.18.step_c / S1.19a.step_c → transition state to E.00.
  * Scheduler sweep (every 30 min) — find bookings with slot_iso_start in
    the T-24h and T-2h windows, dispatch BOOKING_REMINDER_24H (client) and
    BOOKING_REMINDER_2H_PARTNER (partner).
  * Scheduler sweep (every 90 min) — find contacts idle mid-funnel > 24h,
    dispatch IDLE_REMINDER template.
"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timedelta, timezone

import calendar_client as gcal
import copy_library
import crm
import killswitch
import razorpay
import state_machine
import templates
import wa_client

# Meeting reference_id prefixes — must match those set at payment-link creation
# in project_discussion.py / walkthrough.py.
_REF_PROJECT_DISC = "pd"
_REF_WALKTHROUGH = "sw"

# States considered "mid-funnel" for the idle sweep.
_IDLE_STATES = (
    "S1.10", "S1.11", "S1.12", "S1.13a", "S1.13b",
    "S1.14", "S1.14a", "S1.14.GATE", "S1.14b", "S1.15",
    "S1.17", "S1.17.SLOT", "S1.18.step_b",
    "S1.19", "S1.19.CAP", "S1.19a.tier", "S1.19a.slot", "S1.19a.step_b",
    "S1.20a", "S1.20b",
    "S1.40",
    "S1.50", "S1.51",
    "E.00", "E.SUB.step_a",
)

_IDLE_HOURS = int(os.environ.get("IDLE_HOURS", "24"))
_PARTNER_WA_ID = os.environ.get("PARTNER_WHATSAPP_E164", "+919560107193").lstrip("+")


def handler(event: dict, context) -> dict:
    if not killswitch.is_enabled():
        return {"statusCode": 200, "body": "killswitch off"}

    source = event.get("source", "")
    path = (event.get("path") or event.get("resource") or "").rstrip("/")
    detail_type = event.get("detail-type", "")

    if path.endswith("/webhook/razorpay"):
        return _handle_razorpay_webhook(event)
    if source == "aws.scheduler" or source == "aws.events":
        return _handle_scheduled(event, detail_type)

    print(f"funnel: unknown trigger — source={source!r} path={path!r} detail_type={detail_type!r}")
    return {"statusCode": 400, "body": "unknown trigger"}


# ─── Scheduled sweeps ────────────────────────────────────────────────────────

def _handle_scheduled(event: dict, detail_type: str) -> dict:
    """Route by EventBridge rule name / detail_type.

    The template.yaml wires two rules:
      * `as-whatsapp-reminders-cron` (every 30 min) → detail_type "reminders"
      * `as-whatsapp-idle-cron` (every 90 min)      → detail_type "idle"
    """
    detail = event.get("detail", {})
    kind = detail.get("kind") or detail_type or "reminders"
    if kind in ("reminders", "booking-reminders"):
        return _sweep_booking_reminders()
    if kind in ("idle", "idle-sweep"):
        return _sweep_idle_contacts()
    print(f"funnel: unknown scheduled kind {kind!r} — noop")
    return {"statusCode": 200, "body": "noop"}


def _sweep_booking_reminders() -> dict:
    now = datetime.now(timezone.utc)
    # Client 24h reminder: slots in [now+23.5h, now+24.5h)
    client_cutoff_start = (now + timedelta(hours=23, minutes=30)).isoformat()
    client_cutoff_end = (now + timedelta(hours=24, minutes=30)).isoformat()
    partner_cutoff_start = (now + timedelta(hours=1, minutes=30)).isoformat()
    partner_cutoff_end = (now + timedelta(hours=2, minutes=30)).isoformat()

    client_bookings = crm.scan_bookings_between(client_cutoff_start, client_cutoff_end)
    partner_bookings = crm.scan_bookings_between(partner_cutoff_start, partner_cutoff_end)

    sent_client = _fire_reminders(client_bookings, "BOOKING_REMINDER_24H", target="client")
    sent_partner = _fire_reminders(partner_bookings, "BOOKING_REMINDER_2H_PARTNER", target="partner")

    print(f"funnel: reminders sweep — client={sent_client} partner={sent_partner}")
    return {"statusCode": 200, "body": f"reminders sent client={sent_client} partner={sent_partner}"}


def _fire_reminders(bookings: list[dict], template_key: str, target: str) -> int:
    sent = 0
    for booking in bookings:
        contact_id = booking.get("contact_id", "")
        slot_start = booking.get("slot_iso_start", "")
        if not contact_id or not slot_start:
            continue
        if crm.reminder_already_sent(contact_id, template_key + "_SENT", slot_start):
            continue

        # For the client-side reminder we need the contact's wa_id. For the
        # partner-side reminder we always send to the fixed PARTNER_WA_ID.
        try:
            if target == "client":
                profile = _profile(contact_id)
                phone = profile.get("phone_e164", "")
                if not phone:
                    continue
                to_wa_id = phone.lstrip("+")
            else:
                to_wa_id = _PARTNER_WA_ID

            templates.send(template_key, to_wa_id=to_wa_id)
            crm.write_event(
                contact_id,
                template_key + "_SENT",
                {"slot_iso_start": slot_start, "target": target},
            )
            sent += 1
        except RuntimeError as exc:
            # Template not approved yet — skip quietly, count as skipped
            print(f"funnel: skipping {template_key} for {contact_id}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"funnel: {template_key} send failed for {contact_id}: {exc!r}")
    return sent


def _sweep_idle_contacts() -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=_IDLE_HOURS)).isoformat()
    profiles = crm.scan_idle_in_funnel(cutoff, _IDLE_STATES)
    sent = 0
    for profile in profiles:
        contact_id = profile.get("contact_id", "")
        phone = profile.get("phone_e164", "")
        if not contact_id or not phone:
            continue
        try:
            templates.send("IDLE_REMINDER", to_wa_id=phone.lstrip("+"))
            crm.write_event(
                contact_id,
                "IDLE_REMINDER_SENT",
                {"idle_state": profile.get("current_state", "")},
            )
            crm.mark_idle_reminder_sent(contact_id)
            sent += 1
        except RuntimeError as exc:
            print(f"funnel: skipping IDLE_REMINDER for {contact_id}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"funnel: IDLE_REMINDER send failed for {contact_id}: {exc!r}")
    print(f"funnel: idle sweep — considered={len(profiles)} sent={sent}")
    return {"statusCode": 200, "body": f"idle sweep sent={sent}"}


# ─── Razorpay webhook ────────────────────────────────────────────────────────

def _handle_razorpay_webhook(event: dict) -> dict:
    body = _raw_body(event)
    signature = _header(event, "x-razorpay-signature")

    try:
        ok = razorpay.verify_webhook_signature(body, signature)
    except Exception as exc:  # noqa: BLE001
        print(f"funnel: razorpay signature verify raised: {exc!r}")
        return {"statusCode": 500, "body": "signature verify failed"}
    if not ok:
        print("funnel: razorpay signature mismatch — rejecting")
        return {"statusCode": 403, "body": "signature mismatch"}

    payload = json.loads(body.decode("utf-8"))
    event_type = payload.get("event", "")

    if event_type not in ("payment_link.paid", "payment.captured"):
        print(f"funnel: razorpay {event_type} ignored")
        return {"statusCode": 200, "body": "ignored"}

    payment_link = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
    payment_id = payment.get("id", "")
    reference_id = payment_link.get("reference_id", "")

    if not payment_id or not reference_id:
        print(f"funnel: razorpay payload missing payment_id/reference_id — noop")
        return {"statusCode": 200, "body": "ignored (missing fields)"}

    if crm.payment_already_processed(payment_id):
        print(f"funnel: razorpay {payment_id} already processed — dedup")
        return {"statusCode": 200, "body": "duplicate"}

    parsed = _parse_reference_id(reference_id)
    if not parsed:
        print(f"funnel: reference_id {reference_id!r} — cannot parse")
        return {"statusCode": 200, "body": "ignored (bad ref)"}

    prefix, contact_id, slot_yyyymmddhhmm = parsed

    # 1. Record payment (also serves as future idempotency guard)
    amount_paid = int(payment.get("amount", 0)) / 100
    crm.write_event(
        contact_id,
        "PAYMENT_CAPTURED",
        {
            "razorpay_payment_id": payment_id,
            "razorpay_link_id": payment_link.get("id", ""),
            "reference_id": reference_id,
            "amount_inr": amount_paid,
            "currency": payment.get("currency", "INR"),
            "method": payment.get("method", ""),
        },
    )

    # 2. Fetch session context saved during the state flow
    profile = _profile(contact_id)
    session = profile.get("session", {}) or {}
    slot_iso_start = session.get("slot_iso_start", "")
    slot_iso_end = session.get("slot_iso_end", "")
    slot_human = session.get("slot_human", "")
    to_wa_id = profile.get("phone_e164", "").lstrip("+")

    if not slot_iso_start or not to_wa_id:
        print(f"funnel: session missing slot/phone for {contact_id} — payment recorded, confirm manually")
        return {"statusCode": 200, "body": "payment recorded, session missing"}

    # 3. Create calendar event
    try:
        if prefix == _REF_PROJECT_DISC:
            summary = "Project Discussion — Atelier Shreenu"
        else:
            summary = "Site & Vision Walkthrough — Atelier Shreenu"
        event_out = gcal.create_event(
            summary=summary,
            start_iso=slot_iso_start,
            end_iso=slot_iso_end,
            attendee_phone_e164="+" + to_wa_id,
            attendee_name=session.get("contact_name", ""),
            description=_describe(session, prefix),
        )
        crm.write_event(
            contact_id,
            "BOOKING_CREATED",
            {
                "meeting_type": "project_discussion" if prefix == _REF_PROJECT_DISC else "site_walkthrough",
                "slot_iso_start": slot_iso_start,
                "slot_iso_end": slot_iso_end,
                "cal_event_id": event_out.get("id", ""),
                "cal_event_link": event_out.get("htmlLink", ""),
                "amount_inr": amount_paid,
            },
        )
    except Exception as exc:  # noqa: BLE001
        print(f"funnel: calendar create failed after payment {payment_id}: {exc!r}")
        # Payment is captured but calendar failed — still confirm, log the mismatch
        # so ops can create the event manually.
        crm.write_event(
            contact_id,
            "BOOKING_CREATE_FAILED",
            {"payment_id": payment_id, "error": str(exc)[:500]},
        )

    # 4. Send the confirmation copy to the client
    try:
        if prefix == _REF_PROJECT_DISC:
            body_text = copy_library.render("S1.18.step_c", {"slot_human": slot_human})
            state_id = "S1.18.step_c"
        else:
            amount_human = f"{int(amount_paid):,}"
            body_text = copy_library.render(
                "S1.19a.step_c",
                {"slot_human": slot_human, "amount_human": amount_human},
            )
            state_id = "S1.19a.step_c"
        wa_client.send_text(to_wa_id, body_text, state_id=state_id)
    except Exception as exc:  # noqa: BLE001
        print(f"funnel: confirmation send failed for {contact_id}: {exc!r}")

    # 5. Transition state
    state_machine.set_state(contact_id, "E.00")

    return {"statusCode": 200, "body": "ok"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

_REF_PATTERN = re.compile(r"^(pd|sw)-([0-9a-f-]{36})-(\d{12})$")


def _parse_reference_id(reference_id: str) -> tuple[str, str, str] | None:
    m = _REF_PATTERN.match(reference_id)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def _describe(session: dict, prefix: str) -> str:
    parts = []
    if prefix == _REF_PROJECT_DISC:
        parts.append("Project Discussion via Google Meet — 30 minutes.")
    else:
        tier = session.get("walkthrough_tier", "")
        duration = session.get("walkthrough_duration_min", "")
        parts.append(f"Site & Vision Walkthrough ({tier}) — {duration} minutes.")
        if session.get("site_address"):
            parts.append(f"Site address: {session['site_address']}")
    if session.get("project_type"):
        parts.append(f"Project type: {session['project_type']}")
    if session.get("contact_email"):
        parts.append(f"Client email: {session['contact_email']}")
    return "\n".join(parts)


def _profile(contact_id: str) -> dict:
    """Fetch the contact's PROFILE row directly (bypasses public crm helpers)."""
    import boto3
    table = boto3.resource("dynamodb").Table(os.environ.get("TABLE_NAME", "as-email-contacts"))
    resp = table.get_item(Key={"contact_id": contact_id, "sk": "PROFILE"})
    return resp.get("Item", {}) or {}


def _raw_body(event: dict) -> bytes:
    body = event.get("body", "") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def _header(event: dict, name: str) -> str:
    headers = event.get("headers") or {}
    name_lower = name.lower()
    for k, v in headers.items():
        if k.lower() == name_lower:
            return v or ""
    return ""
