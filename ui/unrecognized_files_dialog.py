# -*- coding: utf-8 -*-
"""Review files that could not be assigned to a normal business category."""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)


class UnrecognizedFilesDialog(QDialog):
    def __init__(self, files, parent=None):
        super().__init__(parent)
        self.files = tuple(Path(item) for item in files)
        self.setWindowTitle("未识别文件")
        self.resize(680, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("以下文件未计入光联或 MPO 汇总，请人工确认："))
        self.file_list = QListWidget()
        for path in self.files:
            self.file_list.addItem(str(path))
        if self.files:
            self.file_list.setCurrentRow(0)
        layout.addWidget(self.file_list, 1)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton("复制文件名")
        self.open_folder_button = QPushButton("打开所在文件夹")
        self.close_button = QPushButton("关闭")
        self.copy_button.clicked.connect(self.copy_filenames)
        self.open_folder_button.clicked.connect(self.open_selected_folder)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.open_folder_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    def copy_filenames(self):
        QApplication.clipboard().setText("\n".join(path.name for path in self.files))

    def open_selected_folder(self):
        row = self.file_list.currentRow()
        if row < 0 or row >= len(self.files):
            return False
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.files[row].parent)))
