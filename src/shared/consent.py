"""DND / consent — WhatsApp-channel-specific opt-out with audit event.

The email agent atomically flips all three DND channels on any opt-out
(email + whatsapp + phone). Here we default to whatsapp-only, but the same
"opt-out is universal" fan-out is available via `set_dnd_all_channels()` for
STOP-style broad opt-outs.
"""

from __future__ import annotations

import os

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
