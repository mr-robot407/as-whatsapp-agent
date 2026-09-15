"""Unit tests for shared/consent.py — human-takeover timing logic.

The DynamoDB writes are mocked; we only verify the deadline comparison in
`is_human_takeover_active()`, since a wrong branch here would either mute
the agent forever or fail to mute at all.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


class TestHumanTakeover(unittest.TestCase):
    def _load(self, item):
        # Reset module cache so the mocked boto3 client is picked up.
        for mod in ("consent", "crm"):
            sys.modules.pop(mod, None)
        with patch("boto3.resource") as res, patch("boto3.client"):
            table = MagicMock()
            table.get_item.return_value = {"Item": item}
            res.return_value.Table.return_value = table
            import consent
            return consent

    def test_no_field_returns_false(self):
        consent = self._load({})
        self.assertFalse(consent.is_human_takeover_active("cid"))

    def test_future_deadline_returns_true(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
        consent = self._load({"human_takeover_until": future})
        self.assertTrue(consent.is_human_takeover_active("cid"))

    def test_past_deadline_returns_false(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
        consent = self._load({"human_takeover_until": past})
        self.assertFalse(consent.is_human_takeover_active("cid"))

    def test_malformed_deadline_returns_false(self):
        consent = self._load({"human_takeover_until": "not-a-date"})
        self.assertFalse(consent.is_human_takeover_active("cid"))


if __name__ == "__main__":
    unittest.main()
