# -*- coding: utf-8 -*-
"""主界面复用的小型原生控件。"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PathField(QWidget):
    changed = Signal(str)

    def __init__(self, value="", mode="file", file_filter="Excel (*.xlsx)", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.file_filter = file_filter
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        self.edit = QLineEdit(str(value or ""))
        self.edit.textChanged.connect(self.changed)
        self.button = QPushButton("浏览")
        self.button.setObjectName("smallButton")
        self.button.clicked.connect(self.browse)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def value(self):
        return self.edit.text().strip()

    def set_value(self, value):
        self.edit.setText(str(value or ""))

    def browse(self):
        current = self.value()
        if self.mode == "dir":
            selected = QFileDialog.getExistingDirectory(self, "选择文件夹", current)
        elif self.mode == "save":
            selected, _ = QFileDialog.getSaveFileName(
                self,
                "选择输出文件",
                current,
                self.file_filter,
            )
            if selected and not Path(selected).suffix:
                selected += ".xlsx"
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "选择文件",
                current,
                self.file_filter,
            )
        if selected:
            self.set_value(selected)


class StatCard(QFrame):
    def __init__(self, label, value="0", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(3)
        caption = QLabel(label)
        caption.setObjectName("statLabel")
        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("statValue")
        layout.addWidget(caption)
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value_label.setText(str(value))


def circular_pixmap(path, size):
    source = QPixmap(str(path))
    if source.isNull():
        fallback = QPixmap(size, size)
        fallback.fill(QColor("#2AB8AE"))
        return fallback
    source = source.scaled(
        size,
        size,
        Qt.KeepAspectRatioByExpanding,
        Qt.SmoothTransformation,
    )
    output = QPixmap(size, size)
    output.fill(Qt.transparent)
    painter = QPainter(output)
    painter.setRenderHint(QPainter.Antialiasing)
    path_shape = QPainterPath()
    path_shape.addEllipse(0, 0, size, size)
    painter.setClipPath(path_shape)
    painter.drawPixmap(0, 0, source)
    painter.end()
    return output
