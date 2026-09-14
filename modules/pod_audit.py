# -*- coding: utf-8 -*-
"""从所有已下载 POD 中随机抽查 5%，并按承运商执行校验。"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import random
import re
from typing import Callable, Iterable, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pypdf import PdfReader


DELIVERED_TERMS = (
    "delivered",
    "completed",
    "proof of delivery",
    "delivery confirmation",
)


@dataclass(frozen=True)
class PodAuditItem:
    tracking_number: str
    carrier: str
    pdf_file: str
    sample_reason: str
    tracking_status: str
    valid_pdf: bool
    tracking_found: bool
    delivered_found: bool
    status_field: str
    result: str
    details: str
    signature_found: bool = False


def _normalize_search_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _fedex_signature_image_found(reader) -> bool:
    """识别 FedEx SPOD 中区别于页底背景和 Logo 的横向签名图。"""
    dimensions = []
    for page in reader.pages[:5]:
        page_dimensions = []
        try:
            resources = page.get("/Resources") or {}
            xobjects = resources.get("/XObject") or {}
            for reference in xobjects.values():
                image = reference.get_object()
                if str(image.get("/Subtype")) != "/Image":
                    continue
                page_dimensions.append((int(image.get("/Width", 0)), int(image.get("/Height", 0))))
        except (AttributeError, TypeError, ValueError):
            pass
        if not page_dimensions:
            for image in getattr(page, "images", ()):
                size = getattr(getattr(image, "image", None), "size", None)
                if size:
                    page_dimensions.append(tuple(size))
        dimensions.extend(page_dimensions)
    return any(
        100 <= width <= 600
        and 30 <= height <= 140
        and 2.2 <= width / max(height, 1) <= 8
        for width, height in dimensions
    )


def inspect_pod(pdf_file, tracking_number, carrier="") -> PodAuditItem:
    path_text = str(pdf_file or "").strip()
    if not path_text:
        return PodAuditItem(
            tracking_number=str(tracking_number),
            carrier=str(carrier),
            pdf_file="",
            sample_reason="",
            tracking_status="",
            valid_pdf=False,
            tracking_found=False,
            delivered_found=False,
            status_field="",
            result="失败",
            details="POD文件路径为空",
            signature_found=False,
        )
    path = Path(path_text)
    valid_pdf = False
    tracking_found = False
    delivered_found = False
    status_field = ""
    details = ""
    signature_found = False
    try:
        reader = PdfReader(str(path))
        valid_pdf = len(reader.pages) > 0
        page_text = []
        for page in reader.pages[:5]:
            page_text.append(page.extract_text() or "")
        text = "\n".join(page_text)
        folded = text.casefold()
        normalized = _normalize_search_text(text)
        candidates = {
            _normalize_search_text(tracking_number),
            _normalize_search_text(path.stem),
        }
        candidates.discard("")
        tracking_found = any(candidate in normalized for candidate in candidates)
        for line in text.splitlines():
            if any(term in line.casefold() for term in DELIVERED_TERMS):
                status_field = " ".join(line.split())[:300]
                break
        delivered_found = bool(status_field) or any(
            term in folded for term in DELIVERED_TERMS
        )
        if delivered_found and not status_field:
            status_field = next(
                (term for term in DELIVERED_TERMS if term in folded), ""
            )
        if str(carrier).strip().casefold() == "fedex":
            # FedEx 现在归档官网查询页而非官方 SPOD。官网主页面会显示
            # “Signed for by”或“签收人”，但不会包含独立签名图片。
            signature_found = any(
                marker in folded for marker in ("signed for by", "签收人")
            )
        if not text.strip():
            details = "PDF没有可提取文本，需要人工查看或OCR"
        elif str(carrier).strip().casefold() == "fedex" and not signature_found:
            details = "FedEx网页POD未识别到签收人字段"
        elif not tracking_found and not delivered_found:
            details = "未找到运单号和送达字段"
        elif not tracking_found:
            details = "未找到输入运单号或POD文件名中的主单号"
        elif not delivered_found:
            details = "未找到Delivered/Completed等送达字段"
    except Exception as exc:  # noqa: BLE001
        details = f"PDF读取失败：{exc}"

    is_fedex = str(carrier).strip().casefold() == "fedex"
    carrier_check_passed = signature_found if is_fedex else delivered_found
    if valid_pdf and tracking_found and carrier_check_passed:
        result = "通过"
    elif valid_pdf:
        result = "人工复核"
    else:
        result = "失败"
    return PodAuditItem(
        tracking_number=str(tracking_number),
        carrier=str(carrier),
        pdf_file=str(path),
        sample_reason="",
        tracking_status="",
        valid_pdf=valid_pdf,
        tracking_found=tracking_found,
        delivered_found=delivered_found,
        status_field=status_field,
        result=result,
        details=details,
        signature_found=signature_found,
    )


def choose_pod_samples(
    results: Iterable[dict],
    sample_rate: float = 0.05,
    fedex_sample_rate: float = 0.20,
    rng: Optional[random.Random] = None,
) -> list[tuple[dict, str]]:
    fedex_eligible = []
    other_eligible = []
    for result in results:
        pdf_file = str(result.get("POD文件") or result.get("pdf_file") or "").strip()
        carrier = str(
            result.get("快递公司") or result.get("carrier") or ""
        ).strip().casefold()
        status = str(result.get("状态") or result.get("status") or "").strip().casefold()
        delivered = bool(result.get("is_delivered")) or status in {
            "delivered", "completed"
        }
        if not delivered or not pdf_file:
            continue
        if carrier == "fedex":
            detail_file = str(
                result.get("POD详情文件") or result.get("detail_pdf_file") or ""
            ).strip()
            if (pdf_file and Path(pdf_file).is_file()) or (
                detail_file and Path(detail_file).is_file()
            ):
                fedex_eligible.append(result)
        elif Path(pdf_file).is_file():
            other_eligible.append(result)

    generator = rng or random.SystemRandom()
    selected = []
    if other_eligible:
        count = min(math.ceil(len(other_eligible) * sample_rate), len(other_eligible))
        selected.extend(
            (result, "其他承运商POD随机抽查5%")
            for result in generator.sample(other_eligible, count)
        )
    if fedex_eligible:
        count = min(
            math.ceil(len(fedex_eligible) * fedex_sample_rate),
            len(fedex_eligible),
        )
        for source in generator.sample(fedex_eligible, count):
            for key, label in (
                ("POD文件", "查询主页"),
                ("POD详情文件", "详情页"),
            ):
                item = dict(source)
                item["_audit_pdf_file"] = str(item.get(key) or "")
                item["_audit_pod_kind"] = label
                selected.append((item, f"FedEx POD随机抽查20%-{label}"))
    return selected


def _save_audit_workbook(items: list[PodAuditItem], output_file: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "POD抽查"
    sheet.sheet_view.showGridLines = False
    headers = (
        "运单号", "承运商", "POD文件", "抽查原因", "查询状态", "PDF有效",
        "运单号匹配", "提取状态", "送达字段匹配", "FedEx签收人字段", "结果", "说明",
    )
    sheet.append(headers)
    for item in items:
        sheet.append((
            item.tracking_number,
            item.carrier,
            item.pdf_file,
            item.sample_reason,
            item.tracking_status,
            "是" if item.valid_pdf else "否",
            "是" if item.tracking_found else "否",
            item.status_field,
            "是" if item.delivered_found else "否",
            "是" if item.signature_found else "否",
            item.result,
            item.details,
        ))
    header_fill = PatternFill("solid", fgColor="173F5F")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
    widths = (18, 12, 42, 20, 24, 10, 12, 36, 14, 12, 12, 44)
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[chr(64 + index)].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    output_file.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_file)


def audit_pod_sample(
    results: Iterable[dict],
    output_file,
    inspector: Callable[..., PodAuditItem] = inspect_pod,
    rng: Optional[random.Random] = None,
) -> list[PodAuditItem]:
    sampled = choose_pod_samples(results, rng=rng)
    items = []
    for result, reason in sampled:
        pdf_to_check = (
            result.get("_audit_pdf_file", "")
            if "_audit_pdf_file" in result
            else result.get("POD文件") or result.get("pdf_file")
        )
        checked = inspector(
            pdf_to_check,
            result.get("运单号") or result.get("tracking_number"),
            result.get("快递公司") or result.get("carrier", ""),
        )
        items.append(PodAuditItem(
            tracking_number=checked.tracking_number,
            carrier=checked.carrier,
            pdf_file=checked.pdf_file,
            sample_reason=reason,
            tracking_status=str(
                result.get("状态") or result.get("status") or ""
            ),
            valid_pdf=checked.valid_pdf,
            tracking_found=checked.tracking_found,
            delivered_found=checked.delivered_found,
            status_field=checked.status_field,
            result=checked.result,
            details=checked.details,
            signature_found=checked.signature_found,
        ))
    if items:
        _save_audit_workbook(items, Path(output_file))
    return items
