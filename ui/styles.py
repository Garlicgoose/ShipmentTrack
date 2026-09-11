# -*- coding: utf-8 -*-
"""ShipmentTrack 原生 Qt 样式。"""


APP_STYLE = r"""
* {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #1A2B3B;
}
QMainWindow, QWidget#appRoot { background: #F4F7FA; }
QFrame#sidebar { background: #102A43; border: none; }
QLabel#profileName { color: white; font-weight: 600; }
QLabel#profileCaption { color: #90A9BC; font-size: 11px; }
QLabel#popupProfileName { font-size: 15px; font-weight: 700; color: #172B3C; }
QLabel#pageTitle { font-size: 24px; font-weight: 700; color: #172B3C; }
QLabel#sectionTitle { font-size: 16px; font-weight: 700; color: #20384C; }
QLabel#muted { color: #708294; }
QLabel#statLabel { color: #708294; font-size: 12px; }
QLabel#statValue { color: #172B3C; font-size: 24px; font-weight: 700; }

QPushButton#navButton {
    color: #C8D6E1;
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-radius: 8px;
    background: transparent;
    font-weight: 600;
}
QPushButton#navButton:hover { color: white; background: #183B57; }
QPushButton#navButton:checked { color: white; background: #17505F; }

QFrame#card, QGroupBox {
    background: white;
    border: 1px solid #DDE6ED;
    border-radius: 12px;
}
QGroupBox {
    margin-top: 12px;
    padding: 18px 14px 14px 14px;
    font-size: 14px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #20384C;
}

QLineEdit, QComboBox, QSpinBox {
    min-height: 36px;
    padding: 0 10px;
    background: #FBFCFD;
    border: 1px solid #CBD8E2;
    border-radius: 7px;
    selection-background-color: #0B8F87;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #0B8F87; }
QLineEdit:disabled { color: #8798A7; background: #F1F4F6; }
QComboBox::drop-down { border: none; width: 24px; }

QPushButton {
    min-height: 36px;
    padding: 0 14px;
    border: 1px solid #C8D6E0;
    border-radius: 7px;
    background: white;
    color: #294256;
    font-weight: 600;
}
QPushButton:hover { background: #F2F7F9; border-color: #9EB2C1; }
QPushButton:pressed { background: #E7EFF4; }
QPushButton:disabled { color: #9AA8B4; background: #EEF2F5; border-color: #DEE5EA; }
QPushButton#primaryButton {
    color: white;
    background: #0B8F87;
    border-color: #0B8F87;
}
QPushButton#primaryButton:hover { background: #087A74; border-color: #087A74; }
QPushButton#dangerButton { color: #A84343; }
QPushButton#smallButton { min-height: 30px; padding: 0 10px; }
QPushButton#fileLinkButton {
    min-height: 28px;
    padding: 0 9px;
    color: #087A74;
    background: #E7F6F3;
    border: 1px solid #C3E8E3;
    border-radius: 6px;
}
QPushButton#fileLinkButton:hover { background: #D8F0EC; border-color: #88CEC5; }
QPushButton#fileLinkButton:disabled { color: #9AA8B4; background: #F2F5F7; border-color: #E2E8EC; }
QPushButton#filterChip {
    min-height: 30px;
    padding: 0 11px;
    border-radius: 15px;
    color: #607386;
    background: #F4F7F9;
    border: 1px solid #DCE5EB;
}
QPushButton#filterChip:hover { color: #173F5F; background: #ECF2F5; }
QPushButton#filterChip:checked { color: white; background: #173F5F; border-color: #173F5F; }

QRadioButton, QCheckBox { spacing: 7px; }
QRadioButton::indicator, QCheckBox::indicator { width: 16px; height: 16px; }
QRadioButton::indicator:checked, QCheckBox::indicator:checked { background: #0B8F87; border: 2px solid white; }

QProgressBar {
    min-height: 8px;
    max-height: 8px;
    border: none;
    border-radius: 4px;
    background: #E5EDF2;
    color: transparent;
}
QProgressBar::chunk { border-radius: 4px; background: #0B8F87; }

QTableView, QTableWidget, QPlainTextEdit {
    background: white;
    border: 1px solid #DDE6ED;
    border-radius: 9px;
    gridline-color: transparent;
    selection-background-color: #E4F4F2;
    selection-color: #172B3C;
}
QTableView::item, QTableWidget::item { padding: 8px; border-bottom: 1px solid #ECF1F4; }
QTableView::item:hover, QTableWidget::item:hover { background: #F5FAFA; }
QHeaderView::section {
    background: #F6F9FB;
    color: #657889;
    border: none;
    border-bottom: 1px solid #DDE6ED;
    padding: 9px 8px;
    font-weight: 700;
}
QPlainTextEdit { padding: 7px; color: #506577; font-family: Consolas, "Microsoft YaHei UI"; }
QPlainTextEdit#trackingLog { background: #F8FAFB; border-color: #E1E8ED; }

QTabWidget::pane { border: none; background: transparent; top: -1px; }
QTabBar::tab {
    min-height: 34px;
    padding: 0 18px;
    color: #687B8C;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover { color: #173F5F; }
QTabBar::tab:selected { color: #087A74; border-bottom-color: #0B8F87; font-weight: 700; }

QFrame#profileButton { border-radius: 8px; background: transparent; }
QFrame#profileButton:hover { background: #183B57; }
QDialog#profilePopup { background: white; border: 1px solid #D7E2EA; border-radius: 12px; }

QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QStatusBar { background: #EDF2F5; color: #607386; }
QToolTip { color: white; background: #173F5F; border: none; padding: 5px; }
"""
