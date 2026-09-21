# -*- coding: utf-8 -*-
"""清洗 dist 产物：删掉打包进来但程序运行时用不到的文件。

安全性：删除前会扫描 _internal 里所有 PE 文件（.dll/.pyd/.exe）的导入表，
只要还有保留的文件引用待删目标，就跳过该目标并打印原因。

用法:
    python scripts/trim_dist.py                      # 清洗 dist\\Shipment Track
    python scripts/trim_dist.py --check              # 只检查，不删除
    python scripts/trim_dist.py --dist "<目录>"      # 指定产物目录
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import pefile
except ImportError:  # pragma: no cover - 只在开发机缺库时触发
    pefile = None


# 每一项都是 _internal 下的相对路径；Qt 侧只保留 QtCore/QtGui/QtWidgets 及
# 平台、图片格式、样式插件（程序使用 QPixmap 加载 png/jpg 头像与图标）。
CANDIDATES = (
    # Qt 本地化翻译：程序没有安装 QTranslator，界面文案全在源码里
    "PySide6/translations",
    # Qt Quick / QML / 虚拟键盘：没有任何模块 import PySide6.QtQml/QtQuick
    "PySide6/Qt6Quick.dll",
    "PySide6/Qt6Qml.dll",
    "PySide6/Qt6QmlModels.dll",
    "PySide6/Qt6QmlMeta.dll",
    "PySide6/Qt6QmlWorkerScript.dll",
    "PySide6/Qt6VirtualKeyboard.dll",
    "PySide6/plugins/platforminputcontexts",
    # 软件 OpenGL 渲染器：界面为原生控件，没有 OpenGL 窗口
    "PySide6/opengl32sw.dll",
    "PySide6/Qt6OpenGL.dll",
    # QtPdf：POD PDF 由 playwright/page.pdf 生成，从不使用 QtPdf
    "PySide6/Qt6Pdf.dll",
    "PySide6/plugins/imageformats/qpdf.dll",
    # QtNetwork：网络请求走 Python requests/urllib，不使用 Qt 网络栈
    "PySide6/Qt6Network.dll",
    "PySide6/QtNetwork.pyd",
    "PySide6/plugins/tls",
    "PySide6/plugins/networkinformation",
    # 触屏输入插件：桌面鼠标操作不需要
    "PySide6/plugins/generic/qtuiotouchplugin.dll",
    # 用不到的图片格式：界面只加载 png（图标）与 jpg（头像），保留 qjpeg/qico
    "PySide6/plugins/imageformats/qgif.dll",
    "PySide6/plugins/imageformats/qicns.dll",
    "PySide6/plugins/imageformats/qsvg.dll",
    "PySide6/plugins/imageformats/qtga.dll",
    "PySide6/plugins/imageformats/qtiff.dll",
    "PySide6/plugins/imageformats/qwbmp.dll",
    "PySide6/plugins/imageformats/qwebp.dll",
    # playwright 浏览器驱动：只需要 launch/pdf，测试运行器 UI 与类型声明不发
    "playwright/driver/package/types",
    "playwright/driver/package/lib/vite",
    "playwright/driver/package/bin",
)

PE_SUFFIXES = {".dll", ".pyd", ".exe"}


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def imported_names(path: Path) -> set[str]:
    """返回 PE 文件导入的 DLL 名（小写）。"""
    if pefile is None:
        return set()
    try:
        binary = pefile.PE(str(path), fast_load=True)
    except Exception:
        return set()
    names: set[str] = set()
    try:
        binary.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
        for entry in getattr(binary, "DIRECTORY_ENTRY_IMPORT", []) or []:
            name = entry.dll
            if isinstance(name, bytes):
                name = name.decode("ascii", "ignore")
            if name:
                names.add(name.casefold())
    finally:
        binary.close()
    return names


def collect_all_imports(root: Path, skip_roots: list[Path]) -> dict[str, set[str]]:
    """扫描 root 下所有 PE 文件，返回 {导入的 dll 名: 引用者路径}。"""
    references: dict[str, set[str]] = {}
    skip = {item.resolve() for item in skip_roots}
    for item in root.rglob("*"):
        if not item.is_file() or item.suffix.casefold() not in PE_SUFFIXES:
            continue
        resolved = item.resolve()
        if any(parent == resolved or parent in resolved.parents for parent in skip):
            continue
        for name in imported_names(item):
            references.setdefault(name, set()).add(str(item.relative_to(root)))
    return references


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist",
        default=str(Path("dist") / "Shipment Track"),
        help="产物目录（默认 dist\\Shipment Track）",
    )
    parser.add_argument("--check", action="store_true", help="只检查不删除")
    args = parser.parse_args(argv)

    dist = Path(args.dist)
    internal = dist / "_internal"
    if not internal.is_dir():
        print(f"[skip] 找不到 {internal}，先执行 build.ps1", file=sys.stderr)
        return 0

    targets = []
    for relative in CANDIDATES:
        path = internal / Path(relative)
        if path.exists():
            targets.append((relative, path))

    print(f"候选 {len(targets)} 项，总大小 {human(sum(path_size(p) for _, p in targets))}")
    if not targets:
        return 0

    references = collect_all_imports(internal, [path for _, path in targets])

    freed = 0
    removed = 0
    for relative, path in targets:
        blockers = sorted({
            owner
            for name, owners in references.items()
            if Path(relative).name.casefold() == name
            for owner in owners
        })
        if blockers:
            print(f"[keep] {relative} 仍被引用：{', '.join(blockers[:3])}")
            continue
        size = path_size(path)
        if args.check:
            print(f"[plan] {relative}  {human(size)}")
            continue
        if path.is_dir():
            for item in sorted(path.rglob("*"), reverse=True):
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    try:
                        item.rmdir()
                    except OSError:
                        pass
            try:
                path.rmdir()
            except OSError:
                pass
        else:
            path.unlink()
        removed += 1
        freed += size
        print(f"[done] 删除 {relative}  {human(size)}")

    if args.check:
        print("检查模式：未删除任何文件")
    else:
        print(f"共删除 {removed} 项，释放 {human(freed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
