"""S1.50 → S1.51 — Other / Press capture."""

from __future__ import annotations

import copy_library
import crm
import wa_client

_S150_ITEMS = [
    {"id": "S1.51",              "title": "Press / publication"},
    {"id": "X.HUMAN_REQUEST",    "title": "Speak to the studio"},
    {"id": "E.IG",               "title": "Follow on Instagram"},
    {"id": "X.ARCH_OTHER",       "title": "Close this thread"},
]


def handle_s150(ctx) -> str:
    if ctx.button_id in [b["id"] for b in _S150_ITEMS]:
        target = ctx.button_id
        if target == "X.ARCH_OTHER":
            return "X.ARCH"
        return target

    interactive = {
        "type": "list",
        "body": {"text": copy_library.get("S1.50", "body")},
        "action": {
            "button": "Choose",
            "sections": [{"title": "How may the studio assist?", "rows": _S150_ITEMS}],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.50")
    return "S1.50"


def handle_s151(ctx) -> str:
    # Capture publication name + email freeform, then send ack.
    if ctx.message_type == "text" and ctx.text_body.strip():
        crm.write_event(
            ctx.contact_id,
            "PRESS_CAPTURE",
            {"text": ctx.text_body[:2000]},
        )
        wa_client.send_text(ctx.wa_id, copy_library.get("S1.51", "ack"), state_id="S1.51.ack")
        return "X.ARCH"

    wa_client.send_text(ctx.wa_id, copy_library.get("S1.51", "body"), state_id="S1.51")
    return "S1.51"
