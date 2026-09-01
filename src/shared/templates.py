"""WhatsApp template registry — gates sends on Meta approval and DLT ID presence.

Templates with `meta_template_id` or `dlt_template_id` set to null are BLOCKED at
this layer per `config/templates_registry.json`. This is the single point where
DLT/Meta approval status is enforced before any Marketing/Utility send.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import wa_client

_CONFIG_PATH = Path(
    os.environ.get(
        "CONFIG_DIR", str(Path(__file__).parent.parent.parent / "config")
    )
) / "templates_registry.json"


@lru_cache(maxsize=1)
def _registry() -> dict:
    with open(_CONFIG_PATH) as fh:
        return json.load(fh)["templates"]


def get(template_key: str) -> dict:
    reg = _registry()
    if template_key not in reg:
        raise KeyError(f"templates: unknown template key {template_key!r}")
    return reg[template_key]


def is_approved(template_key: str) -> bool:
    """True iff both Meta template id and DLT template id are populated."""
    entry = get(template_key)
    return bool(entry.get("meta_template_id")) and bool(entry.get("dlt_template_id"))


def assert_approved(template_key: str) -> dict:
    """Raise RuntimeError if template is not approved (missing Meta id or DLT id)."""
    entry = get(template_key)
    missing = []
    if not entry.get("meta_template_id"):
        missing.append("meta_template_id")
    if not entry.get("dlt_template_id"):
        missing.append("dlt_template_id")
    if missing:
        raise RuntimeError(
            f"templates: {template_key!r} blocked — missing {missing}. "
            f"Populate `config/templates_registry.json` after approval."
        )
    return entry


def send(
    template_key: str,
    to_wa_id: str,
    components: list[dict] | None = None,
) -> dict:
    """Send an approved template. Raises if not approved or audience gates fail."""
    entry = assert_approved(template_key)
    return wa_client.send_template(
        to_wa_id=to_wa_id,
        template_name=entry["meta_template_name"],
        language_code=entry.get("language", "en"),
        components=components,
    )
