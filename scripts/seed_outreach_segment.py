#!/usr/bin/env python3
"""Seed the outreach queue by marking PROFILE rows `outreach_queue_state=pending`.

Filters:
  * phone_e164 present
  * dnd.whatsapp not set
  * campaign_count_ytd < max (config/outreach_policy.json)
  * outreach_queue_state not already set
  * lead_score in target bands (default: cold, warm)

Usage:
  python3 scripts/seed_outreach_segment.py --limit 500
  python3 scripts/seed_outreach_segment.py --limit 100 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Attr

REPO = Path(__file__).resolve().parent.parent
POLICY = REPO / "config" / "outreach_policy.json"

TABLE_NAME = os.environ.get("TABLE_NAME", "as-email-contacts")
REGION = os.environ.get("AWS_REGION", "ap-south-1")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--lead-bands", default="cold,warm")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    policy = json.loads(POLICY.read_text())
    max_year = int(policy.get("marketing_templates_per_recipient_per_year", 4))
    bands = tuple(b.strip() for b in args.lead_bands.split(",") if b.strip())

    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)

    seeded = 0
    considered = 0
    kwargs: dict = {
        "FilterExpression": (
            Attr("sk").eq("PROFILE")
            & Attr("phone_e164").exists()
            & Attr("campaign_count_ytd").lt(max_year)
            & Attr("outreach_queue_state").not_exists()
        )
    }
    while seeded < args.limit:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            considered += 1
            if item.get("dnd", {}).get("whatsapp", False):
                continue
            if item.get("lead_score", "cold") not in bands:
                continue
            print(f"→ {item['contact_id']}  {item.get('phone_e164', '')}  {item.get('name', '')}")
            if not args.dry_run:
                table.update_item(
                    Key={"contact_id": item["contact_id"], "sk": "PROFILE"},
                    UpdateExpression="SET outreach_queue_state = :s",
                    ExpressionAttributeValues={":s": "pending"},
                )
            seeded += 1
            if seeded >= args.limit:
                break
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek

    print(f"done: considered={considered} seeded={seeded} (dry_run={args.dry_run})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
