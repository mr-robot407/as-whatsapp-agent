#!/usr/bin/env python3
"""Pull DLT template IDs from the chosen aggregator and merge into templates_registry.

Env:
  DLT_AGGREGATOR                  routemobile | gupshup | manual
  DLT_AGGREGATOR_API_KEY          provider API key
  DLT_PRINCIPAL_ENTITY_ID         your PE id

Usage:
  python3 scripts/dlt_sync.py                 # provider from DLT_AGGREGATOR
  python3 scripts/dlt_sync.py --manual        # read TEMPLATE_KEY=DLT_ID from stdin
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", action="store_true",
                    help="Read TEMPLATE_KEY=DLT_ID from stdin")
    args = ap.parse_args()

    reg = json.loads(CONFIG.read_text())

    if args.manual:
        mapping = _read_manual()
    else:
        provider = os.environ.get("DLT_AGGREGATOR", "manual").lower()
        fetcher = _FETCHERS.get(provider)
        if not fetcher:
            print(f"error: no fetcher for aggregator {provider!r}", file=sys.stderr)
            return 2
        mapping = fetcher(reg)

    changed = False
    for k, dlt_id in mapping.items():
        if k not in reg["templates"]:
            print(f"warning: unknown template key {k!r} — skipping")
            continue
        if reg["templates"][k].get("dlt_template_id"):
            continue
        reg["templates"][k]["dlt_template_id"] = dlt_id
        changed = True
        print(f"→ {k}: dlt_template_id = {dlt_id}")

    if changed:
        CONFIG.write_text(json.dumps(reg, indent=2) + "\n")
        print(f"updated {CONFIG}")
    else:
        print("nothing to update")
    return 0


def _read_manual() -> dict:
    out = {}
    print("reading TEMPLATE_KEY=DLT_ID pairs from stdin (blank line to end):", file=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            break
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _fetch_routemobile(reg: dict) -> dict:
    api = "https://api.rmlconnect.net/bulksms/dltAPI"
    key = os.environ["DLT_AGGREGATOR_API_KEY"]
    pe = os.environ["DLT_PRINCIPAL_ENTITY_ID"]
    r = requests.get(api, params={"apikey": key, "peid": pe}, timeout=30)
    r.raise_for_status()
    tmpl = {t["templateName"]: t["templateId"] for t in r.json().get("templates", [])}
    return {k: tmpl[e["meta_template_name"]]
            for k, e in reg["templates"].items() if e["meta_template_name"] in tmpl}


def _fetch_gupshup(reg: dict) -> dict:
    api = "https://api.gupshup.io/wa/api/v1/dlt/templates"
    key = os.environ["DLT_AGGREGATOR_API_KEY"]
    r = requests.get(api, headers={"apikey": key}, timeout=30)
    r.raise_for_status()
    tmpl = {t["templateName"]: t["templateId"] for t in r.json().get("data", [])}
    return {k: tmpl[e["meta_template_name"]]
            for k, e in reg["templates"].items() if e["meta_template_name"] in tmpl}


def _fetch_manual(_reg: dict) -> dict:
    return _read_manual()


_FETCHERS = {
    "routemobile": _fetch_routemobile,
    "gupshup":     _fetch_gupshup,
    "manual":      _fetch_manual,
}


if __name__ == "__main__":
    sys.exit(main())
