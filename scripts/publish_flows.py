#!/usr/bin/env python3
"""Publish WhatsApp Flow JSONs to Meta and write flow_id back to the registry.

For each flow with flow_id == null:
  1. POST /{waba_id}/flows           — create draft
  2. POST /{flow_id}/assets          — upload the Flow JSON
  3. POST /{flow_id}/publish         — publish
  4. Write flow_id back to config/flows_registry.json

Env: META_ACCESS_TOKEN, META_WABA_ID, META_GRAPH_VERSION.

Usage:
  python3 scripts/publish_flows.py
  python3 scripts/publish_flows.py --key CONTACT_CONFIRMATION
  python3 scripts/publish_flows.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "config" / "flows_registry.json"
GRAPH = f"https://graph.facebook.com/{os.environ.get('META_GRAPH_VERSION', 'v21.0')}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", action="append")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("META_ACCESS_TOKEN")
    waba = os.environ.get("META_WABA_ID")
    if not token or not waba:
        print("error: META_ACCESS_TOKEN and META_WABA_ID required", file=sys.stderr)
        return 2

    reg = json.loads(CONFIG.read_text())
    keys = args.key or list(reg["flows"].keys())
    changed = False

    for k in keys:
        entry = reg["flows"].get(k)
        if not entry:
            print(f"warning: unknown flow key {k!r}")
            continue
        if entry.get("flow_id"):
            print(f"skip {k}: already published")
            continue

        spec_path = REPO / entry["spec_path"]
        if not spec_path.exists():
            print(f"skip {k}: spec {spec_path} not found")
            continue

        print(f"→ publishing {k}")
        if args.dry_run:
            print(f"  would POST {spec_path} to /{waba}/flows")
            continue

        r = requests.post(
            f"{GRAPH}/{waba}/flows",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": k, "categories": ["OTHER"]},
            timeout=30,
        )
        if r.status_code >= 400:
            print(f"  ✗ create {r.status_code}: {r.text[:300]}", file=sys.stderr)
            continue
        flow_id = r.json().get("id", "")

        with open(spec_path, "rb") as fh:
            r = requests.post(
                f"{GRAPH}/{flow_id}/assets",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (spec_path.name, fh, "application/json")},
                data={"name": "flow.json", "asset_type": "FLOW_JSON"},
                timeout=60,
            )
        if r.status_code >= 400:
            print(f"  ✗ upload {r.status_code}: {r.text[:300]}", file=sys.stderr)
            continue

        r = requests.post(
            f"{GRAPH}/{flow_id}/publish",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if r.status_code >= 400:
            print(f"  ✗ publish {r.status_code}: {r.text[:300]}", file=sys.stderr)
            continue

        entry["flow_id"] = flow_id
        changed = True
        print(f"  ✓ flow_id={flow_id}")

    if changed:
        CONFIG.write_text(json.dumps(reg, indent=2) + "\n")
        print(f"updated {CONFIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
