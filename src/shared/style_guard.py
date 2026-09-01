"""Style guard — blocks messages containing disallowed phrases.

Loaded from `config/disallowed_phrases.json` (shared with the email agent's copy).
Call `assert_clean()` before every outbound message send.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

_CONFIG_PATH = Path(
    os.environ.get(
        "CONFIG_DIR", str(Path(__file__).parent.parent.parent / "config")
    )
) / "disallowed_phrases.json"


@lru_cache(maxsize=1)
def _load_phrases() -> tuple[str, ...]:
    try:
        with open(_CONFIG_PATH) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return ()
    if isinstance(data, dict):
        data = data.get("phrases", [])
    return tuple(p.strip() for p in data if p and p.strip())


def scan(text: str) -> list[str]:
    """Return the disallowed phrases (case-insensitive, word-boundary) present in text."""
    hits: list[str] = []
    lowered = text or ""
    for phrase in _load_phrases():
        pattern = r"\b" + re.escape(phrase) + r"\b"
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            hits.append(phrase)
    return hits


def is_clean(text: str) -> bool:
    return not scan(text)


def assert_clean(text: str, state_id: str = "") -> None:
    """Raise ValueError if text contains disallowed phrases."""
    hits = scan(text)
    if hits:
        prefix = f"[{state_id}] " if state_id else ""
        raise ValueError(
            f"{prefix}style_guard violation — disallowed phrases: {hits}"
        )
