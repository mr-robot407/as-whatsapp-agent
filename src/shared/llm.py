"""Anthropic Claude client — classifier + reply generator with prompt caching.

Mirrors the email agent's pattern (see `as-email-agent/src/inbound/app.py` for
the classifier call). Adds:

  1. A reply generator for free-text customer/vendor queries — the static
     prefix (voice rules + KB + copy library) is cache-marked so subsequent
     calls hit the Anthropic prompt cache and pay only for the per-turn
     suffix.
  2. Hard `style_guard.assert_clean()` on every generated reply. On any
     violation, the module returns `None` and the caller must fall back to
     the copy-library escalation path — the assistant never invents text.
  3. `is_enabled()` — checks `ANTHROPIC_API_KEY` presence AND the SSM flag
     `/as-whatsapp-agent/LLM_ENABLED` so the LLM layer can be A/B'd against
     the scripted-only funnel without a redeploy.

Environment:
    ANTHROPIC_API_KEY               — required for any LLM call.
    ANTHROPIC_CLASSIFIER_MODEL      — default: claude-haiku-4-5-20251001.
    ANTHROPIC_REPLY_MODEL           — default: claude-haiku-4-5-20251001.
    LLM_ENABLED_PARAM               — default: /as-whatsapp-agent/LLM_ENABLED.
"""

from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path

import boto3

import style_guard

