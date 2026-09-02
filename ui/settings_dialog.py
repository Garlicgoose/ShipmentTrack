# -*- coding: utf-8 -*-
"""设置对话框：文件路径 / EI 账号密码 / FedEx API / 模拟 Chrome 路径。"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLineEdit, QPushButton, QFileDialog,
                               QCheckBox, QDialogButtonBox)

from units import detect_chrome_path


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings - Shipment Track")
        self.setMinimumWidth(560)
        self._settings = settings

        lay = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(10)

        # ---------- 文件路径 ----------
        self.input_file = QLineEdit(settings.get("tracking_input_file", ""))
        self.input_file.setPlaceholderText("含快递公司列和运单号列的 Excel")
        form.addRow("输入 Excel：", self._with_browse(self.input_file, "file"))

        self.output_dir = QLineEdit(settings.get("tracking_output_dir", ""))
        form.addRow("输出文件夹：", self._with_browse(self.output_dir, "dir"))

        # ---------- EI 账号密码 ----------
        self.ei_email = QLineEdit(settings.get("tracking_ei_email", ""))
        form.addRow("EI 邮箱：", self.ei_email)

        self.ei_password = QLineEdit(settings.get("tracking_ei_password", ""))
        self.ei_password.setEchoMode(QLineEdit.Password)
        form.addRow("EI 密码：", self.ei_password)

        # ---------- FedEx API ----------
        self.fedex_key = QLineEdit(settings.get("fedex_api_key", ""))
        form.addRow("FedEx API Key：", self.fedex_key)

        self.fedex_secret = QLineEdit(settings.get("fedex_api_secret", ""))
        self.fedex_secret.setEchoMode(QLineEdit.Password)
        form.addRow("FedEx API Secret：", self.fedex_secret)

        # ---------- 模拟 Chrome 路径 ----------
        chrome_row = QHBoxLayout()
        self.chrome_path = QLineEdit(settings.get("chrome_path", ""))
        self.chrome_path.setPlaceholderText("Playwright Chromium 的 chrome.exe 路径")
        chrome_row.addWidget(self.chrome_path)
        chrome_row.addWidget(self._browse_btn(self.chrome_path, "file"))
        detect_btn = QPushButton("自动检测")
        detect_btn.clicked.connect(self._auto_detect_chrome)
        chrome_row.addWidget(detect_btn)
        form.addRow("Chrome：", chrome_row)

        # ---------- 最小化浏览器 ----------
        self.minimize_box = QCheckBox("最小化")
        self.minimize_box.setChecked(bool(settings.get("minimize_browser", True)))
        form.addRow("", self.minimize_box)

        lay.addLayout(form)

        # ---------- 按钮 ----------
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("保存")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    # ---------- helpers ----------

    def _browse_btn(self, line_edit, mode):
        btn = QPushButton("浏览")
        btn.clicked.connect(lambda: self._browse(line_edit, mode))
        return btn

    def _with_browse(self, line_edit, mode):
        row = QHBoxLayout()
        row.addWidget(line_edit)
        row.addWidget(self._browse_btn(line_edit, mode))
        return row

    def _browse(self, line_edit, mode):
        if mode == "file":
            path, _ = QFileDialog.getOpenFileName(
                self, "选择文件", line_edit.text())
        else:
            path = QFileDialog.getExistingDirectory(
                self, "选择文件夹", line_edit.text())
        if path:
            line_edit.setText(path)

    def _auto_detect_chrome(self):
        path = detect_chrome_path()
        if path:
            self.chrome_path.setText(path)
        else:
            self.chrome_path.setText("")

    # ---------- 取值 ----------

    def values(self):
        return {
            "tracking_input_file": self.input_file.text().strip(),
            "tracking_output_dir": self.output_dir.text().strip(),
            "tracking_ei_email": self.ei_email.text().strip(),
            "tracking_ei_password": self.ei_password.text(),
            "fedex_api_key": self.fedex_key.text().strip(),
            "fedex_api_secret": self.fedex_secret.text(),
            "chrome_path": self.chrome_path.text().strip(),
            "minimize_browser": self.minimize_box.isChecked(),
        }
