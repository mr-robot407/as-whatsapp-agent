"""Meta webhook signature verification — X-Hub-Signature-256."""

from __future__ import annotations

import hashlib
import hmac


def verify(app_secret: str, raw_body: bytes, header_value: str) -> bool:
    """Verify the `X-Hub-Signature-256` header sent by Meta.

    The header format is `sha256=<hex-digest>`, computed as
    HMAC-SHA256(app_secret, raw_body).
    """
    if not header_value or not header_value.startswith("sha256="):
        return False
    provided = header_value.split("=", 1)[1].strip()
    expected = hmac.new(
        app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, provided)
