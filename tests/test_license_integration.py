import unittest
from unittest import mock
from pathlib import Path

import license
from portable_auth import VerificationResult


class LicenseIntegrationTests(unittest.TestCase):
    def test_adapter_uses_signed_shared_manifest_and_one_day_grace(self):
        self.assertTrue(license.LICENSE_URL.endswith("ShipmentTrack_license.json"))
        self.assertEqual(44, len(license.PUBLIC_KEY_B64))
        self.assertEqual("authorization.cache", license.CACHE_FILE.name)
        verifier = license._make_verifier()
        self.assertEqual(24 * 60 * 60, verifier.config.offline_grace_seconds)

    def test_adapter_returns_neutral_errors_and_revalidates_session(self):
        denied = VerificationResult(False, "unavailable", license.NEUTRAL_ERROR)
        with mock.patch.object(license._verifier, "verify", return_value=denied):
            self.assertEqual(
                (False, "unavailable", license.NEUTRAL_ERROR),
                license.verify("machine"),
            )
        with mock.patch.object(
            license._verifier, "revalidate_session", return_value=denied
        ):
            self.assertEqual(
                (False, "unavailable", license.NEUTRAL_ERROR),
                license.revalidate_session("machine"),
            )

    def test_main_and_workflows_have_separate_verification_points(self):
        main_source = Path("main.py").read_text("utf-8")
        ui_source = Path("ui/main_window.py").read_text("utf-8")
        self.assertIn("license_mod.revalidate_session", main_source)
        self.assertEqual(2, ui_source.count("if not self._authorization_ready():"))
        self.assertIn("license_mod.revalidate_session", ui_source)


if __name__ == "__main__":
    unittest.main()
