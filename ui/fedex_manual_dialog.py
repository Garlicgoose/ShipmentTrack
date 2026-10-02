# -*- coding: utf-8 -*-
"""Button-driven FedEx webpage POD panel with a persistent queue."""
from __future__ import annotations

from pathlib import Path
import threading
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from modules.fedex_manual_pod import ManualFedExPodSession, ManualPodResult
from modules.fedex_pod_auto import AUTO_BATCH_LIMIT, run_experimental_auto
from modules.fedex_pod_queue import FedExPodQueue
from modules.fedex_web_pod import FedExEdgePodSession
from units import detect_browser_path


def default_queue_path(output_dir) -> Path:
    output = Path(output_dir)
    if output.name.casefold() == "fedex" and output.parent.name.casefold() == "pdf":
        root = output.parents[1]
    else:
        root = output
    return root / "fedex_pod_queue.sqlite"


class ManualPodWorker(QThread):
    message = Signal(str)
    current = Signal(str, int, int)
    stage_changed = Signal(str, str)
    copy_requested = Signal(str)
    completed = Signal(object)
    queue_changed = Signal()
    finished_status = Signal(str)

    def __init__(self, numbers, output_dir, browser_type="edge", browser_path="",
                 queue_path=None, parent=None):
        super().__init__(parent)
        self.numbers = list(dict.fromkeys(str(number) for number in numbers))
        self.output_dir = Path(output_dir)
        self.browser_type = str(browser_type or "edge")
        self.browser_path = browser_path
        self.queue = FedExPodQueue(queue_path or default_queue_path(output_dir))
        self.queue.add_numbers(self.numbers, source="本次查询结果")
        self.stop_event = threading.Event()
        self.skip_event = threading.Event()
        self.retry_event = threading.Event()
        self.print_event = threading.Event()
        self.next_event = threading.Event()
        self.pause_event = threading.Event()

    def _process(self, session, task):
        number = task.number
        session.prepare(number)
        snapshot = None
        main_pdf = task.main_pdf
        expected = task.expected_page
        self.copy_requested.emit(number)
        self.stage_changed.emit(number, expected)
        self.message.emit(
            "当前单号已复制。点击 FedEx 输入框后程序会填号；"
            "请自行点击 TRACK，页面就绪后点“保存当前页面 PDF”。"
        )
        while not self.stop_event.is_set():
            if self.skip_event.is_set():
                self.skip_event.clear()
                self.queue.skip(number)
                self.queue_changed.emit()
                return "skip"
            if self.pause_event.is_set():
                self.pause_event.clear()
                self.queue.pause(number, "用户暂停")
                self.queue_changed.emit()
                return "pause"
            if self.retry_event.is_set():
                self.retry_event.clear()
                session.prepare(number)
                self.message.emit("已重新准备当前票；队列阶段和已保存 PDF 保持不变。")
            if self.print_event.is_set():
                self.print_event.clear()
                try:
                    saved = session.save_current(number, expected, snapshot)
                    if saved.page_type == "main":
                        main_pdf = saved.path
                        snapshot = saved.snapshot
                        self.queue.mark_main_saved(number, main_pdf)
                        expected = "detail"
                        self.stage_changed.emit(number, expected)
                        self.message.emit("主页 PDF 已保存。请点击 FedEx 详情，再次点击保存按钮。")
                    else:
                        self.queue.mark_completed(number, main_pdf, saved.path)
                        self.completed.emit(ManualPodResult(number, main_pdf, saved.path))
                        self.stage_changed.emit(number, "completed")
                        self.message.emit("两份 PDF 已保存。请点击“下一票”；程序不会切换网页。")
                    self.queue_changed.emit()
                except Exception as exc:
                    message = str(exc)
                    if any(word in message.casefold() for word in (
                        "限流", "验证码", "too many", "access denied", "系统错误"
                    )):
                        self.queue.pause(number, message)
                        self.queue_changed.emit()
                        self.message.emit(f"当前票已进入暂停列表：{message}")
                        return "pause"
                    self.message.emit(f"未保存：{message}")
            if self.next_event.is_set():
                self.next_event.clear()
                current = self.queue.get(number)
                if current and current.state == "completed":
                    return "done"
                self.message.emit("当前票尚未完成两份 PDF；可继续保存、暂停或跳过。")
            try:
                if session.fill_after_user_click(number):
                    self.message.emit("单号已逐字输入，请点击 FedEx 的 TRACK。")
            except Exception:
                pass
            time.sleep(0.2)
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
            while not self.stop_event.is_set():
                task = self.queue.next_ready()
                if task is None:
                    break
                total = self.queue.counts()["total"]
                self.current.emit(task.number, task.position, total)
                if self._process(session, task) == "stop":
                    break
            self.finished_status.emit("已停止" if self.stop_event.is_set() else "当前可处理队列已结束")
        except Exception as exc:
            self.finished_status.emit(f"无法继续：{exc}")
        finally:
            if session is not None:
                session.close()
            if playwright is not None:
                playwright.stop()


