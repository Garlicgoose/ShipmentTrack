# -*- coding: utf-8 -*-
"""应用设置和文件名映射的持久化。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Iterable, Optional

from units import get_base_path, read_json, write_json


DEFAULT_SETTINGS = {
    "tracking_input_file": "",
    "tracking_output_dir": "",
    "inspect_input_dir": "",
    "droplist_input_dir": "",
    "excel_output_file": "",
    "tracking_ei_email": "",
    "tracking_ei_password": "",
    "fedex_api_key": "",
    "fedex_api_secret": "",
    "chrome_path": "",
    "minimize_browser": True,
    "only_arrival": False,
}


@dataclass(frozen=True)
class FilenameMappingRule:
    pattern: str
    target_type: str
    match_type: str = "contains"
    note: str = ""

    def normalized(self) -> "FilenameMappingRule":
        match_type = (self.match_type or "contains").strip().lower()
        if match_type not in {"contains", "exact", "regex"}:
            match_type = "contains"
        return FilenameMappingRule(
            pattern=str(self.pattern or "").strip(),
            target_type=str(self.target_type or "").strip(),
            match_type=match_type,
            note=str(self.note or "").strip(),
        )


DEFAULT_FILENAME_MAPPINGS = [
    FilenameMappingRule(pattern="光联", target_type="光联"),
    FilenameMappingRule(pattern="MPO", target_type="MPO"),
]


@dataclass(frozen=True)
class MappingMatch:
    target_type: str
    note: str
    pattern: str
    matched: bool


class FilenameMapper:
    def __init__(self, rules: Iterable[FilenameMappingRule]):
        self.rules = [rule.normalized() for rule in rules]

    def match(self, filename: str) -> MappingMatch:
        stem = Path(str(filename or "")).stem.strip()
        folded = stem.casefold()
        for rule in self.rules:
            if not rule.pattern or not rule.target_type:
                continue
            if rule.match_type == "exact":
                matched = folded == rule.pattern.casefold()
            elif rule.match_type == "regex":
                try:
                    matched = re.search(rule.pattern, stem, re.IGNORECASE) is not None
                except re.error:
                    matched = False
            else:
                matched = rule.pattern.casefold() in folded
            if matched:
                return MappingMatch(
                    target_type=rule.target_type,
                    note=rule.note,
                    pattern=rule.pattern,
                    matched=True,
                )
        return MappingMatch(
            target_type="未识别",
            note="没有匹配的文件名规则",
            pattern="",
            matched=False,
        )


class SettingsStore:
    def __init__(
        self,
        settings_path: Optional[Path] = None,
        mappings_path: Optional[Path] = None,
    ):
        base = get_base_path()
        self.settings_path = Path(settings_path or base / "settings.json")
        self.mappings_path = Path(mappings_path or base / "filename_mappings.json")

    def load_settings(self) -> dict:
        result = dict(DEFAULT_SETTINGS)
        data = read_json(self.settings_path, default={})
        if isinstance(data, dict):
            result.update({key: data[key] for key in DEFAULT_SETTINGS if key in data})
        return result

    def save_settings(self, settings: dict) -> None:
        safe = {
            key: settings.get(key, default)
            for key, default in DEFAULT_SETTINGS.items()
        }
        write_json(self.settings_path, safe)

    def load_mappings(self) -> list[FilenameMappingRule]:
        data = read_json(self.mappings_path, default=None)
        if not isinstance(data, list):
            return list(DEFAULT_FILENAME_MAPPINGS)
        rules = []
        for item in data:
            if not isinstance(item, dict):
                continue
            rule = FilenameMappingRule(
                pattern=item.get("pattern", ""),
                target_type=item.get("target_type", ""),
                match_type=item.get("match_type", "contains"),
                note=item.get("note", ""),
            ).normalized()
            if rule.pattern and rule.target_type:
                rules.append(rule)
        return rules or list(DEFAULT_FILENAME_MAPPINGS)

    def save_mappings(self, rules: Iterable[FilenameMappingRule]) -> None:
        normalized = [rule.normalized() for rule in rules]
        valid = [rule for rule in normalized if rule.pattern and rule.target_type]
        write_json(self.mappings_path, [asdict(rule) for rule in valid])
