"""WhatsApp Cloud API client — send text, template, interactive, media, flow.

Credentials live in Secrets Manager at `as-whatsapp-agent/meta` as:
    {
        "access_token": "EAAG…",
        "app_secret": "…",
        "verify_token": "…",
        "phone_number_id": "…"
    }

All outbound payloads pass through `style_guard.assert_clean()` on any
user-visible text.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

import boto3
import requests

import style_guard

_SECRET_ARN = os.environ.get(
    "META_SECRET_ARN",
    f"arn:aws:secretsmanager:{os.environ.get('REGION', 'ap-south-1')}:{os.environ.get('AWS_ACCOUNT_ID', '')}:secret:as-whatsapp-agent/meta",
)
_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v21.0")
_API_BASE = f"https://graph.facebook.com/{_GRAPH_VERSION}"
_TIMEOUT_S = 10


@lru_cache(maxsize=1)
def _credentials() -> dict:
    sm = boto3.client("secretsmanager")
    secret = json.loads(sm.get_secret_value(SecretId=_SECRET_ARN)["SecretString"])
    required = {"access_token", "app_secret", "verify_token", "phone_number_id"}
    missing = required - secret.keys()
    if missing:
        raise RuntimeError(f"wa_client: secret missing keys: {missing}")
    return secret


def access_token() -> str:
    return _credentials()["access_token"]


def app_secret() -> str:
    return _credentials()["app_secret"]


def verify_token() -> str:
    return _credentials()["verify_token"]


def phone_number_id() -> str:
    return _credentials()["phone_number_id"]


# ─── Send ───────────────────────────────────────────────────────────────────

def send_text(to_wa_id: str, body: str, state_id: str = "") -> dict:
    """Send a free-form text message (only inside the 24-hour window)."""
    style_guard.assert_clean(body, state_id=state_id)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": body, "preview_url": True},
    }
    return _post_messages(payload)


def send_template(
    to_wa_id: str,
    template_name: str,
    language_code: str = "en",
    components: list[dict] | None = None,
) -> dict:
    """Send an approved template message (works outside the 24-hour window)."""
    template: dict[str, Any] = {
        "name": template_name,
        "language": {"code": language_code},
    }
    if components:
        template["components"] = components
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "template",
        "template": template,
    }
    return _post_messages(payload)


def send_interactive(to_wa_id: str, interactive: dict, state_id: str = "") -> dict:
    """Send a button / list / cta_url / flow interactive message.

    Caller is responsible for constructing the `interactive` dict per Meta's schema.
    Any body/header text is scanned by style_guard.
    """
    for key in ("body", "header", "footer"):
        text = interactive.get(key, {}).get("text")
        if text:
            style_guard.assert_clean(text, state_id=state_id)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "interactive",
        "interactive": interactive,
    }
    return _post_messages(payload)


def mark_read(message_id: str) -> dict:
    """Send read receipt for an inbound message id."""
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    return _post_messages(payload)


# ─── HTTP ────────────────────────────────────────────────────────────────────

def _post_messages(payload: dict) -> dict:
    url = f"{_API_BASE}/{phone_number_id()}/messages"
    headers = {
        "Authorization": f"Bearer {access_token()}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=_TIMEOUT_S)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"wa_client: Meta API {resp.status_code}: {resp.text[:500]}"
        )
    return resp.json()
