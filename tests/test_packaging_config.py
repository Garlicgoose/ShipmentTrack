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

    def test_build_uses_data_folder_without_machine_id_utility(self):
        script = (ROOT / "build.ps1").read_text("utf-8-sig")
        self.assertNotIn("GetMachineId", script)
        self.assertNotIn('"machine_id.py"', script)
        self.assertIn('$dataDir = Join-Path $dist "data"', script)
        self.assertIn("-Destination $dataDir", script)

    def test_build_obfuscates_signed_authorization_core(self):
        script = (ROOT / "build.ps1").read_text("utf-8-sig")
        spec = (ROOT / "ShipmentTrack.spec").read_text("utf-8")
        self.assertIn("pyarmor gen -O $authObfuscated license.py portable_auth.py", script)
        self.assertIn('Path("build/auth_obfuscated").resolve()', spec)
        self.assertIn("pathex=[str(auth_obfuscated), \".\"]", spec)
        self.assertIn('_protected_modules = {"license", "portable_auth"}', spec)
        self.assertIn('str(auth_obfuscated / f"{name}.py")', spec)
        self.assertIn('"pyarmor_runtime_000000"', spec)

    def test_spec_includes_profile_asset_and_excludes_heavy_optional_modules(self):
        spec = (ROOT / "ShipmentTrack.spec").read_text("utf-8")
        self.assertIn("assets/github_avatar.jpg", spec)
        self.assertIn('"modules.dhl_module"', spec)
        for module in ("pandas", "scipy", "pyarrow", "PySide6.QtWebEngineWidgets"):
            self.assertIn(f'"{module}"', spec)
        self.assertNotIn('"cryptography"', spec)
        self.assertNotIn('"OpenSSL"', spec)
        self.assertIn('_foreign_icu = {"icuuc.dll", "icudt78.dll"}', spec)

    def test_default_mapping_file_is_valid(self):
        mappings = json.loads((ROOT / "filename_mappings.json").read_text("utf-8"))
        self.assertEqual(24, len(mappings))
        self.assertEqual({"光联", "MPO"}, {item["target_type"] for item in mappings})
        self.assertEqual("EI自提", mappings[0]["display_type"])
        self.assertEqual(["光联", "MPO"], [item["target_type"] for item in mappings[-2:]])
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
        self.assertIn("FedEx 检查运单号和", readme)
        self.assertIn("跟踪与 Excel 合并使用独立后台任务", readme)
        self.assertIn("默认 `Sheet1` 和空表不计入合并数量", readme)
        self.assertIn("delivery_status_mappings.json", readme)
        self.assertIn("data/settings.json", readme)
        self.assertIn("可任选一侧单独合并", readme)
        self.assertIn("`类型箱数` Sheet", readme)
        self.assertIn("至少一个文件夹", guide)
        self.assertIn("Ed25519 公钥", readme)
        self.assertIn("24 小时缓存", readme)
        self.assertIn("经过数字签名", guide)
        authorization = (ROOT / "docs" / "AUTHORIZATION.md").read_text("utf-8")
        self.assertIn("ed25519-private.key", authorization)
        self.assertIn("--revision 2", authorization)
        self.assertIn("PyArmor trial/non-profits", authorization)
        self.assertNotIn("GetMachineId.exe", readme)
        self.assertNotIn("GetMachineId.exe", guide)

    def test_packaged_app_has_offline_smoke_mode(self):
        main_source = (ROOT / "main.py").read_text("utf-8")
        self.assertIn('"--smoke-test"', main_source)
        self.assertIn('"modules.pod_audit"', main_source)
        self.assertIn('"modules.excel_reconcile"', main_source)

    def test_dependencies_are_pinned_without_pandas(self):
        requirements = (ROOT / "requirements.txt").read_text("utf-8")
        for package in (
            "PySide6", "playwright", "openpyxl", "requests", "pypdf",
            "cryptography", "pyarmor", "pyinstaller",
        ):
            self.assertRegex(requirements, rf"(?mi)^{package}==")
        self.assertNotRegex(requirements, r"(?mi)^pandas(?:==|>=)")

    def test_runtime_status_cache_is_not_committed(self):
        ignore = (ROOT / ".gitignore").read_text("utf-8")
        self.assertIn("data/", ignore)
        self.assertIn("modules/fedex_status_cache.json", ignore)


if __name__ == "__main__":
    unittest.main()
