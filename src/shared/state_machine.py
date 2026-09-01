"""Per-contact conversation state + STOP keyword detection.

Persistence lives on the PROFILE item in DynamoDB:
    current_state : str    e.g. "S1.10"
    session       : dict   arbitrary per-state context (built-up area, tier, etc.)

STOP keywords are loaded from `config/outreach_policy.json` and matched
whole-word case-insensitive on the raw inbound text body.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3

_TABLE_NAME = os.environ.get("TABLE_NAME", "as-email-contacts")
_POLICY_PATH = Path(
    os.environ.get(
        "CONFIG_DIR", str(Path(__file__).parent.parent.parent / "config")
    )
) / "outreach_policy.json"

_resource = boto3.resource("dynamodb")
_table = _resource.Table(_TABLE_NAME)

_ROOT_STATE = "S1.00"


# ─── State read/write ────────────────────────────────────────────────────────

def get_state(contact_id: str) -> tuple[str, dict]:
    """Return (current_state, session). Defaults to S1.00 + empty session."""
    resp = _table.get_item(Key={"contact_id": contact_id, "sk": "PROFILE"})
    item = resp.get("Item", {})
    return item.get("current_state", _ROOT_STATE), item.get("session", {}) or {}


def set_state(contact_id: str, new_state: str, session_update: dict | None = None) -> None:
    """Set current_state, optionally merging keys into session."""
    if session_update:
        # Merge existing session with update
        _table.update_item(
            Key={"contact_id": contact_id, "sk": "PROFILE"},
            UpdateExpression=(
                "SET current_state = :s, "
                "session = if_not_exists(session, :empty), "
                "last_state_change_at = :t"
            ),
            ExpressionAttributeValues={
                ":s": new_state,
                ":empty": {},
                ":t": _iso_now(),
            },
        )
        # DDB has no "merge map" primitive — read-modify-write for session
        for k, v in session_update.items():
            _table.update_item(
                Key={"contact_id": contact_id, "sk": "PROFILE"},
                UpdateExpression="SET session.#k = :v",
                ExpressionAttributeNames={"#k": k},
                ExpressionAttributeValues={":v": v},
            )
    else:
        _table.update_item(
            Key={"contact_id": contact_id, "sk": "PROFILE"},
            UpdateExpression="SET current_state = :s, last_state_change_at = :t",
            ExpressionAttributeValues={":s": new_state, ":t": _iso_now()},
        )


def clear_session(contact_id: str) -> None:
    _table.update_item(
        Key={"contact_id": contact_id, "sk": "PROFILE"},
        UpdateExpression="SET session = :empty",
        ExpressionAttributeValues={":empty": {}},
    )


# ─── STOP keyword detection ──────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _stop_keywords() -> tuple[str, ...]:
    try:
        with open(_POLICY_PATH) as fh:
            policy = json.load(fh)
    except FileNotFoundError:
        return ()
    return tuple(k.strip().upper() for k in policy.get("stop_keywords", []) if k.strip())


@lru_cache(maxsize=1)
def _stop_pattern() -> re.Pattern:
    kws = _stop_keywords()
    if not kws:
        return re.compile(r"(?!x)x")  # matches nothing
    # Sort longest-first so "OPT OUT" wins over "OPT"
    kws_sorted = sorted(kws, key=len, reverse=True)
    escaped = "|".join(re.escape(k) for k in kws_sorted)
    return re.compile(rf"\b({escaped})\b", flags=re.IGNORECASE)


def is_stop_keyword(text: str) -> bool:
    """True if the message body matches a configured STOP keyword."""
    if not text:
        return False
    return bool(_stop_pattern().search(text))


# ─── Restart / restart keywords ──────────────────────────────────────────────

_RESTART_KEYWORDS = ("RESTART", "RESET", "MENU")


def is_restart_keyword(text: str) -> bool:
    if not text:
        return False
    text_upper = text.strip().upper()
    return text_upper in _RESTART_KEYWORDS


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
