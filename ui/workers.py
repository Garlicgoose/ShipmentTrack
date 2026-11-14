# -*- coding: utf-8 -*-
"""后台任务：QThread worker，UI 全程丝滑（线程降优先级，不抢资源）。"""
import ctypes
import inspect
import traceback
import threading

from PySide6.QtCore import QThread, Signal


class PauseController:
    """Cooperative pause that only blocks at explicit shipment boundaries."""

    def __init__(self):
        self._condition = threading.Condition()
        self._pause_requested = False

    def request_pause(self):
        with self._condition:
            self._pause_requested = True

    def resume(self):
        with self._condition:
            self._pause_requested = False
            self._condition.notify_all()

    def wait_if_paused(self, on_pause=None):
        with self._condition:
            if not self._pause_requested:
                return False
            if on_pause:
                on_pause()
            while self._pause_requested:
                self._condition.wait()
            return True


def _set_thread_idle_priority():
    """Windows 下将当前线程降到 IDLE(-15)，后台任务不抢 UI 资源。"""
    try:
        THREAD_SET_INFORMATION = 0x0020
        THREAD_QUERY_INFORMATION = 0x0040
        THREAD_PRIORITY_IDLE = -15
        k = ctypes.windll.kernel32
        h = k.OpenThread(THREAD_SET_INFORMATION | THREAD_QUERY_INFORMATION,
                         False, k.GetCurrentThreadId())
        if h:
            k.SetThreadPriority(h, THREAD_PRIORITY_IDLE)
            k.CloseHandle(h)
    except Exception:
        pass


class TaskWorker(QThread):
    log = Signal(str)
    progress = Signal(int)
    item = Signal(object)
    paused = Signal()
    finished_ok = Signal(bool, str)  # (ok, error_message)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        _set_thread_idle_priority()
        try:
            kwargs = {
                "log": self.log.emit,
                "progress": self.progress.emit,
            }
            parameters = inspect.signature(self._fn).parameters
            if "item" in parameters:
                kwargs["item"] = self.item.emit
            if "paused" in parameters:
                kwargs["paused"] = self.paused.emit
            self._fn(**kwargs)
            self.finished_ok.emit(True, "")
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.finished_ok.emit(False, str(exc))
