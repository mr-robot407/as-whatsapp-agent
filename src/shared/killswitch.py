"""Kill switch — reads /as-whatsapp-agent/AGENT_ENABLED from SSM with a 5-min cache.

Fail-open on SSM error so a transient AWS blip does not silence the agent.
"""

from __future__ import annotations

import os
import time

import boto3

_PARAM = os.environ.get("AGENT_ENABLED_PARAM", "/as-whatsapp-agent/AGENT_ENABLED")
_CACHE_TTL = 300  # seconds

_ssm = boto3.client("ssm")
_cache_value: bool = True
_cache_ts: float = 0.0


def is_enabled() -> bool:
    global _cache_value, _cache_ts
    now = time.time()
    if now - _cache_ts < _CACHE_TTL:
        return _cache_value
    try:
        resp = _ssm.get_parameter(Name=_PARAM)
        _cache_value = resp["Parameter"]["Value"].strip().lower() == "true"
    except Exception as exc:  # noqa: BLE001 — fail-open
        print(f"killswitch: SSM read failed ({exc.__class__.__name__}) — defaulting to enabled")
        _cache_value = True
    _cache_ts = now
    return _cache_value
