import os
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QPushButton,
    QTableWidgetItem,
    QWidget,
)
from PySide6.QtTest import QTest

from modules.settings_store import SettingsStore
from ui.main_window import APP_FEATURES, APP_VERSION, MainWindow, PROFILE_AVATAR, PROFILE_NAME


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
        self.assertEqual(
            "a5aa5690996a6e28222789ba9de6d022fcae276ce9126a039fa22cc0e7ed7a38",
            hashlib.sha256(Path(PROFILE_AVATAR).read_bytes()).hexdigest(),
        )
        sidebar = self.window.findChild(QFrame, "sidebar")
        self.assertEqual(168, sidebar.width())
        popup_labels = [
            label.text() for label in self.window.profile_popup.findChildren(QLabel)
            if label.text()
        ]
        self.assertEqual(
            [PROFILE_NAME, f"ShipmentTrack v{APP_VERSION}"]
            + [f"•  {feature}" for feature in APP_FEATURES],
            popup_labels,
        )
        sidebar_profile_text = [
            label.text() for label in self.window.profile_button.findChildren(QLabel)
            if label.text()
        ]
        self.assertEqual([], sidebar_profile_text)
        self.assertEqual([], self.window.settings_page.findChildren(QScrollArea))
        tabs = self.window.settings_page.settings_tabs
        self.assertEqual(4, tabs.count())
        self.assertEqual(
            ["连接与路径", "映射", "货代抵达状态", "POD 抽查比例"],
            [tabs.tabText(index) for index in range(tabs.count())],
        )
        self.assertEqual(
            {"edge", "chrome"},
            set(self.window.settings_page.browser_buttons),
        )
        self.assertTrue(self.window.settings_page.browser_buttons["edge"].isChecked())
        self.assertEqual(
            {"FedEx": 20, "DHL": 5, "UPS": 5, "EI": 5, "DSV": 5},
            {
                carrier: int(field.text())
                for carrier, field in self.window.settings_page.audit_rate_inputs.items()
            },
        )
        self.assertEqual("1.2", APP_VERSION)
        popup_buttons = [
            button.text() for button in self.window.profile_popup.findChildren(QPushButton)
        ]
        self.assertEqual(["更新日志", "检查更新"], popup_buttons)

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
        labels = [label.text() for label in self.window.findChildren(QLabel)]
        self.assertNotIn("绿色圆环表示当前已送达比例", labels)
        self.assertNotIn("当前处理", labels)
        self.assertNotIn("查询范围", labels)
        self.assertIn("用时", labels)
        self.assertNotIn("本次 POD", labels)
        self.assertEqual(
            ["FedEx", "DHL", "UPS", "EI", "DSV"],
            list(self.window.carrier_average_labels),
        )

    def test_tracking_overview_updates_carrier_averages_only_when_finished(self):
        self.window._carrier_timings = {
            carrier: {"total": 0.0, "count": 0}
            for carrier in self.window.carrier_average_labels
        }
        self.window._append_tracking_result({
            "运单号": "123",
            "快递公司": "FedEx",
            "状态": "Delivered",
            "用时(秒)": 1,
        })
        self.window._append_tracking_result({
            "运单号": "456",
            "快递公司": "FEDEX",
            "状态": "Delivered",
            "用时(秒)": 2,
        })
        self.window._append_tracking_result({
            "运单号": "789",
            "快递公司": "DHL",
            "状态": "Delivered",
            "用时(秒)": 3,
        })
        self.assertTrue(all(
            label.text() == "--"
            for label in self.window.carrier_average_labels.values()
        ))
        self.window._update_carrier_averages()
        self.assertEqual("1.50", self.window.carrier_average_labels["FedEx"].text())
        self.assertEqual("3.00", self.window.carrier_average_labels["DHL"].text())
        self.assertEqual("--", self.window.carrier_average_labels["UPS"].text())

    def test_tracking_overview_formats_elapsed_time(self):
        with mock.patch.object(self.window._tracking_elapsed, "isValid", return_value=True), \
             mock.patch.object(self.window._tracking_elapsed, "elapsed", return_value=65_000):
            self.window._update_tracking_elapsed()
        self.assertEqual("01:05", self.window.elapsed_label.text())

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

    def test_fedex_pod_green_dot_opens_main_and_detail_pages(self):
        main_pdf = Path(self.temp_dir.name) / "789.pdf"
        detail_pdf = Path(self.temp_dir.name) / "789+.pdf"
        main_pdf.write_bytes(b"%PDF-main")
        detail_pdf.write_bytes(b"%PDF-detail")
        self.window._append_tracking_result({
            "运单号": "789",
            "快递公司": "FedEx",
            "状态": "Delivered",
            "抵达时间": "2026/9/10",
            "用时(秒)": 1,
            "POD文件": str(main_pdf),
            "POD详情文件": str(detail_pdf),
            "备注": "",
        })
        pod_item = self.window.tracking_table.item(0, 5)
        self.assertIn("主页和详情页", pod_item.toolTip())
        with mock.patch(
            "ui.main_window.QDesktopServices.openUrl", return_value=True
        ) as open_url:
            self.window._handle_tracking_cell_click(0, 5)
        self.assertEqual(2, open_url.call_count)

    def test_delivered_fedex_is_queued_for_manual_pod_and_updates_table(self):
        from modules.fedex_manual_pod import ManualPodResult
        main_pdf = Path(self.temp_dir.name) / "541964339019.pdf"
        detail_pdf = Path(self.temp_dir.name) / "541964339019+.pdf"
        main_pdf.write_bytes(b"%PDF-main")
        detail_pdf.write_bytes(b"%PDF-detail")
        self.window._append_tracking_result({
            "运单号": "541964339019", "快递公司": "FedEx",
            "状态": "Delivered", "is_delivered": True,
        })
        self.assertEqual(["541964339019"], self.window._fedex_manual_jobs)
        self.window._manual_fedex_completed(ManualPodResult(
            "541964339019", str(main_pdf), str(detail_pdf)
        ))
        pod_cell = self.window.tracking_table.item(0, 5)
        self.assertEqual("●", pod_cell.text())
        self.assertEqual([str(main_pdf), str(detail_pdf)], pod_cell.data(Qt.UserRole))

    def test_settings_tabs_have_no_overlapping_controls(self):
        """回归：三个设置分区挤在一页时表格和按钮会互相压住，拆页后不得再重叠。"""
        page = self.window.settings_page
        for width, height in ((1280, 800), (1024, 680)):
            self.window.resize(width, height)
            self.window.show()
            page.show()
            QTest.qWait(120)
            for index in range(page.settings_tabs.count()):
                page.settings_tabs.setCurrentIndex(index)
                QTest.qWait(60)
                current = page.settings_tabs.currentWidget()
                self.assertEqual([], self._sibling_overlaps(current), page.settings_tabs.tabText(index))
        self.window.hide()

    @staticmethod
    def _sibling_overlaps(root):
        """找出同一父控件（页或分组框）下位置互相重叠的直接子控件。"""
        parents = [root] + root.findChildren(QGroupBox)
        overlaps = []
        for parent in parents:
            rectangles = [
                (child, QRect(child.mapTo(parent, QPoint(0, 0)), child.size()))
                for child in parent.children()
                if isinstance(child, QWidget) and child.isVisible() and not child.isHidden()
            ]
            for position, (child, rectangle) in enumerate(rectangles):
                for other, other_rectangle in rectangles[position + 1:]:
                    if rectangle.intersects(other_rectangle):
                        overlaps.append(
                            (child.__class__.__name__, other.__class__.__name__)
                        )
        return overlaps

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
        self.assertEqual([], self.store.load_delivery_statuses()["DHL"])

    def test_settings_page_exposes_fedex_api_validation(self):
        page = self.window.settings_page
        self.assertEqual("验证 FedEx API", page.test_fedex_button.text())
        page.fedex_secret.setText(" secret-with-spaces ")
        with mock.patch.object(page.store, "save_settings") as save_settings:
            page.save()
        self.assertEqual(
            "secret-with-spaces",
            save_settings.call_args.args[0]["fedex_api_secret"],
        )

    def test_settings_tabs_split_mapping_status_and_audit_rate_pages(self):
        page = self.window.settings_page
        tabs = page.settings_tabs
        # 文件名映射留在「映射」页，状态表和比例输入各自独立成页，避免互相挤占重叠
        self.assertTrue(tabs.widget(1).isAncestorOf(page.mapping_table))
        self.assertFalse(tabs.widget(1).isAncestorOf(page.status_table))
        self.assertTrue(tabs.widget(2).isAncestorOf(page.status_table))
        self.assertFalse(tabs.widget(2).isAncestorOf(page.audit_rate_inputs["FedEx"]))
        self.assertTrue(tabs.widget(3).isAncestorOf(page.audit_rate_inputs["FedEx"]))
        self.assertFalse(tabs.widget(3).isAncestorOf(page.mapping_table))
        # 比例只提供输入框，不再有上下调节按钮
        self.assertEqual([], page.audit_page.findChildren(QAbstractSpinBox))
        for carrier, field in page.audit_rate_inputs.items():
            self.assertIsInstance(field, QLineEdit)
            self.assertFalse(field.isReadOnly())
            self.assertEqual(3, field.maxLength())
            self.assertTrue(field.alignment() & Qt.AlignHCenter)
            validator = field.validator()
            self.assertEqual("Acceptable", validator.validate("100", 0)[0].name)
            # 超过 100 只能是中间态，保存时由 audit_rate_values() 拦截
            self.assertEqual("Intermediate", validator.validate("101", 0)[0].name)
            self.assertEqual("Invalid", validator.validate("5a", 0)[0].name)
        self.assertEqual(
            {"FedEx": 20, "DHL": 5, "UPS": 5, "EI": 5, "DSV": 5},
            page.audit_rate_values()[0],
        )
        self.assertEqual([], page.audit_rate_values()[1])

    def test_settings_page_rejects_unparsable_audit_rate(self):
        page = self.window.settings_page
        for text in ("", "999"):
            page.audit_rate_inputs["DHL"].setText(text)
            with mock.patch("ui.settings_page.QMessageBox.warning") as warning:
                with mock.patch.object(page.store, "save_settings") as save_settings:
                    page.save()
            warning.assert_called_once()
            save_settings.assert_not_called()
            self.assertIs(page.audit_page, page.settings_tabs.currentWidget())
        page.audit_rate_inputs["DHL"].setText("5")
        rates, invalid = page.audit_rate_values()
        self.assertEqual([], invalid)
        self.assertEqual(5, rates["DHL"])

    def test_settings_page_saves_independent_pod_audit_rates(self):
        page = self.window.settings_page
        expected = {"FedEx": 0, "DHL": 15, "UPS": 35, "EI": 65, "DSV": 100}
        for carrier, value in expected.items():
            page.audit_rate_inputs[carrier].setText(str(value))
        page.save()
        self.assertEqual(expected, self.store.load_settings()["pod_audit_rates"])

    def test_mapping_preview_and_recommended_rules_are_visible(self):
        page = self.window.settings_page
        page.add_recommended_mappings()
        page.mapping_preview_input.setText("9.19国外Expeditors自提资料.XLSX")
        self.assertIn("Expeditors自提 → 光联", page.mapping_preview_result.text())
        self.assertEqual(5, page.mapping_table.columnCount())
        self.assertTrue(any(
            rule.pattern == "国外Expeditors自提" for rule in page.mapping_rules()
        ))

    def test_mapping_guide_has_in_app_fallback_for_exe_only_updates(self):
        page = self.window.settings_page
        with mock.patch("ui.settings_page.get_resource_path", return_value=Path(self.temp_dir.name)), \
             mock.patch("ui.settings_page.QMessageBox.information") as info:
            page.open_mapping_guide()
        self.assertIn("完全优先", info.call_args.args[2])

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

    def test_excel_result_supports_inspection_only(self):
        inspect_output = Path(self.temp_dir.name) / "合并检验表.xlsx"
        inspect_output.write_bytes(b"xlsx")
        result = SimpleNamespace(
            rows=(SimpleNamespace(
                date="9.10",
                target_type="光联",
                inspect_quantity=12,
                droplist_quantity=None,
                difference=None,
                result="仅检验表统计",
            ),),
            inspect_files=1,
            droplist_files=0,
            inspect_rows=2,
            droplist_rows=0,
            issues=(),
            inspect_output_file=inspect_output,
            droplist_output_file=None,
        )
        self.window._show_excel_result(result)
        self.assertEqual("12", self.window.excel_table.item(0, 2).text())
        self.assertEqual("", self.window.excel_table.item(0, 3).text())
        self.assertEqual("", self.window.excel_table.item(0, 4).text())
        self.assertTrue(self.window.open_inspect_output.isEnabled())
        self.assertFalse(self.window.open_droplist_output.isEnabled())

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
        QTest.qWait(420)
        self.window._switch_page(0, "跟踪")
        QTest.qWait(420)
        self.assertEqual(str(tracking_output.absolute()), self.window.open_tracking_result.path)
        self.assertTrue(self.window.open_tracking_result.isEnabled())
        with mock.patch("ui.components.QDesktopServices.openUrl", return_value=True) as open_url:
            self.assertTrue(self.window.open_tracking_result.open_file())
        open_url.assert_called_once()

    def test_page_switch_hides_content_swap_behind_opaque_cover(self):
        self.assertEqual(0, self.window.stack.currentIndex())
        self.window._switch_page(1, "Excel 合并与核对")

        self.assertTrue(self.window._page_transitioning)
        self.assertEqual(0, self.window.stack.currentIndex())
        self.assertIsNotNone(self.window._page_overlay)
        self.assertTrue(all(not button.isEnabled() for button in self.window.nav_buttons))
        self.assertIn("#F4F7FA", self.window._page_overlay.styleSheet())
        self.assertIsNone(self.window.excel_page.graphicsEffect())

        QTest.qWait(195)
        self.assertEqual(1, self.window.stack.currentIndex())
        self.assertEqual("Excel 合并与核对", self.window.page_title.text())
        self.assertGreater(self.window._page_overlay.graphicsEffect().opacity(), 0.9)

        QTest.qWait(280)
        self.assertFalse(self.window._page_transitioning)
        self.assertIsNone(self.window._page_overlay)
        self.assertIsNone(self.window.excel_page.graphicsEffect())
        self.assertTrue(all(button.isEnabled() for button in self.window.nav_buttons))


if __name__ == "__main__":
    unittest.main()
