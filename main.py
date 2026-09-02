# -*- coding: utf-8 -*-
"""Shipment Track 入口。运行: python main.py"""
import logging
import sys
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Shipment Track")
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    # 全局异常钩子：记录到文件 + 弹窗，避免闪退
    def excepthook(exc_type, exc_value, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with open(BASE_DIR / "shipment_track.log", "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass
        try:
            QMessageBox.critical(None, "Unexpected error", str(exc_value))
        except Exception:
            pass

    sys.excepthook = excepthook

    from ui.main_window import MainWindow, APP_ICON
    from ui.startup_dialog import StartupDialog
    app.setWindowIcon(QIcon(APP_ICON))

    gate = StartupDialog()
    gate.granted.connect(gate.accept)
    if gate.exec() != StartupDialog.Accepted:
        sys.exit(1)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
