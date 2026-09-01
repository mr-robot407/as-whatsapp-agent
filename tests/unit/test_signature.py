"""Unit tests for inbound/signature.py — X-Hub-Signature-256 verification."""

import hashlib
import hmac
import unittest

from signature import verify

_SECRET = "test-app-secret"
_BODY = b'{"entry":[{"id":"123"}]}'


def _sign(body: bytes, secret: str = _SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class TestVerify(unittest.TestCase):
    def test_valid_signature(self):
        self.assertTrue(verify(_SECRET, _BODY, _sign(_BODY)))

    def test_wrong_body(self):
        header = _sign(_BODY)
        tampered = _BODY + b"tampered"
        self.assertFalse(verify(_SECRET, tampered, header))

    def test_wrong_secret(self):
        self.assertFalse(verify("other-secret", _BODY, _sign(_BODY)))

    def test_missing_prefix(self):
        digest = hmac.new(_SECRET.encode(), _BODY, hashlib.sha256).hexdigest()
        self.assertFalse(verify(_SECRET, _BODY, digest))  # no "sha256=" prefix

    def test_empty_header(self):
        self.assertFalse(verify(_SECRET, _BODY, ""))

    def test_wrong_algorithm_prefix(self):
        digest = hmac.new(_SECRET.encode(), _BODY, hashlib.sha256).hexdigest()
        self.assertFalse(verify(_SECRET, _BODY, f"sha1={digest}"))


if __name__ == "__main__":
    unittest.main()
