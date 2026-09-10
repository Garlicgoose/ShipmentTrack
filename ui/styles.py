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
QLabel#brandName { color: white; font-size: 17px; font-weight: 700; }
QLabel#profileName { color: white; font-weight: 600; }
QLabel#profileCaption { color: #90A9BC; font-size: 11px; }
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
    gridline-color: #E8EEF2;
    selection-background-color: #E4F4F2;
    selection-color: #172B3C;
}
QTableView::item, QTableWidget::item { padding: 7px; border-bottom: 1px solid #E8EEF2; }
QHeaderView::section {
    background: #F6F9FB;
    color: #657889;
    border: none;
    border-bottom: 1px solid #DDE6ED;
    padding: 9px 8px;
    font-weight: 700;
}
QPlainTextEdit { padding: 7px; color: #506577; font-family: Consolas, "Microsoft YaHei UI"; }

QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QStatusBar { background: #EDF2F5; color: #607386; }
QToolTip { color: white; background: #173F5F; border: none; padding: 5px; }
"""
