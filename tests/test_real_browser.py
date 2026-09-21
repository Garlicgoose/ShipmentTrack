import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from modules.real_browser import (
    TARGET_ACCEPT_LANGUAGE,
    RealBrowserController,
    page_is_chinese,
)
from modules.tracking_utils import TRACKING_CARRIER_CONFIG, TrackingCarrierSession


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

            command = popen.call_args_list[0].args[0]
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

    def test_launch_forces_english_language(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "msedge.exe"
            executable.write_bytes(b"edge")
            process = mock.Mock()
            page = mock.Mock()
            context = mock.Mock(pages=[page])
            browser = mock.Mock(contexts=[context])
            playwright = mock.Mock()
            playwright.chromium.connect_over_cdp.return_value = browser
            with mock.patch("modules.real_browser._free_local_port", return_value=45678), \
                 mock.patch("modules.real_browser.wait_for_cdp"), \
                 mock.patch("modules.real_browser.subprocess.Popen", return_value=process) as popen:
                controller = RealBrowserController(
                    playwright, executable, root / "profile", browser_name="Microsoft Edge"
                )
                controller.start()

            command = popen.call_args.args[0]
            self.assertIn("--lang=en-US", command)
            self.assertIn(f"--accept-lang={TARGET_ACCEPT_LANGUAGE}", command)
            # DSV / EI 靠请求头和 navigator.language 判断语言，两层都要锁
            context.set_extra_http_headers.assert_called_once_with(
                {"Accept-Language": TARGET_ACCEPT_LANGUAGE}
            )
            self.assertEqual(1, context.add_init_script.call_count)
            page.add_init_script.assert_called_once()

    def test_launch_minimizes_and_avoids_session_restore_windows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "msedge.exe"
            executable.write_bytes(b"edge")
            page = mock.Mock()
            page.context = mock.Mock()
            context = mock.Mock(pages=[page])
            browser = mock.Mock(contexts=[context])
            playwright = mock.Mock()
            playwright.chromium.connect_over_cdp.return_value = browser
            with mock.patch("modules.real_browser._free_local_port", return_value=45678), \
                 mock.patch("modules.real_browser.wait_for_cdp"), \
                 mock.patch("modules.real_browser.subprocess.Popen", return_value=mock.Mock()) as popen, \
                 mock.patch.object(RealBrowserController, "minimize_windows", return_value=1) as minimize:
                controller = RealBrowserController(
                    playwright, executable, root / "profile",
                    browser_name="Microsoft Edge", minimize=True,
                )
                controller.start()

            command = popen.call_args.args[0]
            # 多重保险：启动参数自带最小化 + 不恢复上次会话（否则会冒出没最小化的旧窗口）
            self.assertIn("--start-minimized", command)
            self.assertIn("--hide-crash-restore-bubble", command)
            self.assertIn("--disable-session-crashed-bubble", command)
            minimize.assert_called_once()

    def test_prepare_windows_closes_extra_pages(self):
        extra_one, extra_two = mock.Mock(), mock.Mock()
        page = mock.Mock()
        context = mock.Mock(pages=[page, extra_one, extra_two])
        controller = RealBrowserController.__new__(RealBrowserController)
        controller.context = context
        controller.page = page
        controller.minimize = False
        controller.log = lambda _message: None
        controller._prepare_windows()
        extra_one.close.assert_called_once()
        extra_two.close.assert_called_once()
        page.close.assert_not_called()

    def test_close_terminates_process_tree(self):
        process = mock.Mock()
        process.poll.return_value = None
        controller = RealBrowserController.__new__(RealBrowserController)
        controller.browser = mock.Mock()
        controller.process = process
        controller.page = controller.context = None
        with mock.patch("modules.real_browser._terminate_process_tree") as terminate:
            controller.close()
        terminate.assert_called_once_with(process)
        self.assertIsNone(controller.process)

    def test_close_all_launched_browsers_kills_everything(self):
        from modules import real_browser

        first, second = mock.Mock(), mock.Mock()
        real_browser._LAUNCHED_PROCESSES.update({first, second})
        with mock.patch("modules.real_browser._terminate_process_tree") as terminate:
            real_browser.close_all_launched_browsers()
        self.assertEqual(2, terminate.call_count)
        self.assertEqual(set(), real_browser._LAUNCHED_PROCESSES)


class EnglishPageTests(unittest.TestCase):
    def make_controller(self, temp_dir):
        executable = Path(temp_dir) / "msedge.exe"
        executable.write_bytes(b"edge")
        return RealBrowserController(
            mock.Mock(), executable, Path(temp_dir) / "profile",
            log_func=lambda _message: None,
        )

    def test_page_is_chinese_uses_html_lang_and_body_text(self):
        page = mock.Mock()
        page.evaluate.side_effect = ["zh-CN"]
        self.assertTrue(page_is_chinese(page))

        page = mock.Mock()
        page.evaluate.side_effect = ["en", 60]
        self.assertTrue(page_is_chinese(page))

        page = mock.Mock()
        page.evaluate.side_effect = ["en", 3]
        self.assertFalse(page_is_chinese(page))

        page = mock.Mock()
        page.evaluate.side_effect = RuntimeError("页面已跳转")
        self.assertFalse(page_is_chinese(page))

    def test_ensure_english_page_leaves_english_pages_alone(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = self.make_controller(temp_dir)
            page = mock.Mock()
            page.evaluate.side_effect = ["en", 2]
            self.assertFalse(controller.ensure_english_page(page))
            page.locator.assert_not_called()

    def test_ensure_english_page_clicks_english_option_when_chinese(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = self.make_controller(temp_dir)
            page = mock.Mock()
            page.evaluate.side_effect = ["zh-CN", "en", 0]
            option = mock.Mock()
            option.is_visible.return_value = True
            page.locator.return_value.first = option
            self.assertTrue(controller.ensure_english_page(page))
            option.click.assert_called_once()

    def test_dsv_and_ei_are_configured_to_force_english(self):
        self.assertTrue(TRACKING_CARRIER_CONFIG["DSV"].get("force_english"))
        self.assertTrue(TRACKING_CARRIER_CONFIG["EI"].get("force_english"))
        self.assertFalse(TRACKING_CARRIER_CONFIG["DHL"].get("force_english"))
        self.assertFalse(TRACKING_CARRIER_CONFIG["UPS"].get("force_english"))

    def test_session_switches_dsv_page_to_english_after_warmup(self):
        fake_module = SimpleNamespace(
            PDF_DIR="output/pdf/DSV",
            warm_up_dsv=mock.Mock(),
            remove_overlays=mock.Mock(),
            query_dsv_one=mock.Mock(),
        )
        controller = mock.Mock()
        controller.start.return_value = (mock.Mock(), mock.Mock())
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "msedge.exe"
            executable.write_bytes(b"edge")
            with mock.patch("modules.tracking_utils.importlib", SimpleNamespace(import_module=lambda _name: fake_module)), \
                 mock.patch("modules.tracking_utils.RealBrowserController", return_value=controller), \
                 mock.patch("modules.tracking_utils.detect_browser_path", return_value=str(executable)):
                session = TrackingCarrierSession(
                    mock.Mock(), "DSV", Path(temp_dir),
                    ei_login_enabled=False, ei_email="", ei_password="",
                    browser_path=str(executable),
                )
                session.start()

        fake_module.warm_up_dsv.assert_called_once()
        controller.ensure_english_page.assert_called_once()


if __name__ == "__main__":
    unittest.main()
