#!/usr/bin/env python3
"""Ingest DATABASE/*.json into DynamoDB `as-email-contacts`.

Each JSON row is expected to have (at minimum):
  {"name": "…", "phone_e164" (or "phone"): "+91…"}  and optionally  "emails": ["…"]

Behaviour: skip rows without a valid phone; merge with existing PROFILE
(matched by GSI-PHONE) — never overwrite dnd / lead_score / campaign counts.
Idempotent.

Usage:
  python3 scripts/ingest_crm.py
  python3 scripts/ingest_crm.py --file DATABASE/phone_only_crm.json
  python3 scripts/ingest_crm.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "shared"))

from identity import normalise_e164  # noqa: E402

TABLE_NAME = os.environ.get("TABLE_NAME", "as-email-contacts")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
GSI_PHONE = os.environ.get("GSI_PHONE", "GSI-PHONE")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = args.file or [
        str(REPO / "DATABASE" / "both_crm.json"),
        str(REPO / "DATABASE" / "phone_only_crm.json"),
    ]

    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)

    stats = {"read": 0, "created": 0, "merged": 0, "skipped_no_phone": 0}

    for path in files:
        p = Path(path)
        if not p.exists():
            print(f"warning: {path} not found — skipping")
            continue
        print(f"loading {path}…")
        with open(p) as fh:
            rows = json.load(fh)
        for row in rows:
            stats["read"] += 1
            try:
                phone = normalise_e164(row.get("phone") or row.get("phone_e164") or "")
            except Exception:
                stats["skipped_no_phone"] += 1
                continue

            existing = table.query(
                IndexName=GSI_PHONE,
                KeyConditionExpression=Key("phone_e164").eq(phone),
                Limit=1,
            ).get("Items", [])

            if existing:
                stats["merged"] += 1
                if not args.dry_run:
                    _merge(table, existing[0], row)
                continue

            stats["created"] += 1
            if not args.dry_run:
                _create(table, phone, row)

    print(f"done: {stats}")
    return 0


def _create(table, phone: str, row: dict) -> None:
    item = {
        "contact_id": str(uuid.uuid4()),
        "sk": "PROFILE",
        "phone_e164": phone,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dnd": {"email": False, "whatsapp": False, "phone": False},
        "lead_score": "cold",
        "campaign_count_ytd": 0,
        "source_channel": "crm_ingest",
    }
    if row.get("name"):
        item["name"] = row["name"]
    emails = row.get("emails") or ([row["email"]] if row.get("email") else [])
    if emails:
        item["email_normalised"] = emails[0].strip().lower()
        item["all_emails"] = [e.strip().lower() for e in emails]
    table.put_item(Item=item)


def _merge(table, existing: dict, row: dict) -> None:
    updates: list[str] = []
    values: dict = {}
    names_dict: dict = {}
    if row.get("name") and not existing.get("name"):
        updates.append("#name = :n")
        values[":n"] = row["name"]
        names_dict["#name"] = "name"
    emails = row.get("emails") or ([row["email"]] if row.get("email") else [])
    if emails and not existing.get("email_normalised"):
        updates.append("email_normalised = :e")
        values[":e"] = emails[0].strip().lower()
    if not updates:
        return
    kwargs = {
        "Key": {"contact_id": existing["contact_id"], "sk": "PROFILE"},
        "UpdateExpression": "SET " + ", ".join(updates),
        "ExpressionAttributeValues": values,
    }
    if names_dict:
        kwargs["ExpressionAttributeNames"] = names_dict
    table.update_item(**kwargs)


if __name__ == "__main__":
    sys.exit(main())
