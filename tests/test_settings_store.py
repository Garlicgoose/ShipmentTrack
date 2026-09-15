import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules.settings_store import (
    FilenameMapper,
    FilenameMappingRule,
    SettingsStore,
)
from units import detect_browser_path, detect_chrome_path, write_json


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
        self.assertEqual(24, len(defaults))
        self.assertEqual("MPO国外EI自提", defaults[0].pattern)
        self.assertEqual("EI自提", defaults[0].display_type)
        self.assertEqual("MPO", defaults[0].target_type)
        self.assertEqual(["光联", "MPO"], [rule.target_type for rule in defaults[-2:]])
        self.assertEqual("光联", FilenameMapper(defaults).match("9.4 814T出货资料.xlsx").target_type)
        self.assertEqual("第一车", FilenameMapper(defaults).match("9.10国外第一车出货资料.xlsx").display_type)

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

    def test_specific_mapping_beats_generic_mpo_fallback(self):
        mapper = FilenameMapper([
            FilenameMappingRule("MPO", "MPO", display_type="MPO"),
            FilenameMappingRule("MPO国外DSV自提", "MPO", display_type="DSV自提"),
            FilenameMappingRule("MPO国外Omni自提", "MPO", display_type="Omni自提"),
        ])
        dsv = mapper.match("9.9MPO国外DSV自提出货—陆运出货资料.xlsx")
        omni = mapper.match("9.10MPO国外Omni自提出货—空运(重庆)出货资料.xlsx")
        self.assertEqual("DSV自提", dsv.display_type)
        self.assertEqual("Omni自提", omni.display_type)
        self.assertEqual("MPO国外DSV自提", dsv.pattern)
        self.assertEqual("MPO国外Omni自提", omni.pattern)

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

    def test_real_browser_settings_and_detection(self):
        settings = self.store.load_settings()
        self.assertEqual("edge", settings["browser_type"])
        self.assertEqual("", settings["browser_path"])
        with mock.patch("units.browser_candidates", return_value=[Path(self.temp_dir.name) / "missing.exe"]):
            self.assertEqual("", detect_browser_path("edge"))

    def test_legacy_installed_browser_path_is_migrated(self):
        self.store.settings_path.write_text(json.dumps({
            "chrome_path": r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        }), encoding="utf-8")
        settings = self.store.load_settings()
        self.assertEqual("edge", settings["browser_type"])
        self.assertTrue(settings["browser_path"].endswith("msedge.exe"))

    def test_custom_delivery_statuses_round_trip(self):
        self.store.save_delivery_statuses({
            "EI": ["交给其他清关人"],
            "DSV": ["Cargo released", "Cargo released"],
        })
        self.assertEqual(
            {"DHL": [], "EI": ["交给其他清关人"], "DSV": ["Cargo released"]},
            self.store.load_delivery_statuses(),
        )

    def test_custom_store_paths_keep_status_mapping_in_same_directory(self):
        self.assertEqual(
            self.store.settings_path.parent / "delivery_status_mappings.json",
            self.store.delivery_statuses_path,
        )

    def test_default_store_uses_data_folder_and_migrates_legacy_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "settings.json").write_text(
                json.dumps({"tracking_output_dir": "D:/legacy"}),
                encoding="utf-8",
            )
            (root / "filename_mappings.json").write_text(
                json.dumps([{"pattern": "旧规则", "target_type": "MPO"}]),
                encoding="utf-8",
            )
            (root / "delivery_status_mappings.json").write_text(
                json.dumps({"EI": ["Legacy status"], "DSV": []}),
                encoding="utf-8",
            )
            with mock.patch("modules.settings_store.get_base_path", return_value=root), \
                 mock.patch("modules.settings_store.get_data_path", return_value=root / "data"):
                store = SettingsStore()
                self.assertEqual("D:/legacy", store.load_settings()["tracking_output_dir"])
                self.assertEqual("旧规则", store.load_mappings()[0].pattern)
                self.assertEqual(["Legacy status"], store.load_delivery_statuses()["EI"])

            self.assertEqual(root / "data" / "settings.json", store.settings_path)
            self.assertTrue((root / "data" / "settings.json").is_file())
            self.assertTrue((root / "data" / "filename_mappings.json").is_file())
            self.assertTrue((root / "data" / "delivery_status_mappings.json").is_file())


if __name__ == "__main__":
    unittest.main()
