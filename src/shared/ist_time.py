"""IST helpers — operating window and business-hours guard for WhatsApp sends."""

from __future__ import annotations

import os
import zoneinfo
from datetime import datetime, timedelta

_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")

# Defaults match .env.example — override at handler startup if needed.
_OPEN_HOUR = int(os.environ.get("OPERATING_OPEN_HOUR", "9"))
_CLOSE_HOUR = int(os.environ.get("OPERATING_CLOSE_HOUR", "18"))
_OPERATING_DAYS = set(
    d.strip().lower()
    for d in os.environ.get(
        "OPERATING_DAYS", "mon,tue,wed,thu,fri,sat"
    ).split(",")
)

_WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def now_ist() -> datetime:
    return datetime.now(_TZ)


def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime passed to to_ist — supply tzinfo")
    return dt.astimezone(_TZ)


def is_business_hours(dt: datetime | None = None) -> bool:
    """True if dt (or now) is within OPERATING_DAYS and OPERATING_HOURS in IST."""
    dt = to_ist(dt) if dt else now_ist()
    if _WEEKDAY_NAMES[dt.weekday()] not in _OPERATING_DAYS:
        return False
    return _OPEN_HOUR <= dt.hour < _CLOSE_HOUR


def next_business_open(dt: datetime | None = None) -> datetime:
    """Return the next open datetime at OPEN_HOUR IST on an OPERATING_DAY."""
    dt = to_ist(dt) if dt else now_ist()
    cursor = dt.replace(hour=_OPEN_HOUR, minute=0, second=0, microsecond=0)
    if dt.hour >= _OPEN_HOUR:
        cursor += timedelta(days=1)
    while _WEEKDAY_NAMES[cursor.weekday()] not in _OPERATING_DAYS:
        cursor += timedelta(days=1)
    return cursor
