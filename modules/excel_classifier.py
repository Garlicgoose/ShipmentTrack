# -*- coding: utf-8 -*-
"""Centralized, evidence-based business-category recognition for Excel files."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


BUSINESS_TYPES = ("光联", "MPO")
SAMPLE_LIMIT = 12
IDENTIFIER_HEADER_RE = re.compile(
    r"(?:tracking|awb|waybill|shipment|运单|提单|s/?o|订单)", re.IGNORECASE
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
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return re.sub(r"[^0-9a-z]+", "", text)


def sample_identifiers(sheet, header_row=1, limit=SAMPLE_LIMIT) -> tuple[str, ...]:
    """Read only enough business identifiers for classification, then stop."""
    candidate_columns = []
    for column in range(1, sheet.max_column + 1):
        header = str(sheet.cell(header_row, column).value or "").strip()
        if IDENTIFIER_HEADER_RE.search(header):
            candidate_columns.append(column)
    if not candidate_columns:
        candidate_columns = list(range(1, min(sheet.max_column, 4) + 1))

    values = []
    seen = set()
    for row in range(header_row + 1, sheet.max_row + 1):
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
    """Resolve category by structure, then reference overlap, then filename hint."""
    references = references or {}
    sample_set = {normalize_identifier(value) for value in samples}
    sample_set.discard("")
    hits = {
        category: len(sample_set & set(references.get(category, ())))
        for category in BUSINESS_TYPES
    }
    best_hits = max(hits.values(), default=0)
    sample_categories = [category for category, count in hits.items() if count == best_hits and count > 0]
    sample_category = sample_categories[0] if len(sample_categories) == 1 else ""

    evidence = [
        value for value in (structural_category, sample_category, filename_category)
        if value in BUSINESS_TYPES
    ]
    if structural_category in BUSINESS_TYPES:
        if sample_category and sample_category != structural_category:
            return ClassificationDecision("未识别", 0.0, "结构与运单样本冲突", True)
        return ClassificationDecision(structural_category, 0.95, "工作表结构")
    if sample_category:
        if filename_category in BUSINESS_TYPES and filename_category != sample_category:
            return ClassificationDecision("未识别", 0.0, "运单样本与文件名规则冲突", True)
        return ClassificationDecision(sample_category, 0.9, f"运单样本匹配 {best_hits} 项")
    if filename_category in BUSINESS_TYPES:
        # Configured filename mappings remain backward-compatible, but are
        # explicitly marked lower-confidence than content-based evidence.
        return ClassificationDecision(filename_category, 0.55, "文件名辅助规则")
    if len(set(evidence)) > 1:
        return ClassificationDecision("未识别", 0.0, "分类证据冲突", True)
    return ClassificationDecision("未识别", 0.0, "没有足够的结构或运单样本证据")
