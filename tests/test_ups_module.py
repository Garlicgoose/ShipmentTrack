import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules import ups_module


class UpsOverlayTests(unittest.TestCase):
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
