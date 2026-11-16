# -*- coding: utf-8 -*-
"""Compact, searchable-by-reading dialogs for reconciliation diagnostics."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class ExcelIssuesDialog(QDialog):
    def __init__(self, issues, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shipment 异常详情")
        self.resize(1120, 540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(QLabel(f"共 {len(issues)} 条异常；按 Shipment 核对缺失、运单和数量。"))
        self.table = QTableWidget(len(issues), 8)
        self.table.setHorizontalHeaderLabels((
            "日期", "类型", "Shipment", "异常", "检验表运单", "Droplist 运单",
            "数量（检验 / Drop）", "来源（文件 / Sheet / 行）",
        ))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        for row, issue in enumerate(issues):
            quantities = f"{_number(issue.inspect_quantity)} / {_number(issue.droplist_quantity)}"
            values = (
                issue.date,
                issue.target_type,
                issue.shipment,
                issue.reason,
                "、".join(issue.inspect_awbs) or "—",
                "、".join(issue.droplist_awbs) or "—",
                quantities,
                "\n".join((*issue.inspect_sources, *issue.droplist_sources)) or "—",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 3:
                    item.setForeground(QColor("#A04435"))
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 56)
        self.table.setColumnWidth(0, 92)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 150)
        self.table.setColumnWidth(6, 150)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)


class DroplistSheetCheckDialog(QDialog):
    def __init__(self, checks, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Droplist Sheet 自检")
        self.resize(960, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        failures = sum(check.status == "未识别" for check in checks)
        layout.addWidget(QLabel(f"检查 {len(checks)} 个 Sheet，未识别 {failures} 个。"))
        self.table = QTableWidget(len(checks), 5)
        self.table.setHorizontalHeaderLabels(("来源文件", "Sheet", "结果", "合并行数", "说明"))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        for row, check in enumerate(checks):
            values = (check.source_file, check.sheet, check.status, check.rows, check.detail)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if check.status == "未识别":
                    item.setForeground(QColor("#A04435"))
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 40)
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 90)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)


def _number(value):
    return "—" if value is None else f"{value:g}"
