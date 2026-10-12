"""ACTS regression: legacy MACIE A paid-query endpoint must fail closed.

Run: python -m unittest discover -s tests -p 'test_acts_macie_a_auth.py'
This test never calls external model providers and never requires API credentials.
"""
import os
import unittest
from unittest.mock import patch


class LegacyMacieAAuthenticationTests(unittest.TestCase):
    def test_missing_admin_key_denies_request(self):
        with patch.dict(os.environ, {"MACIE_ADMIN_KEY": "test-only-secret"}):
            from macie_web import app
            with app.test_client() as client:
                response = client.post(
                    "/macie/query",
                    json={"query": "ACTS unauthorized probe", "shell": "core"},
                )
            self.assertEqual(response.status_code, 401)

    def test_unconfigured_admin_key_fails_closed(self):
        with patch.dict(os.environ, {"MACIE_ADMIN_KEY": ""}):
            from macie_web import app
            with app.test_client() as client:
                response = client.post(
                    "/macie/query",
                    json={"query": "ACTS unauthorized probe", "shell": "core"},
                    headers={"X-Admin-Key": "arbitrary"},
                )
            self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
