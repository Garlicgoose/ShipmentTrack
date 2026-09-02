# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: Shipment Track（onedir，不打包 Chromium）。

Chromium 浏览器单独放在 exe 同级的 chrome/ 目录（见 build.ps1 的复制步骤），
程序设置里的「模拟 Chrome 路径」会优先自动检测该目录。
"""
from PyInstaller.utils.hooks import collect_all

datas = [("assets/app_icon.ico", "assets"), ("assets/app_icon.png", "assets")]
binaries = []
hiddenimports = [
    # importlib 动态加载的快递模块（PyInstaller 无法静态发现）
    "modules.dhl_module",
    "modules.dsv_module",
    "modules.ei_module",
    "modules.ups_module",
]

# Playwright：收集整个包（含 driver/node.exe 与 JS 文件）
pw_datas, pw_binaries, pw_hidden = collect_all("playwright")
datas += pw_datas
binaries += pw_binaries
hiddenimports += pw_hidden

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    noarchive=False,
)

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
