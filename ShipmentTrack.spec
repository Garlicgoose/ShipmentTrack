# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: ShipmentTrack（onedir，Chromium 作为外接依赖）。

Playwright 驱动仍需随程序发布，但 Chromium 浏览器本体不进入产物。
程序通过自动检测或设置页手动选择外部 chrome.exe。
"""
from pathlib import Path

auth_obfuscated = Path("build/auth_obfuscated").resolve()

datas = [
    ("assets/app_icon.ico", "assets"),
    ("assets/app_icon.png", "assets"),
    ("assets/github_avatar.jpg", "assets"),
]
binaries = []
hiddenimports = [
    # importlib 动态加载的快递模块（PyInstaller 无法静态发现）
    "modules.dhl_module",
    "modules.dsv_module",
    "modules.ei_module",
    "modules.ups_module",
    "modules.fedex_module",
    "modules.excel_reconcile",
]

a = Analysis(
    ["main.py"],
    # Prefer the PyArmor-generated authorization modules over their plain source.
    pathex=[str(auth_obfuscated), "."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # 这些均为 openpyxl/requests/PySide6 的可选依赖，本程序不使用。
    excludes=[
        "tkinter",
        "matplotlib",
        "pandas",
        "numpy",
        "scipy",
        "pyarrow",
        "PIL",
        "qtpy",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
    ],
    noarchive=False,
)

# 某些构建环境的 PATH 中含 Poppler 自带 ICU。PyInstaller 会误收集它，
# 覆盖 Windows 系统 ICU，导致 PySide6.QtWidgets 报 DLL load failed。
_foreign_icu = {"icuuc.dll", "icudt78.dll"}
a.binaries = [
    entry for entry in a.binaries
    if Path(entry[0]).name.casefold() not in _foreign_icu
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Shipment Track",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="assets/app_icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="Shipment Track",
)
