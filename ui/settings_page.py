# -*- coding: utf-8 -*-
"""设置页：账号、路径、外接 Chromium 和文件名映射。"""
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.settings_store import (
    DEFAULT_FILENAME_MAPPINGS, DEFAULT_POD_AUDIT_RATES,
    FilenameMapper, FilenameMappingRule,
)
from modules import fedex_module
from ui.components import PathField
from ui.workers import TaskWorker
from units import detect_browser_path, get_resource_path


class SettingsPage(QWidget):
    saved = Signal(dict)
    message = Signal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.settings = store.load_settings()
        self._build()
        self.load_values()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        self.settings_tabs = QTabWidget()

        general_page = QWidget()
        general_layout = QHBoxLayout(general_page)
        general_layout.setContentsMargins(4, 10, 4, 4)
        general_layout.setSpacing(12)

        credentials = QGroupBox("账号与 API")
        credentials_form = QFormLayout(credentials)
        credentials_form.setHorizontalSpacing(18)
        credentials_form.setVerticalSpacing(10)
        self.fedex_key = QLineEdit()
        self.fedex_secret = QLineEdit()
        self.fedex_secret.setEchoMode(QLineEdit.Password)
        self.test_fedex_button = QPushButton("验证 FedEx API")
        self.test_fedex_button.setObjectName("smallButton")
        self.test_fedex_button.clicked.connect(self.test_fedex_api)
        self._fedex_test_worker = None
        self.ei_email = QLineEdit()
        self.ei_password = QLineEdit()
        self.ei_password.setEchoMode(QLineEdit.Password)
        credentials_form.addRow("FedEx API Key", self.fedex_key)
        credentials_form.addRow("FedEx API Secret", self.fedex_secret)
        credentials_form.addRow("", self.test_fedex_button)
        credentials_form.addRow("EI 账号", self.ei_email)
        credentials_form.addRow("EI 密码", self.ei_password)
        general_layout.addWidget(credentials, 2)

        paths = QGroupBox("文件与浏览器")
        paths_form = QFormLayout(paths)
        paths_form.setHorizontalSpacing(18)
        paths_form.setVerticalSpacing(10)
        self.tracking_input = PathField(mode="file")
        self.tracking_output = PathField(mode="dir")
        self.inspect_input = PathField(mode="dir")
        self.droplist_input = PathField(mode="dir")
        self.excel_output = PathField(mode="dir")
        self.browser_group = QButtonGroup(self)
        self.browser_group.setExclusive(True)
        browser_choices = QHBoxLayout()
        self.browser_buttons = {}
        for browser_type, label in (("edge", "Microsoft Edge"), ("chrome", "Google Chrome")):
            button = QPushButton(label)
            button.setObjectName("browserChoiceButton")
            button.setCheckable(True)
            self.browser_group.addButton(button)
            self.browser_buttons[browser_type] = button
            browser_choices.addWidget(button)
        self.browser_buttons["edge"].setChecked(True)
        self.browser_path = PathField(mode="file", file_filter="浏览器程序 (*.exe)")
        self.chrome_path = self.browser_path  # legacy UI attribute
        detect_button = QPushButton("自动检测浏览器")
        detect_button.setObjectName("smallButton")
        detect_button.clicked.connect(self.detect_browser)
        chrome_widget = QWidget()
        chrome_layout = QVBoxLayout(chrome_widget)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(6)
        chrome_layout.addLayout(browser_choices)
        chrome_layout.addWidget(self.browser_path)
        chrome_layout.addWidget(detect_button, 0)
        self.minimize_browser = QCheckBox("查询时最小化浏览器")
        paths_form.addRow("默认跟踪 Excel", self.tracking_input)
        paths_form.addRow("跟踪输出文件夹", self.tracking_output)
        paths_form.addRow("检验表文件夹", self.inspect_input)
        paths_form.addRow("Droplist 文件夹", self.droplist_input)
        paths_form.addRow("合并输出文件夹", self.excel_output)
        paths_form.addRow("实际浏览器", chrome_widget)
        paths_form.addRow("", self.minimize_browser)
        general_layout.addWidget(paths, 3)
        self.settings_tabs.addTab(general_page, "连接与路径")

        mapping_page = QWidget()
        mapping_page_layout = QVBoxLayout(mapping_page)
        mapping_page_layout.setContentsMargins(4, 10, 4, 4)
        mapping_page_layout.setSpacing(10)

        mappings = QGroupBox("文件名映射")
        mapping_layout = QVBoxLayout(mappings)
        hint = QLabel("文件名关键字 → 检验表原类型 → 光联/MPO；匹配方式填 包含、完全 或 正则。")
        hint.setObjectName("muted")
        mapping_layout.addWidget(hint)
        self.mapping_table = QTableWidget(0, 5)
        self.mapping_table.setHorizontalHeaderLabels(
            ("文件名关键字", "检验表类型", "归总类别", "备注", "匹配方式")
        )
        header = self.mapping_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.mapping_table.verticalHeader().setVisible(False)
        self.mapping_table.verticalHeader().setDefaultSectionSize(36)
        self.mapping_table.setShowGrid(False)
        self.mapping_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.mapping_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.mapping_table.setMinimumHeight(170)
        self.mapping_table.setMaximumHeight(230)
        mapping_layout.addWidget(self.mapping_table)
        self.mapping_table.itemChanged.connect(self.preview_mapping)
        preview_row = QHBoxLayout()
        self.mapping_preview_input = QLineEdit()
        self.mapping_preview_input.setPlaceholderText("输入示例文件名，预览最终类型")
        self.mapping_preview_input.textChanged.connect(self.preview_mapping)
        self.mapping_preview_result = QLabel("预览：请输入文件名")
        self.mapping_preview_result.setObjectName("muted")
        preview_row.addWidget(self.mapping_preview_input, 2)
        preview_row.addWidget(self.mapping_preview_result, 3)
        mapping_layout.addLayout(preview_row)
        actions = QHBoxLayout()
        for text, handler in (
            ("添加", self.add_mapping),
            ("删除", self.remove_mapping),
            ("上移", lambda: self.move_mapping(-1)),
            ("下移", lambda: self.move_mapping(1)),
        ):
            button = QPushButton(text)
            button.setObjectName("smallButton")
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch(1)
        recommend_button = QPushButton("补充推荐规则")
        recommend_button.setObjectName("smallButton")
        recommend_button.clicked.connect(self.add_recommended_mappings)
        actions.addWidget(recommend_button)
        guide_button = QPushButton("查看映射说明")
        guide_button.setObjectName("smallButton")
        guide_button.clicked.connect(self.open_mapping_guide)
        actions.addWidget(guide_button)
        mapping_layout.addLayout(actions)
        mapping_page_layout.addWidget(mappings)

        mapping_page_layout.addStretch(1)
        self.settings_tabs.addTab(mapping_page, "映射")

        status_page = QWidget()
        status_page_layout = QVBoxLayout(status_page)
        status_page_layout.setContentsMargins(4, 10, 4, 4)
        status_page_layout.setSpacing(10)

        statuses = QGroupBox("货代抵达状态")
        status_layout = QVBoxLayout(statuses)
        status_hint = QLabel(
            "为 DHL、EI 或 DSV 添加额外抵达状态；仅与当前状态完整匹配。"
        )
        status_hint.setObjectName("muted")
        status_layout.addWidget(status_hint)
        self.status_table = QTableWidget(0, 2)
        self.status_table.setHorizontalHeaderLabels(("承运商", "额外抵达状态"))
        self.status_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.status_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.verticalHeader().setDefaultSectionSize(34)
        self.status_table.setShowGrid(False)
        self.status_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.status_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.status_table.setMinimumHeight(160)
        self.status_table.setMaximumHeight(340)
        status_layout.addWidget(self.status_table)
        status_actions = QHBoxLayout()
        add_status = QPushButton("添加状态")
        add_status.setObjectName("smallButton")
        add_status.clicked.connect(self.add_delivery_status)
        remove_status = QPushButton("删除状态")
        remove_status.setObjectName("smallButton")
        remove_status.clicked.connect(self.remove_delivery_status)
        status_actions.addWidget(add_status)
        status_actions.addWidget(remove_status)
        status_actions.addStretch(1)
        status_layout.addLayout(status_actions)
        status_page_layout.addWidget(statuses)
        status_page_layout.addStretch(1)
        self.status_page = status_page
        self.settings_tabs.addTab(status_page, "货代抵达状态")

        audit_page = QWidget()
        audit_page_layout = QVBoxLayout(audit_page)
        audit_page_layout.setContentsMargins(4, 10, 4, 4)
        audit_page_layout.setSpacing(10)

        audit_rates = QGroupBox("POD 抽查比例")
        audit_layout = QHBoxLayout(audit_rates)
        audit_layout.setSpacing(14)
        self.audit_rate_inputs = {}
        for carrier, default in DEFAULT_POD_AUDIT_RATES.items():
            field_layout = QVBoxLayout()
            field_layout.setSpacing(4)
            label = QLabel(carrier)
            label.setObjectName("muted")
            field = QLineEdit()
            field.setObjectName("rateInput")
            field.setValidator(QIntValidator(0, 100, self))
            field.setMaxLength(3)
            field.setFixedWidth(88)
            field.setAlignment(Qt.AlignCenter)
            field.setText(str(default))
            self.audit_rate_inputs[carrier] = field
            field_row = QHBoxLayout()
            field_row.setSpacing(4)
            field_row.addWidget(field)
            percent = QLabel("%")
            percent.setObjectName("muted")
            field_row.addWidget(percent)
            field_layout.addWidget(label)
            field_layout.addLayout(field_row)
            audit_layout.addLayout(field_layout)
        audit_layout.addStretch(1)
        audit_page_layout.addWidget(audit_rates)

        rate_hint = QLabel(
            "只填写 0 到 100 的整数；0 表示不抽查，100 表示全部抽查。\n"
            "每个承运商独立生效，保存后写入 data\\settings.json。"
        )
        rate_hint.setObjectName("muted")
        audit_page_layout.addWidget(rate_hint)
        audit_page_layout.addStretch(1)
        self.audit_page = audit_page
        self.settings_tabs.addTab(audit_page, "POD 抽查比例")
        outer.addWidget(self.settings_tabs, 1)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_button = QPushButton("保存设置")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.save)
        save_row.addWidget(save_button)
        outer.addLayout(save_row)

    def load_values(self):
        self.settings = self.store.load_settings()
        self.fedex_key.setText(self.settings["fedex_api_key"])
        self.fedex_secret.setText(self.settings["fedex_api_secret"])
        self.ei_email.setText(self.settings["tracking_ei_email"])
        self.ei_password.setText(self.settings["tracking_ei_password"])
        self.tracking_input.set_value(self.settings["tracking_input_file"])
        self.tracking_output.set_value(self.settings["tracking_output_dir"])
        self.inspect_input.set_value(self.settings["inspect_input_dir"])
        self.droplist_input.set_value(self.settings["droplist_input_dir"])
        self.excel_output.set_value(self.settings["excel_output_dir"])
        browser_type = str(self.settings.get("browser_type", "edge")).casefold()
        if browser_type not in self.browser_buttons:
            browser_type = "edge"
        self.browser_buttons[browser_type].setChecked(True)
        self.browser_path.set_value(self.settings.get("browser_path", ""))
        self.minimize_browser.setChecked(bool(self.settings["minimize_browser"]))
        rates = self.settings.get("pod_audit_rates", DEFAULT_POD_AUDIT_RATES)
        for carrier in self.audit_rate_inputs:
            self.set_audit_rate(carrier, rates.get(carrier, DEFAULT_POD_AUDIT_RATES[carrier]))
        self.mapping_table.setRowCount(0)
        for rule in self.store.load_mappings():
            self.add_mapping(rule)
        self.status_table.setRowCount(0)
        for carrier, values in self.store.load_delivery_statuses().items():
            for value in values:
                self.add_delivery_status(carrier, value)

    def add_mapping(self, rule=None):
        if not isinstance(rule, FilenameMappingRule):
            rule = FilenameMappingRule("", "", display_type="")
        row = self.mapping_table.rowCount()
        self.mapping_table.insertRow(row)
        pattern_item = QTableWidgetItem(rule.pattern)
        pattern_item.setData(256, rule.match_type)
        self.mapping_table.setItem(row, 0, pattern_item)
        self.mapping_table.setItem(row, 1, QTableWidgetItem(rule.display_type))
        self.mapping_table.setItem(row, 2, QTableWidgetItem(rule.target_type))
        self.mapping_table.setItem(row, 3, QTableWidgetItem(rule.note))
        self.mapping_table.setItem(row, 4, QTableWidgetItem({
            "contains": "包含", "exact": "完全", "regex": "正则"
        }.get(rule.match_type, "包含")))
        self.mapping_table.setCurrentCell(row, 0)

    def remove_mapping(self):
        row = self.mapping_table.currentRow()
        if row >= 0:
            self.mapping_table.removeRow(row)

    def move_mapping(self, direction):
        row = self.mapping_table.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= self.mapping_table.rowCount():
            return
        source = self._rule_at(row)
        other = self._rule_at(target)
        self._set_rule(row, other)
        self._set_rule(target, source)
        self.mapping_table.setCurrentCell(target, 1)

    def _rule_at(self, row):
        values = []
        for column in range(5):
            item = self.mapping_table.item(row, column)
            values.append(item.text().strip() if item else "")
        match_type = {"包含": "contains", "完全": "exact", "正则": "regex"}.get(
            values[4], values[4]
        )
        return FilenameMappingRule(
            pattern=values[0],
            target_type=values[2],
            match_type=match_type or "contains",
            note=values[3],
            display_type=values[1],
        )

    def _set_rule(self, row, rule):
        for column, value in enumerate(
            (rule.pattern, rule.display_type, rule.target_type, rule.note,
             {"contains": "包含", "exact": "完全", "regex": "正则"}.get(rule.match_type, "包含"))
        ):
            self.mapping_table.setItem(row, column, QTableWidgetItem(value))

    def mapping_rules(self):
        return [self._rule_at(row) for row in range(self.mapping_table.rowCount())]

    def add_recommended_mappings(self):
        existing = {rule.pattern.casefold() for rule in self.mapping_rules()}
        added = 0
        for rule in DEFAULT_FILENAME_MAPPINGS:
            if rule.pattern.casefold() not in existing:
                self.add_mapping(rule)
                existing.add(rule.pattern.casefold())
                added += 1
        self.message.emit(f"已补充 {added} 条推荐规则；请预览并保存设置")

    def preview_mapping(self, *_args):
        filename = self.mapping_preview_input.text().strip()
        if not filename:
            self.mapping_preview_result.setText("预览：请输入文件名")
            return
        matched = FilenameMapper(self.mapping_rules()).match(filename)
        if matched.matched:
            self.mapping_preview_result.setText(
                f"{matched.display_type} → {matched.target_type}（规则：{matched.pattern}）"
            )
        else:
            self.mapping_preview_result.setText("未匹配：请添加更具体的关键字规则")

    def open_mapping_guide(self):
        guide = get_resource_path() / "docs" / "FILENAME_MAPPING_GUIDE.md"
        if guide.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide)))
        else:
            QMessageBox.information(
                self,
                "文件名映射说明",
                "文件名关键字命中后，‘检验表类型’保留详细名称，‘归总类别’只用于光联/MPO数量核对。\n\n"
                "匹配方式：包含、完全、正则；完全优先，其次正则，最后包含。多个包含规则命中时，较长关键字优先。\n\n"
                "例如：国外Expeditors自提 → Expeditors自提 → 光联。先输入示例文件名预览，再保存。",
            )

    def add_delivery_status(self, carrier="EI", status=""):
        if isinstance(carrier, bool):
            carrier = "EI"
        row = self.status_table.rowCount()
        self.status_table.insertRow(row)
        self.status_table.setItem(row, 0, QTableWidgetItem(str(carrier)))
        self.status_table.setItem(row, 1, QTableWidgetItem(str(status)))
        self.status_table.setCurrentCell(row, 1)

    def remove_delivery_status(self):
        row = self.status_table.currentRow()
        if row >= 0:
            self.status_table.removeRow(row)

    def delivery_status_mapping(self):
        mapping = {"DHL": [], "EI": [], "DSV": []}
        invalid = []
        for row in range(self.status_table.rowCount()):
            carrier_item = self.status_table.item(row, 0)
            status_item = self.status_table.item(row, 1)
            carrier = (carrier_item.text() if carrier_item else "").strip().upper()
            status = (status_item.text() if status_item else "").strip()
            if not carrier and not status:
                continue
            if carrier not in mapping:
                invalid.append(carrier or "空白")
                continue
            if status and status not in mapping[carrier]:
                mapping[carrier].append(status)
        return mapping, invalid

    def set_audit_rate(self, carrier, value):
        """把抽查比例写进输入框，非法值回落到默认值。"""
        field = self.audit_rate_inputs[carrier]
        try:
            number = int(float(str(value).strip()))
        except (TypeError, ValueError):
            number = DEFAULT_POD_AUDIT_RATES[carrier]
        field.setText(str(min(100, max(0, number))))

    def audit_rate_values(self):
        """返回 (符合要求的比例, 填写错误的承运商列表)。"""
        rates = {}
        invalid = []
        for carrier, field in self.audit_rate_inputs.items():
            text = field.text().strip()
            if not text.isdigit() or int(text) > 100:
                invalid.append(carrier)
                continue
            rates[carrier] = int(text)
        return rates, invalid

    def selected_browser_type(self):
        return next(
            (kind for kind, button in self.browser_buttons.items() if button.isChecked()),
            "edge",
        )

    def detect_browser(self):
        browser_type = self.selected_browser_type()
        path = detect_browser_path(browser_type)
        self.browser_path.set_value(path)
        label = "Microsoft Edge" if browser_type == "edge" else "Google Chrome"
        self.message.emit(
            f"已检测到 {label}" if path else f"没有检测到 {label}，请手动选择程序路径"
        )

    def detect_chromium(self):
        """Compatibility entry point for older callers."""
        self.detect_browser()

    def test_fedex_api(self):
        if self._fedex_test_worker and self._fedex_test_worker.isRunning():
            return
        key = self.fedex_key.text().strip()
        secret = self.fedex_secret.text().strip()
        if not key or not secret:
            QMessageBox.warning(self, "ShipmentTrack", "请先填写完整的 FedEx API Key 和 Secret。")
            return
        self.test_fedex_button.setEnabled(False)
        self.test_fedex_button.setText("验证中…")

        def task(log, progress, item):
            item(fedex_module.validate_fedex_credentials(key, secret))

        self._fedex_test_worker = TaskWorker(task, self)
        self._fedex_test_worker.item.connect(self._show_fedex_test_result)
        self._fedex_test_worker.finished_ok.connect(self._finish_fedex_test)
        self._fedex_test_worker.start()

    def _show_fedex_test_result(self, result):
        ok, message = result
        if ok:
            QMessageBox.information(self, "ShipmentTrack", message)
        else:
            QMessageBox.warning(self, "ShipmentTrack", f"FedEx API 验证失败：\n{message}")

    def _finish_fedex_test(self, ok, error):
        self.test_fedex_button.setEnabled(True)
        self.test_fedex_button.setText("验证 FedEx API")
        if not ok:
            QMessageBox.warning(self, "ShipmentTrack", f"FedEx API 验证失败：\n{error}")
        self._fedex_test_worker = None

    def save(self):
        raw_rules = self.mapping_rules()
        invalid_match = [rule.pattern for rule in raw_rules if rule.match_type not in {
            "contains", "exact", "regex"
        }]
        if invalid_match:
            QMessageBox.warning(self, "ShipmentTrack", "匹配方式只能填写 包含、完全 或 正则。")
            return
        rules = [rule.normalized() for rule in raw_rules]
        rules = [
            rule for rule in rules
            if rule.pattern and rule.display_type and rule.target_type
        ]
        if not rules:
            QMessageBox.warning(self, "ShipmentTrack", "至少保留一条有效的文件名映射。")
            return
        invalid_groups = sorted({
            rule.target_type for rule in rules
            if rule.target_type not in {"光联", "MPO"}
        })
        if invalid_groups:
            QMessageBox.warning(
                self,
                "ShipmentTrack",
                "归总类别只能填写光联或 MPO：" + "、".join(invalid_groups),
            )
            return
        delivery_statuses, invalid_carriers = self.delivery_status_mapping()
        if invalid_carriers:
            QMessageBox.warning(
                self,
                "ShipmentTrack",
                "状态承运商只能填写 DHL、EI 或 DSV：" + "、".join(invalid_carriers),
            )
            return
        rates, invalid_rates = self.audit_rate_values()
        if invalid_rates:
            QMessageBox.warning(
                self,
                "ShipmentTrack",
                "POD 抽查比例只能填写 0 到 100 的整数：" + "、".join(invalid_rates),
            )
            self.settings_tabs.setCurrentWidget(self.audit_page)
            return
        settings = dict(self.settings)
        settings.update({
            "fedex_api_key": self.fedex_key.text().strip(),
            "fedex_api_secret": self.fedex_secret.text().strip(),
            "tracking_ei_email": self.ei_email.text().strip(),
            "tracking_ei_password": self.ei_password.text(),
            "tracking_input_file": self.tracking_input.value(),
            "tracking_output_dir": self.tracking_output.value(),
            "inspect_input_dir": self.inspect_input.value(),
            "droplist_input_dir": self.droplist_input.value(),
            "excel_output_dir": self.excel_output.value(),
            "browser_type": self.selected_browser_type(),
            "browser_path": self.browser_path.value(),
            "chrome_path": "",
            "minimize_browser": self.minimize_browser.isChecked(),
            "pod_audit_rates": rates,
        })
        self.store.save_settings(settings)
        self.store.save_mappings(rules)
        self.store.save_delivery_statuses(delivery_statuses)
        self.settings = settings
        self.saved.emit(dict(settings))
        self.message.emit("设置已保存")
