import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QTableWidgetItem

from modules.settings_store import SettingsStore
from ui.main_window import MainWindow, PROFILE_AVATAR, PROFILE_NAME


class NativeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.store = SettingsStore(root / "settings.json", root / "mappings.json")
        self.window = MainWindow(settings_store=self.store)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def test_native_shell_has_three_pages_and_profile(self):
        self.assertEqual(3, self.window.stack.count())
        self.assertEqual(
            ["跟踪", "Excel 合并与核对", "设置"],
            [button.text() for button in self.window.nav_buttons],
        )
        labels = [label.text() for label in self.window.findChildren(QLabel)]
        self.assertIn(PROFILE_NAME, labels)
        self.assertNotIn("物流查询工作台", labels)
        self.assertTrue(Path(PROFILE_AVATAR).is_file())

    def test_tracking_page_has_smooth_progress_and_live_table(self):
        self.assertEqual(240, self.window._tracking_progress_anim.duration())
        self.window._append_tracking_result({
            "运单号": "123",
            "快递公司": "FedEx",
            "状态": "Delivered",
            "抵达时间": "2026/9/10",
            "用时(秒)": 1.2,
            "备注": "",
        })
        self.window._append_tracking_result({
            "运单号": "456",
            "快递公司": "DHL",
            "状态": "Unknown",
            "抵达时间": "",
            "用时(秒)": 2.4,
            "备注": "需要人工复核",
        })
        self.assertEqual(2, self.window.tracking_table.rowCount())
        self.assertEqual("1", self.window.tracking_stats["delivered"].value_label.text())
        self.assertEqual("1", self.window.tracking_stats["attention"].value_label.text())
        self.window.tracking_filter.setCurrentText("已送达")
        self.window._filter_tracking_rows()
        self.assertFalse(self.window.tracking_table.isRowHidden(0))
        self.assertTrue(self.window.tracking_table.isRowHidden(1))

    def test_settings_page_writes_mapping_json_without_manual_editing(self):
        page = self.window.settings_page
        page.add_mapping()
        row = page.mapping_table.rowCount() - 1
        page.mapping_table.setItem(row, 1, QTableWidgetItem("OFS"))
        page.mapping_table.setItem(row, 2, QTableWidgetItem("光联"))
        page.mapping_table.setItem(row, 3, QTableWidgetItem("历史名称"))
        page.save()
        rules = self.store.load_mappings()
        self.assertTrue(any(rule.pattern == "OFS" for rule in rules))
        self.assertTrue(self.store.mappings_path.is_file())

    def test_excel_page_is_single_combined_workflow(self):
        self.assertEqual(6, self.window.excel_table.columnCount())
        headers = [
            self.window.excel_table.horizontalHeaderItem(index).text()
            for index in range(self.window.excel_table.columnCount())
        ]
        self.assertEqual(
            ["日期", "类型", "检验表数量", "Droplist 数量", "差异", "结果"],
            headers,
        )


if __name__ == "__main__":
    unittest.main()
