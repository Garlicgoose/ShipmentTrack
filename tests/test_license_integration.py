import base64
import json
import tempfile
import unittest
import urllib.error
from unittest import mock
from pathlib import Path

import license
from authorization import AuthConfig, VerificationResult, canonical_payload, machine_digest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class LicenseIntegrationTests(unittest.TestCase):
    def _verifier_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        private = Ed25519PrivateKey.generate()
        public = base64.b64encode(private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )).decode("ascii")
        now = [2_000_000_000.0]
        machine = "machine-a"

        def document(revision=1, enabled=True):
            payload = {
                "schema": 1,
                "revision": revision,
                "issued_at": "2026-11-04T00:00:00Z",
                "global_enabled": True,
                "machines": {machine_digest(machine): enabled},
            }
            return json.dumps({
                "payload": payload,
                "signature": base64.b64encode(
                    private.sign(canonical_payload(payload))
                ).decode("ascii"),
            }).encode("utf-8")

        config = AuthConfig(
            "https://example.invalid/runtime.json",
            public,
            root / "authorization.cache",
            offline_grace_seconds=license.OFFLINE_GRACE_SECONDS,
            generic_error=license.NEUTRAL_ERROR,
        )
        verifier = license.ShipmentTrackVerifier(
            config,
            revision_file=root / "authorization.revision",
            fetcher=lambda *_: document(),
            clock=lambda: now[0],
            protector=lambda value: value[::-1],
            unprotector=lambda value: value[::-1],
        )
        return temporary, verifier, document, now, machine

    def test_adapter_uses_signed_shared_manifest_daily_check_and_seven_day_grace(self):
        self.assertTrue(license.LICENSE_URL.endswith("ShipmentTrack_license.json"))
        self.assertEqual(44, len(license.PUBLIC_KEY_B64))
        self.assertEqual("authorization.cache", license.CACHE_FILE.name)
        verifier = license._make_verifier()
        self.assertEqual(24 * 60 * 60, license.ONLINE_RECHECK_SECONDS)
        self.assertEqual(7 * 24 * 60 * 60, verifier.config.offline_grace_seconds)
        self.assertEqual("authorization.revision", verifier.revision_file.name)

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

    def test_machine_id_comes_from_shared_authorization_package(self):
        source = Path("license.py").read_text("utf-8")
        self.assertIn("from authorization import", source)
        self.assertIn("get_machine_id(DATA_DIR)", source)
        self.assertFalse(Path("machine_id.py").exists())
        self.assertFalse(Path("portable_auth.py").exists())

    def test_recent_success_skips_network_then_offline_cache_expires_after_seven_days(self):
        temporary, verifier, _document, now, machine = self._verifier_fixture()
        self.addCleanup(temporary.cleanup)
        self.assertEqual("online", verifier.verify_if_due(machine).mode)
        verifier._fetcher = lambda *_: (_ for _ in ()).throw(
            AssertionError("network should not be used before 24 hours")
        )
        now[0] += license.ONLINE_RECHECK_SECONDS - 1
        self.assertEqual("recent-cache", verifier.verify_if_due(machine).mode)
        verifier._fetcher = lambda *_: (_ for _ in ()).throw(
            urllib.error.URLError("offline")
        )
        now[0] += 2
        self.assertEqual("offline-cache", verifier.verify_if_due(machine).mode)
        now[0] += license.OFFLINE_GRACE_SECONDS
        self.assertFalse(verifier.verify_if_due(machine).ok)

    def test_signed_manifest_revision_cannot_roll_back(self):
        temporary, verifier, document, _now, machine = self._verifier_fixture()
        self.addCleanup(temporary.cleanup)
        verifier._fetcher = lambda *_: document(revision=2)
        self.assertTrue(verifier.verify_if_due(machine).ok)
        verifier._fetcher = lambda *_: document(revision=1)
        verifier.config.cache_file.unlink()
        result = verifier.verify_if_due(machine)
        self.assertFalse(result.ok)
        self.assertEqual("invalid-response", result.mode)


if __name__ == "__main__":
    unittest.main()
