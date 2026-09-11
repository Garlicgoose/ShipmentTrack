"""从 Demo SVG 生成 Windows 应用所需的 PNG 和 ICO。"""
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main():
    QGuiApplication.instance() or QGuiApplication([])
    assets = Path(__file__).resolve().parents[1] / "assets"
    renderer = QSvgRenderer(str(assets / "app_icon_demo.svg"))
    if not renderer.isValid():
        raise RuntimeError("app_icon_demo.svg 无效")
    canvas = QImage(QSize(256, 256), QImage.Format_ARGB32)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    png_path = assets / "app_icon.png"
    if not canvas.save(str(png_path), "PNG"):
        raise RuntimeError("无法保存 app_icon.png")
    with Image.open(png_path) as icon:
        icon.save(
            assets / "app_icon.ico",
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )


if __name__ == "__main__":
    main()
