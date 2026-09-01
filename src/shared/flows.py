"""WhatsApp Flow send helper — reads `config/flows_registry.json` and dispatches.

A Flow send is an `interactive` message with `type = "flow"` and a Meta-issued
`flow_id`. Autofill is mandatory per Rule E §3.4 — this module wires the
`flow_action_payload.data` block from the caller-provided `autofill` dict.
"""

from __future__ import annotations

import json
import os
import uuid
from functools import lru_cache
from pathlib import Path

import wa_client

_CONFIG_PATH = Path(
    os.environ.get(
        "CONFIG_DIR", str(Path(__file__).parent.parent.parent / "config")
    )
) / "flows_registry.json"


@lru_cache(maxsize=1)
def _registry() -> dict:
    with open(_CONFIG_PATH) as fh:
        return json.load(fh)["flows"]


def get(flow_key: str) -> dict:
    reg = _registry()
    if flow_key not in reg:
        raise KeyError(f"flows: unknown flow key {flow_key!r}")
    return reg[flow_key]


def assert_published(flow_key: str) -> dict:
    entry = get(flow_key)
    if not entry.get("flow_id"):
        raise RuntimeError(
            f"flows: {flow_key!r} not published — run scripts/publish_flows.py "
            "and populate `flow_id` in config/flows_registry.json"
        )
    return entry


def send(
    flow_key: str,
    to_wa_id: str,
    header_text: str,
    body_text: str,
    footer_text: str,
    cta_label: str,
    flow_token: str,
    autofill: dict,
    state_id: str = "",
) -> dict:
    """Send a Flow interactive message with autofilled fields."""
    entry = assert_published(flow_key)
    interactive = {
        "type": "flow",
        "header": {"type": "text", "text": header_text},
        "body": {"text": body_text},
        "footer": {"text": footer_text},
        "action": {
            "name": "flow",
            "parameters": {
                "flow_message_version": "3",
                "flow_token": flow_token,
                "flow_id": entry["flow_id"],
                "flow_cta": cta_label,
                "flow_action": "navigate",
                "flow_action_payload": {
                    "screen": entry.get("first_screen", "WELCOME"),
                    "data": autofill,
                },
            },
        },
    }
    return wa_client.send_interactive(to_wa_id, interactive, state_id=state_id)


def new_flow_token() -> str:
    return str(uuid.uuid4())
