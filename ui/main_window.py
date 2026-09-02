# -*- coding: utf-8 -*-
"""Shipment Track 主窗口。"""
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QPushButton, QCheckBox, QProgressBar,
                               QPlainTextEdit, QMessageBox)

from units import get_base_path, read_json, write_json, detect_chrome_path
from ui.workers import TaskWorker
from ui.settings_dialog import SettingsDialog
from ui.about_dialog import AboutDialog, APP_NAME, APP_VERSION

APP_ICON = str(get_base_path() / "assets" / "app_icon.png")

DEFAULT_SETTINGS = {
    "tracking_input_file": "",
    "tracking_output_dir": "",
    "tracking_ei_email": "",
    "tracking_ei_password": "",
    "fedex_api_key": "",
    "fedex_api_secret": "",
    "chrome_path": "",
    "minimize_browser": True,
    "only_arrival": False,
}


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shipment Track")
        self.setWindowIcon(QIcon(APP_ICON))
        self.resize(760, 560)

        self.settings = dict(DEFAULT_SETTINGS)
        self._load_settings()
        # 首次运行自动探测 chrome 路径
        if not self.settings.get("chrome_path"):
            detected = detect_chrome_path()
            if detected:
                self.settings["chrome_path"] = detected
                self._save_settings()

        self._worker = None
        self._build_ui()

    # ---------------- UI ----------------

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # 顶栏：设置/关于（无标题文字，程序名放状态栏）
        top = QHBoxLayout()
        top.addStretch(1)
        settings_btn = QPushButton("设置")
        settings_btn.clicked.connect(self._open_settings)
        top.addWidget(settings_btn)
        about_btn = QPushButton("关于")
        about_btn.clicked.connect(self._open_about)
        top.addWidget(about_btn)
        self.settings_btn = settings_btn
        root.addLayout(top)

        # 复选框：只查状态（不下载 POD）
        self.only_arrival_box = QCheckBox("只查状态")
        self.only_arrival_box.setChecked(bool(self.settings.get("only_arrival", False)))
        self.only_arrival_box.toggled.connect(self._on_only_arrival_toggled)
        root.addWidget(self.only_arrival_box)

        # 开始按钮
        self.run_btn = QPushButton("开始查询")
        self.run_btn.setMinimumHeight(34)
        self.run_btn.clicked.connect(self._start)
        root.addWidget(self.run_btn)

        # 进度条（绿色 + 平滑动画）
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setStyleSheet(
            "QProgressBar { border: 1px solid #cccccc; border-radius: 3px;"
            " text-align: center; background: #f0f0f0; }"
            "QProgressBar::chunk { background-color: #4CAF50;"
            " border-radius: 2px; }")
        self._progress_anim = QPropertyAnimation(self.progress, b"value", self)
        self._progress_anim.setDuration(240)
        self._progress_anim.setEasingCurve(QEasingCurve.OutCubic)
        root.addWidget(self.progress)

        # 输出面板
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setStyleSheet(
            "font-family: Consolas, 'Microsoft YaHei UI'; font-size: 12px;")
        root.addWidget(self.log_view, 1)

        # 状态栏：左侧运行状态消息，右侧永久程序名
        from ui.about_dialog import APP_NAME, APP_VERSION
        name_label = QLabel(f"{APP_NAME} v{APP_VERSION}")
        name_label.setStyleSheet("color: #666;")
        self.statusBar().addPermanentWidget(name_label)
        self.statusBar().showMessage("就绪")

    # ---------------- 设置持久化 ----------------

    def _load_settings(self):
        data = read_json(get_base_path() / "settings.json", default={})
        if isinstance(data, dict):
            self.settings.update({k: data[k] for k in DEFAULT_SETTINGS
                                  if k in data})

    def _save_settings(self):
        write_json(get_base_path() / "settings.json", self.settings)

    def _on_only_arrival_toggled(self, checked):
        self.settings["only_arrival"] = checked
        self._save_settings()

    # ---------------- 按钮事件 ----------------

    def _open_settings(self):
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "查询进行中，请稍后再修改设置。")
            return
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings.update(dlg.values())
            self._save_settings()
            self.statusBar().showMessage("设置已保存", 3000)

    def _open_about(self):
        AboutDialog(self).exec()

    # ---------------- 执行 ----------------

    def _start(self):
        if self._worker is not None and self._worker.isRunning():
            return

        input_file = self.settings.get("tracking_input_file", "").strip()
        output_dir = self.settings.get("tracking_output_dir", "").strip()

        if not input_file:
            QMessageBox.warning(self, "提示", "请先在「设置」中选择输入 Excel。")
            self._open_settings()
            return
        if not Path(input_file).exists():
            QMessageBox.warning(self, "提示", f"找不到输入 Excel：{input_file}")
            return
        if not output_dir:
            QMessageBox.warning(self, "提示", "请先在「设置」中选择输出文件夹。")
            self._open_settings()
            return

        # FedEx 行预检：有 FedEx 运单但没填 API Key
        if not self.settings.get("fedex_api_key") or not self.settings.get("fedex_api_secret"):
            try:
                import pandas as pd
                df = pd.read_excel(input_file, engine="openpyxl")
                if df.shape[1] >= 2:
                    from modules.tracking_utils import normalize_tracking_company_name
                    companies = {normalize_tracking_company_name(str(v))
                                 for v in df.iloc[:, 0].dropna()}
                    if "FedEx" in companies:
                        QMessageBox.warning(
                            self, "提示",
                            "Excel 中有 FedEx 运单，但未填写 FedEx API Key/Secret。\n"
                            "请在「设置」中填写（developer.fedex.com 注册获取）。")
                        self._open_settings()
                        return
            except Exception:
                pass

        self.log_view.clear()
        self.progress.setValue(0)
        self.run_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.only_arrival_box.setEnabled(False)
        self.statusBar().showMessage("查询中...")

        save_pdf = not bool(self.settings.get("only_arrival", False))

        # 把当前设置固化到内存，避免运行中设置被改
        run_cfg = dict(self.settings)

        def worker(log, progress):
            from modules.tracking_runner import run_tracking
            run_tracking(
                input_file=run_cfg["tracking_input_file"],
                output_dir=run_cfg["tracking_output_dir"],
                # 填了 EI 凭据才登录，否则走匿名查询（避免无凭据时崩溃）
                ei_login_enabled=bool(run_cfg.get("tracking_ei_email"))
                and bool(run_cfg.get("tracking_ei_password")),
                ei_email=run_cfg.get("tracking_ei_email", ""),
                ei_password=run_cfg.get("tracking_ei_password", ""),
                fedex_api_key=run_cfg.get("fedex_api_key", ""),
                fedex_api_secret=run_cfg.get("fedex_api_secret", ""),
                chrome_path=run_cfg.get("chrome_path", ""),
                minimize_browser=bool(run_cfg.get("minimize_browser", True)),
                save_pdf=save_pdf,
                log=log,
                progress=progress,
            )

        self._worker = TaskWorker(worker, self)
        self._worker.log.connect(self._append_log)
        self._worker.progress.connect(self._smooth_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.start()

    def _append_log(self, msg):
        self.log_view.appendPlainText(str(msg))

    def _smooth_progress(self, value):
        """进度条平滑动画到目标值（避免跳变，视觉更丝滑）。"""
        self._progress_anim.stop()
        self._progress_anim.setStartValue(self.progress.value())
        self._progress_anim.setEndValue(int(value))
        self._progress_anim.start()

    def _on_finished(self, ok, err):
        self.run_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.only_arrival_box.setEnabled(True)
        self._smooth_progress(100 if ok else self.progress.value())

        if ok:
            self.statusBar().showMessage("完成")
            output_file = Path(self.settings.get("tracking_output_dir", "")) / "tracking_result.xlsx"
            QMessageBox.information(
                self, "完成",
                f"查询完成。\n输出文件：{output_file}")
        else:
            self.statusBar().showMessage("执行失败")
            self._append_log("错误：" + str(err))
            self._append_log(traceback.format_exc())
            QMessageBox.critical(self, "执行错误", str(err))
        self._worker = None
