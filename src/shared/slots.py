"""Candidate slot generator for Discovery Call / Project Discussion / Walkthrough.

Studio defaults (Notion §6): Tue & Thu 10:00–13:00 IST. `slot_windows` config
below can be overridden per meeting type. Slots inside `_BOOKING_BUFFER_HOURS`
are dropped; slots overlapping busy periods on the calendar are dropped.

Slot ID format: `SLOT_YYYYMMDD_HHMM_<duration>m` — encoded so the button
reply can be decoded back to `(start, end)` without a lookup table.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta

import ist_time

_BOOKING_BUFFER_HOURS = int(os.environ.get("BOOKING_BUFFER_HOURS", "2"))
_LOOKAHEAD_DAYS = int(os.environ.get("SLOT_LOOKAHEAD_DAYS", "14"))
_MAX_SLOTS_SHOWN = int(os.environ.get("MAX_SLOTS_SHOWN", "6"))
_DAILY_CAP = int(os.environ.get("SLOT_DAILY_CAP", "4"))

# Days of week (Mon=0..Sun=6) on which the partner takes bookings. Default per
# Notion §6 recommendation.
_BOOKING_DAYS = tuple(
    int(d) for d in os.environ.get("BOOKING_WEEKDAYS", "1,3").split(",") if d.strip()
)
# Half-open window on booking days, IST.
_BOOKING_WINDOW_START_HOUR = int(os.environ.get("BOOKING_WINDOW_START", "10"))
_BOOKING_WINDOW_END_HOUR = int(os.environ.get("BOOKING_WINDOW_END", "13"))


@dataclass
class Slot:
    id: str
    title: str
    iso_start: str
    iso_end: str

    def to_list_row(self) -> dict:
        return {"id": self.id, "title": self.title, "description": ""}


def generate(
    duration_minutes: int,
    step_minutes: int | None = None,
    busy: list[dict] | None = None,
    now: datetime | None = None,
) -> list[Slot]:
    """Return up to `_MAX_SLOTS_SHOWN` candidate slots.

    `step_minutes` controls slot cadence (defaults to `duration_minutes`).
    `busy` = list of {"start": iso, "end": iso} to subtract (from calendar.freebusy).
    """
    step = step_minutes or duration_minutes
    now = now or ist_time.now_ist()
    cutoff = now + timedelta(hours=_BOOKING_BUFFER_HOURS)
    horizon = now + timedelta(days=_LOOKAHEAD_DAYS)

    busy_intervals = [(_parse(b["start"]), _parse(b["end"])) for b in (busy or [])]

    out: list[Slot] = []
    per_day_count: dict[str, int] = {}

    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= horizon and len(out) < _MAX_SLOTS_SHOWN:
        if day.weekday() in _BOOKING_DAYS:
            for slot in _slots_in_day(day, duration_minutes, step):
                if len(out) >= _MAX_SLOTS_SHOWN:
                    break
                if slot.iso_start_dt < cutoff:
                    continue
                if per_day_count.get(day.date().isoformat(), 0) >= _DAILY_CAP:
                    break
                if _overlaps_any(slot.iso_start_dt, slot.iso_end_dt, busy_intervals):
                    continue
                out.append(_make(slot.iso_start_dt, duration_minutes))
                per_day_count[day.date().isoformat()] = per_day_count.get(day.date().isoformat(), 0) + 1
        day += timedelta(days=1)

    return out


def decode(slot_id: str) -> tuple[datetime, datetime]:
    """Inverse of `_make(...)`. Raises ValueError on bad id."""
    if not slot_id.startswith("SLOT_"):
        raise ValueError(f"not a slot id: {slot_id!r}")
    _, date_part, hhmm, duration = slot_id.split("_")
    if not duration.endswith("m"):
        raise ValueError(f"bad duration in slot id: {slot_id!r}")
    minutes = int(duration[:-1])
    start = datetime.strptime(date_part + hhmm, "%Y%m%d%H%M").replace(tzinfo=ist_time.now_ist().tzinfo)
    return start, start + timedelta(minutes=minutes)


# ─── Helpers ─────────────────────────────────────────────────────────────────

@dataclass
class _Candidate:
    iso_start_dt: datetime
    iso_end_dt: datetime


def _slots_in_day(day: datetime, duration_minutes: int, step: int) -> list[_Candidate]:
    out = []
    cursor = day.replace(hour=_BOOKING_WINDOW_START_HOUR, minute=0)
    end_of_window = day.replace(hour=_BOOKING_WINDOW_END_HOUR, minute=0)
    while cursor + timedelta(minutes=duration_minutes) <= end_of_window:
        out.append(_Candidate(cursor, cursor + timedelta(minutes=duration_minutes)))
        cursor += timedelta(minutes=step)
    return out


def _overlaps_any(start: datetime, end: datetime, busy: list[tuple[datetime, datetime]]) -> bool:
    for b_start, b_end in busy:
        if start < b_end and end > b_start:
            return True
    return False


def _make(start: datetime, duration_minutes: int) -> Slot:
    end = start + timedelta(minutes=duration_minutes)
    slot_id = f"SLOT_{start.strftime('%Y%m%d')}_{start.strftime('%H%M')}_{duration_minutes}m"
    title = start.strftime("%a %d %b · %H:%M IST")
    return Slot(id=slot_id, title=title, iso_start=start.isoformat(), iso_end=end.isoformat())


def _parse(iso: str) -> datetime:
    """Parse an ISO string (with tzinfo) into a datetime — Google Calendar returns Z-suffixed UTC."""
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    return datetime.fromisoformat(iso).astimezone(ist_time.now_ist().tzinfo)
