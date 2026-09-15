"""Unit tests for config/kb.json — structural sanity + hard-rule assertions.

The KB is fed to the LLM as a cache-marked static prefix; a malformed or
inconsistent KB silently corrupts every reply. These tests are cheap
guardrails against that class of failure.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


_KB_PATH = Path(__file__).parent.parent.parent / "config" / "kb.json"


class TestKbStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = json.loads(_KB_PATH.read_text())

    def test_top_level_keys_present(self):
        for key in ("_meta", "studio", "process", "fees", "vendor_intake",
                    "career_intake", "press_intake", "compliance", "faqs",
                    "escalation"):
            self.assertIn(key, self.kb, f"missing top-level key: {key}")

    def test_partner_number_not_quotable(self):
        # The number IS allowed in _meta.hard_rules (the LLM must know what to
        # refuse). It must NOT appear in any section the LLM could quote from:
        # studio, process, fees, vendor_intake, career_intake, press_intake,
        # compliance, faqs, escalation.
        for section_key in ("studio", "process", "fees", "vendor_intake",
                            "career_intake", "press_intake", "compliance",
                            "faqs", "escalation"):
            section_text = json.dumps(self.kb[section_key])
            for forbidden in ("9560107193", "+91 95601 07193", "95601 07193"):
                self.assertNotIn(
                    forbidden, section_text,
                    f"partner direct number leaked into KB section {section_key!r}: {forbidden}",
                )

    def test_fees_match_pre_signing_schedule(self):
        self.assertEqual(self.kb["fees"]["project_discussion"]["amount_inr"], 1770)
        self.assertEqual(self.kb["fees"]["walkthrough_ncr"]["amount_inr"], 3540)
        self.assertEqual(self.kb["fees"]["walkthrough_outside_ncr"]["amount_inr"], 7080)
        self.assertEqual(self.kb["fees"]["discovery_call"]["amount_inr"], 0)

    def test_hard_rules_include_third_person(self):
        rules = " ".join(self.kb["_meta"]["hard_rules"]).lower()
        self.assertIn("third person", rules)
        self.assertIn("emoji", rules)
        self.assertIn("+91 95601 07193", rules)

    def test_faqs_have_answer_and_topics(self):
        self.assertGreater(len(self.kb["faqs"]), 5)
        for entry in self.kb["faqs"]:
            self.assertIn("q", entry)
            self.assertIn("a", entry)
            self.assertIsInstance(entry.get("topics", []), list)
            self.assertGreater(len(entry["a"]), 20, f"answer too short: {entry['q']}")

    def test_vendor_categories_align_with_state_handler(self):
        cats = {c["id"] for c in self.kb["vendor_intake"]["categories"]}
        # Must match src/shared/states/vendor.py _S120A_ITEMS suffixes
        expected = {"MATERIALS", "FURNITURE", "CONTRACTOR", "CONSULTANT", "TECH", "OTHER"}
        self.assertEqual(cats, expected)


if __name__ == "__main__":
    unittest.main()
