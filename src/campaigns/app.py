"""Campaigns Lambda — 90-min cron dispatcher for the S2.00 outreach hook.

Business-hours-guarded (IST Mon–Sat 09:00–18:00). Selects up to `batch_size`
eligible contacts per fire, respecting:
  * daily_cap (per-invocation-day)
  * ≤4 marketing templates per recipient per calendar year
  * dnd.whatsapp = false
  * consent recorded (per outreach_policy `requires_recorded_consent`)
  * OUTREACH_HOOK template approved (Meta + DLT ids present)

`broadcast_scheduler.select_batch()` centralises the query — a queue slot on
each PROFILE row (`outreach_queue_state` in {"pending","sent","skipped"})
drives selection.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import broadcast_scheduler
import crm
import ist_time
import killswitch
import templates


def handler(event: dict, context) -> dict:
    if not killswitch.is_enabled():
        return {"statusCode": 200, "body": "killswitch off"}
    if not ist_time.is_business_hours():
        return {"statusCode": 200, "body": "outside business hours"}

    dry_run = bool(event.get("dry_run", False))

    if not templates.is_approved("OUTREACH_HOOK"):
        print("campaigns: OUTREACH_HOOK not approved — skipping this cron")
        return {"statusCode": 200, "body": "template not approved"}

    batch = broadcast_scheduler.select_batch()
    print(f"campaigns: selected {len(batch)} eligible recipients (dry_run={dry_run})")

    sent = 0
    skipped = 0
    for profile in batch:
        contact_id = profile["contact_id"]
        phone = profile.get("phone_e164", "")
        if not phone:
            broadcast_scheduler.mark_skipped(contact_id, reason="no_phone")
            skipped += 1
            continue

        if dry_run:
            print(f"campaigns: [dry-run] would send OUTREACH_HOOK to {contact_id} ({phone})")
            continue

        try:
            templates.send("OUTREACH_HOOK", to_wa_id=phone.lstrip("+"))
            broadcast_scheduler.mark_sent(contact_id)
            crm.increment_campaign_count(contact_id)
            crm.write_event(
                contact_id,
                "OUTREACH_HOOK_SENT",
                {
                    "template": "OUTREACH_HOOK",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            print(f"campaigns: OUTREACH_HOOK send failed for {contact_id}: {exc!r}")
            broadcast_scheduler.mark_skipped(contact_id, reason=f"send_failed:{exc.__class__.__name__}")
            skipped += 1

    return {"statusCode": 200, "body": f"sent={sent} skipped={skipped}"}
