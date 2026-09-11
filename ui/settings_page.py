# -*- coding: utf-8 -*-
"""设置页：账号、路径、外接 Chromium 和文件名映射。"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.settings_store import FilenameMappingRule
from ui.components import PathField
from units import detect_chrome_path


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
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, 8, 12)
        self.body_layout.setSpacing(14)

        credentials = QGroupBox("账号与 API")
        credentials_form = QFormLayout(credentials)
        credentials_form.setHorizontalSpacing(18)
        credentials_form.setVerticalSpacing(10)
        self.fedex_key = QLineEdit()
        self.fedex_secret = QLineEdit()
        self.fedex_secret.setEchoMode(QLineEdit.Password)
        self.ei_email = QLineEdit()
        self.ei_password = QLineEdit()
        self.ei_password.setEchoMode(QLineEdit.Password)
        credentials_form.addRow("FedEx API Key", self.fedex_key)
        credentials_form.addRow("FedEx API Secret", self.fedex_secret)
        credentials_form.addRow("EI 账号", self.ei_email)
        credentials_form.addRow("EI 密码", self.ei_password)
        self.body_layout.addWidget(credentials)

        paths = QGroupBox("文件与 Chromium")
        paths_form = QFormLayout(paths)
        paths_form.setHorizontalSpacing(18)
        paths_form.setVerticalSpacing(10)
        self.tracking_input = PathField(mode="file")
        self.tracking_output = PathField(mode="dir")
        self.inspect_input = PathField(mode="dir")
        self.droplist_input = PathField(mode="dir")
        self.excel_output = PathField(mode="dir")
        self.chrome_path = PathField(mode="file", file_filter="Chromium (chrome.exe)")
        detect_button = QPushButton("自动检测 Chromium")
        detect_button.setObjectName("smallButton")
        detect_button.clicked.connect(self.detect_chromium)
        chrome_widget = QWidget()
        chrome_layout = QVBoxLayout(chrome_widget)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(6)
        chrome_layout.addWidget(self.chrome_path)
        chrome_layout.addWidget(detect_button, 0)
        self.minimize_browser = QCheckBox("查询时最小化 Chromium")
        paths_form.addRow("默认跟踪 Excel", self.tracking_input)
        paths_form.addRow("跟踪输出文件夹", self.tracking_output)
        paths_form.addRow("检验表文件夹", self.inspect_input)
        paths_form.addRow("Droplist 文件夹", self.droplist_input)
        paths_form.addRow("合并输出文件夹", self.excel_output)
        paths_form.addRow("Chromium 路径", chrome_widget)
        paths_form.addRow("", self.minimize_browser)
        self.body_layout.addWidget(paths)

        mappings = QGroupBox("文件名映射")
        mapping_layout = QVBoxLayout(mappings)
        hint = QLabel("关键字对应检验表原类型，再归总到光联或 MPO。保存后自动写入 JSON。")
        hint.setObjectName("muted")
        mapping_layout.addWidget(hint)
        self.mapping_table = QTableWidget(0, 4)
        self.mapping_table.setHorizontalHeaderLabels(
            ("文件名关键字", "检验表类型", "归总类别", "备注")
        )
        header = self.mapping_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.mapping_table.verticalHeader().setVisible(False)
        self.mapping_table.verticalHeader().setDefaultSectionSize(36)
        self.mapping_table.setShowGrid(False)
        self.mapping_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.mapping_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.mapping_table.setMinimumHeight(150)
        self.mapping_table.setMaximumHeight(230)
        mapping_layout.addWidget(self.mapping_table)
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
        mapping_layout.addLayout(actions)
        self.body_layout.addWidget(mappings)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_button = QPushButton("保存设置")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.save)
        save_row.addWidget(save_button)
        self.body_layout.addLayout(save_row)
        self.body_layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll)

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
        self.chrome_path.set_value(self.settings["chrome_path"])
        self.minimize_browser.setChecked(bool(self.settings["minimize_browser"]))
        self.mapping_table.setRowCount(0)
        for rule in self.store.load_mappings():
            self.add_mapping(rule)

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
        for column in range(4):
            item = self.mapping_table.item(row, column)
            values.append(item.text().strip() if item else "")
        pattern_item = self.mapping_table.item(row, 0)
        return FilenameMappingRule(
            pattern=values[0],
            target_type=values[2],
            match_type=(pattern_item.data(256) if pattern_item else "contains") or "contains",
            note=values[3],
            display_type=values[1],
        )

    def _set_rule(self, row, rule):
        for column, value in enumerate(
            (rule.pattern, rule.display_type, rule.target_type, rule.note)
        ):
            self.mapping_table.setItem(row, column, QTableWidgetItem(value))
        self.mapping_table.item(row, 0).setData(256, rule.match_type)

    def mapping_rules(self):
        return [self._rule_at(row) for row in range(self.mapping_table.rowCount())]

    def detect_chromium(self):
        path = detect_chrome_path()
        self.chrome_path.set_value(path)
        self.message.emit("已检测到 Chromium" if path else "没有检测到 Chromium，请手动选择 chrome.exe")

    def save(self):
        rules = [rule.normalized() for rule in self.mapping_rules()]
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
        settings = dict(self.settings)
        settings.update({
            "fedex_api_key": self.fedex_key.text().strip(),
            "fedex_api_secret": self.fedex_secret.text(),
            "tracking_ei_email": self.ei_email.text().strip(),
            "tracking_ei_password": self.ei_password.text(),
            "tracking_input_file": self.tracking_input.value(),
            "tracking_output_dir": self.tracking_output.value(),
            "inspect_input_dir": self.inspect_input.value(),
            "droplist_input_dir": self.droplist_input.value(),
            "excel_output_dir": self.excel_output.value(),
            "chrome_path": self.chrome_path.value(),
            "minimize_browser": self.minimize_browser.isChecked(),
        })
        self.store.save_settings(settings)
        self.store.save_mappings(rules)
        self.settings = settings
        self.saved.emit(dict(settings))
        self.message.emit("设置已保存")
