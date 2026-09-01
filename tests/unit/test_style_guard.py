"""Unit tests for shared/style_guard.py — disallowed-phrase scanner."""

import json
import os
import tempfile
import unittest
from pathlib import Path


def _reload_with_phrases(phrases: list[str]):
    """Point style_guard at a temp file, then reload the module."""
    import importlib
    import sys

    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(phrases, fh)
    os.environ["CONFIG_DIR"] = str(Path(path).parent)
    # Rename to disallowed_phrases.json inside the same dir
    target = Path(path).parent / "disallowed_phrases.json"
    os.rename(path, target)
    if "style_guard" in sys.modules:
        importlib.reload(sys.modules["style_guard"])
    import style_guard  # noqa: F401
    return sys.modules["style_guard"], target


class TestStyleGuard(unittest.TestCase):
    def setUp(self):
        self.sg, self.tmp = _reload_with_phrases(["passionate", "commission"])

    def tearDown(self):
        try:
            os.remove(self.tmp)
        except FileNotFoundError:
            pass

    def test_clean_text(self):
        self.assertTrue(self.sg.is_clean("Warm welcome to Atelier Shreenu."))
        self.assertEqual(self.sg.scan("Warm welcome to Atelier Shreenu."), [])

    def test_flags_disallowed(self):
        self.assertFalse(self.sg.is_clean("We are passionate about design."))
        self.assertIn("passionate", self.sg.scan("We are passionate about design."))

    def test_case_insensitive(self):
        self.assertFalse(self.sg.is_clean("PASSIONATE craft"))

    def test_word_boundary(self):
        # "commissioning" should NOT match "commission"
        self.assertTrue(self.sg.is_clean("Commissioning brief attached"))

    def test_assert_clean_raises(self):
        with self.assertRaises(ValueError):
            self.sg.assert_clean("Our commission structure is transparent", state_id="S1.00")


if __name__ == "__main__":
    unittest.main()
