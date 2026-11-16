# -*- coding: utf-8 -*-
"""Button-driven FedEx webpage POD panel with a persistent queue."""
from __future__ import annotations

from pathlib import Path
import threading
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
)

from modules.fedex_manual_pod import ManualFedExPodSession, ManualPodResult
from modules.fedex_pod_auto import AUTO_BATCH_LIMIT, normalize_batch_limit, run_experimental_auto
from modules.fedex_pod_queue import FedExPodQueue
from modules.fedex_pod_segmented import (
    ITEM_INTERVAL_SECONDS,
    SEGMENTED_MAX_JOBS,
    SEGMENT_PAUSE_SECONDS,
    plan_segments,
    run_segmented_auto,
)
from modules.fedex_web_pod import FedExEdgePodSession
from units import detect_browser_path
from ui.components import ToggleSwitch


def default_queue_path(output_dir) -> Path:
    output = Path(output_dir)
    if output.name.casefold() == "fedex" and output.parent.name.casefold() == "pdf":
        root = output.parents[1]
    else:
        root = output
    return root / "fedex_pod_queue.json"


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
        self.pause_event = threading.Event()
        self.open_site_event = threading.Event()

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
            if self.retry_event.is_set():
                self.retry_event.clear()
                session.prepare(number)
                self.message.emit("已重新准备当前票；队列阶段和已保存 PDF 保持不变。")
            if self.open_site_event.is_set():
                self.open_site_event.clear()
                try:
                    session.open_tracking_site()
                    self.message.emit("已在受控浏览器中打开并连接 FedEx Tracking。")
                except Exception as exc:
                    self.message.emit(f"重新连接 FedEx 官网失败：{exc}")
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
                        self.message.emit("两份 PDF 已保存；下一票已自动复制。请在 FedEx 页面自行点击 TRACK。")
                    self.queue_changed.emit()
                    if saved.page_type == "detail":
                        return "paused" if self.pause_event.is_set() else "done"
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
            session.start()
            session.open_tracking_site()
            self.message.emit("已在受控浏览器中打开 FedEx Tracking；请只操作这个窗口。")
            while not self.stop_event.is_set():
                if self.pause_event.is_set():
                    break
                task = self.queue.next_ready()
                if task is None:
                    break
                total = self.queue.counts()["total"]
                self.current.emit(task.number, task.position, total)
                outcome = self._process(session, task)
                if outcome in {"stop", "pause", "paused"}:
                    if outcome == "paused":
                        self.message.emit("已在当前运单完成后暂停；点击“恢复”处理下一票。")
                    break
            if self.stop_event.is_set():
                self.finished_status.emit("已停止，队列进度已保存")
            elif self.pause_event.is_set() or self.queue.counts()["paused"]:
                self.finished_status.emit("已暂停，可恢复当前运单或继续队列")
            else:
                self.finished_status.emit("当前可处理队列已结束")
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

    def __init__(self, queue_path, output_dir, edge_path="", parent=None,
                 batch_limit=AUTO_BATCH_LIMIT):
        super().__init__(parent)
        self.queue = FedExPodQueue(queue_path)
        self.output_dir = Path(output_dir)
        self.edge_path = edge_path if Path(str(edge_path)).name.casefold() == "msedge.exe" else ""
        self.stop_event = threading.Event()
        self.batch_limit = max(1, int(batch_limit or AUTO_BATCH_LIMIT))

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
                batch_limit=self.batch_limit,
                log=self.message.emit,
                completed_callback=completed,
                stop_requested=self.stop_event.is_set,
                direct_download=True,
            )
            if outcome.circuit_open:
                message = "自动连续下载已暂停；失败票可从暂停位置恢复"
            else:
                message = (
                    f"自动连续下载结束：处理 {outcome.processed}，"
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


class SegmentedAutoPodWorker(QThread):
    message = Signal(str)
    completed = Signal(object)
    queue_changed = Signal()
    finished_status = Signal(str)
    failed = Signal(str)

    def __init__(self, queue_path, output_dir, edge_path="", parent=None):
        super().__init__(parent)
        self.queue = FedExPodQueue(queue_path)
        self.output_dir = Path(output_dir)
        self.edge_path = edge_path if Path(str(edge_path)).name.casefold() == "msedge.exe" else ""
        self.stop_event = threading.Event()

    def _interruptible_delay(self, seconds):
        remaining = max(0, int(seconds))
        while remaining > 0 and not self.stop_event.is_set():
            step = min(60, remaining)
            if self.stop_event.wait(step):
                return
            remaining -= step
            if remaining and seconds >= SEGMENT_PAUSE_SECONDS:
                self.message.emit(f"后台等待中，剩余约 {max(1, remaining // 60)} 分钟")

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

            outcome = run_segmented_auto(
                self.queue,
                session,
                log=self.message.emit,
                completed_callback=completed,
                stop_requested=self.stop_event.is_set,
                delay=self._interruptible_delay,
            )
            if outcome.reason:
                message = (
                    f"分段自动下载失败并停止：{outcome.failed_number}\n{outcome.reason}\n"
                    f"已完成 {outcome.completed} 票，失败票已进入暂停列表。"
                )
                self.failed.emit(message)
            elif outcome.stopped:
                message = "分段自动下载已停止，队列进度已保存"
            else:
                message = (
                    f"分段自动下载结束：目标 {outcome.target}，完成 {outcome.completed}，"
                    f"暂停 {outcome.paused}，完成分段 {outcome.segments_completed}"
                )
            self.finished_status.emit(message)
        except Exception as exc:
            message = f"分段自动下载无法继续：{exc}"
            self.failed.emit(message)
            self.finished_status.emit(message)
        finally:
            if session is not None:
                session.close()
            if playwright is not None:
                playwright.stop()


class FedExManualDialog(QDialog):
    completed = Signal(object)
    queue_finished = Signal()

    def __init__(self, numbers, output_dir, browser_type="edge", browser_path="",
                 parent=None, queue_path=None, auto_batch_limit=AUTO_BATCH_LIMIT):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window)
        self.setWindowModality(Qt.NonModal)
        self.setWindowTitle("FedEx POD 任务中心")
        self.resize(760, 500)
        self.setMinimumWidth(680)
        self.worker = None
        self._active = False
        self._paused = False
        self.numbers = list(dict.fromkeys(str(number) for number in numbers))
        self._session_numbers = list(self.numbers)
        self.output_dir = Path(output_dir)
        self.browser_type = browser_type
        self.browser_path = browser_path
        self.auto_batch_limit = normalize_batch_limit(auto_batch_limit)
        self.queue = FedExPodQueue(queue_path or default_queue_path(output_dir))
        self.queue.add_numbers(self.numbers, source="本次查询结果")
        self.queue.sync_existing_pdfs(self.output_dir)
        self.current_number = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.current_label = QLabel("FedEx POD 队列")
        self.current_label.setObjectName("sectionTitle")
        header.addWidget(self.current_label, 1)
        self.pin_switch = ToggleSwitch()
        self.pin_switch.toggled.connect(self._set_pinned)
        header.addWidget(QLabel("置顶"))
        header.addWidget(self.pin_switch)
        layout.addLayout(header)

        self.stage_label = QLabel("自动模式保存官网主页和详情；手动模式由你操作 TRACK，并用“保存”保存当前页。")
        self.stage_label.setObjectName("muted")
        layout.addWidget(self.stage_label)

        controls = QHBoxLayout()
        self.automatic_switch = ToggleSwitch()
        self.automatic_switch.setChecked(True)
        self.automatic_label = QLabel("自动下载")
        controls.addWidget(self.automatic_label)
        controls.addWidget(self.automatic_switch)
        self.segment_switch = ToggleSwitch()
        self.segment_switch.setChecked(True)
        self.segment_label = QLabel("分段")
        controls.addWidget(self.segment_label)
        controls.addWidget(self.segment_switch)
        controls.addStretch(1)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.refresh_queue)
        controls.addWidget(self.refresh_button)
        self.import_button = QPushButton("导入 Excel")
        self.import_button.clicked.connect(self.import_excel)
        controls.addWidget(self.import_button)
        layout.addLayout(controls)

        self.automatic_switch.toggled.connect(self._update_mode)
        self.segment_switch.toggled.connect(self._update_mode)

        actions = QHBoxLayout()
        self.start_button = QPushButton("开始")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start)
        self.pause_button = QPushButton("暂停")
        self.pause_button.clicked.connect(self.pause)
        self.resume_button = QPushButton("恢复")
        self.resume_button.clicked.connect(self.resume)
        self.print_button = QPushButton("保存")
        self.print_button.setObjectName("primaryButton")
        self.print_button.clicked.connect(self.save_current_page)
        self.copy_button = QPushButton("复制当前单号")
        self.copy_button.clicked.connect(self.copy_current)
        self.connect_site_button = QPushButton("重新连接官网")
        self.connect_site_button.clicked.connect(self.open_tracking_site)
        for button in (self.start_button, self.pause_button, self.resume_button,
                       self.print_button, self.copy_button, self.connect_site_button):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("运行日志")
        layout.addWidget(self.log, 1)
        self._update_mode()
        self._refresh_queue()

    def _set_pinned(self, pinned):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(pinned))
        self.show()
        self.raise_()

    def _update_mode(self, *_args):
        automatic = self.automatic_switch.isChecked()
        self.segment_label.setText("分段" if self.segment_switch.isChecked() else "连续")
        self.automatic_label.setText("自动下载" if automatic else "手动下载")
        self.segment_switch.setVisible(automatic)
        self.segment_label.setVisible(automatic)
        self.print_button.setVisible(not automatic)
        self.copy_button.setVisible(not automatic)
        self.connect_site_button.setVisible(not automatic)
        self.stage_label.setText(
            "自动模式下载官网主页和详情；遇到问题会暂停当前运单。"
            if automatic else
            "手动模式：点击 TRACK、打开详情，再分别点“保存”；完成后自动复制下一票。"
        )
        for control in (self.automatic_switch, self.segment_switch):
            control.setEnabled(not self._active)
        self._refresh_controls()

    def _refresh_queue(self):
        counts = self.queue.counts()
        total = counts["total"]
        completed = counts["completed"]
        ready = counts["pending"] + counts["main_saved"]
        waiting = counts["paused"]
        self.current_label.setText(
            f"当前：{self.current_number}" if self.current_number else
            f"已完成 {completed}/{total}　待处理 {ready}　暂停 {waiting}"
        )
        self.progress.setValue(round(100 * completed / total) if total else 0)
        self._refresh_controls()

    def _refresh_controls(self):
        counts = self.queue.counts()
        ready = counts["pending"] + counts["main_saved"]
        can_run = ready > 0 or counts["paused"] > 0
        self.start_button.setEnabled(
            not self._active and ready > 0 and not self._paused and counts["paused"] == 0
        )
        self.pause_button.setEnabled(self._active and not self._paused)
        self.resume_button.setEnabled(not self._active and can_run and (self._paused or counts["paused"] > 0))
        self.refresh_button.setEnabled(not self._active)
        self.import_button.setEnabled(not self._active)
        self.print_button.setEnabled(self._active and not self.automatic_switch.isChecked())
        self.copy_button.setEnabled(not self._active and bool(self.current_number))
        self.connect_site_button.setEnabled(self._active and not self.automatic_switch.isChecked())

    def start(self):
        if self._active:
            return
        if self.automatic_switch.isChecked():
            if self.segment_switch.isChecked():
                self._start_segmented()
            else:
                self._start_continuous()
        else:
            self._start_manual()

    def start_segmented(self):
        self.automatic_switch.setChecked(True)
        self.segment_switch.setChecked(True)
        self.start()

    def start_auto(self):
        self.automatic_switch.setChecked(True)
        self.segment_switch.setChecked(False)
        self.start()

    def _wire_worker(self, worker):
        self.worker = worker
        worker.message.connect(self.log.appendPlainText)
        worker.completed.connect(self.completed)
        worker.completed.connect(lambda _result: self._refresh_queue())
        worker.queue_changed.connect(self._refresh_queue)
        worker.finished_status.connect(self._finished)
        if isinstance(worker, ManualPodWorker):
            worker.current.connect(self._set_current)
            worker.stage_changed.connect(self._set_stage)
            worker.copy_requested.connect(self._copy_number)
        if isinstance(worker, SegmentedAutoPodWorker):
            worker.failed.connect(self._show_segmented_failure)
        self._active = True
        self._paused = False
        self._update_mode()
        worker.start()

    def _start_manual(self):
        worker = ManualPodWorker([], self.output_dir, self.browser_type,
                                 self.browser_path, self.queue.path, self)
        self._wire_worker(worker)
        self.log.appendPlainText("手动下载开始")

    def _start_segmented(self):
        worker = SegmentedAutoPodWorker(
            self.queue.path, self.output_dir, self.browser_path, self
        )
        self._wire_worker(worker)
        self.log.appendPlainText("自动分段下载开始")

    def _start_continuous(self):
        ready = self.queue.counts()["pending"] + self.queue.counts()["main_saved"]
        worker = ExperimentalAutoPodWorker(
            self.queue.path, self.output_dir, self.browser_path, self,
            batch_limit=max(1, ready),
        )
        self._wire_worker(worker)
        self.log.appendPlainText("自动连续下载开始")

    def pause(self):
        if not self._active or self.worker is None:
            return
        self._paused = True
        if isinstance(self.worker, ManualPodWorker):
            self.worker.pause_event.set()
            self.log.appendPlainText("已请求暂停；当前运单完成后暂停队列")
        else:
            self.worker.stop_event.set()
            self.log.appendPlainText("已请求暂停；当前运单完成后暂停队列")
        self.pause_button.setEnabled(False)
        self._refresh_controls()

    def resume(self):
        if self._active:
            return
        paused_tasks = self.queue.tasks(("paused",))
        if paused_tasks:
            task = paused_tasks[0]
            self.queue.resume(task.number)
            self.log.appendPlainText(f"恢复运单 {task.number}，从已保存阶段继续")
        self._paused = False
        self._refresh_queue()
        self.start()

    def refresh_queue(self):
        if self._active:
            return
        numbers = list(dict.fromkeys(self._session_numbers))
        old = len(self.queue.tasks())
        kept = self.queue.retain_numbers(numbers, source="本次运单")
        removed = max(0, old - len(kept))
        self.queue.sync_existing_pdfs(self.output_dir)
        self.current_number = ""
        self.log.appendPlainText(
            f"队列已刷新：移除 {removed} 个旧运单，保留本次 {len(kept)} 个；已有 PDF 保留。"
        )
        self._refresh_queue()

    def _set_current(self, number, index, total):
        self.current_number = number
        self.current_label.setText(f"{index}/{total}　当前：{number}")
        self._refresh_controls()

    def _set_stage(self, number, stage):
        labels = {
            "main": "等待主页：点击 TRACK，确认结果后点“保存”",
            "detail": "主页已保存：在 FedEx 页面打开详情后点“保存”",
            "completed": "两页已保存；下一票已复制，请自行点击 TRACK",
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
        if self._active:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 FedEx 运单", "", "Excel (*.xlsx *.xlsm)"
        )
        if not path:
            return
        try:
            requested_numbers = self.queue.read_excel_numbers(path)
            added = self.queue.add_numbers(
                requested_numbers, source=str(Path(path).resolve())
            )
            self._session_numbers.extend(requested_numbers)
            self._session_numbers = list(dict.fromkeys(self._session_numbers))
            self.queue.sync_existing_pdfs(self.output_dir)
        except Exception as exc:
            QMessageBox.warning(self, "ShipmentTrack", str(exc))
            return
        self.log.appendPlainText(f"已导入 {len(added)} 个新运单")
        self._refresh_queue()

    def save_current_page(self):
        if isinstance(self.worker, ManualPodWorker) and self._active:
            self.worker.print_event.set()

    def open_tracking_site(self):
        if isinstance(self.worker, ManualPodWorker) and self._active:
            self.worker.open_site_event.set()

    def _finished(self, message):
        self.log.appendPlainText(message)
        self.current_number = ""
        self._active = False
        self.worker = None
        counts = self.queue.counts()
        has_work = bool(counts["pending"] + counts["main_saved"] + counts["paused"])
        self._paused = has_work and (
            self._paused or "暂停" in message or counts["paused"] > 0
        )
        self._update_mode()
        self._refresh_queue()
        self.queue_finished.emit()

    def _show_segmented_failure(self, message):
        QMessageBox.warning(self, "FedEx 自动下载已暂停", str(message))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop_event.set()
            self.worker.wait(5000)
            if self.worker.isRunning():
                event.ignore()
                return
        super().closeEvent(event)
