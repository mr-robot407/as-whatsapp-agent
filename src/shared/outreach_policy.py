"""Loader for `config/outreach_policy.json` — outreach caps + windows."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

_CONFIG_PATH = Path(
    os.environ.get(
        "CONFIG_DIR", str(Path(__file__).parent.parent.parent / "config")
    )
) / "outreach_policy.json"


@lru_cache(maxsize=1)
def load() -> dict:
    with open(_CONFIG_PATH) as fh:
        return json.load(fh)


def daily_cap() -> int:
    return int(load().get("daily_cap", 50))


def batch_size() -> int:
    return int(load().get("batch_size", 10))


def max_marketing_per_year() -> int:
    return int(load().get("marketing_templates_per_recipient_per_year", 4))
