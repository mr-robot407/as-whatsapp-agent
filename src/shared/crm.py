"""DynamoDB helpers — contact resolution by phone, event writes, lookups.

The table `as-email-contacts` is shared with the email agent; schema mirrors
`as-email-agent/src/shared/db.py`. This module is phone-first — helpers for
email are re-exported for the rare cross-channel case (same contact reached
by both).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key

from identity import new_contact_id

_TABLE_NAME = os.environ.get("TABLE_NAME", "as-email-contacts")
_GSI_PHONE = os.environ.get("GSI_PHONE", "GSI-PHONE")
_GSI_EMAIL = os.environ.get("GSI_EMAIL", "GSI-EMAIL")

_resource = boto3.resource("dynamodb")
_table = _resource.Table(_TABLE_NAME)


# ─── Identity resolution ─────────────────────────────────────────────────────

def resolve_by_phone(phone_e164: str) -> dict | None:
    """Query GSI-PHONE; return the PROFILE item for this phone or None."""
    resp = _table.query(
        IndexName=_GSI_PHONE,
        KeyConditionExpression=Key("phone_e164").eq(phone_e164),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def resolve_by_email(email: str) -> dict | None:
    email_norm = email.strip().lower()
    resp = _table.query(
        IndexName=_GSI_EMAIL,
        KeyConditionExpression=Key("email_normalised").eq(email_norm),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def get_or_create_by_phone(phone_e164: str, name: str = "") -> tuple[str, bool]:
    """Return (contact_id, created). Creates PROFILE if phone not found."""
    existing = resolve_by_phone(phone_e164)
    if existing:
        return existing["contact_id"], False
    contact_id = new_contact_id()
    item: dict[str, Any] = {
        "contact_id": contact_id,
        "sk": "PROFILE",
        "phone_e164": phone_e164,
        "created_at": _ts(),
        "dnd": {"email": False, "whatsapp": False, "phone": False},
        "lead_score": "cold",
        "campaign_count_ytd": 0,
        "source_channel": "whatsapp",
    }
    if name:
        item["name"] = name
    _table.put_item(Item=item)
    return contact_id, True


# ─── Event writes ─────────────────────────────────────────────────────────────

def write_event(contact_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Append an event row (sk = ts#event_type)."""
    ts = _ts()
    _table.put_item(
        Item={
            "contact_id": contact_id,
            "sk": f"{ts}#{event_type}",
            "type": event_type,
            "ts": ts,
            **payload,
        }
    )


def message_processed(message_id: str) -> bool:
    """Idempotency check — has this Meta message id already been recorded?

    Meta retries webhook delivery on non-2xx responses; this guards against
    processing the same inbound message twice.
    """
    resp = _table.scan(
        FilterExpression=(
            Attr("type").eq("WHATSAPP_INBOUND")
            & Attr("wa_message_id").eq(message_id)
        ),
        Limit=1,
    )
    return len(resp.get("Items", [])) > 0


# ─── Lead score / campaign counter ───────────────────────────────────────────

def update_lead_score(contact_id: str, prior: str, new: str, reason: str) -> None:
    _table.update_item(
        Key={"contact_id": contact_id, "sk": "PROFILE"},
        UpdateExpression="SET lead_score = :s",
        ExpressionAttributeValues={":s": new},
    )
    write_event(
        contact_id,
        "LEAD_SCORE_UPDATE",
        {"prior_band": prior, "new_band": new, "reason": reason, "channel": "whatsapp"},
    )


def increment_campaign_count(contact_id: str) -> int:
    resp = _table.update_item(
        Key={"contact_id": contact_id, "sk": "PROFILE"},
        UpdateExpression="ADD campaign_count_ytd :one",
        ExpressionAttributeValues={":one": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(resp["Attributes"]["campaign_count_ytd"])


# ─── Booking checks (shared with email-agent semantics) ──────────────────────

def has_paid_booking(contact_id: str) -> bool:
    resp = _table.query(
        KeyConditionExpression=Key("contact_id").eq(contact_id),
        FilterExpression=Attr("type").eq("PAYMENT_CAPTURED"),
    )
    return len(resp.get("Items", [])) > 0


def has_any_booking(contact_id: str) -> bool:
    resp = _table.query(
        KeyConditionExpression=Key("contact_id").eq(contact_id),
        FilterExpression=Attr("type").eq("BOOKING_CREATED"),
    )
    return len(resp.get("Items", [])) > 0


def payment_already_processed(razorpay_payment_id: str) -> bool:
    """Idempotency guard — Razorpay retries `payment_link.paid` on non-2xx."""
    resp = _table.scan(
        FilterExpression=(
            Attr("type").eq("PAYMENT_CAPTURED")
            & Attr("razorpay_payment_id").eq(razorpay_payment_id)
        ),
        Limit=1,
    )
    return len(resp.get("Items", [])) > 0


def reminder_already_sent(contact_id: str, reminder_type: str, slot_iso_start: str) -> bool:
    """Dedupe reminder sends per (contact, reminder_type, slot)."""
    resp = _table.query(
        KeyConditionExpression=Key("contact_id").eq(contact_id),
        FilterExpression=(
            Attr("type").eq(reminder_type)
            & Attr("slot_iso_start").eq(slot_iso_start)
        ),
    )
    return len(resp.get("Items", [])) > 0


def scan_bookings_between(cutoff_start_iso: str, cutoff_end_iso: str) -> list[dict]:
    """Return BOOKING_CREATED events with slot_iso_start ∈ [start, end)."""
    results: list[dict] = []
    kwargs: dict = {
        "FilterExpression": (
            Attr("type").eq("BOOKING_CREATED")
            & Attr("slot_iso_start").gte(cutoff_start_iso)
            & Attr("slot_iso_start").lt(cutoff_end_iso)
        )
    }
    while True:
        resp = _table.scan(**kwargs)
        results.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    return results


def scan_idle_in_funnel(
    idle_since_iso: str,
    idle_states: tuple[str, ...],
) -> list[dict]:
    """PROFILE items whose current_state is mid-funnel and last_state_change_at ≤ cutoff."""
    results: list[dict] = []
    kwargs: dict = {
        "FilterExpression": (
            Attr("sk").eq("PROFILE")
            & Attr("current_state").is_in(list(idle_states))
            & Attr("last_state_change_at").lte(idle_since_iso)
            & Attr("idle_reminder_sent").not_exists()
        )
    }
    while True:
        resp = _table.scan(**kwargs)
        results.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    return results


def mark_idle_reminder_sent(contact_id: str) -> None:
    _table.update_item(
        Key={"contact_id": contact_id, "sk": "PROFILE"},
        UpdateExpression="SET idle_reminder_sent = :t",
        ExpressionAttributeValues={":t": _ts()},
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
