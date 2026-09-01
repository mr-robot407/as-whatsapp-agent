"""Unit tests for _parse_reference_id in src/funnel/app.py.

The reference_id encoding is the contract between the payment-link creator
(state handlers) and the Razorpay webhook consumer (funnel). If the format
drifts, payments capture but bookings don't confirm — so this is tested
tightly.
"""

import os
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(_REPO, "src", "funnel"))

from app import _parse_reference_id


class TestParseReferenceId(unittest.TestCase):
    def test_project_discussion_shape(self):
        got = _parse_reference_id("pd-11111111-2222-3333-4444-555555555555-202609081100")
        self.assertEqual(got, ("pd", "11111111-2222-3333-4444-555555555555", "202609081100"))

    def test_walkthrough_shape(self):
        got = _parse_reference_id("sw-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee-202609121030")
        self.assertEqual(got, ("sw", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "202609121030"))

    def test_rejects_unknown_prefix(self):
        self.assertIsNone(_parse_reference_id("xy-11111111-2222-3333-4444-555555555555-202609081100"))

    def test_rejects_missing_slot(self):
        self.assertIsNone(_parse_reference_id("pd-11111111-2222-3333-4444-555555555555"))

    def test_rejects_bad_contact_id(self):
        self.assertIsNone(_parse_reference_id("pd-not-a-uuid-202609081100"))

    def test_rejects_empty(self):
        self.assertIsNone(_parse_reference_id(""))


if __name__ == "__main__":
    unittest.main()
