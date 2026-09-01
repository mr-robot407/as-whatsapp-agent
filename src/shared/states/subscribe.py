"""E.SUB.step_a → E.SUB.step_b — quarterly editorial digest subscription."""

from __future__ import annotations

from datetime import datetime, timezone

import copy_library
import crm
import wa_client

_ESUB_CONFIRM_ID = "E.SUB.CONFIRM"
_ESUB_DECLINE_ID = "E.SUB.DECLINE"


def handle_step_a(ctx) -> str:
    if ctx.button_id == _ESUB_CONFIRM_ID:
        email = ctx.session.get("contact_email", "")
        if not email:
            wa_client.send_text(
                ctx.wa_id,
                "An email address is required to subscribe — kindly share one.",
                state_id="E.SUB.step_a.no_email",
            )
            return "E.SUB.step_a"
        crm.write_event(
            ctx.contact_id,
            "SUBSCRIBE_QUARTERLY_DIGEST",
            {"email": email, "confirmed_at": datetime.now(timezone.utc).isoformat()},
        )
        ctx.session["digest_email"] = email
        return "E.SUB.step_b"
    if ctx.button_id == _ESUB_DECLINE_ID:
        return "E.00"

    email_on_file = ctx.session.get("contact_email", "(not on file)")
    body = copy_library.render("E.SUB", {"emailOnFile": email_on_file}, key="step_a")
    interactive = {
        "type": "button",
        "body": {"text": body},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": _ESUB_CONFIRM_ID, "title": "Subscribe"}},
                {"type": "reply", "reply": {"id": _ESUB_DECLINE_ID, "title": "Not now"}},
            ]
        },
    }
    wa_client.send_interactive(ctx.wa_id, interactive, state_id="E.SUB.step_a")
    return "E.SUB.step_a"


def handle_step_b(ctx) -> str:
    email = ctx.session.get("digest_email", "")
    body = copy_library.render(
        "E.SUB",
        {"email": email, "nextQuarterStartHuman": _next_quarter_start_human()},
        key="step_b",
    )
    wa_client.send_text(ctx.wa_id, body, state_id="E.SUB.step_b")
    return "E.00"


def _next_quarter_start_human() -> str:
    now = datetime.now(timezone.utc)
    year = now.year
    month = ((now.month - 1) // 3 + 1) * 3 + 1
    if month > 12:
        month = 1
        year += 1
    return datetime(year, month, 1).strftime("%d %b %Y")
