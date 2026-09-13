import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QScrollArea,
    QTableWidgetItem,
)

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
        self.assertNotIn("ShipmentTrack", labels)
        self.assertNotIn("物流查询工作台", labels)
        self.assertTrue(Path(PROFILE_AVATAR).is_file())
        sidebar = self.window.findChild(QFrame, "sidebar")
        self.assertEqual(168, sidebar.width())
        popup_labels = [
            label.text() for label in self.window.profile_popup.findChildren(QLabel)
            if label.text()
        ]
        self.assertEqual([PROFILE_NAME], popup_labels)
        sidebar_profile_text = [
            label.text() for label in self.window.profile_button.findChildren(QLabel)
            if label.text()
        ]
        self.assertEqual([], sidebar_profile_text)
        self.assertEqual([], self.window.settings_page.findChildren(QScrollArea))
        self.assertEqual(2, self.window.settings_page.settings_tabs.count())

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
        self.assertEqual(0.5, self.window.delivery_ring.ratio)
        self.assertEqual(1, self.window._tracking_counts["attention"])
        self.window._set_tracking_filter("delivered")
        self.assertFalse(self.window.tracking_table.isRowHidden(0))
        self.assertTrue(self.window.tracking_table.isRowHidden(1))
        self.assertTrue(self.window.pod_switch.isChecked())

    def test_pod_green_dot_opens_local_file(self):
        pdf = Path(self.temp_dir.name) / "pod.pdf"
        pdf.write_bytes(b"%PDF-test")
        self.window._append_tracking_result({
            "运单号": "789",
            "快递公司": "FedEx",
            "状态": "Delivered",
            "抵达时间": "2026/9/10",
            "用时(秒)": 1,
            "POD文件": str(pdf),
            "备注": "",
        })
        pod_item = self.window.tracking_table.item(0, 5)
        self.assertEqual("●", pod_item.text())
        with mock.patch("ui.main_window.QDesktopServices.openUrl", return_value=True) as open_url:
            self.window._handle_tracking_cell_click(0, 5)
        open_url.assert_called_once()

    def test_settings_page_writes_mapping_json_without_manual_editing(self):
        page = self.window.settings_page
        page.add_mapping()
        row = page.mapping_table.rowCount() - 1
        page.mapping_table.setItem(row, 0, QTableWidgetItem("OFS"))
        page.mapping_table.setItem(row, 1, QTableWidgetItem("澳车"))
        page.mapping_table.setItem(row, 2, QTableWidgetItem("光联"))
        page.mapping_table.setItem(row, 3, QTableWidgetItem("历史名称"))
        page.add_delivery_status("EI", "交给其他清关人")
        page.save()
        rules = self.store.load_mappings()
        self.assertTrue(any(rule.pattern == "OFS" for rule in rules))
        ofs = next(rule for rule in rules if rule.pattern == "OFS")
        self.assertEqual("澳车", ofs.display_type)
        self.assertEqual("光联", ofs.target_type)
        self.assertTrue(self.store.mappings_path.is_file())
        self.assertIsNone(page.mapping_table.cellWidget(0, 0))
        self.assertLessEqual(page.mapping_table.maximumHeight(), 230)
        self.assertEqual(
            ["交给其他清关人"],
            self.store.load_delivery_statuses()["EI"],
        )

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
        self.assertEqual("dir", self.window.excel_output.mode)
        self.assertFalse(self.window.open_inspect_output.isEnabled())
        self.assertFalse(self.window.open_droplist_output.isEnabled())

    def test_excel_result_enables_both_output_buttons(self):
        inspect_output = Path(self.temp_dir.name) / "合并检验表.xlsx"
        droplist_output = Path(self.temp_dir.name) / "合并Droplist.xlsx"
        inspect_output.write_bytes(b"xlsx")
        droplist_output.write_bytes(b"xlsx")
        result = SimpleNamespace(
            rows=(),
            inspect_files=2,
            droplist_files=2,
            inspect_rows=10,
            droplist_rows=8,
            issues=(),
            inspect_output_file=inspect_output,
            droplist_output_file=droplist_output,
        )
        self.window._show_excel_result(result)
        self.assertEqual(str(inspect_output), self.window.open_inspect_output.path)
        self.assertEqual(str(droplist_output), self.window.open_droplist_output.path)
        self.assertTrue(self.window.open_inspect_output.isEnabled())
        self.assertTrue(self.window.open_droplist_output.isEnabled())

    def test_parallel_panels_keep_their_own_controls_and_output_paths(self):
        tracking_output = Path(self.temp_dir.name) / "tracking_result.xlsx"
        cleaned_output = Path(self.temp_dir.name) / "tracking_list_cleaned_sorted.xlsx"
        audit_output = Path(self.temp_dir.name) / "pod_audit.xlsx"
        for path in (tracking_output, cleaned_output, audit_output):
            path.write_bytes(b"xlsx")
        self.window._tracking_output_paths = {
            "result": tracking_output,
            "cleaned": cleaned_output,
            "audit": audit_output,
        }
        self.window._refresh_output_buttons(0)

        self.window._set_tracking_running(True)
        self.assertTrue(self.window.excel_run_button.isEnabled())
        self.assertFalse(self.window.run_button.isEnabled())
        self.window.excel_run_button.setEnabled(False)
        self.assertFalse(self.window.excel_run_button.isEnabled())
        self.window._set_tracking_running(False)
        self.assertTrue(self.window.run_button.isEnabled())

        self.window._switch_page(1, "Excel 合并与核对")
        self.window._switch_page(0, "跟踪")
        self.assertEqual(str(tracking_output.absolute()), self.window.open_tracking_result.path)
        self.assertTrue(self.window.open_tracking_result.isEnabled())
        with mock.patch("ui.components.QDesktopServices.openUrl", return_value=True) as open_url:
            self.assertTrue(self.window.open_tracking_result.open_file())
        open_url.assert_called_once()


if __name__ == "__main__":
    unittest.main()
