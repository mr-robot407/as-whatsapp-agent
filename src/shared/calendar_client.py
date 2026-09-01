"""Google Calendar client — creates and reads bookings on the shared calendar.

Credentials shared with the email agent — Secrets Manager path
`as-email-agent/google-oauth` per §.env.example. Same calendar
(`ateliershreenu@gmail.com`) and same service-account impersonation.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

import boto3
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

_SECRET_ARN = os.environ.get(
    "GOOGLE_OAUTH_SECRET_ARN",
    f"arn:aws:secretsmanager:{os.environ.get('REGION', 'ap-south-1')}:{os.environ.get('AWS_ACCOUNT_ID', '')}:secret:as-email-agent/google-oauth",
)
_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "ateliershreenu@gmail.com")
_SCOPES = ["https://www.googleapis.com/auth/calendar"]


@lru_cache(maxsize=1)
def _service():
    sm = boto3.client("secretsmanager")
    secret = json.loads(sm.get_secret_value(SecretId=_SECRET_ARN)["SecretString"])
    creds = Credentials(
        token=None,
        refresh_token=secret["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=secret["client_id"],
        client_secret=secret["client_secret"],
        scopes=_SCOPES,
    )
    creds.refresh(Request())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    attendee_phone_e164: str,
    attendee_name: str = "",
    description: str = "",
    location: str = "Atelier Shreenu, Palam Vihar, Gurugram — 122017",
) -> dict:
    """Create a Google Calendar event and return the event resource.

    Attendees are keyed by email in Google Calendar; for phone-only WhatsApp
    contacts the phone number goes into the description so the studio has it.
    """
    if attendee_phone_e164:
        description = (
            f"WhatsApp contact: {attendee_phone_e164}"
            + (f"\nName: {attendee_name}" if attendee_name else "")
            + ("\n\n" + description if description else "")
        )
    body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start_iso, "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": end_iso, "timeZone": "Asia/Kolkata"},
    }
    return _service().events().insert(calendarId=_CALENDAR_ID, body=body).execute()


def get_event(event_id: str) -> dict:
    return _service().events().get(calendarId=_CALENDAR_ID, eventId=event_id).execute()


def freebusy(start_iso: str, end_iso: str) -> list[dict]:
    """Return busy intervals on the studio calendar in [start_iso, end_iso).

    Each interval is `{"start": iso, "end": iso}`. Empty list = calendar is free.
    """
    body = {
        "timeMin": start_iso,
        "timeMax": end_iso,
        "timeZone": "Asia/Kolkata",
        "items": [{"id": _CALENDAR_ID}],
    }
    resp = _service().freebusy().query(body=body).execute()
    return resp.get("calendars", {}).get(_CALENDAR_ID, {}).get("busy", [])
