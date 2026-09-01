"""24-hour customer service window guard.

Meta permits free-form (non-template) messages only within 24 hours of the
contact's most recent inbound message. Outside the window, only pre-approved
templates may be sent.

The guard checks for a recent WHATSAPP_INBOUND event on this contact_id.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key

_TABLE_NAME = os.environ.get("TABLE_NAME", "as-email-contacts")
_WINDOW_HOURS = int(os.environ.get("CUSTOMER_SERVICE_WINDOW_HOURS", "24"))

_resource = boto3.resource("dynamodb")
_table = _resource.Table(_TABLE_NAME)


def window_open(contact_id: str, now: datetime | None = None) -> bool:
    """True if the contact has sent an inbound message in the last WINDOW_HOURS."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=_WINDOW_HOURS)).isoformat(timespec="milliseconds")
    resp = _table.query(
        KeyConditionExpression=Key("contact_id").eq(contact_id) & Key("sk").gte(cutoff),
        FilterExpression=Attr("type").eq("WHATSAPP_INBOUND"),
        Limit=1,
        ScanIndexForward=False,
    )
    return len(resp.get("Items", [])) > 0


def assert_window_open(contact_id: str, state_id: str = "") -> None:
    """Raise RuntimeError if outside 24-hour window — caller must switch to template."""
    if not window_open(contact_id):
        prefix = f"[{state_id}] " if state_id else ""
        raise RuntimeError(
            f"{prefix}customer-service window closed for {contact_id} — use an approved template"
        )
