"""Unit tests for shared/link_builder.py."""

import os
import unittest
from urllib.parse import parse_qs, urlparse

os.environ["UNSUBSCRIBE_URL"] = "https://api.example.com/prod/unsubscribe"

from link_builder import unsubscribe, utm


class TestUtm(unittest.TestCase):
    def test_adds_defaults(self):
        result = utm("https://ateliershreenu.com/practice", campaign="S2.00")
        query = parse_qs(urlparse(result).query)
        self.assertEqual(query["utm_source"], ["whatsapp"])
        self.assertEqual(query["utm_medium"], ["whatsapp"])
        self.assertEqual(query["utm_campaign"], ["S2.00"])

    def test_preserves_existing_query(self):
        result = utm("https://x.com/y?foo=bar", campaign="S2.01")
        query = parse_qs(urlparse(result).query)
        self.assertEqual(query["foo"], ["bar"])
        self.assertEqual(query["utm_campaign"], ["S2.01"])

    def test_optional_content_and_term(self):
        result = utm("https://x.com", campaign="C", content="plate1", term="warm")
        query = parse_qs(urlparse(result).query)
        self.assertEqual(query["utm_content"], ["plate1"])
        self.assertEqual(query["utm_term"], ["warm"])


class TestUnsubscribe(unittest.TestCase):
    def test_includes_contact_id(self):
        url = unsubscribe("abc-123")
        self.assertIn("cid=abc-123", url)

    def test_includes_campaign_when_given(self):
        url = unsubscribe("abc-123", campaign="S2.00")
        self.assertIn("c=S2.00", url)


if __name__ == "__main__":
    unittest.main()
