import os
import tempfile
import base64
import unittest
from pathlib import Path
from unittest import mock

from modules import ups_module


class UpsOverlayTests(unittest.TestCase):
    def test_save_pdf_reprints_when_first_cdp_result_is_blank(self):
        with tempfile.TemporaryDirectory() as folder:
            cdp = mock.Mock()
            cdp.send.return_value = {"data": base64.b64encode(b"valid").decode("ascii")}
            page = mock.Mock()
            page.context.new_cdp_session.return_value = cdp
            with mock.patch.object(ups_module, "PDF_DIR", folder), \
                 mock.patch.object(ups_module, "close_ups_assistant"), \
                 mock.patch.object(ups_module, "expand_show_details", return_value=True), \
                 mock.patch.object(ups_module, "cleanup_before_pdf"), \
                 mock.patch.object(ups_module, "_ups_pdf_has_content", side_effect=[False, True]), \
                 mock.patch.object(ups_module.time, "sleep"):
                path = ups_module.save_ups_pdf(page, "1Z123")
            self.assertEqual(b"valid", Path(path).read_bytes())
            self.assertEqual(2, cdp.send.call_count)

    def test_pdf_content_check_rejects_blank_and_accepts_text_pdf(self):
        from io import BytesIO
        from pypdf import PdfWriter
        from types import SimpleNamespace

        blank = BytesIO()
        PdfWriter().write(blank)
        self.assertFalse(ups_module._ups_pdf_has_content(blank.getvalue()))
        with mock.patch(
            "pypdf.PdfReader",
            return_value=SimpleNamespace(pages=[SimpleNamespace(
                extract_text=lambda: "UPS Tracking Details Delivered", get=lambda key: {}
            )]),
        ):
            self.assertTrue(ups_module._ups_pdf_has_content(b"pdf"))

    def test_pdf_content_check_requires_current_tracking_number(self):
        from types import SimpleNamespace

        page = SimpleNamespace(
            extract_text=lambda: "UPS Tracking Details Delivered 1Z999",
            get=lambda _key: {},
        )
        with mock.patch(
            "pypdf.PdfReader", return_value=SimpleNamespace(pages=[page])
        ):
            self.assertFalse(ups_module._ups_pdf_has_content(b"pdf", "1Z123"))
            self.assertTrue(ups_module._ups_pdf_has_content(b"pdf", "1Z999"))

    def test_print_cleanup_targets_reported_left_bottom_overlays(self):
        page = mock.Mock()
        page.evaluate.return_value = ["this website uses cookies"]
        with mock.patch.object(ups_module, "close_cookie_popup"), \
             mock.patch.object(ups_module, "close_ups_assistant"):
            hidden = ups_module.hide_ups_print_overlays(page)
        self.assertEqual(["this website uses cookies"], hidden)
        css = page.add_style_tag.call_args.kwargs["content"].casefold()
        script = page.evaluate.call_args.args[0].casefold()
        self.assertIn("cookie-banner", css)
        self.assertIn("tracking number copied", script)
        self.assertIn("chat-button", script)

    @unittest.skipUnless(
        os.environ.get("SHIPMENTTRACK_LIVE_EDGE_TEST") == "1",
        "Run manually with installed Edge",
    )
    def test_generated_pdf_excludes_fixed_ups_overlays(self):
        from playwright.sync_api import sync_playwright
        from pypdf import PdfReader
        from units import detect_browser_path

        edge = detect_browser_path("edge")
        if not edge:
            self.skipTest("Edge unavailable")
        html = """<html><body>
          <main><h1>Tracking Details</h1><p>Delivered 1Z93375Y6776116978</p></main>
          <div class='cookie-banner' style='position:fixed;bottom:0'>
            This website uses cookies and analytics technologies
          </div>
          <div class='toast' style='position:fixed;bottom:40px'>Tracking number copied to clipboard</div>
          <button class='chat-button' aria-label='Open chat'>Chat</button>
        </body></html>"""
        with tempfile.TemporaryDirectory() as folder, sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=edge, headless=True)
            page = browser.new_page()
            page.set_content(html)
            ups_module.hide_ups_print_overlays(page)
            output = Path(folder) / "ups.pdf"
            page.pdf(path=str(output), format="A4", print_background=True)
            browser.close()
            text = "\n".join(p.extract_text() or "" for p in PdfReader(output).pages)
        self.assertIn("Delivered 1Z93375Y6776116978", text)
        self.assertNotIn("uses cookies", text)
        self.assertNotIn("copied to clipboard", text)


if __name__ == "__main__":
    unittest.main()
