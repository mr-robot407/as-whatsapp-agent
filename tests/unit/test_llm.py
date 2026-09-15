"""Unit tests for shared/llm.py — classifier + reply generator + guardrails.

The Anthropic SDK is stubbed with a fake client so the tests never make real
API calls. We verify:
  - `is_enabled()` respects the SSM flag AND the API key init state.
  - `classify_intent()` normalises and validates the model output.
  - `generate_reply()` extracts JSON, runs style_guard, blocks forbidden
    content, and returns None on escalate/failure.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


def _fake_config_dir() -> Path:
    d = Path(tempfile.mkdtemp())
    (d / "disallowed_phrases.json").write_text(json.dumps(["passionate", "commission"]))
    (d / "kb.json").write_text(json.dumps({"fees": {"project_discussion": {"amount_inr": 1770}}}))
    (d / "copy_library.json").write_text(json.dumps({"X.FALLBACK": {"body": "Fallback"}}))
    return d


class _FakeMessages:
    def __init__(self, output: str):
        self._output = output

    def create(self, **kwargs):  # noqa: ARG002
        return SimpleNamespace(content=[SimpleNamespace(text=self._output)])


class _FakeAnthropic:
    def __init__(self, output: str):
        self.messages = _FakeMessages(output)


def _load_llm(output: str, *, api_key: str = "sk-fake", llm_enabled: bool = True):
    """Fresh-import llm with a stubbed Anthropic client + SSM flag."""
    cfg = _fake_config_dir()
    os.environ["CONFIG_DIR"] = str(cfg)
    os.environ["ANTHROPIC_API_KEY"] = api_key
    for mod in ("llm", "style_guard"):
        if mod in sys.modules:
            del sys.modules[mod]
    import llm as llm_mod
    llm_mod._anthropic = _FakeAnthropic(output) if api_key else None
    llm_mod._llm_enabled_cache = llm_enabled
    llm_mod._llm_enabled_cache_ts = 10**12  # far future, skip SSM
    importlib.reload(sys.modules["style_guard"])
    return llm_mod


class TestClassifyIntent(unittest.TestCase):
    def test_returns_label(self):
        llm = _load_llm("FAQ")
        self.assertEqual(llm.classify_intent("What is the discovery call?"), "FAQ")

    def test_normalises_case_and_spaces(self):
        llm = _load_llm(" personhood query ")
        self.assertEqual(llm.classify_intent("are you a bot"), "PERSONHOOD_QUERY")

    def test_unknown_label_falls_back(self):
        llm = _load_llm("MAYBE_LATER")
        self.assertEqual(llm.classify_intent("hmm"), "UNSURE")

    def test_disabled_returns_unsure(self):
        llm = _load_llm("FAQ", api_key="", llm_enabled=False)
        self.assertEqual(llm.classify_intent("What is the discovery call?"), "UNSURE")


class TestGenerateReply(unittest.TestCase):
    def test_clean_reply_passes(self):
        llm = _load_llm(json.dumps({"reply": "The studio takes on residential projects.", "escalate": False}))
        out = llm.generate_reply("Do you do homes?", current_state="S1.20b", contact_kind="client")
        self.assertEqual(out, "The studio takes on residential projects.")

    def test_escalate_flag_returns_none(self):
        llm = _load_llm(json.dumps({"reply": "", "escalate": True}))
        self.assertIsNone(llm.generate_reply("give me Shreenu's number", current_state="S1.14"))

    def test_forbidden_number_blocked(self):
        # Even if the model somehow outputs the partner's number, the module drops it.
        llm = _load_llm(json.dumps({"reply": "Call +91 95601 07193.", "escalate": False}))
        self.assertIsNone(llm.generate_reply("give partner number", current_state="S1.14"))

    def test_style_guard_violation_blocked(self):
        llm = _load_llm(json.dumps({"reply": "The studio is passionate about design.", "escalate": False}))
        self.assertIsNone(llm.generate_reply("what motivates you", current_state="S1.14"))

    def test_non_json_output_returns_none(self):
        llm = _load_llm("this is not JSON at all")
        self.assertIsNone(llm.generate_reply("hi", current_state="S1.00"))

    def test_disabled_returns_none(self):
        llm = _load_llm("{}", api_key="", llm_enabled=False)
        self.assertIsNone(llm.generate_reply("hi", current_state="S1.00"))


if __name__ == "__main__":
    unittest.main()
