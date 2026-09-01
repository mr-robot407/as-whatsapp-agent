"""E.00 / E.IG / E.WEB / E.EMAIL / E.VC / E.RECO — post-menu engagement offers.

These are the closing "share the studio" pathways offered after any productive
interaction. Each one sends a link (with UTM per Rule D) or asset, then returns
the contact to E.00 for further optional taps.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import copy_library
import crm
import link_builder
import wa_client

_LINKS_PATH = Path(
    os.environ.get(
        "CONFIG_DIR", str(Path(__file__).parent.parent.parent.parent / "config")
    )
) / "link_registry.json"


@lru_cache(maxsize=1)
def _links() -> dict:
    with open(_LINKS_PATH) as fh:
        return json.load(fh)


# ─── E.00 post-menu ───────────────────────────────────────────────────────────

_E00_ITEMS = [
    {"id": "E.IG",   "title": "Follow on Instagram"},
    {"id": "E.VC",   "title": "Save the studio contact"},
    {"id": "E.RECO", "title": "Recommend to a friend"},
    {"id": "E.WEB",  "title": "Visit the website"},
    {"id": "E.EMAIL","title": "Email the studio"},
]

_E00_TRANSITIONS = {item["id"]: item["id"] for item in _E00_ITEMS}


def handle_post_menu(ctx) -> str:
    button_id = ctx.button_id
    if button_id in _E00_TRANSITIONS:
        target = _E00_TRANSITIONS[button_id]
        crm.write_event(
            ctx.contact_id,
            "STATE_TRANSITION",
            {"from": "E.00", "to": target, "via": button_id},
        )
        return target

    interactive = {
        "type": "list",
        "body": {"text": copy_library.get("E.00", "body")},
        "action": {
            "button": "Choose",
            "sections": [{"title": "Optional next steps", "rows": _E00_ITEMS}],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="E.00")
    return "E.00"


# ─── E.IG Instagram ──────────────────────────────────────────────────────────

def handle_instagram(ctx) -> str:
    url = link_builder.utm(_links()["instagram"], campaign="E.IG", content="follow")
    wa_client.send_text(ctx.wa_id, f"{copy_library.get('E.IG', 'body')}\n\n{url}", state_id="E.IG")
    wa_client.send_text(ctx.wa_id, copy_library.get("E.IG", "post_link"), state_id="E.IG.post")
    return "E.00"


# ─── E.WEB website ───────────────────────────────────────────────────────────

def handle_website(ctx) -> str:
    url = link_builder.utm(_links()["website"], campaign="E.WEB")
    wa_client.send_text(ctx.wa_id, url, state_id="E.WEB")
    wa_client.send_text(ctx.wa_id, copy_library.get("E.WEB", "post_link"), state_id="E.WEB.post")
    return "E.00"


# ─── E.EMAIL mailto ──────────────────────────────────────────────────────────

def handle_email(ctx) -> str:
    wa_client.send_text(ctx.wa_id, _links()["studio_email_mailto"], state_id="E.EMAIL")
    wa_client.send_text(ctx.wa_id, copy_library.get("E.EMAIL", "post_link"), state_id="E.EMAIL.post")
    return "E.00"


# ─── E.VC vCard ──────────────────────────────────────────────────────────────

def handle_vcard(ctx) -> str:
    wa_client.send_text(ctx.wa_id, copy_library.get("E.VC", "body"), state_id="E.VC.intro")
    # vCard payload send is deferred to Phase 4 (vcard_builder module); for now
    # advise the studio contact by email.
    wa_client.send_text(
        ctx.wa_id,
        "The studio contact card will follow in a subsequent message.",
        state_id="E.VC.stub",
    )
    return "E.00"


# ─── E.RECO recommend ────────────────────────────────────────────────────────

def handle_recommend(ctx) -> str:
    share_url = _links()["recommend_share"]
    wa_client.send_text(ctx.wa_id, copy_library.get("E.RECO", "body"), state_id="E.RECO.intro")
    wa_client.send_text(ctx.wa_id, share_url, state_id="E.RECO.link")
    return "E.00"
