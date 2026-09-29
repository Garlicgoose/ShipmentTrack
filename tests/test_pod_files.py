import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from modules.pod_files import move_pod_files, update_tracking_pod_paths


class PodFileTests(unittest.TestCase):
    def test_moves_by_carrier_and_never_overwrites_same_name(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first_dir = root / "input-a"
            second_dir = root / "input-b"
            first_dir.mkdir()
            second_dir.mkdir()
            first = first_dir / "123.pdf"
            second = second_dir / "123.pdf"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            result = move_pod_files(
                [("UPS", str(first)), ("UPS", str(second))], root / "archive"
            )
            targets = [Path(new) for _old, new in result.moved]
            self.assertEqual(2, len(targets))
            self.assertEqual({"123.pdf", "123 (1).pdf"}, {path.name for path in targets})
            self.assertTrue(all(path.parent.name == "UPS" for path in targets))
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())

    def test_updates_both_pod_columns_in_tracking_result(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tracking_result.xlsx"
            book = Workbook()
            book.active.append(("运单号", "POD文件", "POD详情文件"))
            book.active.append(("123", "C:/old/123.pdf", "C:/old/123+.pdf"))
            book.save(path)
            count = update_tracking_pod_paths(path, (
                ("C:/old/123.pdf", "D:/archive/UPS/123.pdf"),
                ("C:/old/123+.pdf", "D:/archive/FedEx/123+.pdf"),
            ))
            self.assertEqual(2, count)
            output = load_workbook(path, read_only=True)
            self.assertEqual("D:/archive/UPS/123.pdf", output.active["B2"].value)
            self.assertEqual("D:/archive/FedEx/123+.pdf", output.active["C2"].value)
            output.close()


if __name__ == "__main__":
    unittest.main()
