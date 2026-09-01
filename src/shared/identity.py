"""Phone-number normalisation and contact-id helpers for the WhatsApp channel."""

from __future__ import annotations

import re
import uuid

_DIGITS = re.compile(r"\D+")
_DEFAULT_COUNTRY_CODE = "91"


def normalise_e164(raw: str, default_cc: str = _DEFAULT_COUNTRY_CODE) -> str:
    """Return E.164 form (leading `+`, digits only).

    Accepts inputs like `+91 95602 06195`, `919560206195`, `9560206195`.
    A bare 10-digit input is prefixed with `default_cc`.
    """
    if not raw:
        raise ValueError("empty phone number")
    digits = _DIGITS.sub("", raw)
    if not digits:
        raise ValueError(f"no digits in phone number: {raw!r}")
    if len(digits) == 10:
        digits = default_cc + digits
    return "+" + digits


def wa_id_from_e164(e164: str) -> str:
    """Meta's WhatsApp payloads use `wa_id` without the leading `+` — strip it."""
    if not e164.startswith("+"):
        raise ValueError(f"expected E.164 with leading +, got {e164!r}")
    return e164[1:]


def e164_from_wa_id(wa_id: str) -> str:
    """Inverse of wa_id_from_e164 — restore leading `+`."""
    return "+" + wa_id.lstrip("+")


def new_contact_id() -> str:
    return str(uuid.uuid4())
