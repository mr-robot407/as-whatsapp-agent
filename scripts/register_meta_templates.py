#!/usr/bin/env python3
"""Register WhatsApp templates with Meta and write meta_template_id back.

Reads config/templates_registry.json + config/copy_library.json, walks each
template with meta_template_id == null, calls
`POST /{waba_id}/message_templates`, and updates the registry.

Env: META_ACCESS_TOKEN, META_WABA_ID, META_GRAPH_VERSION (default v21.0).

Usage:
  python3 scripts/register_meta_templates.py
  python3 scripts/register_meta_templates.py --key OOH_ACK
  python3 scripts/register_meta_templates.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "config" / "templates_registry.json"
COPY = REPO / "config" / "copy_library.json"
GRAPH = f"https://graph.facebook.com/{os.environ.get('META_GRAPH_VERSION', 'v21.0')}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", action="append")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("META_ACCESS_TOKEN")
    waba = os.environ.get("META_WABA_ID")
    if not token or not waba:
        print("error: META_ACCESS_TOKEN and META_WABA_ID must be set", file=sys.stderr)
        return 2

    reg = json.loads(CONFIG.read_text())
    copy = json.loads(COPY.read_text())
    keys = args.key or list(reg["templates"].keys())
    changed = False

    for k in keys:
        entry = reg["templates"].get(k)
        if not entry:
            print(f"warning: unknown template key {k!r}")
            continue
        if entry.get("meta_template_id"):
            print(f"skip {k}: already registered")
            continue

        body_text = _resolve_body(copy, entry["state_id"])
        if not body_text:
            print(f"skip {k}: no copy body for state_id {entry['state_id']!r}")
            continue

        payload = _build_payload(entry, body_text)
        print(f"→ register {k} ({entry['meta_template_name']})")
        if args.dry_run:
            print(json.dumps(payload, indent=2))
            continue

        r = requests.post(
            f"{GRAPH}/{waba}/message_templates",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=30,
        )
        if r.status_code >= 400:
            print(f"  ✗ {r.status_code}: {r.text[:300]}", file=sys.stderr)
            continue
        j = r.json()
        entry["meta_template_id"] = j.get("id", "")
        changed = True
        print(f"  ✓ id={j.get('id', '?')} status={j.get('status', '?')}")

    if changed:
        CONFIG.write_text(json.dumps(reg, indent=2) + "\n")
        print(f"updated {CONFIG}")
    return 0


def _resolve_body(copy: dict, state_id: str) -> str:
    for candidate in [s.strip() for s in state_id.replace("/", " ").split()]:
        if candidate in copy and "body" in copy[candidate]:
            return copy[candidate]["body"]
    return ""


def _build_payload(entry: dict, body_text: str) -> dict:
    components: list[dict] = []
    if "header_image" in entry.get("components", []):
        components.append({"type": "HEADER", "format": "IMAGE"})
    components.append({"type": "BODY", "text": body_text})
    if "footer" in entry.get("components", []):
        components.append({"type": "FOOTER", "text": "Atelier Shreenu"})
    return {
        "name": entry["meta_template_name"],
        "category": entry["category"],
        "language": entry.get("language", "en"),
        "components": components,
    }


if __name__ == "__main__":
    sys.exit(main())
