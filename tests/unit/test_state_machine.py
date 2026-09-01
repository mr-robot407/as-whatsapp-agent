"""Unit tests for shared/state_machine.py — STOP + RESTART keyword detection.

DDB-backed helpers (get_state / set_state) are not tested here — those need
integration tests with a real table or moto (out of scope for Phase 2a).
"""

import unittest

from state_machine import is_restart_keyword, is_stop_keyword


class TestStopKeyword(unittest.TestCase):
    def test_bare_stop(self):
        self.assertTrue(is_stop_keyword("STOP"))

    def test_lowercase_stop(self):
        self.assertTrue(is_stop_keyword("stop"))

    def test_stop_in_sentence(self):
        self.assertTrue(is_stop_keyword("Please STOP messaging me"))

    def test_multi_word_opt_out(self):
        self.assertTrue(is_stop_keyword("OPT OUT of these messages"))

    def test_unsubscribe(self):
        self.assertTrue(is_stop_keyword("UNSUBSCRIBE"))

    def test_dnd(self):
        self.assertTrue(is_stop_keyword("please put me on DND"))

    def test_non_stop_message(self):
        self.assertFalse(is_stop_keyword("I would like to design a home"))

    def test_partial_match_rejected(self):
        # "stopping" should not match "STOP"
        self.assertFalse(is_stop_keyword("just stopping by"))

    def test_empty_body(self):
        self.assertFalse(is_stop_keyword(""))

    def test_none_safe(self):
        self.assertFalse(is_stop_keyword(None))


class TestRestartKeyword(unittest.TestCase):
    def test_restart(self):
        self.assertTrue(is_restart_keyword("RESTART"))

    def test_restart_lowercase(self):
        self.assertTrue(is_restart_keyword("restart"))

    def test_menu(self):
        self.assertTrue(is_restart_keyword("MENU"))

    def test_restart_with_whitespace(self):
        self.assertTrue(is_restart_keyword("  RESET  "))

    def test_restart_in_sentence_rejected(self):
        # RESTART must be the whole message — accidental mentions in prose don't count
        self.assertFalse(is_restart_keyword("please restart the conversation"))


if __name__ == "__main__":
    unittest.main()
