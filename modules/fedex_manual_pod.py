# -*- coding: utf-8 -*-
"""FedEx webpage POD: user submits/searches; app only fills after a click and prints."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from openpyxl import load_workbook

from modules.fedex_web_pod import (
    DETAIL_CONTENT_RE,
    TRACKING_PAGE,
    _body_text,
    _main_page_ready,
    _print_current_page,
    is_valid_pdf,
    normalize_tracking_number,
    output_paths,
)
from modules.real_browser import RealBrowserController
from units import get_data_path


BLOCK_PAGE_RE = re.compile(
    r"too many requests|access denied|temporarily unavailable|service unavailable|"
    r"captcha|unusual traffic|请求过多|访问被拒绝|验证码|系统错误",
    re.I,
)

# Only a real pointer click on a tracking input triggers the input. This script
# never clicks TRACK or submits the form. Native value setter triggers React's
# input/change listeners so the website itself can enable its TRACK button.
ARM_INPUT_SCRIPT = r"""
(number) => {
  const key = '__shipmentTrackManualFill';
  if (window[key]) document.removeEventListener('pointerdown', window[key], true);
  const handler = event => {
    const field = event.target?.closest?.('input, textarea');
    if (!field) return;
    const hint = [field.id, field.name, field.placeholder, field.ariaLabel]
      .filter(Boolean).join(' ').toLowerCase();
    if (!/track|tracking|运单|追踪/.test(hint)) return;
    setTimeout(() => {
      const setter = Object.getOwnPropertyDescriptor(
        field.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
        'value'
      )?.set;
      if (!setter) return;
      setter.call(field, number);
      field.dispatchEvent(new Event('input', {bubbles: true}));
      field.dispatchEvent(new Event('change', {bubbles: true}));
      document.removeEventListener('pointerdown', handler, true);
      window[key] = null;
    }, 0);
  };
  window[key] = handler;
  document.addEventListener('pointerdown', handler, true);
}
"""


@dataclass(frozen=True)
class ManualPodResult:
    number: str
    main_pdf: str
    detail_pdf: str


class ManualFedExPodSession:
    def __init__(self, playwright, browser_path, browser_type, output_dir, log=None):
        self.output_dir = Path(output_dir)
        kind = str(browser_type or "edge").casefold()
        self.controller = RealBrowserController(
            playwright,
            browser_path,
            get_data_path() / "browser_profiles" / kind / "fedex_manual",
            browser_name="Google Chrome" if kind == "chrome" else "Microsoft Edge",
            minimize=False,
            log_func=log,
        )
        self.context = None
        self.page = None

    def start(self):
        self.context, self.page = self.controller.start()
        self.page.goto(TRACKING_PAGE, wait_until="domcontentloaded", timeout=45_000)

    def prepare(self, number):
        number = normalize_tracking_number(number)
        if self.page is None:
            self.start()
        else:
            self.page.goto(TRACKING_PAGE, wait_until="domcontentloaded", timeout=45_000)
        self.page.evaluate(ARM_INPUT_SCRIPT, number)
        return number

    def main_ready(self, number):
        text = _body_text(self.page)
        if BLOCK_PAGE_RE.search(text):
            raise RuntimeError("FedEx 页面出现限流、验证码或服务错误；请人工处理后重试")
        return _main_page_ready(self.page, number)

    def save_main(self, number):
        if not self.main_ready(number):
            raise RuntimeError("尚未看到当前运单的查询结果，不保存主页")
        main_pdf, _ = output_paths(self.output_dir, number)
        snapshot = (_body_text(self.page), str(self.page.url))
        _print_current_page(self.context, self.page, main_pdf)
        return str(main_pdf), snapshot

    def detail_ready(self, number, snapshot):
        text = _body_text(self.page)
        if BLOCK_PAGE_RE.search(text):
            raise RuntimeError("FedEx 详情页出现限流、验证码或服务错误")
        before_text, before_url = snapshot
        compact = re.sub(r"[\s-]+", "", text)
        return (
            number in compact
            and text != before_text
            and bool(DETAIL_CONTENT_RE.search(text))
            and (str(self.page.url) != before_url or abs(len(text) - len(before_text)) >= 80)
        )

    def save_detail(self, number, snapshot):
        if not self.detail_ready(number, snapshot):
            raise RuntimeError("尚未看到当前运单的详情内容，不保存详情页")
        _, detail_pdf = output_paths(self.output_dir, number)
        _print_current_page(self.context, self.page, detail_pdf)
        if not is_valid_pdf(detail_pdf):
            raise RuntimeError("FedEx 详情 PDF 无效")
        return str(detail_pdf)

    def close(self):
        self.controller.close()
        self.context = self.page = None


def update_tracking_result_file(result_file, pod_result: ManualPodResult) -> bool:
    """Write two manually saved POD paths back to the existing tracking result."""
    path = Path(result_file)
    if not path.is_file():
        return False
    workbook = load_workbook(path)
    try:
        sheet = workbook.active
        headers = {str(cell.value or "").strip(): cell.column for cell in sheet[1]}
        required = {"运单号", "快递公司", "POD文件", "POD详情文件"}
        if not required.issubset(headers):
            return False
        for row in range(2, sheet.max_row + 1):
            number = str(sheet.cell(row, headers["运单号"]).value or "").strip()
            carrier = str(sheet.cell(row, headers["快递公司"]).value or "").strip()
            if number == pod_result.number and carrier.casefold() == "fedex":
                sheet.cell(row, headers["POD文件"], pod_result.main_pdf)
                sheet.cell(row, headers["POD详情文件"], pod_result.detail_pdf)
                workbook.save(path)
                return True
        return False
    finally:
        workbook.close()
