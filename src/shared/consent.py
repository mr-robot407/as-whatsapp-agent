"""DND / consent — WhatsApp-channel-specific opt-out with audit event.

The email agent atomically flips all three DND channels on any opt-out
(email + whatsapp + phone). Here we default to whatsapp-only, but the same
"opt-out is universal" fan-out is available via `set_dnd_all_channels()` for
STOP-style broad opt-outs.

`human_takeover_until` is a per-contact temporary mute: while the timestamp
is in the future, the router still ingests the inbound (write_event) but
suppresses all agent-generated replies. Used when a partner takes over a
thread manually — the LLM won't step on the human reply.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import boto3

import crm

_TABLE_NAME = os.environ.get("TABLE_NAME", "as-email-contacts")
_resource = boto3.resource("dynamodb")
_table = _resource.Table(_TABLE_NAME)


def is_dnd_whatsapp(contact_id: str) -> bool:
    resp = _table.get_item(Key={"contact_id": contact_id, "sk": "PROFILE"})
    item = resp.get("Item", {})
    return item.get("dnd", {}).get("whatsapp", False)


def set_dnd_whatsapp(contact_id: str, trigger: str, source_state: str) -> None:
    """Opt this contact out of WhatsApp only. Writes OPT_OUT event."""
    _table.update_item(
        Key={"contact_id": contact_id, "sk": "PROFILE"},
        UpdateExpression="SET #dnd.whatsapp = :t",
        ExpressionAttributeNames={"#dnd": "dnd"},
        ExpressionAttributeValues={":t": True},
    )
    crm.write_event(
        contact_id,
        "OPT_OUT",
        {"trigger": trigger, "source_state": source_state, "channel": "whatsapp"},
    )


def is_human_takeover_active(contact_id: str) -> bool:
    """True iff `human_takeover_until` is set and still in the future (UTC)."""
    resp = _table.get_item(Key={"contact_id": contact_id, "sk": "PROFILE"})
    item = resp.get("Item", {})
    until = item.get("human_takeover_until")
    if not until:
        return False
    try:
        deadline = datetime.fromisoformat(until.replace("Z", "+00:00"))
    except ValueError:
        return False
    return deadline > datetime.now(timezone.utc)


def set_human_takeover(contact_id: str, hours: int = 24, actor: str = "partner", note: str = "") -> str:
    """Mute agent replies for this contact until now+hours. Returns ISO deadline."""
    deadline = datetime.now(timezone.utc) + timedelta(hours=hours)
    deadline_iso = deadline.isoformat(timespec="seconds")
    _table.update_item(
        Key={"contact_id": contact_id, "sk": "PROFILE"},
        UpdateExpression="SET human_takeover_until = :d, human_takeover_actor = :a",
        ExpressionAttributeValues={":d": deadline_iso, ":a": actor},
    )
    crm.write_event(
        contact_id,
        "HUMAN_TAKEOVER_SET",
        {"until": deadline_iso, "actor": actor, "note": note[:200]},
    )
    return deadline_iso


def clear_human_takeover(contact_id: str, actor: str = "partner") -> None:
    """Release the mute so the agent can reply again."""
    _table.update_item(
        Key={"contact_id": contact_id, "sk": "PROFILE"},
        UpdateExpression="REMOVE human_takeover_until, human_takeover_actor",
    )
    crm.write_event(contact_id, "HUMAN_TAKEOVER_CLEARED", {"actor": actor})


def set_dnd_all_channels(contact_id: str, trigger: str, source_state: str) -> None:
    """Fan-out opt-out across all channels — used for STOP and hard bounces."""
    _table.update_item(
        Key={"contact_id": contact_id, "sk": "PROFILE"},
        UpdateExpression="SET #dnd.#email = :t, #dnd.whatsapp = :t, #dnd.#phone = :t",
        ExpressionAttributeNames={"#dnd": "dnd", "#email": "email", "#phone": "phone"},
        ExpressionAttributeValues={":t": True},
    )
    crm.write_event(
        contact_id,
        "OPT_OUT",
        {"trigger": trigger, "source_state": source_state, "channel": "all"},
    )
