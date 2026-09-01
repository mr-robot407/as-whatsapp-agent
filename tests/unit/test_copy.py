"""Unit tests for shared/copy.py — copy_library loader and substitution renderer."""

import unittest

import copy_library as copy_mod


class TestCopyLibrary(unittest.TestCase):
    def test_get_welcome_body(self):
        body = copy_mod.get("S1.00", "body")
        self.assertIn("Atelier Shreenu", body)
        self.assertIn("Gurugram", body)

    def test_get_welcome_footer(self):
        footer = copy_mod.get("S1.00", "footer")
        self.assertIn("Mon–Sat", footer)

    def test_missing_state_raises(self):
        with self.assertRaises(KeyError):
            copy_mod.get("S9.99")

    def test_missing_key_raises(self):
        with self.assertRaises(KeyError):
            copy_mod.get("S1.00", "does_not_exist")

    def test_render_with_substitutions(self):
        # S1.16 has a {slot_human} placeholder
        rendered = copy_mod.render("S1.16", {"slot_human": "Tuesday 11:00 IST"})
        self.assertIn("Tuesday 11:00 IST", rendered)
        self.assertNotIn("{slot_human}", rendered)

    def test_render_unfilled_placeholder_raises(self):
        with self.assertRaises(ValueError) as cm:
            copy_mod.render("S1.16", {})
        self.assertIn("slot_human", str(cm.exception))

    def test_render_no_placeholders_needed(self):
        # S1.10 has no placeholders — render with empty subs should succeed
        self.assertEqual(copy_mod.render("S1.10"), copy_mod.get("S1.10"))


if __name__ == "__main__":
    unittest.main()
