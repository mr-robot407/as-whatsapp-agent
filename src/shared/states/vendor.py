"""S1.20a → S1.20b → S1.20c — vendor / service-provider procurement queue.

Not conversational: capture category + one link + optional attachment, then
archive with instructions on how to reach the studio via email.
"""

from __future__ import annotations

import answering
import copy_library
import crm
import wa_client

_S120A_ITEMS = [
    {"id": "S1.20a.MATERIALS",   "title": "Materials & finishes"},
    {"id": "S1.20a.FURNITURE",   "title": "Furniture & fixtures"},
    {"id": "S1.20a.CONTRACTOR",  "title": "Contractors / execution"},
    {"id": "S1.20a.CONSULTANT",  "title": "Consultants / design collaborators"},
    {"id": "S1.20a.TECH",        "title": "Tech / software"},
    {"id": "S1.20a.OTHER",       "title": "Other"},
]


# ─── S1.20a category select ──────────────────────────────────────────────────

def handle_s120a(ctx) -> str:
    if ctx.button_id in [b["id"] for b in _S120A_ITEMS]:
        ctx.session["vendor_category"] = ctx.button_id.split(".")[-1]
        crm.write_event(
            ctx.contact_id,
            "STATE_TRANSITION",
            {"from": "S1.20a", "to": "S1.20b", "category": ctx.session["vendor_category"]},
        )
        return "S1.20b"

    interactive = {
        "type": "list",
        "body": {"text": copy_library.get("S1.20a", "body")},
        "action": {
            "button": "Choose category",
            "sections": [{"title": "Vendor / service category", "rows": _S120A_ITEMS}],
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="S1.20a")
    return "S1.20a"


# ─── S1.20b capture ──────────────────────────────────────────────────────────

def handle_s120b(ctx) -> str:
    # If the vendor is asking a follow-up question (FAQ intent from router),
    # answer via the LLM before archiving so the exchange feels considered.
    if ctx.message_type == "text" and ctx.intent == "FAQ":
        return answering.answer_or_fallback(
            ctx,
            contact_kind="vendor",
            fallback_state_id="S1.20b",
            fallback_copy_state_id="S1.20b",
        )

    if ctx.message_type in ("text", "document", "image"):
        payload = {
            "category": ctx.session.get("vendor_category", "UNSPECIFIED"),
            "msg_type": ctx.message_type,
        }
        if ctx.message_type == "text":
            payload["text"] = ctx.text_body[:2000]
        crm.write_event(ctx.contact_id, "VENDOR_INTRO_CAPTURED", payload)
        return "S1.20c"

    wa_client.send_text(ctx.wa_id, copy_library.get("S1.20b", "body"), state_id="S1.20b")
    return "S1.20b"


# ─── S1.20c archive with instructions ────────────────────────────────────────

def handle_s120c(ctx) -> str:
    # First entry: send the routing confirmation and archive.
    if not ctx.session.get("vendor_routed_ack_sent"):
        wa_client.send_text(ctx.wa_id, copy_library.get("S1.20c", "body"), state_id="S1.20c")
        crm.write_event(ctx.contact_id, "VENDOR_ROUTED", {"category": ctx.session.get("vendor_category", "")})
        ctx.session["vendor_routed_ack_sent"] = True
        return "X.ARCH"

    # Follow-up ping after archive — vendors often ask for a timeline. Answer
    # via the LLM instead of silence; router already jumped to X.ARCH for
    # non-questions.
    if ctx.message_type == "text":
        return answering.answer_or_fallback(
            ctx,
            contact_kind="vendor",
            fallback_state_id="X.ARCH",
            fallback_copy_state_id="S1.20c",
        )
    return "X.ARCH"
