"""S1.10 → S1.11 → S1.12 → S1.13a → S1.13b — project qualification path.

S1.12 enforces the studio's 1,500 sq ft floor. Under-threshold projects are
routed to S1.12a which offers a paid discussion or a channel-close.
"""

from __future__ import annotations

import copy_library
import crm
import wa_client

_S10_ITEMS = [
    {"id": "S1.10.RES",   "title": "Residence",      "description": "Home, apartment, villa"},
    {"id": "S1.10.COMM",  "title": "Commercial",     "description": "Office, retail, F&B"},
    {"id": "S1.10.HOSP",  "title": "Hospitality",    "description": "Hotel, resort, restaurant"},
    {"id": "S1.10.OTHER", "title": "Other",          "description": "Cultural, institutional"},
]

_S12_AREA_BUTTONS = [
    {"id": "S1.12.UNDER1500",  "title": "Under 1,500 sq ft"},
    {"id": "S1.12.1500_3000",  "title": "1,500 – 3,000"},
    {"id": "S1.12.3000_5000",  "title": "3,000 – 5,000"},
]

_S12_AREA_BUTTONS_2 = [
    {"id": "S1.12.5000_10000", "title": "5,000 – 10,000"},
    {"id": "S1.12.OVER10000",  "title": "Above 10,000"},
]

_S12A_ITEMS = [
    {"id": "S1.17_FROM_UNDERSIZE", "title": "Paid project discussion", "description": "Rs. 1,770 · 30 min · Meet"},
    {"id": "E.IG_FROM_UNDERSIZE",  "title": "Follow the studio",       "description": "Instagram — no obligation"},
    {"id": "X.ARCH_UNDERSIZE",     "title": "Close this thread",       "description": "No further messages"},
]

_S13A_ITEMS = [
    {"id": "S1.13a.NEW",       "title": "New build"},
    {"id": "S1.13a.RENOVATE",  "title": "Renovation"},
    {"id": "S1.13a.INTERIORS", "title": "Interiors only"},
    {"id": "S1.13a.MIXED",     "title": "Mixed / not sure"},
]

_S13B_ITEMS = [
    {"id": "S1.13b.FULL",       "title": "Full architecture + interiors"},
    {"id": "S1.13b.ARCH_ONLY",  "title": "Architecture only"},
    {"id": "S1.13b.INTERIORS",  "title": "Interiors only"},
    {"id": "S1.13b.CONSULT",    "title": "Consulting engagement"},
]


# ─── S1.10 project nature ────────────────────────────────────────────────────

