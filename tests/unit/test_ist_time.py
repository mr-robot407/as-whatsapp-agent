"""Unit tests for shared/ist_time.py — IST business-hours guard."""

import unittest
import zoneinfo
from datetime import datetime

from ist_time import is_business_hours, next_business_open

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")


def _ist(y: int, m: int, d: int, hour: int, minute: int = 0) -> datetime:
    return datetime(y, m, d, hour, minute, tzinfo=_IST)


class TestIsBusinessHours(unittest.TestCase):
    # 2026-09-07 = Monday, 2026-09-12 = Saturday, 2026-09-13 = Sunday.

    def test_monday_morning_open(self):
        self.assertTrue(is_business_hours(_ist(2026, 9, 7, 9, 0)))

    def test_saturday_afternoon_open(self):
        self.assertTrue(is_business_hours(_ist(2026, 9, 12, 15, 30)))

    def test_monday_before_9_closed(self):
        self.assertFalse(is_business_hours(_ist(2026, 9, 7, 8, 59)))

    def test_monday_after_18_closed(self):
        self.assertFalse(is_business_hours(_ist(2026, 9, 7, 18, 0)))

    def test_sunday_closed(self):
        self.assertFalse(is_business_hours(_ist(2026, 9, 13, 12, 0)))


class TestNextBusinessOpen(unittest.TestCase):
    def test_within_hours_returns_next_day_9am(self):
        dt = _ist(2026, 9, 7, 14, 0)  # Mon 14:00
        nxt = next_business_open(dt)
        self.assertEqual(nxt, _ist(2026, 9, 8, 9, 0))  # Tue 09:00

    def test_before_hours_returns_same_day_9am(self):
        dt = _ist(2026, 9, 7, 7, 0)  # Mon 07:00
        nxt = next_business_open(dt)
        self.assertEqual(nxt, _ist(2026, 9, 7, 9, 0))  # Mon 09:00

    def test_saturday_evening_skips_sunday(self):
        dt = _ist(2026, 9, 12, 20, 0)  # Sat 20:00
        nxt = next_business_open(dt)
        self.assertEqual(nxt, _ist(2026, 9, 14, 9, 0))  # Mon 09:00 (skips Sun)


if __name__ == "__main__":
    unittest.main()
