"""UTM-tagged link builder + one-tap unsubscribe URL."""

from __future__ import annotations

import os
from urllib.parse import quote, urlencode, urlparse, urlunparse, parse_qsl

_UNSUBSCRIBE_BASE = os.environ.get(
    "UNSUBSCRIBE_URL",
    "https://TODO.execute-api.ap-south-1.amazonaws.com/prod/unsubscribe",
)


def utm(
    url: str,
    campaign: str,
    source: str = "whatsapp",
    medium: str = "whatsapp",
    content: str | None = None,
    term: str | None = None,
) -> str:
    """Append UTM params to a URL, preserving existing query args."""
    parsed = urlparse(url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing.update(
        {
            "utm_source": source,
            "utm_medium": medium,
            "utm_campaign": campaign,
        }
    )
    if content:
        existing["utm_content"] = content
    if term:
        existing["utm_term"] = term
    return urlunparse(parsed._replace(query=urlencode(existing)))


def unsubscribe(contact_id: str, campaign: str = "") -> str:
    """Build the one-tap unsubscribe URL for a specific contact + campaign."""
    query = {"cid": contact_id}
    if campaign:
        query["c"] = campaign
    return _UNSUBSCRIBE_BASE + "?" + urlencode(query, quote_via=quote)
