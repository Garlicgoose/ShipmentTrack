import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules import fedex_web_pod as web_pod


class FedExWebPodTests(unittest.TestCase):
    def test_fedex_pod_uses_english_site_and_thirty_second_warmup(self):
        self.assertIn("/en-cn/", web_pod.TRACKING_PAGE)
        self.assertIn("locale=en_CN", web_pod.TRACKING_RESULT_URL)
        with mock.patch.object(web_pod, "find_edge", return_value="msedge.exe"):
            session = web_pod.FedExEdgePodSession(mock.Mock(), "pod")
        self.assertEqual(30, session.warmup_seconds)

    def test_output_uses_main_and_plus_detail_names(self):
        main, detail = web_pod.output_paths(Path("pod"), "5194 7043-9011")
        self.assertEqual("519470439011.pdf", main.name)
        self.assertEqual("519470439011+.pdf", detail.name)

    def test_main_page_accepts_chinese_signed_result_without_delivered_word(self):
        visible = mock.Mock()
        visible.is_visible.return_value = True
        locator = mock.Mock()
        locator.count.return_value = 1
        locator.nth.return_value = visible
        page = mock.Mock()
        page.get_by_role.return_value = locator
        with mock.patch.object(
            web_pod,
            "_body_text",
            return_value="519470439011\n星期三\n签收人：S.TEAGUE\n查看更多详细信息",
        ):
            self.assertTrue(web_pod._main_page_ready(page, "519470439011"))

    def test_download_prints_main_then_clicked_detail_page(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(web_pod, "find_edge", return_value="msedge.exe"):
            session = web_pod.FedExEdgePodSession(
                mock.Mock(), temp_dir, minimize_browser=False
            )
            session.page = mock.Mock()
            session.context = mock.Mock()

            def write_pdf(_context, _page, destination):
                destination.write_bytes(b"%PDF-1.7\n" + b"x" * 1100)

            with mock.patch.object(session, "start"), \
                 mock.patch.object(session, "_load_main_page") as load, \
                 mock.patch.object(web_pod, "_body_text", return_value="main"), \
                 mock.patch.object(web_pod, "_open_details") as details, \
                 mock.patch.object(
                     web_pod, "_print_current_page", side_effect=write_pdf
                 ) as render:
                result = session.download("519470439011")

            self.assertTrue(result.ok)
            self.assertEqual("519470439011.pdf", Path(result.main_pdf).name)
            self.assertEqual("519470439011+.pdf", Path(result.detail_pdf).name)
            load.assert_called_once_with("519470439011")
            details.assert_called_once_with(
                session.page, "main", session.timeout_seconds, "519470439011"
            )
            self.assertEqual(2, render.call_count)

    def test_invalid_pdf_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.pdf"
            path.write_bytes(b"not a pdf")
            self.assertFalse(web_pod.is_valid_pdf(path))

    def test_tracking_form_types_with_real_keys_so_track_button_enables(self):
        box = mock.Mock()
        button = mock.Mock()
        button.is_enabled.return_value = True
        page = mock.Mock()
        page.locator.return_value.first = box
        page.get_by_role.return_value = button
        button.count.return_value = 1
        button.first = button
        with mock.patch.object(web_pod, "_dismiss_cookie_banner"):
            web_pod._submit_tracking_form(page, "519470439011", 30_000)
        box.wait_for.assert_called_once_with(state="visible", timeout=30_000)
        # fill() 会让 Track 按钮一直 disabled，必须用真实按键逐字输入
        box.press_sequentially.assert_called_once_with("519470439011", delay=60)
        box.fill.assert_not_called()
        # 页面有多个 TRACK 按钮，优先用回车（和真人操作一致）
        box.press.assert_any_call("Enter")

    def test_tracking_form_clicks_submit_button_inside_same_form(self):
        box = mock.Mock()
        box.press.side_effect = RuntimeError("没有 Enter 行为")
        box.evaluate.return_value = True
        page = mock.Mock()
        page.locator.return_value.first = box
        with mock.patch.object(web_pod, "_dismiss_cookie_banner"), \
             mock.patch.object(web_pod, "_track_button") as track_button:
            web_pod._submit_tracking_form(page, "519470439011", 30_000)
        self.assertIn("closest('form')", box.evaluate.call_args.args[0])
        track_button.assert_not_called()

    def test_tracking_form_reports_failure_when_submit_never_works(self):
        box = mock.Mock()
        box.press.side_effect = RuntimeError("没有 Enter 行为")
        box.evaluate.return_value = False
        button = mock.Mock()
        button.is_enabled.return_value = False
        page = mock.Mock()
        page.locator.return_value.first = box
        with mock.patch.object(web_pod, "_dismiss_cookie_banner"), \
             mock.patch.object(web_pod, "_track_button", return_value=button), \
             mock.patch.object(web_pod.time, "monotonic", side_effect=[0.0, 1.0, 99.0]):
            with self.assertRaisesRegex(web_pod.FedExWebPodError, "查询提交失败"):
                web_pod._submit_tracking_form(page, "519470439011", 5_000)
        button.click.assert_not_called()

    def test_load_main_page_prefers_form_and_skips_direct_url(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(web_pod, "find_edge", return_value="msedge.exe"):
            session = web_pod.FedExEdgePodSession(
                mock.Mock(), temp_dir, minimize_browser=False, warmup_seconds=0,
            )
            session.page = mock.Mock()
            session.context = mock.Mock()
            with mock.patch.object(web_pod, "_submit_tracking_form") as submit, \
                 mock.patch.object(web_pod, "_wait_for_main_page"), \
                 mock.patch.object(web_pod, "_is_system_error_page", return_value=False):
                session._load_main_page("519470439011")

        # CN 英文站表单查询优先（和人工一致，冷会话下直达链接会落到 system-error）
        submit.assert_called_once_with(session.page, "519470439011", session.timeout_ms)
        session.page.goto.assert_not_called()

    def test_load_main_page_retries_chinese_site_after_system_error(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(web_pod, "find_edge", return_value="msedge.exe"):
            session = web_pod.FedExEdgePodSession(
                mock.Mock(), temp_dir, minimize_browser=False, warmup_seconds=0,
            )
            session.page = mock.Mock()
            session.context = mock.Mock()
            goto_calls = []
            session.page.goto.side_effect = lambda url, **kwargs: goto_calls.append(url)

            attempts = {"direct": 0, "form": 0}

            def wait_main(page, number, seconds):
                if attempts["direct"] < 2:
                    attempts["direct"] += 1
                    raise web_pod.FedExWebPodError("等待 FedEx 查询结果主页超时")

            def submit(page, number, timeout_ms):
                attempts["form"] += 1
                raise web_pod.FedExWebPodError("FedEx 查询提交失败")

            with mock.patch.object(web_pod, "_submit_tracking_form", side_effect=submit), \
                 mock.patch.object(web_pod, "_wait_for_main_page", side_effect=wait_main), \
                 mock.patch.object(web_pod, "_is_system_error_page", return_value=True), \
                 mock.patch.object(web_pod, "_dismiss_cookie_banner"):
                with self.assertRaises(web_pod.FedExWebPodError) as ctx:
                    session._load_main_page("519470439011")

        self.assertIn("CN 英文站", str(ctx.exception))
        self.assertEqual(2, attempts["direct"])  # 直达链接重试 2 次
        self.assertEqual(1, attempts["form"])    # 再退回表单一次
        self.assertTrue(any("locale=en_CN" in url for url in goto_calls))
        self.assertTrue(any(url == web_pod.TRACKING_PAGE for url in goto_calls))
        session.context.add_cookies.assert_called()

    def test_print_cleanup_hides_cookie_and_chat_overlays(self):
        page = mock.Mock()
        with mock.patch.object(web_pod, "_dismiss_cookie_banner") as dismiss:
            web_pod._hide_print_overlays(page)
        dismiss.assert_called_once_with(page)
        css = page.add_style_tag.call_args.kwargs["content"]
        self.assertIn("usercentrics", css)
        self.assertIn("nuance", css)

    def test_session_selects_chinese_english_site_by_itself(self):
        """回归：程序要自己切到 CN 英文版，不能等用户手动选。"""
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(web_pod, "find_edge", return_value="msedge.exe"):
            session = web_pod.FedExEdgePodSession(
                mock.Mock(), temp_dir, minimize_browser=False, warmup_seconds=0,
            )
            session.page = mock.Mock()
            session.context = mock.Mock()
            session.page.evaluate.return_value = "en-cn"
            self.assertTrue(session._ensure_chinese_english_page())
            session.page.goto.assert_not_called()

    def test_session_reloads_when_site_is_not_chinese_english(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(web_pod, "find_edge", return_value="msedge.exe"):
            session = web_pod.FedExEdgePodSession(
                mock.Mock(), temp_dir, minimize_browser=False, warmup_seconds=0,
            )
            session.page = mock.Mock()
            session.context = mock.Mock()
            session.page.evaluate.side_effect = ["en-us", "en-cn"]
            with mock.patch.object(web_pod, "_dismiss_cookie_banner"):
                self.assertTrue(session._ensure_chinese_english_page())
            session.page.goto.assert_called_once()
            session.context.add_cookies.assert_called()  # 重设 fdx_locale=en_CN

    def test_session_minimizes_window_after_navigation(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(web_pod, "find_edge", return_value="msedge.exe"):
            session = web_pod.FedExEdgePodSession(
                mock.Mock(), temp_dir, minimize_browser=True, warmup_seconds=0,
            )
            session.page = mock.Mock()
            cdp = mock.Mock()
            session.context = mock.Mock()
            session.context.new_cdp_session.return_value = cdp
            cdp.send.return_value = {"windowId": 7}
            session.minimize_window()
            session.context.new_cdp_session.assert_called_once_with(session.page)
            self.assertEqual(
                mock.call("Browser.setWindowBounds",
                          {"windowId": 7, "bounds": {"windowState": "minimized"}}),
                cdp.send.call_args,
            )

    def test_details_prefers_control_in_current_tracking_card(self):
        wrong = mock.Mock()
        wrong.is_visible.return_value = True
        wrong.evaluate.return_value = False
        correct = mock.Mock()
        correct.is_visible.return_value = True
        correct.evaluate.return_value = True
        locator = mock.Mock()
        locator.count.return_value = 2
        locator.nth.side_effect = [wrong, correct]
        page = mock.Mock()
        page.get_by_role.return_value = locator
        with mock.patch.object(
            web_pod, "_body_text", return_value="Travel History"
        ):
            web_pod._open_details(page, "main", 15, "519470439011")
        wrong.click.assert_not_called()
        correct.click.assert_called_once_with(timeout=5_000)


if __name__ == "__main__":
    unittest.main()
