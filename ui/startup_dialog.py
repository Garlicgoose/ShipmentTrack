# -*- coding: utf-8 -*-
"""启动窗口：自动进行授权检查（无圆点点击，检查通过自动进入主界面）。

检查失败时弹出英文错误提示并退出，不暴露任何授权相关信息。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QProgressBar,
                               QMessageBox)

from units import get_resource_path
from ui.workers import TaskWorker

APP_ICON = str(get_resource_path() / "assets" / "app_icon.png")


class StartupDialog(QDialog):
    granted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shipment Track")
        self.setWindowIcon(QIcon(APP_ICON))
        self.setFixedSize(340, 180)
        self._worker = None

        lay = QVBoxLayout(self)
        lay.addStretch(1)

        icon = QLabel()
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(QIcon(APP_ICON).pixmap(56, 56))
        lay.addWidget(icon)

        self.status_label = QLabel("Starting...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #666;")
        lay.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        lay.addWidget(self.progress)

        lay.addStretch(1)

    def showEvent(self, event):
        super().showEvent(event)
        if self._worker is None:
            self._start_check()

    def _start_check(self):
        self._worker = TaskWorker(
            lambda log, progress: self._do_check())
        self._worker.finished_ok.connect(self._on_done)
        self._worker.start()

    def _do_check(self):
        import machine_id
        import license as license_mod
        mid = machine_id.get_machine_id()
        ok, _mode, err = license_mod.verify(mid)
        if not ok:
            raise RuntimeError(err or "Unable to start. Please try again.")
        return True

    def _on_done(self, ok, err):
        if ok:
            self.granted.emit()
            self.accept()
        else:
            self.progress.hide()
            self.status_label.setText("")
            QMessageBox.critical(
                self, "Shipment Track",
                err or "Unable to start. Please try again.")
            self.reject()
