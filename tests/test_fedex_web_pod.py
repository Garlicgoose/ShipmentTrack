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

    def test_tracking_form_waits_for_dynamic_input_before_filling(self):
        box = mock.Mock()
        button = mock.Mock()
        page = mock.Mock()
        page.locator.return_value.first = box
        page.get_by_role.return_value = button
        button.count.return_value = 1
        button.first = button
        with mock.patch.object(web_pod, "_dismiss_cookie_banner"):
            web_pod._submit_tracking_form(page, "519470439011", 30_000)
        box.wait_for.assert_called_once_with(state="visible", timeout=30_000)
        box.fill.assert_called_once_with("519470439011")
        button.wait_for.assert_called_once_with(state="visible", timeout=10_000)
        button.click.assert_called_once_with(timeout=10_000)

    def test_print_cleanup_hides_cookie_and_chat_overlays(self):
        page = mock.Mock()
        with mock.patch.object(web_pod, "_dismiss_cookie_banner") as dismiss:
            web_pod._hide_print_overlays(page)
        dismiss.assert_called_once_with(page)
        css = page.add_style_tag.call_args.kwargs["content"]
        self.assertIn("usercentrics", css)
        self.assertIn("nuance", css)

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
