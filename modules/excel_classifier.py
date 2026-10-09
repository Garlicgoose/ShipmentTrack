# -*- coding: utf-8 -*-
"""Centralized, evidence-based business-category recognition for Excel files."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


BUSINESS_TYPES = ("光联", "MPO")
SAMPLE_LIMIT = 12
IDENTIFIER_HEADER_RE = re.compile(
    r"(?:tracking|awb|waybill|运单|提单)", re.IGNORECASE
)


@dataclass(frozen=True)
class ClassificationDecision:
    category: str
    confidence: float
    source: str
    conflict: bool = False

    @property
    def confirmed(self):
        return self.category in BUSINESS_TYPES and not self.conflict


def normalize_identifier(value) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return re.sub(r"[^0-9a-z]+", "", text)


def identifier_columns(sheet, header_row=1):
    return tuple(
        column for column in range(1, sheet.max_column + 1)
        if IDENTIFIER_HEADER_RE.search(str(sheet.cell(header_row, column).value or ""))
    )


def sample_identifiers(sheet, header_row=1, limit=SAMPLE_LIMIT) -> tuple[str, ...]:
    """Read only enough business identifiers for classification, then stop."""
    candidate_columns = identifier_columns(sheet, header_row)
    if not candidate_columns:
        return ()

    values = []
    seen = set()
    for row in range(header_row + 1, min(sheet.max_row, header_row + 200) + 1):
        for column in candidate_columns:
            value = normalize_identifier(sheet.cell(row, column).value)
            if len(value) < 3 or value in seen:
                continue
            seen.add(value)
            values.append(value)
            if len(values) >= limit:
                return tuple(values)
    return tuple(values)


def structure_fingerprint(sheet) -> str:
    """Return a category only when workbook content declares it unambiguously."""
    markers = set()
    for row in range(1, min(sheet.max_row, 6) + 1):
        for column in range(1, min(sheet.max_column, 16) + 1):
            text = unicodedata.normalize(
                "NFKC", str(sheet.cell(row, column).value or "")
            ).strip()
            folded = text.casefold()
            if text in {"光联", "光联业务"}:
                markers.add("光联")
            if folded in {"mpo", "mpo business", "mpo业务"}:
                markers.add("MPO")
    return next(iter(markers)) if len(markers) == 1 else ""


def classify_business_type(
    *,
    structural_category="",
    samples=(),
    references=None,
    filename_category="",
) -> ClassificationDecision:
    """Droplist shipment evidence determines category independently of names."""
    references = references or {}
    sample_set = {normalize_identifier(value) for value in samples}
    sample_set.discard("")
    hits = {
        category: len(sample_set & references.get(category, set()))
        for category in BUSINESS_TYPES
    }
    best_hits = max(hits.values(), default=0)
    sample_categories = [category for category, count in hits.items() if count == best_hits and count > 0]
    sample_category = sample_categories[0] if len(sample_categories) == 1 else ""

    if all(hits[category] > 0 for category in BUSINESS_TYPES):
        return ClassificationDecision("未识别", 0.0, "运单同时匹配光联和 MPO；请确认混合业务或重复运单", True)
    if sample_category:
        return ClassificationDecision(sample_category, 0.98, f"Droplist 运单匹配 {best_hits} 项")
    if structural_category in BUSINESS_TYPES:
        if sample_category and sample_category != structural_category:
            return ClassificationDecision("未识别", 0.0, "结构与运单样本冲突", True)
        return ClassificationDecision(structural_category, 0.95, "工作表结构")
    if filename_category in BUSINESS_TYPES:
        # Configured filename mappings remain backward-compatible, but are
        # explicitly marked lower-confidence than content-based evidence.
        return ClassificationDecision(filename_category, 0.55, "文件名辅助规则")
    return ClassificationDecision("未识别", 0.0, "没有足够的结构或运单样本证据")
