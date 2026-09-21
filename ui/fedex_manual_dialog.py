# -*- coding: utf-8 -*-
"""Native, non-blocking panel for human-submitted FedEx webpage PODs."""
from __future__ import annotations

from pathlib import Path
import threading
import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from modules.fedex_manual_pod import ManualFedExPodSession, ManualPodResult
from units import detect_browser_path


class ManualPodWorker(QThread):
    message = Signal(str)
    current = Signal(str, int, int)
    completed = Signal(object)
    finished_status = Signal(str)

    def __init__(self, numbers, output_dir, browser_type="edge", browser_path="", parent=None):
        super().__init__(parent)
        self.numbers = list(dict.fromkeys(str(number) for number in numbers))
        self.output_dir = Path(output_dir)
        self.browser_type = str(browser_type or "edge")
        self.browser_path = browser_path
        self.stop_event = threading.Event()
        self.skip_event = threading.Event()
        self.retry_event = threading.Event()

    def _wait_for_action(self):
        while not self.stop_event.is_set():
            if self.skip_event.is_set():
                self.skip_event.clear()
                return "skip"
            if self.retry_event.is_set():
                self.retry_event.clear()
                return "retry"
            time.sleep(0.2)
        return "stop"

    def _process(self, session, number):
        session.prepare(number)
        self.message.emit("已打开 FedEx。请点击 Tracking ID 输入框；单号会填入，请自行点击 TRACK。")
        stage = "main"
        snapshot = None
        main_pdf = ""
        while not self.stop_event.is_set():
            if self.skip_event.is_set():
                self.skip_event.clear()
                return "skip"
            if self.retry_event.is_set():
                self.retry_event.clear()
                session.prepare(number)
                stage, snapshot, main_pdf = "main", None, ""
            try:
                if stage == "main" and session.fill_after_user_click(number):
                    self.message.emit("单号已逐字输入。请点击 TRACK。")
                if stage == "main" and session.main_ready(number):
                    main_pdf, snapshot = session.save_main(number)
                    self.message.emit("主页 PDF 已保存。请手动点击 FedEx 详情。")
                    stage = "detail"
                elif stage == "detail" and session.detail_ready(number, snapshot):
                    detail_pdf = session.save_detail(number, snapshot)
                    self.completed.emit(ManualPodResult(number, main_pdf, detail_pdf))
                    return "done"
            except Exception as exc:
                self.message.emit(f"已暂停：{exc}。请修正页面后点“重试当前”，或跳过。")
                action = self._wait_for_action()
                if action != "retry":
                    return action
                session.prepare(number)
                stage, snapshot, main_pdf = "main", None, ""
            time.sleep(0.5)
        return "stop"

    def run(self):
        session = None
        playwright = None
        try:
            from playwright.sync_api import sync_playwright
            path = self.browser_path or detect_browser_path(self.browser_type)
            if not path:
                raise FileNotFoundError("未找到浏览器，请先在设置中选择 Edge 或 Chrome 路径")
            playwright = sync_playwright().start()
            session = ManualFedExPodSession(
                playwright, path, self.browser_type, self.output_dir, self.message.emit
            )
            total = len(self.numbers)
            for index, number in enumerate(self.numbers, 1):
                if self.stop_event.is_set():
                    break
                self.current.emit(number, index, total)
                if self._process(session, number) == "stop":
                    break
            self.finished_status.emit("已停止" if self.stop_event.is_set() else "队列已结束")
        except Exception as exc:
            self.finished_status.emit(f"无法继续：{exc}")
        finally:
            if session is not None:
                session.close()
            if playwright is not None:
                playwright.stop()


class FedExManualDialog(QDialog):
    completed = Signal(object)
    queue_finished = Signal()

    def __init__(self, numbers, output_dir, browser_type="edge", browser_path="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("FedEx POD · 半自动")
        self.resize(500, 290)
        self.setMinimumWidth(430)
        self.worker = None
        self.numbers = list(numbers)
        self.output_dir = output_dir
        self.browser_type = browser_type
        self.browser_path = browser_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        self.current_label = QLabel(f"待处理 {len(self.numbers)} 票 FedEx")
        self.current_label.setObjectName("sectionTitle")
        layout.addWidget(self.current_label)
        layout.addWidget(QLabel("点击网页输入框后自动填号；您点击 TRACK 和详情，程序只保存两页 PDF。"))
        controls = QHBoxLayout()
        self.start_button = QPushButton("打开 FedEx 并开始")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start)
        self.retry_button = QPushButton("重试当前")
        self.retry_button.clicked.connect(self.retry)
        self.skip_button = QPushButton("跳过当前")
        self.skip_button.clicked.connect(self.skip)
        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self.stop)
        for button in (self.start_button, self.retry_button, self.skip_button, self.stop_button):
            controls.addWidget(button)
        layout.addLayout(controls)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)

    def start(self):
        if self.worker and self.worker.isRunning():
            return
        self.worker = ManualPodWorker(
            self.numbers, self.output_dir, self.browser_type, self.browser_path, self
        )
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.current.connect(
            lambda number, index, total: self.current_label.setText(f"{index}/{total}  {number}")
        )
        self.worker.completed.connect(self.completed)
        self.worker.finished_status.connect(self._finished)
        self.start_button.setEnabled(False)
        self.worker.start()

    def retry(self):
        if self.worker:
            self.worker.retry_event.set()

    def skip(self):
        if self.worker:
            self.worker.skip_event.set()

    def stop(self):
        if self.worker:
            self.worker.stop_event.set()

    def _finished(self, message):
        self.log.appendPlainText(message)
        self.start_button.setEnabled(True)
        self.queue_finished.emit()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop_event.set()
            self.worker.wait(5000)
            if self.worker.isRunning():
                event.ignore()
                return
        super().closeEvent(event)
