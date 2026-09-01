#!/usr/bin/env python3
"""Ingest DATABASE/*_crm.json into DynamoDB `as-email-contacts`.

Source shape (both files):
    {
      "schema_version": "1.0",
      "contact_count": N,
      "contacts": [
        {
          "contact_id": "uuid",       # preserved as the DDB partition key
          "name": "…",
          "contact_type": "individual",
          "phones": ["+91…", …],       # first entry is the primary phone
          "emails": ["…", …],
          "data_quality_flags": [],
          "needs_review": false
        }, …
      ]
    }

Behaviour:
  * Preserves source `contact_id` — re-running the script overwrites the
    PROFILE for that id (stateful fields like dnd/lead_score/session are
    RESET; use with care on second runs).
  * Skips rows without at least one parseable phone.
  * `--fast` uses batch_writer (25 puts per call, no dedupe, no conditions)
    — safe for the *first* ingest into an empty table. Default mode does
    per-item PutItem with condition (skip if contact_id already exists).

Usage:
  python3 scripts/ingest_crm.py --fast              # first ingest, empty table
  python3 scripts/ingest_crm.py                     # safe re-run
  python3 scripts/ingest_crm.py --file DATABASE/phone_only_crm.json
  python3 scripts/ingest_crm.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "shared"))

from identity import normalise_e164  # noqa: E402

TABLE_NAME = os.environ.get("TABLE_NAME", "as-email-contacts")
REGION = os.environ.get("AWS_REGION", "ap-south-1")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", default=None)
    ap.add_argument("--fast", action="store_true",
                    help="Use batch_writer (25 puts/call). Safe only on first ingest.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = args.file or [
        str(REPO / "DATABASE" / "both_crm.json"),
        str(REPO / "DATABASE" / "phone_only_crm.json"),
    ]

    session = boto3.Session(region_name=REGION)
    table = session.resource("dynamodb").Table(TABLE_NAME)

    stats = {"read": 0, "written": 0, "skipped_dup": 0, "skipped_no_phone": 0}

    for path in files:
        p = Path(path)
        if not p.exists():
            print(f"warning: {path} not found — skipping")
            continue
        print(f"loading {path}…")
        payload = json.loads(p.read_text())
        contacts = payload.get("contacts", [])
        print(f"  {len(contacts):,} contacts")

        if args.fast and not args.dry_run:
            _fast_write(table, contacts, stats)
        else:
            _slow_write(table, contacts, stats, dry_run=args.dry_run)

    print(f"done: {stats}")
    return 0


# ─── Fast path — batch_writer (no conditions) ────────────────────────────────

def _fast_write(table, contacts, stats):
    with table.batch_writer(overwrite_by_pkeys=["contact_id", "sk"]) as bw:
        for row in contacts:
            stats["read"] += 1
            item = _build_item(row)
            if not item:
                stats["skipped_no_phone"] += 1
                continue
            bw.put_item(Item=item)
            stats["written"] += 1
            if stats["written"] % 5000 == 0:
                print(f"  … {stats['written']:,} written")


# ─── Slow path — per-item PutItem with condition ─────────────────────────────

def _slow_write(table, contacts, stats, dry_run):
    for row in contacts:
        stats["read"] += 1
        item = _build_item(row)
        if not item:
            stats["skipped_no_phone"] += 1
            continue
        if dry_run:
            print(f"  [dry-run] {item['contact_id']} {item['phone_e164']} {item.get('name', '')}")
            continue
        try:
            table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(contact_id)",
            )
            stats["written"] += 1
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                stats["skipped_dup"] += 1
            else:
                raise
        if stats["written"] % 5000 == 0 and stats["written"]:
            print(f"  … {stats['written']:,} written")


def _build_item(row: dict) -> dict | None:
    phones = row.get("phones") or []
    if row.get("phone"):
        phones = [row["phone"]] + phones
    if row.get("phone_e164"):
        phones = [row["phone_e164"]] + phones

    phone = None
    for p in phones:
        try:
            phone = normalise_e164(p)
            break
        except Exception:
            continue
    if not phone:
        return None

    contact_id = row.get("contact_id") or _mk_uuid()
    item = {
        "contact_id": contact_id,
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
    if row.get("contact_type"):
        item["contact_type"] = row["contact_type"]
    emails = row.get("emails") or ([row["email"]] if row.get("email") else [])
    if emails:
        item["email_normalised"] = emails[0].strip().lower()
        if len(emails) > 1:
            item["all_emails"] = [e.strip().lower() for e in emails]
    if row.get("data_quality_flags"):
        item["data_quality_flags"] = row["data_quality_flags"]
    if row.get("needs_review"):
        item["needs_review"] = True
    return item


def _mk_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


if __name__ == "__main__":
    sys.exit(main())
