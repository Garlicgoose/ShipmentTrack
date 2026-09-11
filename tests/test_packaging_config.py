import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingConfigTests(unittest.TestCase):
    def test_build_does_not_copy_or_bundle_chromium(self):
        script = (ROOT / "build.ps1").read_text("utf-8-sig")
        self.assertNotIn("copy chromium", script.casefold())
        self.assertNotIn("chrome-win64\\*", script)
        self.assertIn("外接 Chromium", script)
        self.assertIn("delivery_status_mappings.json", script)

    def test_spec_includes_profile_asset_and_excludes_heavy_optional_modules(self):
        spec = (ROOT / "ShipmentTrack.spec").read_text("utf-8")
        self.assertIn("assets/github_avatar.jpg", spec)
        self.assertIn('"modules.dhl_module"', spec)
        for module in ("pandas", "scipy", "pyarrow", "PySide6.QtWebEngineWidgets"):
            self.assertIn(f'"{module}"', spec)
        self.assertIn('_foreign_icu = {"icuuc.dll", "icudt78.dll"}', spec)

    def test_default_mapping_file_is_valid(self):
        mappings = json.loads((ROOT / "filename_mappings.json").read_text("utf-8"))
        self.assertEqual(["光联", "MPO"], [item["target_type"] for item in mappings])
        delivery = json.loads(
            (ROOT / "delivery_status_mappings.json").read_text("utf-8")
        )
        self.assertEqual({"EI": [], "DSV": []}, delivery)

    def test_documentation_describes_external_chromium(self):
        readme = (ROOT / "README.md").read_text("utf-8")
        guide = (ROOT / "使用说明.txt").read_text("utf-8")
        self.assertIn("Chromium 外接", readme)
        self.assertIn("Chromium 不在程序目录中", guide)
        self.assertIn("合并检验表.xlsx", readme)
        self.assertIn("归总类别只允许光联或 MPO", readme)
        self.assertIn("FedEx 不抽查", readme)
        self.assertIn("delivery_status_mappings.json", readme)

    def test_packaged_app_has_offline_smoke_mode(self):
        main_source = (ROOT / "main.py").read_text("utf-8")
        self.assertIn('"--smoke-test"', main_source)
        self.assertIn('"modules.pod_audit"', main_source)
        self.assertIn('"modules.excel_reconcile"', main_source)

    def test_dependencies_are_pinned_without_pandas(self):
        requirements = (ROOT / "requirements.txt").read_text("utf-8")
        for package in ("PySide6", "playwright", "openpyxl", "requests", "pypdf", "pyinstaller"):
            self.assertRegex(requirements, rf"(?mi)^{package}==")
        self.assertNotRegex(requirements, r"(?mi)^pandas(?:==|>=)")

    def test_runtime_status_cache_is_not_committed(self):
        ignore = (ROOT / ".gitignore").read_text("utf-8")
        self.assertIn("modules/fedex_status_cache.json", ignore)


if __name__ == "__main__":
    unittest.main()
