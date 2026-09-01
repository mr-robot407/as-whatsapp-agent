"""S1.40 → S1.40b — Career (invitation-only)."""

from __future__ import annotations

import copy_library
import crm
import wa_client

_S140_ITEMS = [
    {"id": "S1.40.JUNIOR", "title": "Junior architect / designer"},
    {"id": "S1.40.SENIOR", "title": "Senior architect / designer"},
    {"id": "S1.40.INTERN", "title": "Internship"},
]


def handle_s140(ctx) -> str:
    if ctx.button_id in [b["id"] for b in _S140_ITEMS]:
        role = ctx.button_id.split(".")[-1]
        ctx.session["career_role"] = role
        crm.write_event(ctx.contact_id, "CAREER_INTEREST", {"role": role})
        return "S1.40b"

    interactive = {
        "type": "list",
        "body": {"text": copy_library.get("S1.40", "body")},
        "action": {
            "button": "Choose role",
            "sections": [{"title": "Role of interest", "rows": _S140_ITEMS}],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.40")
    return "S1.40"


def handle_s140b(ctx) -> str:
    wa_client.send_text(ctx.wa_id, copy_library.get("S1.40b", "body"), state_id="S1.40b")
    return "X.ARCH"