def handle_s110(ctx) -> str:
    if ctx.button_id in [item["id"] for item in _S10_ITEMS]:
        crm.write_event(
            ctx.contact_id,
            "STATE_TRANSITION",
            {"from": "S1.10", "to": "S1.11", "via": ctx.button_id, "project_type": ctx.button_id.split(".")[-1]},
        )
        # Persist project type onto session for later reference (via router).
        ctx.session["project_type"] = ctx.button_id.split(".")[-1]
        return "S1.11"

    interactive = {
        "type": "list",
        "body": {"text": copy_library.get("S1.10", "body")},
        "action": {
            "button": "Choose",
            "sections": [{"title": "Project nature", "rows": _S10_ITEMS}],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.10")
    return "S1.10"


# ─── S1.11 location ──────────────────────────────────────────────────────────

def handle_s111(ctx) -> str:
    # Freeform capture — accept any text as the location. Optional per the copy.
    if ctx.message_type == "text" and ctx.text_body.strip():
        ctx.session["project_location"] = ctx.text_body.strip()[:200]
        crm.write_event(
            ctx.contact_id,
            "STATE_TRANSITION",
            {"from": "S1.11", "to": "S1.12", "location": ctx.text_body.strip()[:200]},
        )
        return "S1.12"

    body = copy_library.get("S1.11", "body") + "\n\n" + copy_library.get("S1.11", "tbd_capture_prompt")
    wa_client.send_text(ctx.wa_id, body, state_id="S1.11")
    return "S1.11"


# ─── S1.12 area gate ─────────────────────────────────────────────────────────

def handle_s112(ctx) -> str:
    bid = ctx.button_id
    all_ids = {b["id"] for b in _S12_AREA_BUTTONS + _S12_AREA_BUTTONS_2}
    if bid in all_ids:
        ctx.session["project_area_band"] = bid.split(".")[-1]
        if bid == "S1.12.UNDER1500":
            crm.write_event(
                ctx.contact_id,
                "STATE_TRANSITION",
                {"from": "S1.12", "to": "S1.12a", "reason": "under_threshold", "via": bid},
            )
            return "S1.12a"
        crm.write_event(
            ctx.contact_id,
            "STATE_TRANSITION",
            {"from": "S1.12", "to": "S1.13a", "via": bid},
        )
        return "S1.13a"

    # First screen — 3 buttons (WhatsApp limit).
    interactive = {
        "type": "button",
        "body": {"text": copy_library.get("S1.12", "body")},
        "action": {"buttons": [{"type": "reply", "reply": b} for b in _S12_AREA_BUTTONS]},
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.12")
    # Follow-up screen with the remaining two options (5000-10000, >10000).
    interactive2 = {
        "type": "button",
        "body": {"text": "Or, for larger projects:"},
        "action": {"buttons": [{"type": "reply", "reply": b} for b in _S12_AREA_BUTTONS_2]},
    }
    wa_client.send_interactive(ctx.wa_id, interactive2, state_id="S1.12.large")
    return "S1.12"


# ─── S1.12a under-threshold ──────────────────────────────────────────────────

def handle_s112a(ctx) -> str:
    bid = ctx.button_id
    if bid == "S1.17_FROM_UNDERSIZE":
        return "S1.17"
    if bid == "E.IG_FROM_UNDERSIZE":
        return "E.IG"
    if bid == "X.ARCH_UNDERSIZE":
        return "X.ARCH"

    interactive = {
        "type": "list",
        "body": {"text": copy_library.get("S1.12a", "body")},
        "action": {
            "button": "Choose",
            "sections": [{"title": "Options", "rows": _S12A_ITEMS}],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.12a")
    return "S1.12a"


# ─── S1.13a broad fit ────────────────────────────────────────────────────────

def handle_s113a(ctx) -> str:
    if ctx.button_id in [b["id"] for b in _S13A_ITEMS]:
        ctx.session["project_fit"] = ctx.button_id.split(".")[-1]
        crm.write_event(
            ctx.contact_id,
            "STATE_TRANSITION",
            {"from": "S1.13a", "to": "S1.13b", "via": ctx.button_id},
        )
        return "S1.13b"

    interactive = {
        "type": "list",
        "body": {"text": copy_library.get("S1.13a", "body")},
        "action": {
            "button": "Choose",
            "sections": [{"title": "Project fit", "rows": _S13A_ITEMS}],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.13a")
    return "S1.13a"


# ─── S1.13b engagement form → S1.14 discovery call offer ─────────────────────

def handle_s113b(ctx) -> str:
    if ctx.button_id in [b["id"] for b in _S13B_ITEMS]:
        ctx.session["engagement_form"] = ctx.button_id.split(".")[-1]
        crm.write_event(
            ctx.contact_id,
            "STATE_TRANSITION",
            {"from": "S1.13b", "to": "S1.14", "via": ctx.button_id},
        )
        # Warm the lead — user has completed qualification.
        try:
            crm.update_lead_score(ctx.contact_id, "cold", "warm", "completed_S1.13b")
        except Exception as exc:  # noqa: BLE001
            print(f"S1.13b: lead-score update failed: {exc!r}")
        return "S1.14"

    interactive = {
        "type": "list",
        "body": {"text": copy_library.get("S1.13b", "body")},
        "action": {
            "button": "Choose",
            "sections": [{"title": "Form of engagement", "rows": _S13B_ITEMS}],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.13b")
    return "S1.13b"
