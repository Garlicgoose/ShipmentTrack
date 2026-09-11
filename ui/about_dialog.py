# -*- coding: utf-8 -*-
"""关于对话框：版本号 + 功能介绍，底部署名 Garlicgoose。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton)

APP_NAME = "Shipment Track"
APP_VERSION = "0.9"


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About - Shipment Track")
        self.setFixedWidth(420)

        lay = QVBoxLayout(self)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        lay.addWidget(title)

        version = QLabel(f"Version {APP_VERSION}")
        version.setStyleSheet("color: #666;")
        lay.addWidget(version)

        lay.addSpacing(8)

        info = QLabel(
            "快递批量查询工具：读取 Excel（快递公司 + 运单号），"
            "批量查询 DHL / DSV / EI / UPS / FedEx 运单状态，"
            "自动下载已送达货件的 POD，输出结果 Excel。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #333; line-height: 140%;")
        lay.addWidget(info)

        lay.addStretch(1)

        # 底部署名
        credit = QLabel("Garlicgoose")
        credit.setAlignment(Qt.AlignCenter)
        credit.setStyleSheet("color: #666;")
        lay.addWidget(credit)

        lay.addSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)
