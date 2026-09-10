from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "ui-demo.html"


class DemoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.pages = set()
        self.buttons = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if attrs.get("data-page"):
            self.pages.add(attrs["data-page"])
        if tag == "button":
            self.buttons += 1


class UiDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = DEMO.read_text(encoding="utf-8")
        cls.parser = DemoParser()
        cls.parser.feed(cls.html)

    def test_demo_has_three_requested_workspaces(self):
        self.assertEqual({"tracking", "inspect", "droplist"}, self.parser.pages)

    def test_demo_has_core_interaction_targets(self):
        expected = {
            "runButton", "progressBar", "progressText", "shipmentRows",
            "drawer", "backdrop", "toast", "inspectResult", "droplistResult",
        }
        self.assertTrue(expected.issubset(self.parser.ids))
        self.assertGreaterEqual(self.parser.buttons, 10)

    def test_demo_uses_mock_data_and_no_remote_assets(self):
        self.assertIn("模拟数据", self.html)
        self.assertNotRegex(self.html, r"<(?:script|link)[^>]+(?:src|href)=[\"']https?://")

    def test_inline_script_is_present(self):
        scripts = re.findall(r"<script>(.*?)</script>", self.html, flags=re.S)
        self.assertEqual(1, len(scripts))
        self.assertIn("addEventListener", scripts[0])


if __name__ == "__main__":
    unittest.main()
