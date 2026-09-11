import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


class AppIconTests(unittest.TestCase):
    def test_demo_icon_assets_are_valid(self):
        svg = (ROOT / "assets" / "app_icon_demo.svg").read_text("utf-8")
        self.assertNotIn("<text", svg)
        self.assertGreaterEqual(svg.count("<path"), 2)
        self.assertIn("#16aaa0", svg)
        with Image.open(ROOT / "assets" / "app_icon.png") as image:
            self.assertEqual((256, 256), image.size)
        with Image.open(ROOT / "assets" / "app_icon.ico") as image:
            self.assertEqual("ICO", image.format)


if __name__ == "__main__":
    unittest.main()
