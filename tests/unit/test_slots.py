"""Unit tests for shared/slots.py — candidate slot generator + decode round-trip."""

import os
import unittest
import zoneinfo
from datetime import datetime, timedelta

# Force deterministic booking window: Tue & Thu 10:00–13:00 IST
os.environ["BOOKING_WEEKDAYS"] = "1,3"
os.environ["BOOKING_WINDOW_START"] = "10"
os.environ["BOOKING_WINDOW_END"] = "13"
os.environ["BOOKING_BUFFER_HOURS"] = "0"
os.environ["MAX_SLOTS_SHOWN"] = "6"
os.environ["SLOT_LOOKAHEAD_DAYS"] = "14"

import slots  # noqa: E402

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")


class TestGenerate(unittest.TestCase):
    def test_10min_slots_on_a_tuesday_morning(self):
        # Mon 2026-09-07 00:00 IST → next Tue is 2026-09-08
        now = datetime(2026, 9, 7, 0, 0, tzinfo=_IST)
        got = slots.generate(duration_minutes=10, step_minutes=15, now=now)
        self.assertTrue(len(got) > 0)
        for s in got:
            # All slots should start on a booking weekday (Tue=1 or Thu=3)
            start = datetime.fromisoformat(s.iso_start)
            self.assertIn(start.weekday(), (1, 3), f"{s.title} not on Tue/Thu")
            self.assertGreaterEqual(start.hour, 10)
            self.assertLess(start.hour, 13)

    def test_buffer_hours_skip_immediate_slots(self):
        os.environ["BOOKING_BUFFER_HOURS"] = "48"
        import importlib
        importlib.reload(slots)
        now = datetime(2026, 9, 8, 9, 0, tzinfo=_IST)  # Tuesday 9am
        got = slots.generate(duration_minutes=10, step_minutes=15, now=now)
        for s in got:
            start = datetime.fromisoformat(s.iso_start)
            self.assertGreaterEqual(start, now + timedelta(hours=48))
        os.environ["BOOKING_BUFFER_HOURS"] = "0"
        importlib.reload(slots)

    def test_daily_cap_applied(self):
        os.environ["SLOT_DAILY_CAP"] = "2"
        import importlib
        importlib.reload(slots)
        now = datetime(2026, 9, 7, 0, 0, tzinfo=_IST)
        got = slots.generate(duration_minutes=10, step_minutes=15, now=now)
        # Count per day
        per_day: dict[str, int] = {}
        for s in got:
            d = s.iso_start[:10]
            per_day[d] = per_day.get(d, 0) + 1
        for d, n in per_day.items():
            self.assertLessEqual(n, 2, f"{d} has {n} slots (cap=2)")
        os.environ["SLOT_DAILY_CAP"] = "4"
        importlib.reload(slots)

    def test_busy_intervals_are_subtracted(self):
        now = datetime(2026, 9, 7, 0, 0, tzinfo=_IST)
        # Block 2026-09-08 10:00–13:00 entirely
        busy = [
            {
                "start": datetime(2026, 9, 8, 10, 0, tzinfo=_IST).isoformat(),
                "end":   datetime(2026, 9, 8, 13, 0, tzinfo=_IST).isoformat(),
            }
        ]
        got = slots.generate(duration_minutes=10, step_minutes=15, busy=busy, now=now)
        for s in got:
            start = datetime.fromisoformat(s.iso_start)
            # No slot on 2026-09-08
            self.assertNotEqual(start.date(), datetime(2026, 9, 8).date())


class TestDecodeRoundTrip(unittest.TestCase):
    def test_roundtrip_30min(self):
        now = datetime(2026, 9, 7, 0, 0, tzinfo=_IST)
        got = slots.generate(duration_minutes=30, step_minutes=30, now=now)
        self.assertTrue(got)
        start, end = slots.decode(got[0].id)
        self.assertEqual(start.isoformat()[:16], got[0].iso_start[:16])
        self.assertEqual((end - start).total_seconds(), 30 * 60)

    def test_decode_rejects_garbage(self):
        with self.assertRaises(ValueError):
            slots.decode("not_a_slot_id")

    def test_decode_encodes_duration(self):
        start, end = slots.decode("SLOT_20260908_1100_60m")
        self.assertEqual((end - start).total_seconds(), 60 * 60)


if __name__ == "__main__":
    unittest.main()
