"""LLM-answering helper used by free-form state handlers.

State handlers call `answer_or_fallback(ctx, contact_kind, fallback_state_id)`
when they receive free-text they cannot consume with a scripted branch.

Behaviour:
  1. If the LLM layer is disabled OR the router already classified the intent
     as OFF_TOPIC / UNSURE, send the fallback copy and return the fallback state.
  2. Otherwise, invoke `llm.generate_reply()`. On a clean reply, send it and
     return the current state so the funnel stays put and the user can continue
     asking questions.
  3. On any escalation / style-guard block / model failure, send the fallback
     copy (which offers the Discovery Call) and return the fallback state.

The helper never invents copy: every reply either comes verbatim from the copy
library (fallback path) or from an LLM output that has passed `style_guard`
and the forbidden-content check.
"""

from __future__ import annotations

import copy_library
import crm
import llm
import wa_client


_ANSWERABLE_INTENTS = {"FAQ", "BOOKING_CHANGE", "FUNNEL_STEP", "UNSURE"}


def answer_or_fallback(
    ctx,
    contact_kind: str,
    fallback_state_id: str = "X.FALLBACK",
    fallback_copy_state_id: str | None = None,
) -> str:
    """Try LLM reply; fall back to a copy-library body on any failure.

    Args:
        ctx: RouterContext from the caller.
        contact_kind: 'client' | 'vendor' | 'career' | 'press' | 'unknown'.
        fallback_state_id: state to transition to when the LLM path fails.
        fallback_copy_state_id: copy_library key for the fallback body; if
            omitted, uses fallback_state_id.

    Returns:
        The state_id to transition to.
    """
    fallback_copy_state_id = fallback_copy_state_id or fallback_state_id

    if not llm.is_enabled() or ctx.intent == "OFF_TOPIC":
        _send_fallback(ctx, fallback_copy_state_id)
        return fallback_state_id

    if ctx.intent and ctx.intent not in _ANSWERABLE_INTENTS:
        # PERSONHOOD_QUERY / HUMAN_REQUEST / OPT_OUT were already handled by
        # the router before we ever got here; anything else unexpected is
        # treated as fallback.
        _send_fallback(ctx, fallback_copy_state_id)
        return fallback_state_id

    reply = llm.generate_reply(
        user_text=ctx.text_body,
        current_state=ctx.current_state,
        contact_kind=contact_kind,
        last_turns=[],  # transcript threading is a Phase-5 concern
        state_id_for_style_guard=f"LLM.{ctx.current_state}",
    )
    if not reply:
        crm.write_event(
            ctx.contact_id,
            "LLM_FALLBACK",
            {"state": ctx.current_state, "intent": ctx.intent, "contact_kind": contact_kind},
        )
        _send_fallback(ctx, fallback_copy_state_id)
        return fallback_state_id

    wa_client.send_text(ctx.wa_id, reply, state_id=f"LLM.{ctx.current_state}")
    crm.write_event(
        ctx.contact_id,
        "LLM_REPLY_SENT",
        {"state": ctx.current_state, "intent": ctx.intent, "contact_kind": contact_kind, "reply_len": len(reply)},
    )
    return ctx.current_state


def _send_fallback(ctx, copy_state_id: str) -> None:
    try:
        body = copy_library.get(copy_state_id, "body")
    except KeyError:
        body = copy_library.get("X.FALLBACK", "body")
    wa_client.send_text(ctx.wa_id, body, state_id=copy_state_id)
