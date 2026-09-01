"""Unit tests for shared/templates.py — approval gate.

All templates in the registry currently have `meta_template_id=null` and
`dlt_template_id=null` so every template is BLOCKED. The tests assert that.
When approval IDs land, the tests here should still pass because blocking
is a property of null IDs, not of the specific template.
"""

import unittest

import templates


class TestApprovalGate(unittest.TestCase):
    def test_known_template_returns_entry(self):
        entry = templates.get("OUTREACH_HOOK")
        self.assertEqual(entry["category"], "MARKETING")
        self.assertEqual(entry["meta_template_name"], "atelier_shreenu_outreach_hook")

    def test_unknown_template_raises(self):
        with self.assertRaises(KeyError):
            templates.get("DOES_NOT_EXIST")

    def test_null_ids_block_send(self):
        # Registry ships with null ids → every template must be blocked.
        for key in [
            "OUTREACH_HOOK",
            "PROJECT_DISC_OFFER",
            "WALKTHROUGH_OFFER",
            "OOH_ACK",
            "IDLE_REMINDER",
            "BOOKING_REMINDER_24H",
            "BOOKING_REMINDER_2H_PARTNER",
        ]:
            self.assertFalse(templates.is_approved(key), f"{key} should not be approved yet")

    def test_assert_approved_raises_with_missing_fields(self):
        with self.assertRaises(RuntimeError) as cm:
            templates.assert_approved("OUTREACH_HOOK")
        msg = str(cm.exception)
        self.assertIn("meta_template_id", msg)
        self.assertIn("dlt_template_id", msg)


if __name__ == "__main__":
    unittest.main()
