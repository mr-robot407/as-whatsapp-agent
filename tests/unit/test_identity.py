"""Unit tests for shared/identity.py — phone normalisation and wa_id conversion."""

import unittest

from identity import e164_from_wa_id, normalise_e164, wa_id_from_e164


class TestNormaliseE164(unittest.TestCase):
    def test_already_e164(self):
        self.assertEqual(normalise_e164("+919560206195"), "+919560206195")

    def test_spaced_e164(self):
        self.assertEqual(normalise_e164("+91 95602 06195"), "+919560206195")

    def test_bare_country_code(self):
        self.assertEqual(normalise_e164("919560206195"), "+919560206195")

    def test_bare_10_digits(self):
        self.assertEqual(normalise_e164("9560206195"), "+919560206195")

    def test_custom_country_code(self):
        self.assertEqual(normalise_e164("2015551234", default_cc="1"), "+12015551234")

    def test_dashes_and_brackets(self):
        self.assertEqual(normalise_e164("(956) 020-6195"), "+919560206195")

    def test_empty(self):
        with self.assertRaises(ValueError):
            normalise_e164("")

    def test_no_digits(self):
        with self.assertRaises(ValueError):
            normalise_e164("phone")


class TestWaIdConversion(unittest.TestCase):
    def test_wa_id_from_e164(self):
        self.assertEqual(wa_id_from_e164("+919560206195"), "919560206195")

    def test_wa_id_rejects_no_plus(self):
        with self.assertRaises(ValueError):
            wa_id_from_e164("919560206195")

    def test_e164_from_wa_id(self):
        self.assertEqual(e164_from_wa_id("919560206195"), "+919560206195")

    def test_e164_from_wa_id_tolerates_leading_plus(self):
        self.assertEqual(e164_from_wa_id("+919560206195"), "+919560206195")


if __name__ == "__main__":
    unittest.main()
