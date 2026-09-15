# -*- coding: utf-8 -*-
"""主界面复用的小型原生控件。"""
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PathField(QWidget):
    changed = Signal(str)

    def __init__(self, value="", mode="file", file_filter="Excel (*.xlsx)", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.file_filter = file_filter
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        self.edit = QLineEdit(str(value or ""))
        self.edit.textChanged.connect(self.changed)
        self.button = QPushButton("浏览")
        self.button.setObjectName("smallButton")
        self.button.clicked.connect(self.browse)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def value(self):
        return self.edit.text().strip()

    def set_value(self, value):
        self.edit.setText(str(value or ""))

    def browse(self):
        current = self.value()
        if self.mode == "dir":
            selected = QFileDialog.getExistingDirectory(self, "选择文件夹", current)
        elif self.mode == "save":
            selected, _ = QFileDialog.getSaveFileName(
                self,
                "选择输出文件",
                current,
                self.file_filter,
            )
            if selected and not Path(selected).suffix:
                selected += ".xlsx"
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "选择文件",
                current,
                self.file_filter,
            )
        if selected:
            self.set_value(selected)


class StatCard(QFrame):
    def __init__(self, label, value="0", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(3)
        caption = QLabel(label)
        caption.setObjectName("statLabel")
        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("statValue")
        layout.addWidget(caption)
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value_label.setText(str(value))


class ToggleSwitch(QAbstractButton):
    """不依赖第三方库的 Fluent 风格开关。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 22)

    def sizeHint(self):
        return QSize(42, 22)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(1, 1, self.width() - 2, self.height() - 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#0B8F87" if self.isChecked() else "#AEBBC5"))
        painter.drawRoundedRect(track, 10, 10)
        diameter = 16
        x = self.width() - diameter - 3 if self.isChecked() else 3
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(x, 3, diameter, diameter))
        painter.end()


class CircularProgress(QWidget):
    """只显示比例的环形进度，不绘制数字。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ratio = 0.0
        self.setFixedSize(74, 74)

    @property
    def ratio(self):
        return self._ratio

    def set_progress(self, completed, total):
        ratio = float(completed) / float(total) if total else 0.0
        self._ratio = max(0.0, min(1.0, ratio))
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = QRectF(7, 7, self.width() - 14, self.height() - 14)
        pen = painter.pen()
        pen.setWidth(8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setColor(QColor("#DFE8ED"))
        painter.setPen(pen)
        painter.drawArc(bounds, 0, 360 * 16)
        if self._ratio > 0:
            pen.setColor(QColor("#0B8F87"))
            painter.setPen(pen)
            painter.drawArc(bounds, 90 * 16, -int(self._ratio * 360 * 16))
        painter.end()


class ClickableFrame(QFrame):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ProfilePopup(QDialog):
    changelog_requested = Signal()
    update_requested = Signal()

    def __init__(self, avatar_path, name, version="", features=(), parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("profilePopup")
        self.setFixedSize(310, 292)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(7)
        avatar = QLabel()
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setPixmap(circular_pixmap(avatar_path, 64))
        label = QLabel(name)
        label.setObjectName("popupProfileName")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(avatar)
        layout.addWidget(label)
        if version:
            version_label = QLabel(version)
            version_label.setObjectName("popupVersion")
            version_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(version_label)
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setObjectName("popupSeparator")
        layout.addWidget(separator)
        for feature in features:
            feature_label = QLabel(f"•  {feature}")
            feature_label.setObjectName("popupFeature")
            feature_label.setWordWrap(True)
            layout.addWidget(feature_label)
        actions = QHBoxLayout()
        changelog = QPushButton("更新日志")
        changelog.setObjectName("smallButton")
        changelog.clicked.connect(self.changelog_requested.emit)
        update = QPushButton("检查更新")
        update.setObjectName("smallButton")
        update.clicked.connect(self.update_requested.emit)
        actions.addWidget(changelog)
        actions.addWidget(update)
        layout.addLayout(actions)


class OpenFileButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("fileLinkButton")
        self._path = ""
        self.setEnabled(False)
        self.clicked.connect(self.open_file)

    @property
    def path(self):
        return self._path

    def set_path(self, path):
        self._path = str(Path(path).expanduser().absolute()) if path else ""
        exists = bool(self._path and Path(self._path).is_file())
        self.setEnabled(exists)
        self.setToolTip(self._path if exists else "文件尚未生成")

    def open_file(self):
        if self._path and Path(self._path).is_file():
            return QDesktopServices.openUrl(QUrl.fromLocalFile(self._path))
        self.setEnabled(False)
        self.setToolTip("文件不存在或已被移动")
        return False


def position_popup(popup, anchor):
    point = anchor.mapToGlobal(QPoint(anchor.width() + 8, anchor.height()))
    popup.move(point.x() - popup.width(), point.y() - popup.height() - 4)
    popup.show()


def circular_pixmap(path, size):
    source = QPixmap(str(path))
    if source.isNull():
        fallback = QPixmap(size, size)
        fallback.fill(QColor("#2AB8AE"))
        return fallback
    source = source.scaled(
        size,
        size,
        Qt.KeepAspectRatioByExpanding,
        Qt.SmoothTransformation,
    )
    output = QPixmap(size, size)
    output.fill(Qt.transparent)
    painter = QPainter(output)
    painter.setRenderHint(QPainter.Antialiasing)
    path_shape = QPainterPath()
    path_shape.addEllipse(0, 0, size, size)
    painter.setClipPath(path_shape)
    painter.drawPixmap(0, 0, source)
    painter.end()
    return output
