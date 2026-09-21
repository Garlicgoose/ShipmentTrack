# -*- coding: utf-8 -*-
"""Shipment Track 入口。运行: python main.py"""
import logging
import importlib
import sys
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QTimer


def main():
    # QApplication 可能会消费命令行参数，必须提前读取冒烟标记。
    smoke_test = "--smoke-test" in sys.argv
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

    try:
        from ui.main_window import MainWindow, APP_ICON
        from ui.startup_dialog import StartupDialog
        from modules.real_browser import close_all_launched_browsers
    except Exception:
        if smoke_test:
            try:
                (BASE_DIR / "smoke-test-error.log").write_text(
                    traceback.format_exc(), encoding="utf-8"
                )
            except OSError:
                pass
            return 2
        raise
    app.setWindowIcon(QIcon(APP_ICON))
    # 退出时兜底：把程序启动的浏览器窗口全部关掉，不要留在桌面上
    app.aboutToQuit.connect(close_all_launched_browsers)

    # 打包后的离线冒烟测试：只验证依赖、资源和主窗口可创建，
    # 不进入授权检查，也不会启动任何查询任务。
    if smoke_test:
        try:
            for module_name in (
                "modules.tracking_runner",
                "modules.pod_audit",
                "modules.excel_reconcile",
                "modules.dhl_module",
                "modules.dsv_module",
                "modules.ei_module",
                "modules.ups_module",
                "modules.fedex_module",
                "modules.fedex_web_pod",
                "modules.fedex_manual_pod",
            ):
                importlib.import_module(module_name)
            from ui.main_window import PROFILE_AVATAR
            for resource in (APP_ICON, PROFILE_AVATAR):
                if not Path(resource).is_file():
                    raise FileNotFoundError(f"Packaged resource missing: {resource}")
                # 图片插件被裁掉时文件仍在但读不出来，必须实际解码一次
                if QPixmap(resource).isNull():
                    raise ValueError(f"Packaged resource unreadable: {resource}")
            window = MainWindow()
            window.show()
            QTimer.singleShot(100, window.close)
            QTimer.singleShot(150, app.quit)
            return app.exec()
        except Exception:
            try:
                (BASE_DIR / "smoke-test-error.log").write_text(
                    traceback.format_exc(), encoding="utf-8"
                )
            except OSError:
                pass
            return 3

    gate = StartupDialog()
    gate.granted.connect(gate.accept)
    if gate.exec() != StartupDialog.Accepted:
        return 1

    # Verify the signed in-memory document again after the startup dialog and
    # before constructing the main window.
    import license as license_mod
    ok, _mode, error = license_mod.revalidate_session(
        license_mod.get_current_machine_id()
    )
    if not ok:
        QMessageBox.critical(None, "Shipment Track", error)
        return 1

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
