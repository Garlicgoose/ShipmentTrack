import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules.real_browser import RealBrowserController


class RealBrowserControllerTests(unittest.TestCase):
    def test_launches_installed_browser_with_cdp_and_persistent_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "msedge.exe"
            executable.write_bytes(b"edge")
            profile = root / "profile"
            process = mock.Mock()
            process.wait.return_value = 0
            page = mock.Mock()
            context = mock.Mock(pages=[page])
            browser = mock.Mock(contexts=[context])
            playwright = mock.Mock()
            playwright.chromium.connect_over_cdp.return_value = browser
            with mock.patch("modules.real_browser._free_local_port", return_value=45678), \
                 mock.patch("modules.real_browser.wait_for_cdp") as wait, \
                 mock.patch("modules.real_browser.subprocess.Popen", return_value=process) as popen:
                controller = RealBrowserController(
                    playwright, executable, profile, browser_name="Microsoft Edge"
                )
                returned_context, returned_page = controller.start()
                controller.close()

            command = popen.call_args.args[0]
            self.assertIn("--remote-debugging-port=45678", command)
            self.assertIn(f"--user-data-dir={profile}", command)
            self.assertEqual(context, returned_context)
            self.assertEqual(page, returned_page)
            wait.assert_called_once_with("http://127.0.0.1:45678")
            browser.close.assert_called_once()

    def test_missing_executable_is_actionable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "chrome.exe"
            controller = RealBrowserController(mock.Mock(), missing, Path(temp_dir) / "profile")
            with self.assertRaisesRegex(FileNotFoundError, "找不到已安装"):
                controller.start()


if __name__ == "__main__":
    unittest.main()
