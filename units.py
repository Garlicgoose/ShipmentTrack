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


def get_resource_path() -> Path:
    """只读资源根目录：开发时为项目目录，PyInstaller 后为 _MEIPASS。"""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and frozen_root:
        return Path(frozen_root).resolve()
    return Path(__file__).resolve().parent


def get_data_path() -> Path:
    """统一运行数据目录：始终位于程序根目录下的 data。"""
    return get_base_path() / "data"


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


def browser_candidates(browser_type="edge"):
    """Return installed-browser candidates without including Playwright Chromium."""
    kind = str(browser_type or "edge").strip().casefold()
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    if kind == "chrome":
        return (
            program_files / "Google/Chrome/Application/chrome.exe",
            program_files_x86 / "Google/Chrome/Application/chrome.exe",
            local / "Google/Chrome/Application/chrome.exe",
        )
    return (
        program_files_x86 / "Microsoft/Edge/Application/msedge.exe",
        program_files / "Microsoft/Edge/Application/msedge.exe",
        local / "Microsoft/Edge/Application/msedge.exe",
    )


def detect_browser_path(browser_type="edge"):
    for candidate in browser_candidates(browser_type):
        if candidate.is_file():
            return str(candidate.resolve())
    return ""


def detect_chrome_path():
    """Backward-compatible alias that now finds installed Google Chrome only."""
    return detect_browser_path("chrome")
