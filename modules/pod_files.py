# -*- coding: utf-8 -*-
"""Move generated POD files into a user-managed archive without overwriting."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from typing import Iterable

from openpyxl import load_workbook


@dataclass(frozen=True)
class PodMoveResult:
    moved: tuple[tuple[str, str], ...]
    skipped: tuple[str, ...]
    errors: tuple[str, ...]


def _safe_folder_name(value: str) -> str:
    text = re.sub(r'[<>:"/\\|?*]+', "_", str(value or "POD").strip())
    return text.strip(" .") or "POD"


def _unique_destination(folder: Path, name: str) -> Path:
    candidate = folder / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    for index in range(1, 10_000):
        candidate = folder / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法为 {name} 生成不重复文件名")


def move_pod_files(entries: Iterable[tuple[str, str]], destination) -> PodMoveResult:
    root = Path(destination).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    moved = []
    skipped = []
    errors = []
    seen = set()
    for carrier, path_text in entries:
        source = Path(str(path_text or "")).expanduser()
        try:
            source = source.resolve()
        except OSError:
            source = source.absolute()
        key = str(source).casefold()
        if key in seen:
            continue
        seen.add(key)
        if not source.is_file():
            skipped.append(str(source))
            continue
        carrier_dir = root / _safe_folder_name(carrier)
        carrier_dir.mkdir(parents=True, exist_ok=True)
        if carrier_dir == source.parent:
            skipped.append(str(source))
            continue
        target = _unique_destination(carrier_dir, source.name)
        try:
            shutil.move(str(source), str(target))
            moved.append((str(source), str(target)))
        except OSError as exc:
            errors.append(f"{source}：{exc}")
    return PodMoveResult(tuple(moved), tuple(skipped), tuple(errors))


def update_tracking_pod_paths(result_file, moved_pairs) -> int:
    path = Path(result_file)
    if not path.is_file():
        return 0
    mapping = {str(old).casefold(): str(new) for old, new in moved_pairs}
    if not mapping:
        return 0
    workbook = load_workbook(path)
    updates = 0
    try:
        sheet = workbook.active
        headers = {str(cell.value or "").strip(): cell.column for cell in sheet[1]}
        columns = [headers[name] for name in ("POD文件", "POD详情文件") if name in headers]
        for row in range(2, sheet.max_row + 1):
            for column in columns:
                current = str(sheet.cell(row, column).value or "")
                replacement = mapping.get(current.casefold())
                if replacement:
                    sheet.cell(row, column, replacement)
                    updates += 1
        if updates:
            workbook.save(path)
        return updates
    finally:
        workbook.close()
