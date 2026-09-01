"""S1.00 — Welcome / root menu.

Presents an interactive list of paths (Design a project / Vendor / Career / Other).
On first entry: send welcome copy + menu. On subsequent entry (button reply):
route to the selected branch's state.
"""

from __future__ import annotations

import copy_library
import crm
import wa_client

# Reply IDs advertised on the welcome menu — must match the state map below.
_MENU_ITEMS = [
    {"id": "S1.00.PROJECT", "title": "Design a project", "description": "Residence, commercial, or hospitality"},
    {"id": "S1.00.VENDOR",  "title": "Vendor / firm",    "description": "Suppliers and service providers"},
    {"id": "S1.00.CAREER",  "title": "Career",           "description": "Portfolio submission"},
    {"id": "S1.00.OTHER",   "title": "Other",            "description": "Press, event, or something else"},
]

_TRANSITIONS = {
    "S1.00.PROJECT": "S1.10",
    "S1.00.VENDOR":  "S1.20a",
    "S1.00.CAREER":  "S1.40",
    "S1.00.OTHER":   "S1.50",
}


def handle(ctx) -> str:
    button_id = ctx.button_id
    if button_id in _TRANSITIONS:
        target = _TRANSITIONS[button_id]
        crm.write_event(
            ctx.contact_id,
            "STATE_TRANSITION",
            {"from": "S1.00", "to": target, "via": button_id},
        )
        return target

    # No button (fresh entry or free-text): send welcome + menu.
    _send_welcome_menu(ctx)
    return "S1.00"


def _send_welcome_menu(ctx) -> None:
    body = copy_library.get("S1.00", "body")
    footer = copy_library.get("S1.00", "footer")
    interactive = {
        "type": "list",
        "body": {"text": body},
        "footer": {"text": footer},
        "action": {
            "button": "Choose a path",
            "sections": [
                {
                    "title": "Reason for message",
                    "rows": _MENU_ITEMS,
                }
            ],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.00")