class ExperimentalAutoPodWorker(QThread):
    message = Signal(str)
    completed = Signal(object)
    queue_changed = Signal()
    finished_status = Signal(str)

    def __init__(self, queue_path, output_dir, edge_path="", parent=None):
        super().__init__(parent)
        self.queue = FedExPodQueue(queue_path)
        self.output_dir = Path(output_dir)
        self.edge_path = edge_path if Path(str(edge_path)).name.casefold() == "msedge.exe" else ""
        self.stop_event = threading.Event()

    def run(self):
        playwright = session = None
        try:
            from playwright.sync_api import sync_playwright
            playwright = sync_playwright().start()
            session = FedExEdgePodSession(
                playwright,
                self.output_dir,
                edge_path=self.edge_path,
                minimize_browser=False,
                overwrite=False,
                log_func=self.message.emit,
            )

            def completed(result):
                self.completed.emit(
                    ManualPodResult(result.tracking_number, result.main_pdf, result.detail_pdf)
                )
                self.queue_changed.emit()

            outcome = run_experimental_auto(
                self.queue,
                session,
                log=self.message.emit,
                completed_callback=completed,
                stop_requested=self.stop_event.is_set,
            )
            if outcome.circuit_open:
                message = "实验自动模式已熔断；失败票已进入暂停列表"
            else:
                message = (
                    f"实验自动批次结束：处理 {outcome.processed}，"
                    f"完成 {outcome.completed}，暂停 {outcome.paused}"
                )
            self.finished_status.emit(message)
        except Exception as exc:
            self.finished_status.emit(f"实验自动模式无法继续：{exc}")
        finally:
            if session is not None:
                session.close()
            if playwright is not None:
                playwright.stop()


