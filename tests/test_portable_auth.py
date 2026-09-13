import base64
import json
import tempfile
import unittest
from pathlib import Path
import urllib.error

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from portable_auth import (
    AuthConfig,
    SignedLicenseVerifier,
    canonical_payload,
    machine_digest,
)


class PortableAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.private_key = Ed25519PrivateKey.generate()
        public_raw = self.private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        self.public_b64 = base64.b64encode(public_raw).decode("ascii")
        self.now = [2_000_000_000.0]
        self.machine = "machine-a"

    def tearDown(self):
        self.temp_dir.cleanup()

    def document(self, enabled=True):
        payload = {
            "schema": 1,
            "revision": 1,
            "issued_at": "2026-09-13T00:00:00Z",
            "global_enabled": True,
            "machines": {machine_digest(self.machine): enabled},
        }
        signature = self.private_key.sign(canonical_payload(payload))
        return json.dumps({
            "payload": payload,
            "signature": base64.b64encode(signature).decode("ascii"),
        }).encode("utf-8")

    def verifier(self, fetcher):
        config = AuthConfig(
            "https://example.invalid/licenses.json",
            self.public_b64,
            self.root / "license.cache",
        )
        return SignedLicenseVerifier(
            config,
            fetcher=fetcher,
            clock=lambda: self.now[0],
            protector=lambda value: value[::-1],
            unprotector=lambda value: value[::-1],
        )

    def test_online_success_and_second_session_check(self):
        verifier = self.verifier(lambda *_: self.document())
        self.assertEqual("online", verifier.verify(self.machine).mode)
        self.assertTrue(verifier.config.cache_file.is_file())
        self.assertEqual("session", verifier.revalidate_session(self.machine).mode)
        self.assertFalse(verifier.revalidate_session("other-machine").ok)

    def test_network_failure_uses_cache_for_at_most_one_day(self):
        verifier = self.verifier(lambda *_: self.document())
        self.assertTrue(verifier.verify(self.machine).ok)
        verifier._fetcher = lambda *_: (_ for _ in ()).throw(
            urllib.error.URLError("offline")
        )
        self.now[0] += 24 * 60 * 60 - 1
        self.assertEqual("offline-cache", verifier.verify(self.machine).mode)
        self.now[0] += 2
        self.assertFalse(verifier.verify(self.machine).ok)

    def test_online_revocation_wins_over_existing_cache(self):
        verifier = self.verifier(lambda *_: self.document())
        self.assertTrue(verifier.verify(self.machine).ok)
        verifier._fetcher = lambda *_: self.document(enabled=False)
        result = verifier.verify(self.machine)
        self.assertFalse(result.ok)
        self.assertFalse(verifier.config.cache_file.exists())

    def test_tampered_document_never_falls_back_to_cache(self):
        verifier = self.verifier(lambda *_: self.document())
        self.assertTrue(verifier.verify(self.machine).ok)
        tampered = json.loads(self.document().decode("utf-8"))
        tampered["payload"]["machines"][machine_digest(self.machine)] = False
        verifier._fetcher = lambda *_: json.dumps(tampered).encode("utf-8")
        result = verifier.verify(self.machine)
        self.assertFalse(result.ok)
        self.assertEqual("invalid-response", result.mode)
        self.assertFalse(verifier.config.cache_file.exists())

    def test_machine_ids_are_hashed_for_the_public_manifest(self):
        digest = machine_digest("  Machine-A ")
        self.assertEqual(64, len(digest))
        self.assertEqual(digest, machine_digest("machine-a"))
        self.assertNotIn("machine", digest)


if __name__ == "__main__":
    unittest.main()
