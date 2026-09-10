# -*- coding: utf-8 -*-
"""Shipment Track 基础工具：路径 / JSON 读写。"""
import sys
import json
import os
import tempfile
from pathlib import Path


def get_base_path() -> Path:
    """程序根目录：打包后为 exe 所在目录，开发时为项目目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def read_json(file_path, default=None):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(file_path, data):
    """以 UTF-8 原子写入 JSON，避免程序中断留下半个配置文件。"""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=file_path.name + ".",
        suffix=".tmp",
        dir=str(file_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        Path(temp_name).replace(file_path)
    except Exception:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def detect_chrome_path():
    """自动探测外接 Playwright Chromium 的 chrome.exe 路径。

    Chromium 不进入程序安装包。优先查找 exe 同级目录 chrome/，
    其次 %LOCALAPPDATA%\\ms-playwright\\chromium-*。
    """
    import os
    base = get_base_path()
    candidates = [
        base / "chrome" / "chrome-win64" / "chrome.exe",
        base / "chrome" / "chrome-win" / "chrome.exe",
        base / "chromium" / "chrome-win64" / "chrome.exe",
        base / "chromium" / "chrome-win" / "chrome.exe",
        base / "chromium" / "chrome.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    try:
        import glob
        playwright_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
        hits = sorted(
            glob.glob(os.path.join(playwright_dir, "chromium-*")),
            reverse=True)
        for folder in hits:
            for sub in ("chrome-win64", "chrome-win"):
                exe = os.path.join(folder, sub, "chrome.exe")
                if os.path.exists(exe):
                    return exe
    except Exception:
        pass
    return ""
