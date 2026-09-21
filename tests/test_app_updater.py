import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules import app_updater


class _Response:
    def __init__(self, content):
        self.content = content
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        if size == -1:
            return self.content
        chunk = self.content[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


class AppUpdaterTests(unittest.TestCase):
    def manifest(self, content=b"MZ" + b"x" * 2048, version="1.2"):
        return {
            "version": version,
            "exe_url": "https://github.com/Garlicgoose/ShipmentTrack/raw/main/release/Shipment%20Track.exe",
            "sha256": hashlib.sha256(content).hexdigest(),
            "notes": ["修复测试"],
        }

    def test_version_comparison_is_numeric(self):
        self.assertTrue(app_updater.is_newer_version("1.10", "1.9"))
        self.assertFalse(app_updater.is_newer_version("1.1.0", "1.1"))

    def test_manifest_requires_https_github_and_sha256(self):
        valid = app_updater.validate_manifest(self.manifest())
        self.assertEqual("1.2", valid["version"])
        invalid = self.manifest()
        invalid["exe_url"] = "http://example.com/app.exe"
        with self.assertRaisesRegex(app_updater.UpdateError, "不受信任"):
            app_updater.validate_manifest(invalid)

    def test_fetch_only_returns_newer_release(self):
        document = json.dumps(self.manifest(version="1.1")).encode()
        with mock.patch("modules.app_updater.urlopen", return_value=_Response(document)):
            self.assertIsNone(app_updater.fetch_update_manifest())

    def test_download_verifies_hash_and_windows_header(self):
        content = b"MZ" + b"x" * 2048
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch("modules.app_updater.get_data_path", return_value=Path(temp_dir)), \
             mock.patch("modules.app_updater.urlopen", return_value=_Response(content)):
            path = app_updater.download_update(self.manifest(content))
            self.assertEqual(content, path.read_bytes())

    def test_download_rejects_hash_mismatch(self):
        content = b"MZ" + b"x" * 2048
        manifest = self.manifest(content)
        manifest["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch("modules.app_updater.get_data_path", return_value=Path(temp_dir)), \
             mock.patch("modules.app_updater.urlopen", return_value=_Response(content)):
            with self.assertRaisesRegex(app_updater.UpdateError, "校验失败"):
                app_updater.download_update(manifest)

    def test_stage_update_writes_wait_replace_and_restart_helper(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "new.exe"
            target = root / "Shipment Track.exe"
            source.write_bytes(b"MZnew")
            target.write_bytes(b"MZold")
            with mock.patch("modules.app_updater.get_data_path", return_value=root), \
                 mock.patch("modules.app_updater.subprocess.Popen") as popen:
                helper = app_updater.stage_update(source, target)
            script = helper.read_text("utf-8-sig")
            self.assertIn("Wait-Process", script)
            self.assertIn("Copy-Item -LiteralPath $source -Destination $target -Force", script)
            self.assertIn("Start-Process -FilePath $target", script)
            self.assertIn(str(target), script)
            popen.assert_called_once()

    def test_in_app_changelog_keeps_only_the_four_v12_items(self):
        """用户指定：1.2 的更新内容只保留这四条（其余条目从更新日志删除）。"""
        self.assertEqual(
            (
                "增加 POD 抽查比例",
                "移除已失效的 FedEx 签名和签收人字段",
                "FedEx POD 改用真实浏览器（Edge）查询网页",
                "修复 FedEx API 相关的 bug",
            ),
            app_updater.CURRENT_CHANGELOG,
        )

    def test_changelog_file_matches_release_notes(self):
        changelog = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text("utf-8")
        section = changelog.split("## 1.2")[1].split("## 1.1")[0]
        for note in app_updater.CURRENT_CHANGELOG:
            self.assertIn(note, section)
        self.assertNotIn("设置页拆成四个标签页", section)


if __name__ == "__main__":
    unittest.main()
