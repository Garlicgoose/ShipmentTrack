import json
import tempfile
import unittest
from pathlib import Path

from modules.settings_store import (
    FilenameMapper,
    FilenameMappingRule,
    SettingsStore,
)
from units import detect_chrome_path, write_json


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.store = SettingsStore(
            settings_path=root / "settings.json",
            mappings_path=root / "filename_mappings.json",
            delivery_statuses_path=root / "delivery_status_mappings.json",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_settings_round_trip_keeps_known_keys_only(self):
        settings = self.store.load_settings()
        settings["tracking_output_dir"] = "D:/output"
        settings["fedex_api_secret"] = "fedex-secret"
        settings["tracking_ei_password"] = "ei-password"
        settings["unknown"] = "discard"
        self.store.save_settings(settings)
        loaded = self.store.load_settings()
        self.assertEqual("D:/output", loaded["tracking_output_dir"])
        self.assertEqual("fedex-secret", loaded["fedex_api_secret"])
        self.assertEqual("ei-password", loaded["tracking_ei_password"])
        self.assertNotIn("unknown", loaded)
        raw = self.store.settings_path.read_text("utf-8")
        self.assertNotIn("fedex-secret", raw)
        self.assertNotIn("ei-password", raw)

    def test_default_and_custom_mapping_round_trip(self):
        defaults = self.store.load_mappings()
        self.assertEqual(["光联", "MPO"], [rule.target_type for rule in defaults])

        rules = [
            FilenameMappingRule("澳车", "光联", "contains", "", "澳车"),
            FilenameMappingRule(r"^814S", "MPO", "regex", "", "814S"),
        ]
        self.store.save_mappings(rules)
        self.assertEqual(rules, self.store.load_mappings())

    def test_mapping_is_ordered_and_case_insensitive(self):
        mapper = FilenameMapper([
            FilenameMappingRule("special", "光联"),
            FilenameMappingRule("MPO", "MPO"),
        ])
        match = mapper.match("9.10 SPECIAL mpo.xlsx")
        self.assertTrue(match.matched)
        self.assertEqual("光联", match.target_type)
        self.assertEqual("special", match.display_type)
        self.assertEqual("special", match.pattern)

    def test_invalid_regex_and_unmatched_filename_are_visible(self):
        mapper = FilenameMapper([FilenameMappingRule("[", "MPO", "regex")])
        match = mapper.match("9.10 unknown.xlsx")
        self.assertFalse(match.matched)
        self.assertEqual("未识别", match.target_type)

    def test_json_write_is_valid_utf8(self):
        path = Path(self.temp_dir.name) / "atomic.json"
        write_json(path, {"类型": "光联"})
        self.assertEqual({"类型": "光联"}, json.loads(path.read_text("utf-8")))
        self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_chromium_detection_function_remains_available(self):
        self.assertIsInstance(detect_chrome_path(), str)

    def test_custom_delivery_statuses_round_trip(self):
        self.store.save_delivery_statuses({
            "EI": ["交给其他清关人"],
            "DSV": ["Cargo released", "Cargo released"],
        })
        self.assertEqual(
            {"EI": ["交给其他清关人"], "DSV": ["Cargo released"]},
            self.store.load_delivery_statuses(),
        )


if __name__ == "__main__":
    unittest.main()
