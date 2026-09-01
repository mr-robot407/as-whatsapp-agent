"""Hooks Lambda — one-tap unsubscribe + Google Calendar pull-sync.

Routes:
  GET  /webhook/unsubscribe?cid=<contact_id>&c=<campaign> — HTML confirmation page.
  POST /webhook/unsubscribe                              — RFC 8058 one-click body.
  (Scheduler) source=aws.scheduler + kind=calendar_sync  — pull recent events.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import calendar_client as gcal
import consent
import crm

_HTML_OK = """<!doctype html><meta charset="utf-8"><title>Atelier Shreenu — unsubscribed</title>
<style>body{{font-family:Georgia,serif;max-width:520px;margin:80px auto;color:#222;line-height:1.55;padding:0 20px}}</style>
<h1>Unsubscribed</h1>
<p>The number is removed from Atelier Shreenu's outreach. No further messages will be sent.</p>
<p>The channel remains open at +91 95602 06195 should the studio be of service in future.</p>
"""

_HTML_ERR = """<!doctype html><meta charset="utf-8"><title>Atelier Shreenu</title>
<style>body{{font-family:Georgia,serif;max-width:520px;margin:80px auto;color:#222;line-height:1.55;padding:0 20px}}</style>
<h1>Missing details</h1>
<p>The unsubscribe request could not be processed. Kindly write to
<a href="mailto:info@ateliershreenu.com">info@ateliershreenu.com</a>.</p>
"""


def handler(event: dict, context) -> dict:
    source = event.get("source", "")
    detail = event.get("detail", {}) or {}
    method = event.get("httpMethod", "").upper()
    path = (event.get("path") or event.get("resource") or "").rstrip("/")

    if source == "aws.scheduler" or source == "aws.events":
        kind = detail.get("kind", "")
        if kind == "calendar_sync":
            return _run_calendar_sync()
        print(f"hooks: unknown scheduled kind {kind!r} — noop")
        return _reply(200, "noop")

    if path.endswith("/webhook/unsubscribe"):
        if method == "GET":
            return _handle_unsubscribe_get(event)
        if method == "POST":
            return _handle_unsubscribe_post(event)
        return _reply(405, "method not allowed")

    return _reply(400, "unknown trigger")


# ─── Unsubscribe (GET + POST RFC 8058) ───────────────────────────────────────

def _handle_unsubscribe_get(event: dict) -> dict:
    params = event.get("queryStringParameters") or {}
    contact_id = params.get("cid", "").strip()
    campaign = params.get("c", "").strip()
    if not contact_id:
        return _reply(400, _HTML_ERR, content_type="text/html")
    _apply_optout(contact_id, campaign, method="get")
    return _reply(200, _HTML_OK, content_type="text/html")


def _handle_unsubscribe_post(event: dict) -> dict:
    # RFC 8058 one-click: the mail client POSTs an empty (or ``List-Unsubscribe=One-Click``) body.
    # We accept either query-string or body-form params.
    params = event.get("queryStringParameters") or {}
    if not params.get("cid"):
        body = event.get("body") or ""
        for k, v in parse_qs(body).items():
            if v:
                params[k] = v[0]
    contact_id = (params.get("cid") or "").strip()
    campaign = (params.get("c") or "").strip()
    if not contact_id:
        return _reply(400, "missing cid")
    _apply_optout(contact_id, campaign, method="post_one_click")
    return _reply(200, "ok")


def _apply_optout(contact_id: str, campaign: str, method: str) -> None:
    try:
        consent.set_dnd_all_channels(
            contact_id,
            trigger=f"unsubscribe_link:{method}",
            source_state=campaign or "unknown",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"hooks: unsubscribe failed for {contact_id}: {exc!r}")


# ─── Calendar pull-sync — cancellations propagate to CRM ─────────────────────

def _run_calendar_sync() -> dict:
    """Fetch calendar events in the next 14d; flag cancelled ones on CRM."""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=14)
    try:
        # Simple approach: read events, then for each CRM BOOKING_CREATED in
        # the window, check if the corresponding cal_event still exists /
        # is not cancelled. If missing/cancelled → write BOOKING_CANCELLED event.
        bookings = crm.scan_bookings_between(now.isoformat(), horizon.isoformat())
    except Exception as exc:  # noqa: BLE001
        print(f"hooks: calendar_sync scan failed: {exc!r}")
        return _reply(500, "scan failed")

    cancelled = 0
    for booking in bookings:
        cal_event_id = booking.get("cal_event_id", "")
        if not cal_event_id:
            continue
        contact_id = booking.get("contact_id", "")
        try:
            event = gcal.get_event(cal_event_id)
            if event.get("status") == "cancelled":
                crm.write_event(
                    contact_id,
                    "BOOKING_CANCELLED",
                    {
                        "cal_event_id": cal_event_id,
                        "slot_iso_start": booking.get("slot_iso_start", ""),
                        "reason": "cancelled_via_calendar",
                    },
                )
                cancelled += 1
        except Exception as exc:  # noqa: BLE001
            print(f"hooks: calendar_sync get_event({cal_event_id}) failed: {exc!r}")

    print(f"hooks: calendar_sync — considered={len(bookings)} cancelled={cancelled}")
    return _reply(200, f"sync done cancelled={cancelled}")


# ─── HTTP helpers ────────────────────────────────────────────────────────────

def _reply(status: int, body: str, content_type: str = "text/plain") -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": content_type},
        "body": body,
        "isBase64Encoded": False,
    }
