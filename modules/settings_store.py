# -*- coding: utf-8 -*-
"""应用设置和文件名映射的持久化。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import base64
import ctypes
from pathlib import Path
import re
import sys
from typing import Iterable, Optional

from units import get_base_path, read_json, write_json


DEFAULT_SETTINGS = {
    "tracking_input_file": "",
    "tracking_output_dir": "",
    "inspect_input_dir": "",
    "droplist_input_dir": "",
    "excel_output_dir": "",
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
    display_type: str = ""

    def normalized(self) -> "FilenameMappingRule":
        match_type = (self.match_type or "contains").strip().lower()
        if match_type not in {"contains", "exact", "regex"}:
            match_type = "contains"
        return FilenameMappingRule(
            pattern=str(self.pattern or "").strip(),
            target_type=str(self.target_type or "").strip(),
            match_type=match_type,
            note=str(self.note or "").strip(),
            display_type=str(self.display_type or self.pattern or "").strip(),
        )


DEFAULT_FILENAME_MAPPINGS = [
    FilenameMappingRule(pattern="MPO国外EI自提", target_type="MPO", display_type="EI自提"),
    FilenameMappingRule(pattern="MPO国外澳车", target_type="MPO", display_type="MPO澳车"),
    FilenameMappingRule(pattern="MPO国外港车", target_type="MPO", display_type="MPO港车"),
    FilenameMappingRule(pattern="MPO国外Kerry自提", target_type="MPO", display_type="Kerry自提"),
    FilenameMappingRule(pattern="国外81R1", target_type="光联", display_type="81R1"),
    FilenameMappingRule(pattern="国外81S1", target_type="光联", display_type="81S1"),
    FilenameMappingRule(pattern="国外仓储", target_type="光联", display_type="仓储"),
    FilenameMappingRule(pattern="MPO国外Bondex自提", target_type="MPO", display_type="Bondex自提"),
    FilenameMappingRule(pattern="MPO国外FEDEX自提", target_type="MPO", display_type="FEDEX自提"),
    FilenameMappingRule(pattern="MPO国外K+N自提", target_type="MPO", display_type="K+N自提"),
    FilenameMappingRule(pattern="MPO国外Crane自提", target_type="MPO", display_type="Crane自提"),
    FilenameMappingRule(pattern="MPO国外柜车", target_type="MPO", display_type="柜车"),
    FilenameMappingRule(pattern="国外新增出货资料", target_type="光联", display_type="国外出货资料"),
    FilenameMappingRule(pattern="MPO国外JAS自提", target_type="MPO", display_type="JAS自提"),
    FilenameMappingRule(pattern="国外第一车", target_type="光联", display_type="第一车"),
    FilenameMappingRule(pattern="国外第二车", target_type="光联", display_type="第二车"),
    FilenameMappingRule(pattern="国外第三车", target_type="光联", display_type="第三车"),
    FilenameMappingRule(pattern="国外第四车", target_type="光联", display_type="第四车"),
    FilenameMappingRule(pattern="国外第五车", target_type="光联", display_type="第五车"),
    FilenameMappingRule(pattern="CELESTICA-EI自提", target_type="光联", display_type="CELESTICA-EI自提"),
    FilenameMappingRule(pattern="814T", target_type="光联", display_type="814T"),
    FilenameMappingRule(pattern="国外DHL出货资料", target_type="光联", display_type="国外DHL"),
    FilenameMappingRule(pattern="光联", target_type="光联", display_type="光联"),
    FilenameMappingRule(pattern="MPO", target_type="MPO", display_type="MPO"),
]

DELIVERY_STATUS_CARRIERS = ("EI", "DSV")

SECRET_FIELDS = {"fedex_api_secret", "tracking_ei_password"}


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def protect_secret(value: str) -> str:
    """使用当前 Windows 用户的 DPAPI 加密凭据。"""
    value = str(value or "")
    if not value or value.startswith("dpapi:"):
        return value
    if sys.platform != "win32":
        return value
    source, source_buffer = _blob(value.encode("utf-8"))
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        0x01,
        ctypes.byref(output),
    ):
        raise OSError("Windows DPAPI encryption failed")
    try:
        encrypted = ctypes.string_at(output.pbData, output.cbData)
        return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    finally:
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))
        del source_buffer


def unprotect_secret(value: str) -> str:
    value = str(value or "")
    if not value.startswith("dpapi:") or sys.platform != "win32":
        return value
    try:
        encrypted = base64.b64decode(value[6:], validate=True)
    except (ValueError, TypeError):
        return ""
    source, source_buffer = _blob(encrypted)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        0x01,
        ctypes.byref(output),
    ):
        return ""
    try:
        return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))
        del source_buffer


@dataclass(frozen=True)
class MappingMatch:
    target_type: str
    display_type: str
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
                    display_type=rule.display_type,
                    note=rule.note,
                    pattern=rule.pattern,
                    matched=True,
                )
        return MappingMatch(
            target_type="未识别",
            display_type="未识别",
            note="没有匹配的文件名规则",
            pattern="",
            matched=False,
        )


class SettingsStore:
    def __init__(
        self,
        settings_path: Optional[Path] = None,
        mappings_path: Optional[Path] = None,
        delivery_statuses_path: Optional[Path] = None,
    ):
        base = get_base_path()
        self.settings_path = Path(settings_path or base / "settings.json")
        self.mappings_path = Path(mappings_path or base / "filename_mappings.json")
        self.delivery_statuses_path = Path(
            delivery_statuses_path
            or self.settings_path.parent / "delivery_status_mappings.json"
        )

    def load_settings(self) -> dict:
        result = dict(DEFAULT_SETTINGS)
        data = read_json(self.settings_path, default={})
        if isinstance(data, dict):
            result.update({key: data[key] for key in DEFAULT_SETTINGS if key in data})
        if not result["excel_output_dir"] and result["excel_output_file"]:
            result["excel_output_dir"] = str(Path(result["excel_output_file"]).parent)
        for key in SECRET_FIELDS:
            result[key] = unprotect_secret(result.get(key, ""))
        return result

    def save_settings(self, settings: dict) -> None:
        safe = {
            key: settings.get(key, default)
            for key, default in DEFAULT_SETTINGS.items()
        }
        for key in SECRET_FIELDS:
            safe[key] = protect_secret(safe.get(key, ""))
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
                display_type=(
                    item.get("display_type")
                    or item.get("source_type")
                    or item.get("pattern", "")
                ),
            ).normalized()
            if rule.pattern and rule.target_type:
                rules.append(rule)
        return rules or list(DEFAULT_FILENAME_MAPPINGS)

    def save_mappings(self, rules: Iterable[FilenameMappingRule]) -> None:
        normalized = [rule.normalized() for rule in rules]
        valid = [rule for rule in normalized if rule.pattern and rule.target_type]
        write_json(self.mappings_path, [asdict(rule) for rule in valid])

    def load_delivery_statuses(self) -> dict[str, list[str]]:
        data = read_json(self.delivery_statuses_path, default={})
        result = {carrier: [] for carrier in DELIVERY_STATUS_CARRIERS}
        if not isinstance(data, dict):
            return result
        for carrier in DELIVERY_STATUS_CARRIERS:
            values = data.get(carrier, [])
            if not isinstance(values, list):
                continue
            result[carrier] = list(dict.fromkeys(
                str(value or "").strip()
                for value in values
                if str(value or "").strip()
            ))
        return result

    def save_delivery_statuses(self, mapping: dict[str, Iterable[str]]) -> None:
        data = {}
        for carrier in DELIVERY_STATUS_CARRIERS:
            values = mapping.get(carrier, [])
            data[carrier] = list(dict.fromkeys(
                str(value or "").strip()
                for value in values
                if str(value or "").strip()
            ))
        write_json(self.delivery_statuses_path, data)
