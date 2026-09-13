# -*- coding: utf-8 -*-
"""ShipmentTrack 原生主窗口。"""
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QParallelAnimationGroup,
    QPropertyAnimation,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QColor, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.excel_reconcile import merge_and_reconcile_excel
from modules.settings_store import SettingsStore
from ui.components import (
    ClickableFrame,
    CircularProgress,
    OpenFileButton,
    PathField,
    ProfilePopup,
    ToggleSwitch,
    circular_pixmap,
    position_popup,
)
from ui.settings_page import SettingsPage
from ui.styles import APP_STYLE
from ui.workers import TaskWorker
from units import detect_chrome_path, get_resource_path


APP_ICON = str(get_resource_path() / "assets" / "app_icon.png")
PROFILE_AVATAR = str(get_resource_path() / "assets" / "github_avatar.jpg")
PROFILE_NAME = "Garlicgoose"
CARRIER_NAMES = ("FedEx", "DHL", "UPS", "EI", "DSV")


class MainWindow(QMainWindow):
    def __init__(self, parent=None, settings_store=None):
        super().__init__(parent)
        self.store = settings_store or SettingsStore()
        self.settings = self.store.load_settings()
        if not self.settings.get("chrome_path"):
            detected = detect_chrome_path()
            if detected:
                self.settings["chrome_path"] = detected
                self.store.save_settings(self.settings)

        self._tracking_worker = None
        self._excel_worker = None
        self._page_animation = None
        self._page_overlay = None
        self._page_transitioning = False
        self._tracking_output_paths = {}
        self._excel_output_paths = {}
        self._tracking_run_output_dir = None
        self._tracking_counts = {
            "total": 0, "delivered": 0, "transit": 0, "attention": 0
        }
        self._carrier_timings = {
            carrier: {"total": 0.0, "count": 0} for carrier in CARRIER_NAMES
        }
        self._tracking_elapsed = QElapsedTimer()
        self._tracking_timer = QTimer(self)
        self._tracking_timer.setInterval(500)
        self._tracking_timer.timeout.connect(self._update_tracking_elapsed)
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("ShipmentTrack")
        self.setWindowIcon(QIcon(APP_ICON))
        self.resize(1180, 760)
        self.setMinimumSize(980, 650)
        self.setStyleSheet(APP_STYLE)

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 18)
        content_layout.setSpacing(16)
        self.page_title = QLabel("跟踪")
        self.page_title.setObjectName("pageTitle")
        content_layout.addWidget(self.page_title)
        self.stack = QStackedWidget()
        self.tracking_page = self._build_tracking_page()
        self.excel_page = self._build_excel_page()
        self.settings_page = SettingsPage(self.store)
        self.settings_page.saved.connect(self._on_settings_saved)
        self.settings_page.message.connect(self._show_status)
        self.stack.addWidget(self.tracking_page)
        self.stack.addWidget(self.excel_page)
        self.stack.addWidget(self.settings_page)
        content_layout.addWidget(self.stack, 1)
        root_layout.addWidget(content, 1)

        self.setCentralWidget(root)
        self.statusBar().showMessage("就绪")

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(168)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 14)
        layout.setSpacing(7)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        for index, title in enumerate(("跟踪", "Excel 合并与核对", "设置")):
            button = QPushButton(title)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, page=index, label=title: self._switch_page(page, label)
            )
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        layout.addStretch(1)

        profile_line = QFrame()
        profile_line.setFixedHeight(1)
        profile_line.setStyleSheet("background:#29485F;border:none;")
        layout.addWidget(profile_line)
        layout.addSpacing(8)
        self.profile_button = ClickableFrame()
        self.profile_button.setObjectName("profileButton")
        self.profile_button.setCursor(Qt.PointingHandCursor)
        profile = QHBoxLayout(self.profile_button)
        profile.setContentsMargins(6, 7, 6, 7)
        avatar = QLabel()
        avatar.setObjectName("profileAvatar")
        avatar.setPixmap(circular_pixmap(PROFILE_AVATAR, 36))
        avatar.setFixedSize(36, 36)
        profile.addStretch(1)
        profile.addWidget(avatar)
        profile.addStretch(1)
        self.profile_popup = ProfilePopup(PROFILE_AVATAR, PROFILE_NAME, self)
        self.profile_button.clicked.connect(
            lambda: position_popup(self.profile_popup, self.profile_button)
        )
        layout.addWidget(self.profile_button)
        return sidebar

    def _build_tracking_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        overview = QFrame()
        overview.setObjectName("card")
        overview_layout = QHBoxLayout(overview)
        overview_layout.setContentsMargins(20, 13, 20, 13)
        overview_layout.setSpacing(16)
        self.delivery_ring = CircularProgress()
        overview_layout.addWidget(self.delivery_ring)
        ring_text = QVBoxLayout()
        ring_text.setSpacing(3)
        ring_title = QLabel("送达进度")
        ring_title.setObjectName("sectionTitle")
        self.overview_state_label = QLabel("等待查询")
        self.overview_state_label.setObjectName("muted")
        ring_text.addWidget(ring_title)
        ring_text.addWidget(self.overview_state_label)
        overview_layout.addLayout(ring_text)
        overview_layout.addSpacing(16)
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setStyleSheet("color:#DDE6ED;")
        overview_layout.addWidget(separator)
        elapsed = QVBoxLayout()
        elapsed.setSpacing(3)
        elapsed_title = QLabel("用时")
        elapsed_title.setObjectName("muted")
        self.elapsed_label = QLabel("00:00")
        self.elapsed_label.setObjectName("sectionTitle")
        elapsed.addWidget(elapsed_title)
        elapsed.addWidget(self.elapsed_label)
        overview_layout.addLayout(elapsed, 1)
        average_cards = QHBoxLayout()
        average_cards.setSpacing(8)
        self.carrier_average_labels = {}
        for carrier in CARRIER_NAMES:
            card = QFrame()
            card.setObjectName("averageCard")
            card.setFixedSize(76, 58)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            card_layout.setSpacing(1)
            name = QLabel(carrier)
            name.setObjectName("averageCarrier")
            value = QLabel("--")
            value.setObjectName("averageValue")
            card_layout.addWidget(name)
            card_layout.addWidget(value)
            self.carrier_average_labels[carrier] = value
            average_cards.addWidget(card)
        overview_layout.addLayout(average_cards)
        overview_layout.addStretch(1)
        layout.addWidget(overview)

        query_card = QFrame()
        query_card.setObjectName("card")
        query_layout = QVBoxLayout(query_card)
        query_layout.setContentsMargins(18, 16, 18, 16)
        query_layout.setSpacing(12)
        query_title = QLabel("新建查询")
        query_title.setObjectName("sectionTitle")
        query_layout.addWidget(query_title)
        fields = QHBoxLayout()
        fields.setSpacing(12)
        input_box = QVBoxLayout()
        input_box.addWidget(self._field_label("运单 Excel"))
        self.tracking_input = PathField(
            self.settings.get("tracking_input_file", ""), mode="file"
        )
        input_box.addWidget(self.tracking_input)
        fields.addLayout(input_box, 5)
        output_box = QVBoxLayout()
        output_box.addWidget(self._field_label("输出文件夹"))
        self.tracking_output = PathField(
            self.settings.get("tracking_output_dir", ""), mode="dir"
        )
        output_box.addWidget(self.tracking_output)
        fields.addLayout(output_box, 5)
        mode_box = QVBoxLayout()
        mode_box.addWidget(self._field_label("下载"))
        mode_row = QHBoxLayout()
        self.pod_switch = ToggleSwitch()
        self.pod_switch.setObjectName("podSwitch")
        self.pod_switch.setChecked(not bool(self.settings.get("only_arrival")))
        self.pod_switch.setToolTip("关闭后只查询状态，不下载 POD")
        mode_row.addWidget(self.pod_switch)
        mode_row.addWidget(QLabel("POD"))
        mode_row.addStretch(1)
        mode_box.addLayout(mode_row)
        fields.addLayout(mode_box, 3)
        self.run_button = QPushButton("开始查询")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self._start_tracking)
        fields.addWidget(self.run_button, 0, Qt.AlignBottom)
        query_layout.addLayout(fields)
        progress_row = QHBoxLayout()
        self.tracking_progress = QProgressBar()
        self.tracking_progress.setRange(0, 100)
        self.tracking_progress.setValue(0)
        self.tracking_progress_text = QLabel("0%")
        self.tracking_progress_text.setObjectName("muted")
        progress_row.addWidget(self.tracking_progress, 1)
        progress_row.addWidget(self.tracking_progress_text)
        query_layout.addLayout(progress_row)
        self._tracking_progress_anim = self._make_progress_animation(self.tracking_progress)
        layout.addWidget(query_card)

        results_card = QFrame()
        results_card.setObjectName("card")
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(18, 15, 18, 15)
        results_layout.setSpacing(10)
        results_title = QLabel("查询明细")
        results_title.setObjectName("sectionTitle")
        filter_row = QHBoxLayout()
        filter_row.addWidget(results_title)
        filter_row.addStretch(1)
        self.tracking_filter_group = QButtonGroup(self)
        self.tracking_filter_group.setExclusive(True)
        self.tracking_filter_buttons = {}
        for key, text in (
            ("", "全部"),
            ("delivered", "已送达"),
            ("transit", "运输中"),
            ("attention", "需要关注"),
        ):
            button = QPushButton(text)
            button.setObjectName("filterChip")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, bucket=key: self._set_tracking_filter(bucket)
            )
            self.tracking_filter_group.addButton(button)
            self.tracking_filter_buttons[key] = button
            filter_row.addWidget(button)
        self.tracking_filter_buttons[""].setChecked(True)
        self._tracking_filter_bucket = ""
        self.tracking_search = QLineEdit()
        self.tracking_search.setPlaceholderText("搜索运单号")
        self.tracking_search.setMaximumWidth(210)
        self.tracking_search.textChanged.connect(self._filter_tracking_rows)
        filter_row.addWidget(self.tracking_search)
        results_layout.addLayout(filter_row)
        self.tracking_table = QTableWidget(0, 7)
        self.tracking_table.setObjectName("trackingTable")
        self.tracking_table.setHorizontalHeaderLabels(
            ("运单号", "承运商", "状态", "抵达时间", "用时(秒)", "POD", "备注")
        )
        self.tracking_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tracking_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tracking_table.setAlternatingRowColors(False)
        self.tracking_table.setShowGrid(False)
        self.tracking_table.verticalHeader().setVisible(False)
        self.tracking_table.verticalHeader().setDefaultSectionSize(40)
        self.tracking_table.cellClicked.connect(self._handle_tracking_cell_click)
        self.tracking_table.cellDoubleClicked.connect(self._show_tracking_detail)
        header = self.tracking_table.horizontalHeader()
        for column in range(6):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        results_layout.addWidget(self.tracking_table, 1)
        log_header = QHBoxLayout()
        log_title = QLabel("运行记录")
        log_title.setObjectName("muted")
        log_header.addWidget(log_title)
        log_header.addStretch(1)
        self.open_tracking_result = OpenFileButton("打开结果")
        self.open_cleaned_result = OpenFileButton("打开清洗文件")
        self.open_pod_audit = OpenFileButton("打开 POD 抽查")
        log_header.addWidget(self.open_tracking_result)
        log_header.addWidget(self.open_cleaned_result)
        log_header.addWidget(self.open_pod_audit)
        results_layout.addLayout(log_header)
        self.tracking_log = QPlainTextEdit()
        self.tracking_log.setObjectName("trackingLog")
        self.tracking_log.setReadOnly(True)
        self.tracking_log.setMaximumHeight(92)
        self.tracking_log.setPlaceholderText("运行日志")
        results_layout.addWidget(self.tracking_log)
        layout.addWidget(results_card, 1)
        return page

    def _build_excel_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        input_card = QFrame()
        input_card.setObjectName("card")
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(18, 16, 18, 16)
        input_layout.setSpacing(10)
        title = QLabel("合并并核对")
        title.setObjectName("sectionTitle")
        input_layout.addWidget(title)
        for label, attribute, value, mode in (
            ("检验表文件夹", "inspect_input", self.settings.get("inspect_input_dir", ""), "dir"),
            ("Droplist 文件夹", "droplist_input", self.settings.get("droplist_input_dir", ""), "dir"),
            ("输出文件夹", "excel_output", self.settings.get("excel_output_dir", ""), "dir"),
        ):
            row = QHBoxLayout()
            caption = self._field_label(label)
            caption.setFixedWidth(112)
            field = PathField(value, mode=mode)
            setattr(self, attribute, field)
            row.addWidget(caption)
            row.addWidget(field, 1)
            input_layout.addLayout(row)
        action_row = QHBoxLayout()
        self.excel_progress = QProgressBar()
        self.excel_progress.setRange(0, 100)
        self.excel_progress.setValue(0)
        self.excel_progress_text = QLabel("0%")
        self.excel_progress_text.setObjectName("muted")
        self.excel_run_button = QPushButton("开始合并与核对")
        self.excel_run_button.setObjectName("primaryButton")
        self.excel_run_button.clicked.connect(self._start_excel)
        action_row.addWidget(self.excel_progress, 1)
        action_row.addWidget(self.excel_progress_text)
        action_row.addSpacing(10)
        action_row.addWidget(self.excel_run_button)
        input_layout.addLayout(action_row)
        self._excel_progress_anim = self._make_progress_animation(self.excel_progress)
        layout.addWidget(input_card)

        results_card = QFrame()
        results_card.setObjectName("card")
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(18, 15, 18, 15)
        results_layout.setSpacing(10)
        summary_row = QHBoxLayout()
        self.excel_summary = QLabel("尚未运行")
        self.excel_summary.setObjectName("muted")
        summary_row.addWidget(self.excel_summary, 1)
        self.open_inspect_output = OpenFileButton("打开合并检验表")
        self.open_droplist_output = OpenFileButton("打开合并 Droplist")
        summary_row.addWidget(self.open_inspect_output)
        summary_row.addWidget(self.open_droplist_output)
        results_layout.addLayout(summary_row)
        self.excel_table = QTableWidget(0, 6)
        self.excel_table.setObjectName("excelTable")
        self.excel_table.setHorizontalHeaderLabels(
            ("日期", "类型", "检验表数量", "Droplist 数量", "差异", "结果")
        )
        self.excel_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.excel_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.excel_table.setShowGrid(False)
        self.excel_table.verticalHeader().setVisible(False)
        self.excel_table.verticalHeader().setDefaultSectionSize(40)
        self.excel_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        results_layout.addWidget(self.excel_table, 1)
        layout.addWidget(results_card, 1)
        return page

    @staticmethod
    def _field_label(text):
        label = QLabel(text)
        label.setObjectName("muted")
        return label

    def _switch_page(self, index, title):
        if (
            self._page_transitioning
            or self.stack.currentIndex() == index
            or not 0 <= index < self.stack.count()
        ):
            return
        self._page_transitioning = True
        for button in self.nav_buttons:
            button.setEnabled(False)

        old_page = self.stack.currentWidget()
        overlay = QLabel(self.stack)
        overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        overlay.setGeometry(self.stack.rect())
        overlay.setPixmap(old_page.grab())
        overlay.setScaledContents(True)
        overlay.show()
        overlay.raise_()
        overlay_effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(overlay_effect)
        self._page_overlay = overlay

        self.stack.setUpdatesEnabled(False)
        self.stack.setCurrentIndex(index)
        self.page_title.setText(title)
        self._refresh_output_buttons(index)
        new_page = self.stack.currentWidget()
        new_effect = QGraphicsOpacityEffect(new_page)
        new_effect.setOpacity(0.0)
        new_page.setGraphicsEffect(new_effect)
        self.stack.setUpdatesEnabled(True)
        new_page.update()
        QTimer.singleShot(
            16,
            lambda: self._crossfade_page(
                new_page, new_effect, overlay, overlay_effect
            ),
        )

    def _crossfade_page(self, page, effect, overlay, overlay_effect):
        fade_in = QPropertyAnimation(effect, b"opacity")
        fade_in.setDuration(340)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.InOutCubic)
        fade_out = QPropertyAnimation(overlay_effect, b"opacity")
        fade_out.setDuration(340)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InOutCubic)
        group = QParallelAnimationGroup(self)
        group.addAnimation(fade_in)
        group.addAnimation(fade_out)
        group.finished.connect(
            lambda: self._finish_page_transition(page, overlay)
        )
        self._page_animation = group
        group.start()

    def _finish_page_transition(self, page, overlay):
        page.setGraphicsEffect(None)
        overlay.hide()
        overlay.deleteLater()
        self._page_overlay = None
        self._page_transitioning = False
        for button in self.nav_buttons:
            button.setEnabled(True)

    def _refresh_output_buttons(self, index):
        if index == 0:
            pairs = (
                (self.open_tracking_result, "result"),
                (self.open_cleaned_result, "cleaned"),
                (self.open_pod_audit, "audit"),
            )
            paths = self._tracking_output_paths
        elif index == 1:
            pairs = (
                (self.open_inspect_output, "inspect"),
                (self.open_droplist_output, "droplist"),
            )
            paths = self._excel_output_paths
        else:
            return
        for button, key in pairs:
            button.set_path(paths.get(key, ""))

    @staticmethod
    def _make_progress_animation(progress_bar):
        animation = QPropertyAnimation(progress_bar, b"value", progress_bar)
        animation.setDuration(240)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        return animation

    def _animate_progress(self, progress_bar, animation, label, value):
        value = max(0, min(100, int(value)))
        animation.stop()
        animation.setStartValue(progress_bar.value())
        animation.setEndValue(value)
        animation.start()
        label.setText(f"{value}%")

    def _start_tracking(self):
        if self._tracking_worker and self._tracking_worker.isRunning():
            return
        input_file = self.tracking_input.value()
        output_dir = self.tracking_output.value()
        if not input_file or not Path(input_file).is_file():
            QMessageBox.warning(self, "ShipmentTrack", "请选择有效的运单 Excel。")
            return
        if not output_dir:
            QMessageBox.warning(self, "ShipmentTrack", "请选择输出文件夹。")
            return

        settings = dict(self.settings)
        settings["tracking_input_file"] = input_file
        settings["tracking_output_dir"] = output_dir
        settings["only_arrival"] = not self.pod_switch.isChecked()
        self.store.save_settings(settings)
        self.settings = settings
        self._tracking_run_output_dir = Path(output_dir).expanduser().absolute()
        self.tracking_table.setRowCount(0)
        self.tracking_log.clear()
        for button in (
            self.open_tracking_result,
            self.open_cleaned_result,
            self.open_pod_audit,
        ):
            button.set_path("")
        self._tracking_output_paths = {}
        self._tracking_counts = {
            "total": 0, "delivered": 0, "transit": 0, "attention": 0
        }
        self._carrier_timings = {
            carrier: {"total": 0.0, "count": 0} for carrier in CARRIER_NAMES
        }
        for label in self.carrier_average_labels.values():
            label.setText("--")
        self._update_tracking_stats()
        self.overview_state_label.setText("正在查询")
        self.elapsed_label.setText("00:00")
        self._tracking_elapsed.start()
        self._tracking_timer.start()
        self._set_tracking_running(True)
        self._animate_progress(self.tracking_progress, self._tracking_progress_anim, self.tracking_progress_text, 0)

        run_settings = dict(settings)
        delivery_statuses = self.store.load_delivery_statuses()

        def task(log, progress, item):
            from modules.tracking_runner import run_tracking
            return run_tracking(
                input_file=run_settings["tracking_input_file"],
                output_dir=run_settings["tracking_output_dir"],
                ei_login_enabled=bool(run_settings.get("tracking_ei_email"))
                and bool(run_settings.get("tracking_ei_password")),
                ei_email=run_settings.get("tracking_ei_email", ""),
                ei_password=run_settings.get("tracking_ei_password", ""),
                fedex_api_key=run_settings.get("fedex_api_key", ""),
                fedex_api_secret=run_settings.get("fedex_api_secret", ""),
                chrome_path=run_settings.get("chrome_path", ""),
                minimize_browser=bool(run_settings.get("minimize_browser", True)),
                save_pdf=not bool(run_settings.get("only_arrival", False)),
                log=log,
                progress=progress,
                result=item,
                delivery_statuses=delivery_statuses,
            )

        self._tracking_worker = TaskWorker(task, self)
        self._tracking_worker.log.connect(self.tracking_log.appendPlainText)
        self._tracking_worker.progress.connect(
            lambda value: self._animate_progress(self.tracking_progress, self._tracking_progress_anim, self.tracking_progress_text, value)
        )
        self._tracking_worker.item.connect(self._append_tracking_result)
        self._tracking_worker.finished_ok.connect(self._tracking_finished)
        self._tracking_worker.start()

    def _append_tracking_result(self, result):
        row = self.tracking_table.rowCount()
        self.tracking_table.insertRow(row)
        values = [
            result.get("运单号", ""),
            result.get("快递公司", ""),
            result.get("状态", ""),
            result.get("抵达时间", ""),
            result.get("用时(秒)", ""),
            "",
            result.get("备注", ""),
        ]
        for column, value in enumerate(values):
            self.tracking_table.setItem(row, column, QTableWidgetItem(str(value)))

        pod_path = str(result.get("POD文件", "") or "")
        pod_exists = bool(pod_path and Path(pod_path).is_file())
        pod_item = self.tracking_table.item(row, 5)
        pod_item.setText("●" if pod_exists else "·")
        pod_item.setTextAlignment(Qt.AlignCenter)
        pod_item.setData(Qt.UserRole, pod_path if pod_exists else "")
        pod_item.setForeground(QColor("#21A366" if pod_exists else "#AAB6BF"))
        pod_item.setToolTip("点击打开 POD" if pod_exists else "没有 POD")

        carrier_key = str(result.get("快递公司", "")).strip().casefold()
        carrier = next(
            (name for name in CARRIER_NAMES if name.casefold() == carrier_key),
            None,
        )
        try:
            elapsed = float(result.get("用时(秒)", ""))
        except (TypeError, ValueError):
            elapsed = -1
        if carrier and elapsed >= 0:
            self._carrier_timings[carrier]["total"] += elapsed
            self._carrier_timings[carrier]["count"] += 1

        status = str(result.get("状态", "")).casefold()
        remark = str(result.get("备注", ""))
        self._tracking_counts["total"] += 1
        if "40" in remark or "人工复核" in remark or status in {"error", "blocked", "unknown"}:
            bucket = "attention"
            color = QColor("#AD6B09")
        elif status in {"delivered", "completed"}:
            bucket = "delivered"
            color = QColor("#29845A")
        else:
            bucket = "transit"
            color = QColor("#3175B8")
        status_background = {
            "delivered": QColor("#E8F6EE"),
            "transit": QColor("#EAF2FB"),
            "attention": QColor("#FFF4DD"),
        }[bucket]
        self._tracking_counts[bucket] += 1
        self.tracking_table.item(row, 0).setData(Qt.UserRole, bucket)
        self.tracking_table.item(row, 2).setForeground(color)
        self.tracking_table.item(row, 2).setBackground(status_background)
        self.tracking_table.item(row, 2).setTextAlignment(Qt.AlignCenter)
        for column in (1, 3, 4, 5):
            self.tracking_table.item(row, column).setTextAlignment(Qt.AlignCenter)
        self.tracking_table.item(row, 6).setToolTip(str(result.get("备注", "")))
        self._update_tracking_stats()
        self._filter_tracking_rows()
        self.tracking_table.scrollToBottom()

    def _update_tracking_stats(self):
        self.delivery_ring.set_progress(
            self._tracking_counts["delivered"],
            self._tracking_counts["total"],
        )
        labels = {
            "": ("全部", self._tracking_counts["total"]),
            "delivered": ("已送达", self._tracking_counts["delivered"]),
            "transit": ("运输中", self._tracking_counts["transit"]),
            "attention": ("需要关注", self._tracking_counts["attention"]),
        }
        for key, (label, count) in labels.items():
            self.tracking_filter_buttons[key].setText(f"{label} {count}")

    def _set_tracking_filter(self, bucket):
        self._tracking_filter_bucket = bucket
        self._filter_tracking_rows()

    def _filter_tracking_rows(self, *_args):
        query = self.tracking_search.text().strip().casefold()
        wanted = self._tracking_filter_bucket
        for row in range(self.tracking_table.rowCount()):
            number_item = self.tracking_table.item(row, 0)
            number = number_item.text().casefold() if number_item else ""
            bucket = number_item.data(Qt.UserRole) if number_item else ""
            self.tracking_table.setRowHidden(
                row,
                bool(query and query not in number) or bool(wanted and bucket != wanted),
            )

    def _handle_tracking_cell_click(self, row, column):
        if column != 5:
            return
        item = self.tracking_table.item(row, column)
        path = item.data(Qt.UserRole) if item else ""
        if path and Path(path).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _show_tracking_detail(self, row, _column):
        values = []
        headers = ("运单号", "承运商", "状态", "抵达时间", "用时(秒)", "POD", "备注")
        for column, header in enumerate(headers):
            item = self.tracking_table.item(row, column)
            values.append(f"{header}：{item.text() if item else ''}")
        QMessageBox.information(self, "运单详情", "\n".join(values))

    def _set_tracking_running(self, running):
        self.run_button.setEnabled(not running)
        self.tracking_input.setEnabled(not running)
        self.tracking_output.setEnabled(not running)
        self.pod_switch.setEnabled(not running)
        self.run_button.setText("查询中…" if running else "开始查询")

    def _update_tracking_elapsed(self):
        if not self._tracking_elapsed.isValid():
            return
        seconds = max(0, self._tracking_elapsed.elapsed() // 1000)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.elapsed_label.setText(
            f"{hours:d}:{minutes:02d}:{seconds:02d}"
            if hours else f"{minutes:02d}:{seconds:02d}"
        )

    def _update_carrier_averages(self):
        for carrier, label in self.carrier_average_labels.items():
            timing = self._carrier_timings[carrier]
            if timing["count"]:
                label.setText(f"{timing['total'] / timing['count']:.2f}")
            else:
                label.setText("--")

    def _tracking_finished(self, ok, error):
        self._tracking_timer.stop()
        self._update_tracking_elapsed()
        self._set_tracking_running(False)
        if ok:
            self._animate_progress(self.tracking_progress, self._tracking_progress_anim, self.tracking_progress_text, 100)
            self._show_status("查询完成")
            self.overview_state_label.setText("查询完成")
            self._update_carrier_averages()
            output_dir = self._tracking_run_output_dir or Path(
                self.tracking_output.value()
            ).expanduser().absolute()
            self._tracking_output_paths = {
                "result": output_dir / "tracking_result.xlsx",
                "cleaned": output_dir / "tracking_list_cleaned_sorted.xlsx",
                "audit": output_dir / "pod_audit.xlsx",
            }
            self._refresh_output_buttons(0)
        else:
            self._show_status("查询失败")
            self.overview_state_label.setText("查询失败")
            QMessageBox.critical(self, "ShipmentTrack", error or "查询失败")
        self._tracking_worker = None
        self._tracking_run_output_dir = None

    def _start_excel(self):
        if self._excel_worker and self._excel_worker.isRunning():
            return
        inspect_dir = self.inspect_input.value()
        droplist_dir = self.droplist_input.value()
        output_dir = self.excel_output.value()
        if inspect_dir and not Path(inspect_dir).is_dir():
            QMessageBox.warning(self, "ShipmentTrack", "请选择有效的检验表文件夹。")
            return
        if droplist_dir and not Path(droplist_dir).is_dir():
            QMessageBox.warning(self, "ShipmentTrack", "请选择有效的 Droplist 文件夹。")
            return
        if not inspect_dir and not droplist_dir:
            QMessageBox.warning(self, "ShipmentTrack", "检验表和 Droplist 至少选择一个文件夹。")
            return
        if not output_dir:
            QMessageBox.warning(self, "ShipmentTrack", "请选择输出文件夹。")
            return

        settings = dict(self.settings)
        settings.update({
            "inspect_input_dir": inspect_dir,
            "droplist_input_dir": droplist_dir,
            "excel_output_dir": output_dir,
        })
        self.store.save_settings(settings)
        self.settings = settings
        rules = self.store.load_mappings()
        self.excel_run_button.setEnabled(False)
        self.excel_run_button.setText("处理中…")
        self.excel_table.setRowCount(0)
        self.excel_summary.setText("正在处理")
        self.open_inspect_output.set_path("")
        self.open_droplist_output.set_path("")
        self._excel_output_paths = {}
        self._animate_progress(self.excel_progress, self._excel_progress_anim, self.excel_progress_text, 0)

        def task(log, progress, item):
            result = merge_and_reconcile_excel(
                Path(inspect_dir) if inspect_dir else None,
                Path(droplist_dir) if droplist_dir else None,
                Path(output_dir),
                rules,
                progress,
            )
            item(result)

        self._excel_worker = TaskWorker(task, self)
        self._excel_worker.progress.connect(
            lambda value: self._animate_progress(self.excel_progress, self._excel_progress_anim, self.excel_progress_text, value)
        )
        self._excel_worker.item.connect(self._show_excel_result)
        self._excel_worker.finished_ok.connect(self._excel_finished)
        self._excel_worker.start()

    def _show_excel_result(self, result):
        self.excel_table.setRowCount(0)
        for row_data in result.rows:
            row = self.excel_table.rowCount()
            self.excel_table.insertRow(row)
            values = (
                row_data.date,
                row_data.target_type,
                "" if row_data.inspect_quantity is None else f"{row_data.inspect_quantity:g}",
                "" if row_data.droplist_quantity is None else f"{row_data.droplist_quantity:g}",
                "" if row_data.difference is None else f"{row_data.difference:g}",
                row_data.result,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 5:
                    item.setForeground(QColor("#29845A" if row_data.result == "一致" else "#B54444"))
                self.excel_table.setItem(row, column, item)
        self.excel_summary.setText(
            f"检验表 {result.inspect_files} 个 / {result.inspect_rows} 行　"
            f"Droplist {result.droplist_files} 个 / {result.droplist_rows} 行　"
            f"异常文件 {len(result.issues)} 个"
        )
        self._excel_output_paths = {}
        if result.inspect_output_file:
            self._excel_output_paths["inspect"] = result.inspect_output_file
        if result.droplist_output_file:
            self._excel_output_paths["droplist"] = result.droplist_output_file
        self._refresh_output_buttons(1)

    def _excel_finished(self, ok, error):
        self.excel_run_button.setEnabled(True)
        self.excel_run_button.setText("开始合并与核对")
        if ok:
            self._animate_progress(self.excel_progress, self._excel_progress_anim, self.excel_progress_text, 100)
            self._show_status("Excel 合并与核对完成")
        else:
            self.excel_summary.setText("处理失败")
            self._show_status("Excel 处理失败")
            QMessageBox.critical(self, "ShipmentTrack", error or "Excel 处理失败")
        self._excel_worker = None

    def _on_settings_saved(self, settings):
        self.settings = dict(settings)
        self.tracking_input.set_value(settings.get("tracking_input_file", ""))
        self.tracking_output.set_value(settings.get("tracking_output_dir", ""))
        self.inspect_input.set_value(settings.get("inspect_input_dir", ""))
        self.droplist_input.set_value(settings.get("droplist_input_dir", ""))
        self.excel_output.set_value(settings.get("excel_output_dir", ""))

    def _show_status(self, message):
        self.statusBar().showMessage(str(message), 4000)
