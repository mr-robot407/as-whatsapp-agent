"""Razorpay Payment Links + HMAC-SHA256 webhook signature verify.

Shared credentials with the email agent — read from Secrets Manager at
`as-email-agent/razorpay` per §.env.example.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from functools import lru_cache

import boto3
import requests

_SECRET_ARN = os.environ.get(
    "RAZORPAY_SECRET_ARN",
    f"arn:aws:secretsmanager:{os.environ.get('REGION', 'ap-south-1')}:{os.environ.get('AWS_ACCOUNT_ID', '')}:secret:as-email-agent/razorpay",
)
_API_BASE = "https://api.razorpay.com/v1"
_TIMEOUT_S = 10


@lru_cache(maxsize=1)
def _credentials() -> tuple[str, str, str]:
    sm = boto3.client("secretsmanager")
    secret = json.loads(sm.get_secret_value(SecretId=_SECRET_ARN)["SecretString"])
    return secret["key_id"], secret["key_secret"], secret.get("webhook_secret", "")


def create_payment_link(
    amount_inr: int,
    description: str,
    contact_name: str,
    contact_phone_e164: str,
    reference_id: str,
    expire_by_unix: int,
    contact_email: str = "",
) -> dict:
    """Create a Razorpay Payment Link. Amount is in INR (converted to paise)."""
    key_id, key_secret, _ = _credentials()
    payload = {
        "amount": amount_inr * 100,
        "currency": "INR",
        "description": description,
        "customer": {
            "name": contact_name,
            "contact": contact_phone_e164,
        },
        "notify": {"sms": False, "email": False},
        "reference_id": reference_id,
        "expire_by": expire_by_unix,
    }
    if contact_email:
        payload["customer"]["email"] = contact_email
    resp = requests.post(
        f"{_API_BASE}/payment_links",
        json=payload,
        auth=(key_id, key_secret),
        timeout=_TIMEOUT_S,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"razorpay: {resp.status_code}: {resp.text[:500]}")
    return resp.json()


def verify_webhook_signature(payload_body: bytes, signature: str) -> bool:
    """Verify Razorpay webhook HMAC-SHA256 signature."""
    _, _, webhook_secret = _credentials()
    if not webhook_secret:
        raise RuntimeError("razorpay: webhook_secret missing from secret")
    expected = hmac.new(
        webhook_secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
