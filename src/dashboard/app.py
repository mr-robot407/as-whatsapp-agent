"""Dashboard Lambda — internal control panel.

Routes (all under `/dashboard/*`):
  GET  /dashboard                      → HTML index (bundled)
  GET  /dashboard/api/status           → JSON: killswitch, DLQ depth, today's sends
  POST /dashboard/api/killswitch       → toggle SSM /as-whatsapp-agent/AGENT_ENABLED
  GET  /dashboard/api/contact/{cid}    → PROFILE + last N events for that contact
  GET  /dashboard/api/templates        → templates_registry.json (approval status)
  GET  /dashboard/api/flows            → flows_registry.json (publish status)

No auth. Intended to sit behind an IP allowlist / VPN / basic-auth at the
CloudFront layer; the Lambda itself trusts its caller. Do not expose publicly.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Attr, Key

_TABLE_NAME = os.environ.get("TABLE_NAME", "as-email-contacts")
_DLQ_URL = os.environ.get("DLQ_URL", "")
_KILL_PARAM = os.environ.get("AGENT_ENABLED_PARAM", "/as-whatsapp-agent/AGENT_ENABLED")
_CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", str(Path(__file__).parent.parent.parent / "config")))

_ddb = boto3.resource("dynamodb")
_table = _ddb.Table(_TABLE_NAME)
_ssm = boto3.client("ssm")
_sqs = boto3.client("sqs")

_INDEX_PATH = Path(__file__).parent / "index.html"


def handler(event: dict, context) -> dict:
    method = event.get("httpMethod", "").upper()
    path = event.get("path") or event.get("resource") or ""
    path = path.rstrip("/")

    if path.endswith("/dashboard") or path == "/dashboard":
        return _serve_html()

    if path.endswith("/api/status"):
        return _json(_status())

    if path.endswith("/api/killswitch") and method == "POST":
        return _json(_toggle_killswitch(event))

    if "/api/contact/" in path:
        contact_id = path.rsplit("/", 1)[-1]
        return _json(_contact(contact_id))

    if path.endswith("/api/templates"):
        return _json(_load_json_config("templates_registry.json"))

    if path.endswith("/api/flows"):
        return _json(_load_json_config("flows_registry.json"))

    return _json({"error": "not found"}, status=404)


# ─── Handlers ────────────────────────────────────────────────────────────────

def _serve_html() -> dict:
    try:
        html = _INDEX_PATH.read_text()
    except FileNotFoundError:
        html = "<h1>dashboard/index.html missing</h1>"
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": html,
        "isBase64Encoded": False,
    }


def _status() -> dict:
    enabled = _killswitch_state()
    dlq_depth = _dlq_depth()
    today = date.today().isoformat()
    outreach_today = _count_today("OUTREACH_HOOK_SENT", today)
    inbound_today = _count_today("WHATSAPP_INBOUND", today)
    bookings_today = _count_today("BOOKING_CREATED", today)
    return {
        "killswitch": enabled,
        "dlq_depth": dlq_depth,
        "counts_today": {
            "outreach_sent": outreach_today,
            "inbound_received": inbound_today,
            "bookings_created": bookings_today,
        },
        "date": today,
    }


def _toggle_killswitch(event: dict) -> dict:
    body = event.get("body") or "{}"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {}
    desired = payload.get("enabled")
    if desired is None:
        desired = not _killswitch_state()
    value = "true" if bool(desired) else "false"
    _ssm.put_parameter(Name=_KILL_PARAM, Value=value, Type="String", Overwrite=True)
    return {"killswitch": bool(desired), "param": _KILL_PARAM}


def _contact(contact_id: str) -> dict:
    profile = _table.get_item(Key={"contact_id": contact_id, "sk": "PROFILE"}).get("Item", {})
    events = _table.query(
        KeyConditionExpression=Key("contact_id").eq(contact_id),
        ScanIndexForward=False,
        Limit=25,
    ).get("Items", [])
    events = [e for e in events if e.get("sk") != "PROFILE"]
    return {"profile": profile, "events": events}


# ─── Internals ───────────────────────────────────────────────────────────────

def _killswitch_state() -> bool:
    try:
        resp = _ssm.get_parameter(Name=_KILL_PARAM)
        return resp["Parameter"]["Value"].strip().lower() == "true"
    except Exception:
        return True


def _dlq_depth() -> int:
    if not _DLQ_URL:
        return -1
    try:
        resp = _sqs.get_queue_attributes(
            QueueUrl=_DLQ_URL,
            AttributeNames=["ApproximateNumberOfMessages"],
        )
        return int(resp["Attributes"].get("ApproximateNumberOfMessages", "0"))
    except Exception:
        return -1


def _count_today(event_type: str, today_iso: str) -> int:
    resp = _table.scan(
        FilterExpression=(
            Attr("type").eq(event_type)
            & Attr("ts").begins_with(today_iso)
        ),
        Select="COUNT",
    )
    return int(resp.get("Count", 0))


def _load_json_config(name: str) -> dict:
    with open(_CONFIG_DIR / name) as fh:
        return json.load(fh)


def _json(payload: dict, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
        "isBase64Encoded": False,
    }
