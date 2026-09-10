# -*- coding: utf-8 -*-
"""后台任务：QThread worker，UI 全程丝滑（线程降优先级，不抢资源）。"""
import ctypes
import inspect
import traceback

from PySide6.QtCore import QThread, Signal


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
            self._fn(**kwargs)
            self.finished_ok.emit(True, "")
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.finished_ok.emit(False, str(exc))