class FedExManualDialog(QDialog):
    completed = Signal(object)
    queue_finished = Signal()

    def __init__(self, numbers, output_dir, browser_type="edge", browser_path="",
                 parent=None, queue_path=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowModality(Qt.NonModal)
        self.setWindowTitle("FedEx POD · 半自动")
        self.resize(610, 460)
        self.setMinimumWidth(520)
        self.worker = None
        self.numbers = list(numbers)
        self.output_dir = Path(output_dir)
        self.browser_type = browser_type
        self.browser_path = browser_path
        self.queue = FedExPodQueue(queue_path or default_queue_path(output_dir))
        self.queue.add_numbers(self.numbers, source="本次查询结果")
        self.queue.sync_existing_pdfs(self.output_dir)
        self.current_number = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(9)
        self.current_label = QLabel("FedEx POD 队列")
        self.current_label.setObjectName("sectionTitle")
        layout.addWidget(self.current_label)
        self.stage_label = QLabel("用户负责 TRACK 和详情；程序只在点击保存按钮时检查当前页面。")
        layout.addWidget(self.stage_label)

        source_controls = QHBoxLayout()
        self.start_button = QPushButton("打开浏览器并开始")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start)
        self.auto_button = QPushButton(f"实验自动处理（最多 {AUTO_BATCH_LIMIT} 票）")
        self.auto_button.clicked.connect(self.start_auto)
        self.import_button = QPushButton("添加 Excel")
        self.import_button.clicked.connect(self.import_excel)
        self.copy_button = QPushButton("复制当前单号")
        self.copy_button.clicked.connect(self.copy_current)
        for button in (self.start_button, self.auto_button, self.import_button, self.copy_button):
            source_controls.addWidget(button)
        layout.addLayout(source_controls)

        action_controls = QHBoxLayout()
        self.print_button = QPushButton("保存当前页面 PDF")
        self.print_button.setObjectName("primaryButton")
        self.print_button.clicked.connect(self.save_current_page)
        self.next_button = QPushButton("下一票")
        self.next_button.clicked.connect(self.next_task)
        self.pause_button = QPushButton("暂停当前")
        self.pause_button.clicked.connect(self.pause_current)
        self.skip_button = QPushButton("跳过当前")
        self.skip_button.clicked.connect(self.skip)
        self.retry_button = QPushButton("重新准备")
        self.retry_button.clicked.connect(self.retry)
        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self.stop)
        for button in (self.print_button, self.next_button, self.pause_button,
                       self.skip_button, self.retry_button, self.stop_button):
            action_controls.addWidget(button)
        layout.addLayout(action_controls)

        layout.addWidget(QLabel("暂停列表（选择后可恢复）："))
        paused_controls = QHBoxLayout()
        self.paused_list = QListWidget()
        self.paused_list.setMaximumHeight(74)
        self.resume_button = QPushButton("恢复选中")
        self.resume_button.clicked.connect(self.resume_selected)
        paused_controls.addWidget(self.paused_list, 1)
        paused_controls.addWidget(self.resume_button)
        layout.addLayout(paused_controls)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        self._refresh_queue()

    def _refresh_queue(self):
        counts = self.queue.counts()
        if not self.current_number:
            self.current_label.setText(
                f"已完成 {counts['completed']} / {counts['total']}　"
                f"待处理 {counts['pending'] + counts['main_saved']}　暂停 {counts['paused']}"
            )
        self.paused_list.clear()
        for task in self.queue.tasks(("paused",)):
            self.paused_list.addItem(f"{task.number}　{task.reason}")
        self.start_button.setEnabled(
            not (self.worker and self.worker.isRunning())
            and bool(counts["pending"] + counts["main_saved"])
        )
        self.auto_button.setEnabled(
            not (self.worker and self.worker.isRunning())
            and bool(counts["pending"] + counts["main_saved"])
        )

    def start(self):
        if self.worker and self.worker.isRunning():
            return
        self.worker = ManualPodWorker([], self.output_dir, self.browser_type,
                                      self.browser_path, self.queue.path, self)
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.current.connect(self._set_current)
        self.worker.stage_changed.connect(self._set_stage)
        self.worker.copy_requested.connect(self._copy_number)
        self.worker.completed.connect(self.completed)
        self.worker.completed.connect(lambda _result: self._refresh_queue())
        self.worker.queue_changed.connect(self._refresh_queue)
        self.worker.finished_status.connect(self._finished)
        self.start_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.worker.start()

    def start_auto(self):
        if self.worker and self.worker.isRunning():
            return
        answer = QMessageBox.question(
            self,
            "FedEx 实验自动模式",
            "该模式默认关闭，每轮最多自动处理 10 票；遇到限流、验证码或连续失败会立即熔断。\n\n"
            "是否开始本轮实验自动处理？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.worker = ExperimentalAutoPodWorker(
            self.queue.path, self.output_dir, self.browser_path, self
        )
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.completed.connect(self.completed)
        self.worker.completed.connect(lambda _result: self._refresh_queue())
        self.worker.queue_changed.connect(self._refresh_queue)
        self.worker.finished_status.connect(self._finished)
        self.start_button.setEnabled(False)
        self.auto_button.setEnabled(False)
        self.import_button.setEnabled(False)
        for button in (self.print_button, self.next_button, self.pause_button,
                       self.skip_button, self.retry_button):
            button.setEnabled(False)
        self.log.appendPlainText("实验自动模式启动；本轮硬限制最多 10 票。")
        self.worker.start()

    def _set_current(self, number, index, total):
        self.current_number = number
        self.current_label.setText(f"{index} / {total}　当前：{number}")

    def _set_stage(self, number, stage):
        labels = {
            "main": "等待查询主页：点击输入框、TRACK，然后保存当前页面",
            "detail": "主页已保存：请点击 FedEx 详情，然后再次保存",
            "completed": "两份 PDF 已保存：请点击“下一票”",
        }
        if number == self.current_number:
            self.stage_label.setText(labels.get(stage, stage))

    def _copy_number(self, number):
        QApplication.clipboard().setText(number)
        self.log.appendPlainText(f"已复制：{number}")

    def copy_current(self):
        if self.current_number:
            self._copy_number(self.current_number)

    def import_excel(self):
        if self.worker and self.worker.isRunning():
            return
        path, _ = QFileDialog.getOpenFileName(self, "添加 FedEx POD Excel", "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            added = self.queue.import_excel(path)
            self.queue.sync_existing_pdfs(self.output_dir)
        except Exception as exc:
            QMessageBox.warning(self, "ShipmentTrack", str(exc))
            return
        self.log.appendPlainText(f"Excel 已添加 {len(added)} 个新运单：{path}")
        self._refresh_queue()

    def save_current_page(self):
        if self.worker and self.worker.isRunning():
            self.worker.print_event.set()

    def next_task(self):
        if self.worker and self.worker.isRunning():
            self.worker.next_event.set()

    def retry(self):
        if self.worker and self.worker.isRunning():
            self.worker.retry_event.set()

    def pause_current(self):
        if self.worker and self.worker.isRunning():
            self.worker.pause_event.set()

    def skip(self):
        if self.worker and self.worker.isRunning():
            self.worker.skip_event.set()

    def resume_selected(self):
        selected = self.paused_list.selectedItems()
        for item in selected:
            self.queue.resume(item.text().split()[0])
        if selected:
            self.log.appendPlainText(f"已恢复 {len(selected)} 票到待处理队列")
        self._refresh_queue()

    def stop(self):
        if self.worker:
            self.worker.stop_event.set()

    def _finished(self, message):
        self.log.appendPlainText(message)
        self.current_number = ""
        self.import_button.setEnabled(True)
        for button in (self.print_button, self.next_button, self.pause_button,
                       self.skip_button, self.retry_button):
            button.setEnabled(True)
        self._refresh_queue()
        counts = self.queue.counts()
        has_ready = bool(counts["pending"] + counts["main_saved"])
        self.start_button.setEnabled(has_ready)
        self.auto_button.setEnabled(has_ready)
        self.queue_finished.emit()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop_event.set()
            self.worker.wait(5000)
            if self.worker.isRunning():
                event.ignore()
                return
        super().closeEvent(event)
