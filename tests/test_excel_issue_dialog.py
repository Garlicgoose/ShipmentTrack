import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.excel_issue_dialog import ExcelIssuesDialog, DroplistSheetCheckDialog


class ExcelIssueDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_shipment_issue_dialog_shows_both_sides_and_sheet_sources(self):
        issue = SimpleNamespace(
            date="2026/10/19",
            target_type="MPO",
            shipment="SHIP-1001",
            reason="运单错误；数量不对",
            inspect_awbs=("AWB-OLD",),
            droplist_awbs=("AWB-NEW",),
            inspect_quantity=3,
            droplist_quantity=4,
            inspect_sources=("inspect.xlsx / 第 2 行",),
            droplist_sources=("Drop shipment list.xlsx / Data / 第 3 行",),
        )
        dialog = ExcelIssuesDialog([issue])
        self.assertEqual("SHIP-1001", dialog.table.item(0, 2).text())
        self.assertEqual("AWB-OLD", dialog.table.item(0, 4).text())
        self.assertEqual("AWB-NEW", dialog.table.item(0, 5).text())
        self.assertIn("Data", dialog.table.item(0, 7).text())
        dialog.close()

    def test_sheet_check_dialog_highlights_specific_unrecognized_sheet(self):
        check = SimpleNamespace(
            source_file="2026-10-19/Drop shipment list.xlsx",
            sheet="Sea Cargo",
            status="未识别",
            rows=0,
            detail="表头不完整",
        )
        dialog = DroplistSheetCheckDialog([check])
        self.assertEqual("Sea Cargo", dialog.table.item(0, 1).text())
        self.assertEqual("未识别", dialog.table.item(0, 2).text())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
