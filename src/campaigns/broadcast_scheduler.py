"""Batch selection + queue-state helpers for the S2.00 outreach.

Queue-state model: each PROFILE item carries `outreach_queue_state` in
{"pending", "sent", "skipped"}. Contacts default to unset (never queued).
`scripts/seed_outreach_segment.py` bulk-marks pending; this Lambda
transitions them to sent/skipped.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

import outreach_policy

_TABLE_NAME = os.environ.get("TABLE_NAME", "as-email-contacts")
_resource = boto3.resource("dynamodb")
_table = _resource.Table(_TABLE_NAME)


def select_batch() -> list[dict]:
    """Return up to `batch_size` PROFILE items eligible for OUTREACH_HOOK.

    Eligibility:
      * sk = PROFILE
      * outreach_queue_state = "pending"
      * dnd.whatsapp missing or false
      * campaign_count_ytd < max_marketing_per_year
      * phone_e164 present
    Also enforces the daily_cap on this run (count OUTREACH_HOOK_SENT events
    written today; if the cap is hit, return [] early).
    """
    if _sent_today() >= outreach_policy.daily_cap():
        return []

    limit = outreach_policy.batch_size()
    max_year = outreach_policy.max_marketing_per_year()

    results: list[dict] = []
    kwargs: dict = {
        "FilterExpression": (
            Attr("sk").eq("PROFILE")
            & Attr("outreach_queue_state").eq("pending")
            & Attr("phone_e164").exists()
            & Attr("campaign_count_ytd").lt(max_year)
        )
    }
    while len(results) < limit:
        resp = _table.scan(**kwargs)
        for item in resp.get("Items", []):
            if item.get("dnd", {}).get("whatsapp", False):
                continue
            results.append(item)
            if len(results) >= limit:
                break
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek

    return results


def mark_sent(contact_id: str) -> None:
    _table.update_item(
        Key={"contact_id": contact_id, "sk": "PROFILE"},
        UpdateExpression="SET outreach_queue_state = :s, outreach_sent_at = :t",
        ExpressionAttributeValues={
            ":s": "sent",
            ":t": datetime.now(timezone.utc).isoformat(),
        },
    )


def mark_skipped(contact_id: str, reason: str) -> None:
    _table.update_item(
        Key={"contact_id": contact_id, "sk": "PROFILE"},
        UpdateExpression="SET outreach_queue_state = :s, outreach_skip_reason = :r",
        ExpressionAttributeValues={":s": "skipped", ":r": reason},
    )


def _sent_today() -> int:
    """Count OUTREACH_HOOK_SENT events with sent_at on today's IST date."""
    from datetime import date
    import ist_time
    today = ist_time.now_ist().date().isoformat()
    resp = _table.scan(
        FilterExpression=(
            Attr("type").eq("OUTREACH_HOOK_SENT")
            & Attr("sent_at").begins_with(today)
        ),
        Select="COUNT",
    )
    return int(resp.get("Count", 0))
