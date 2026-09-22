# -*- coding: utf-8 -*-
"""GitHub-backed, hash-verified executable updater for ShipmentTrack."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from units import get_data_path


CURRENT_VERSION = "1.2"
UPDATE_MANIFEST_URL = (
    "https://raw.githubusercontent.com/Garlicgoose/ShipmentTrack/main/release/update.json"
)
CURRENT_CHANGELOG = (
    "五家承运商的 POD 抽查比例可分别设置为 0%–100%",
    "FedEx 批量查询只取 API 状态",
    "FedEx 半自动由用户打开网址，面板独立置顶",
    "网页承运商第一次启动时留 10 秒公司登录时间",
    "映射规则增加匹配方式、预览、推荐规则和说明文档",
    "检验表按最大原始列数保留全部字段",
)


class UpdateError(RuntimeError):
    pass


def version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(value or ""))
    return tuple(int(number) for number in numbers) or (0,)


def is_newer_version(remote: str, current: str = CURRENT_VERSION) -> bool:
    left = version_tuple(remote)
    right = version_tuple(current)
    length = max(len(left), len(right))
    return left + (0,) * (length - len(left)) > right + (0,) * (length - len(right))


def validate_manifest(document: Any) -> dict:
    if not isinstance(document, dict):
        raise UpdateError("更新信息格式无效")
    version = str(document.get("version") or "").strip()
    exe_url = str(document.get("exe_url") or "").strip()
    sha256 = str(document.get("sha256") or "").strip().lower()
    notes = document.get("notes") or []
    if not version or not exe_url or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise UpdateError("更新信息缺少版本、下载地址或 SHA-256")
    parsed = urlparse(exe_url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "github.com", "raw.githubusercontent.com", "objects.githubusercontent.com"
    }:
        raise UpdateError("更新下载地址不受信任")
    if not isinstance(notes, list):
        raise UpdateError("更新日志格式无效")
    return {
        "version": version,
        "exe_url": exe_url,
        "sha256": sha256,
        "notes": [str(note).strip() for note in notes if str(note).strip()],
    }


def fetch_update_manifest(timeout: int = 12) -> dict | None:
    request = Request(
        f"{UPDATE_MANIFEST_URL}?t={int(time.time())}",
        headers={"User-Agent": f"ShipmentTrack/{CURRENT_VERSION}"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            document = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise UpdateError(f"无法读取更新信息：{exc}") from exc
    manifest = validate_manifest(document)
    return manifest if is_newer_version(manifest["version"]) else None


def download_update(manifest: dict, timeout: int = 90) -> Path:
    manifest = validate_manifest(manifest)
    update_dir = get_data_path() / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    destination = update_dir / f"Shipment Track-{manifest['version']}.exe"
    temporary = destination.with_suffix(".download")
    request = Request(
        manifest["exe_url"],
        headers={"User-Agent": f"ShipmentTrack/{CURRENT_VERSION}"},
    )
    digest = hashlib.sha256()
    try:
        with urlopen(request, timeout=timeout) as response, temporary.open("wb") as stream:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                stream.write(chunk)
        if digest.hexdigest().lower() != manifest["sha256"]:
            raise UpdateError("更新文件校验失败，已取消替换")
        if temporary.stat().st_size < 1024 or temporary.read_bytes()[:2] != b"MZ":
            raise UpdateError("下载内容不是有效的 Windows 程序")
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def stage_update(downloaded_exe: Path, target_exe: Path | None = None) -> Path:
    """Start a hidden helper that replaces the locked EXE after this process exits."""
    if not getattr(sys, "frozen", False) and target_exe is None:
        raise UpdateError("开发模式不能自动替换程序，请打包后测试更新")
    source = Path(downloaded_exe).resolve()
    target = Path(target_exe or sys.executable).resolve()
    if not source.is_file() or source.read_bytes()[:2] != b"MZ":
        raise UpdateError("待更新文件无效")
    helper = get_data_path() / "updates" / "apply_shipmenttrack_update.ps1"
    helper.parent.mkdir(parents=True, exist_ok=True)
    script = "\n".join((
        "$ErrorActionPreference = 'Stop'",
        f"$source = '{str(source).replace("'", "''")}'",
        f"$target = '{str(target).replace("'", "''")}'",
        f"$processId = {int(__import__('os').getpid())}",
        "Wait-Process -Id $processId -ErrorAction SilentlyContinue",
        "for ($attempt = 0; $attempt -lt 20; $attempt++) {",
        "  try { Copy-Item -LiteralPath $source -Destination $target -Force; break }",
        "  catch { Start-Sleep -Milliseconds 500 }",
        "}",
        "Start-Process -FilePath $target",
        "Remove-Item -LiteralPath $source -Force -ErrorAction SilentlyContinue",
        "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue",
    ))
    helper.write_text(script, encoding="utf-8-sig")
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )
    return helper
