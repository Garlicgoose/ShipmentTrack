import json
import tempfile
import unittest
from pathlib import Path

from portable_auth import machine_digest, payload_allows_machine, verify_signed_manifest
from scripts.license_admin import generate_keys, sign_file


class LicenseAdminTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generates_key_pair_and_signs_legacy_machine_switches(self):
        private_path = self.root / "private.key"
        public_path = self.root / "public.key"
        public_b64 = generate_keys(private_path, public_path)
        machines_path = self.root / "machines.json"
        machines_path.write_text(
            json.dumps({"machine-a": True, "machine-b": False}),
            "utf-8",
        )
        output_path = self.root / "authorization.json"
        sign_file(
            private_path,
            machines_path,
            output_path,
            revision=7,
        )

        raw = output_path.read_bytes()
        payload = verify_signed_manifest(raw, public_b64)
        self.assertEqual(7, payload["revision"])
        self.assertTrue(payload_allows_machine(payload, "machine-a"))
        self.assertFalse(payload_allows_machine(payload, "machine-b"))
        self.assertIn(machine_digest("machine-a"), payload["machines"])
        self.assertNotIn("machine-a", output_path.read_text("utf-8"))

    def test_key_generation_refuses_to_overwrite_private_key(self):
        private_path = self.root / "private.key"
        public_path = self.root / "public.key"
        generate_keys(private_path, public_path)
        with self.assertRaises(FileExistsError):
            generate_keys(private_path, public_path)


if __name__ == "__main__":
    unittest.main()