def _resolve_api_key() -> str | None:
    """Prefer env var (dev + email-agent parity); fall back to Secrets Manager."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    arn = os.environ.get("ANTHROPIC_SECRET_ARN")
    if not arn:
        return None
    try:
        sm = boto3.client("secretsmanager")
        raw = sm.get_secret_value(SecretId=arn)["SecretString"]
        parsed = json.loads(raw)
        return parsed.get("api_key") or parsed.get("ANTHROPIC_API_KEY")
    except Exception as exc:  # noqa: BLE001
        print(f"llm._resolve_api_key: SecretsManager read failed — {exc.__class__.__name__}: {exc}")
        return None


try:
    from anthropic import Anthropic
    _api_key = _resolve_api_key()
    _anthropic = Anthropic(api_key=_api_key) if _api_key else None
    if _anthropic is None:
        print("llm init: no ANTHROPIC_API_KEY resolved (env var + secrets manager both empty)")
except Exception as _init_exc:  # noqa: BLE001
    print(f"llm init: anthropic client init failed — {_init_exc.__class__.__name__}: {_init_exc}")
    _anthropic = None

_CLASSIFIER_MODEL = os.environ.get("ANTHROPIC_CLASSIFIER_MODEL", "claude-haiku-4-5-20251001")
_REPLY_MODEL = os.environ.get("ANTHROPIC_REPLY_MODEL", "claude-haiku-4-5-20251001")

_LLM_ENABLED_PARAM = os.environ.get("LLM_ENABLED_PARAM", "/as-whatsapp-agent/LLM_ENABLED")
_LLM_ENABLED_CACHE_TTL = 300
_llm_enabled_cache: bool = False
_llm_enabled_cache_ts: float = 0.0

_ssm = boto3.client("ssm")


# ─── Enablement ──────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    """True iff API key is set AND SSM flag is 'true'. Fail-closed on error."""
    if _anthropic is None:
        return False
    global _llm_enabled_cache, _llm_enabled_cache_ts
    now = time.time()
    if now - _llm_enabled_cache_ts < _LLM_ENABLED_CACHE_TTL:
        return _llm_enabled_cache
    try:
        resp = _ssm.get_parameter(Name=_LLM_ENABLED_PARAM)
        _llm_enabled_cache = resp["Parameter"]["Value"].strip().lower() == "true"
    except Exception as exc:  # noqa: BLE001
        print(f"llm.is_enabled: SSM read failed ({exc.__class__.__name__}) — defaulting off")
        _llm_enabled_cache = False
    _llm_enabled_cache_ts = now
    return _llm_enabled_cache


# ─── Prompts + KB loading (cache-static) ─────────────────────────────────────

_CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", str(Path(__file__).parent.parent.parent / "config")))


@lru_cache(maxsize=1)
def _kb_json() -> str:
    with open(_CONFIG_DIR / "kb.json") as fh:
        return fh.read()


@lru_cache(maxsize=1)
def _copy_library_json() -> str:
    with open(_CONFIG_DIR / "copy_library.json") as fh:
        return fh.read()


_CLASSIFIER_LABELS = (
    "FUNNEL_STEP",       # message continues the scripted flow — router should stay in current state
    "FAQ",               # question answerable from KB
    "BOOKING_CHANGE",    # reschedule / cancel / re-payment request
    "HUMAN_REQUEST",     # explicit ask to speak to a person
    "PERSONHOOD_QUERY",  # asking if the assistant is a bot / a human
    "OPT_OUT",           # STOP / unsubscribe intent expressed conversationally
    "OFF_TOPIC",         # unrelated / trolling / spam
    "UNSURE",            # low confidence
)

_CLASSIFIER_SYSTEM = (
    "You are a single-label intent classifier for the WhatsApp channel of "
    "Atelier Shreenu, an architecture and interior design studio. "
    "The user is either a prospective client, a vendor / service provider, "
    "a career applicant, or press. You do not answer the message; you only "
    "assign one intent label. "
    "Labels: FUNNEL_STEP | FAQ | BOOKING_CHANGE | HUMAN_REQUEST | "
    "PERSONHOOD_QUERY | OPT_OUT | OFF_TOPIC | UNSURE. "
    "Return exactly one label. No punctuation. No explanation."
)


def _reply_system_blocks() -> list[dict]:
    """System prompt built as content blocks so we can cache-mark the static prefix.

    The KB and copy library rarely change; marking them with
    `cache_control: {"type": "ephemeral"}` lets subsequent calls reuse the
    cached prefix and pay ~90% less on tokens.
    """
    static_prefix = (
        "You are the reply generator for the Atelier Shreenu WhatsApp "
        "concierge assistant. You do NOT roleplay a human. Every reply you "
        "produce must comply with the studio's voice rules, quote only facts "
        "in the knowledge base, and remain inside the 24-hour WhatsApp "
        "service window (the caller has already checked this).\n\n"

        "HARD RULES — a violation on any of these is a defect:\n"
        "  1. Third-person only. Refer to the studio as 'the studio', 'the "
        "     practice', or 'Atelier Shreenu'. Never 'I', 'me', 'my'. Use 'we' "
        "     only for the practice as a whole.\n"
        "  2. Emojis are forbidden except 📍 and 📅 in address/booking "
        "     contexts.\n"
        "  3. Never disclose the partner's direct number (+91 95601 07193).\n"
        "  4. Never quote a fee other than ₹1,770, ₹3,540, or ₹7,080.\n"
        "  5. Never invent timelines, availability, or process steps not in "
        "     the KB. If a customer asks something the KB does not cover, "
        "     reply with: 'The studio will bring this up on the Discovery "
        "     Call.' and offer S1.14.\n"
        "  6. No sales pressure. No chattiness. No filler. Restrained, "
        "     considered, useful. 1–3 short sentences maximum.\n"
        "  7. When a reply cites the fee schedule, cite the exact figure "
        "     with GST note as written in the KB.\n"
        "  8. End every reply with a concrete next action drawn from the "
        "     copy library (book a Discovery Call, choose a vendor category, "
        "     send portfolio to info@ateliershreenu.com, etc.) when one is "
        "     available for the customer's context.\n\n"

        "You will receive:\n"
        "  • KNOWLEDGE_BASE — a JSON document of facts you may cite.\n"
        "  • COPY_LIBRARY  — a JSON document of verbatim message bodies. "
        "     Prefer verbatim copy where any entry fits the situation; only "
        "     generate a new reply when no library entry applies.\n"
        "  • CURRENT_STATE — the scripted state the contact is in.\n"
        "  • CONTACT_KIND  — client | vendor | career | press | unknown.\n"
        "  • LAST_TURNS    — the recent conversation transcript (compact).\n"
        "  • USER_MESSAGE  — the latest inbound text from the contact.\n\n"

        "Output format: a JSON object with exactly two fields:\n"
        "  { \"reply\": \"<final WhatsApp body>\", \"escalate\": <bool> }\n"
        "Set escalate=true if the request cannot be answered inside the "
        "hard rules (asks for Shreenu's direct number, asks for unlisted "
        "fees, hostile intent, etc.). When escalate=true, set reply to an "
        "empty string.\n"
    )
    return [
        {"type": "text", "text": static_prefix, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"KNOWLEDGE_BASE:\n{_kb_json()}", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"COPY_LIBRARY:\n{_copy_library_json()}", "cache_control": {"type": "ephemeral"}},
    ]


# ─── Public API ──────────────────────────────────────────────────────────────

def classify_intent(user_text: str, current_state: str = "") -> str:
    """Return one intent label from _CLASSIFIER_LABELS. Falls back to UNSURE."""
    if not is_enabled():
        return "UNSURE"
    user_content = (
        f"CURRENT_STATE: {current_state}\n\n"
        f"USER_MESSAGE:\n{user_text[:2000]}"
    )
    try:
        resp = _anthropic.messages.create(
            model=_CLASSIFIER_MODEL,
            max_tokens=8,
            system=_CLASSIFIER_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
        label = resp.content[0].text.strip().upper().replace(" ", "_")
    except Exception as exc:  # noqa: BLE001
        print(f"llm.classify_intent: {exc.__class__.__name__}: {exc}")
        return "UNSURE"
    return label if label in _CLASSIFIER_LABELS else "UNSURE"


def generate_reply(
    user_text: str,
    current_state: str,
    contact_kind: str = "unknown",
    last_turns: list[dict] | None = None,
    state_id_for_style_guard: str = "LLM.REPLY",
) -> str | None:
    """Generate a reply for a free-text query.

    Returns:
        str  — an approved, style-guard-clean reply body ready to send.
        None — the model chose to escalate OR the output failed style guard.
               Caller must fall back to a copy-library escalation state.
    """
    if not is_enabled():
        return None

    turns_compact = last_turns or []
    if len(turns_compact) > 6:
        turns_compact = turns_compact[-6:]

    user_payload = (
        f"CURRENT_STATE: {current_state}\n"
        f"CONTACT_KIND: {contact_kind}\n"
        f"LAST_TURNS: {json.dumps(turns_compact, ensure_ascii=False)}\n\n"
        f"USER_MESSAGE:\n{user_text[:2000]}"
    )

    try:
        resp = _anthropic.messages.create(
            model=_REPLY_MODEL,
            max_tokens=350,
            system=_reply_system_blocks(),
            messages=[{"role": "user", "content": user_payload}],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"llm.generate_reply: {exc.__class__.__name__}: {exc}")
        return None

    raw = resp.content[0].text.strip()
    parsed = _extract_json(raw)
    if not parsed:
        print(f"llm.generate_reply: model returned non-JSON — raw={raw[:200]!r}")
        return None

    if parsed.get("escalate") is True:
        return None

    reply = (parsed.get("reply") or "").strip()
    if not reply:
        return None

    try:
        style_guard.assert_clean(reply, state_id=state_id_for_style_guard)
    except ValueError as exc:
        print(f"llm.generate_reply: style_guard blocked — {exc}")
        return None

    if _has_forbidden_content(reply):
        print(f"llm.generate_reply: forbidden content check failed — dropping reply")
        return None

    return reply


# ─── Guardrails ──────────────────────────────────────────────────────────────

_FORBIDDEN_SUBSTRINGS = (
    "+91 95601 07193",   # partner's direct number
    "9560107193",
    "95601 07193",
)


def _has_forbidden_content(text: str) -> bool:
    lowered = text.lower()
    if any(s.lower() in lowered for s in _FORBIDDEN_SUBSTRINGS):
        return True
    return False


def _extract_json(raw: str) -> dict | None:
    """Extract a JSON object from the model output; tolerate leading prose."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
