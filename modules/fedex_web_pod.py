# -*- coding: utf-8 -*-
"""Use a real Microsoft Edge session to archive two FedEx tracking pages."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from typing import Any, Callable, Optional
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

from modules.real_browser import register_browser_process, terminate_browser_process
from units import get_data_path


TRACKING_PAGE = "https://www.fedex.com/en-cn/tracking.html"
TRACKING_RESULT_URL = (
    "https://www.fedex.com/fedextrack/?trknbr={}&cntry_code=cn&locale=en_CN"
)
TRACKING_RE = re.compile(r"^[A-Za-z0-9]{8,30}$")
SUBMIT_BUTTON_RE = re.compile(r"^(?:货件查询|追踪|track|track shipment)$", re.I)
# FedEx 直达链接参数不对时会跳到 system-error / “找不到该运单号”，US 站且刷不出详情
SYSTEM_ERROR_RE = re.compile(
    r"can.t find that tracking number|check with the shipper|system-error",
    re.I,
)
DETAIL_BUTTON_RE = re.compile(
    r"(?:view|see)\s+(?:more\s+|full\s+)?(?:shipment\s+)?details?|"
    r"shipment\s+details?|detailed\s+results?|travel\s+history|"
    r"查看(?:更多)?详细信息|查看(?:更多)?详情|货件详情",
    re.I,
)
DETAIL_CONTENT_RE = re.compile(
    r"travel\s+history|shipment\s+facts|shipment\s+details|"
    r"运输历史记录|物流记录|行程历史|货件详情",
    re.I,
)
EDGE_PATHS = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


class FedExWebPodError(RuntimeError):
    """FedEx page query or PDF rendering failed."""


@dataclass(frozen=True)
class FedExWebPodResult:
    tracking_number: str
    ok: bool
    main_pdf: str = ""
    detail_pdf: str = ""
    error: str = ""


def normalize_tracking_number(value: Any) -> str:
    number = re.sub(r"[\s-]+", "", str(value or "").strip())
    if not TRACKING_RE.fullmatch(number):
        raise ValueError(f"FedEx 运单号格式不正确：{value!r}")
    return number


def output_paths(output_dir: Path, tracking_number: str) -> tuple[Path, Path]:
    number = normalize_tracking_number(tracking_number)
    return output_dir / f"{number}.pdf", output_dir / f"{number}+.pdf"


def is_valid_pdf(path: Path) -> bool:
    try:
        return (
            path.is_file()
            and path.stat().st_size >= 1024
            and path.read_bytes()[:5] == b"%PDF-"
        )
    except OSError:
        return False


def find_edge(explicit_path: str = "") -> str:
    candidates = []
    if explicit_path and Path(explicit_path).name.casefold() == "msedge.exe":
        candidates.append(Path(explicit_path))
    env_path = os.getenv("FEDEX_EDGE_PATH", "")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(EDGE_PATHS)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    raise FileNotFoundError("找不到 Microsoft Edge（msedge.exe）。")


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_cdp(cdp_url: str, timeout_seconds: float = 20) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Optional[BaseException] = None
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{cdp_url}/json/version", timeout=1) as response:
                data = json.loads(response.read().decode("utf-8"))
            if data.get("webSocketDebuggerUrl"):
                return
        except (OSError, ValueError, URLError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise FedExWebPodError(f"无法连接真实 Edge：{last_error}")


def _body_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=10_000)
    except Exception:
        return ""


def _detail_locator(page):
    for role in ("button", "link"):
        locator = page.get_by_role(role, name=DETAIL_BUTTON_RE)
        if locator.count():
            return locator
    return page.get_by_text(DETAIL_BUTTON_RE)


def _visible_detail_candidate(page, tracking_number: str = ""):
    """Prefer the details control inside the card for the requested shipment."""
    locator = _detail_locator(page)
    fallback = None
    for index in range(min(locator.count(), 20)):
        try:
            candidate = locator.nth(index)
            if not candidate.is_visible():
                continue
            if fallback is None:
                fallback = candidate
            if tracking_number and candidate.evaluate(
                """(element, number) => {
                    const wanted = String(number).replace(/[\\s-]+/g, '');
                    let current = element;
                    for (let depth = 0; current && depth < 8; depth += 1) {
                        const text = (current.innerText || '').replace(/[\\s-]+/g, '');
                        if (text.includes(wanted)) return true;
                        current = current.parentElement;
                    }
                    return false;
                }""",
                tracking_number,
            ):
                return candidate
        except Exception:
            pass
    return fallback


def _main_page_ready(page, tracking_number: str) -> bool:
    text = _body_text(page)
    if tracking_number not in re.sub(r"[\s-]+", "", text):
        return False
    return _visible_detail_candidate(page, tracking_number) is not None


def _dismiss_cookie_banner(page) -> None:
    pattern = re.compile(
        r"reject optional cookies|accept all cookies|拒绝可选|仅使用必要|接受全部",
        re.I,
    )
    locator = page.get_by_role("button", name=pattern)
    for index in range(min(locator.count(), 6)):
        try:
            candidate = locator.nth(index)
            if candidate.is_visible():
                candidate.click(timeout=2_000)
                page.wait_for_timeout(500)
                return
        except Exception:
            pass


def _hide_print_overlays(page) -> None:
    """Keep cookie consent and FedEx chat overlays out of archived PDFs."""
    _dismiss_cookie_banner(page)
    try:
        page.add_style_tag(content="""
            #usercentrics-root,
            iframe[src*="usercentrics"],
            iframe[src*="nuance"],
            [id*="nuance"],
            [class*="nuance"] {
                display: none !important;
                visibility: hidden !important;
            }
        """)
        page.wait_for_timeout(250)
    except Exception:
        pass


def _submit_tracking_form(page, tracking_number: str, timeout_ms: int) -> None:
    page.goto(TRACKING_PAGE, wait_until="domcontentloaded", timeout=timeout_ms)
    _dismiss_cookie_banner(page)
    box = _find_tracking_input(page, timeout_ms)
    _dismiss_cookie_banner(page)
    _fill_tracking_input(box, tracking_number)
    _submit_tracking_entry(page, box, timeout_ms)


def _find_tracking_input(page, timeout_ms: int):
    box = page.locator("input[id^='tracking_number_']:visible").first
    try:
        box.wait_for(state="visible", timeout=timeout_ms)
        return box
    except Exception:
        pass
    box = page.locator(
        "input[name*='tracking']:visible, textarea[name*='tracking']:visible"
    ).first
    try:
        box.wait_for(state="visible", timeout=5_000)
    except Exception as exc:
        raise FedExWebPodError("FedEx 查询输入框未出现") from exc
    return box


def _fill_tracking_input(box, tracking_number: str) -> None:
    """逐字输入，不能只用 fill()。

    FedEx 追踪页是 React 表单，locator.fill() 直接写值不会让提交按钮脱离
    disabled（实测点击报 “element is not enabled”），点进输入框用真实按键
    逐字输入才会启用，最后再补发 input/change 事件兜底。
    """
    try:
        box.click(timeout=5_000)
        box.press("Control+A")
        box.press("Backspace")
    except Exception:
        pass
    box.press_sequentially(str(tracking_number), delay=60)
    try:
        box.evaluate(
            "el => { el.dispatchEvent(new Event('input', {bubbles: true}));"
            " el.dispatchEvent(new Event('change', {bubbles: true})); }"
        )
    except Exception:
        pass


def _track_button(page):
    button = page.get_by_role("button", name=SUBMIT_BUTTON_RE)
    if button.count():
        return button.first
    return page.locator("button[type='submit']:visible").first


# CN 追踪页上有多个 TRACK 按钮（首屏组件 + 手风琴），取“第一个可用的”会点错组件；
# 先回车，再点输入框所在 form 内的提交按钮。
SUBMIT_IN_FORM_SCRIPT = """
el => {
  const form = el.closest('form');
  if (!form) return false;
  const button = form.querySelector("button[type=submit], button:not([type])");
  if (button && !button.disabled) { button.click(); return true; }
  if (typeof form.requestSubmit === 'function') { form.requestSubmit(); return true; }
  return false;
}
"""


def _submit_tracking_entry(page, box, timeout_ms: int) -> str:
    """提交查询：Enter → 同一表单内的提交按钮 → 任意可用 TRACK 按钮。"""
    try:
        box.press("Enter")
        return "enter"
    except Exception:
        pass
    try:
        if box.evaluate(SUBMIT_IN_FORM_SCRIPT):
            return "form-button"
    except Exception:
        pass
    button = _track_button(page)
    try:
        button.wait_for(state="visible", timeout=min(10_000, timeout_ms))
    except Exception as exc:
        raise FedExWebPodError("FedEx 查询按钮未出现") from exc
    deadline = time.monotonic() + max(5.0, min(timeout_ms / 1000.0, 15.0))
    while time.monotonic() < deadline:
        try:
            if button.is_enabled():
                button.click(timeout=8_000)
                return "button"
        except Exception:
            pass
        page.wait_for_timeout(300)
    raise FedExWebPodError("FedEx 查询提交失败（回车与按钮都不可用）")


def _wait_for_main_page(page, tracking_number: str, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _main_page_ready(page, tracking_number):
            return
        page.wait_for_timeout(500)
    raise FedExWebPodError("等待 FedEx 查询结果主页超时")


def _is_system_error_page(page) -> bool:
    """是否落到 FedEx 的 system-error / “找不到该运单号”页面（通常是 US 站）。"""
    try:
        url = str(getattr(page, "url", "") or "")
    except Exception:
        url = ""
    if "system-error" in url.casefold():
        return True
    try:
        text = str(_body_text(page) or "")
    except Exception:
        return False
    return bool(SYSTEM_ERROR_RE.search(text))


def _open_details(
    page,
    main_text: str,
    timeout_seconds: int,
    tracking_number: str = "",
) -> None:
    candidate = _visible_detail_candidate(page, tracking_number)
    if candidate is None:
        # 结果页是异步渲染的 SPA，“View more details”按钮可能稍后才出现，
        # 轮询等它出来再点，而不是立刻放弃。
        poll_deadline = time.monotonic() + min(timeout_seconds, 15)
        while candidate is None and time.monotonic() < poll_deadline:
            page.wait_for_timeout(1_000)
            candidate = _visible_detail_candidate(page, tracking_number)
    if candidate is None:
        raise FedExWebPodError("没有找到 FedEx‘查看更多详细信息’")
    candidate.click(timeout=5_000)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        text = _body_text(page)
        if text != main_text and DETAIL_CONTENT_RE.search(text):
            return
        page.wait_for_timeout(500)
    raise FedExWebPodError("等待 FedEx 详情页展开超时")


def _print_current_page(context, page, destination: Path) -> None:
    if "fedex.com" not in str(page.url).casefold():
        raise FedExWebPodError("当前不是 FedEx 官网页面")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _hide_print_overlays(page)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    session = context.new_cdp_session(page)
    last_error = None
    try:
        # 结果页是异步渲染的 SPA，有时第一次 printToPDF 时还没画完，等它稳定再打印，
        # 失败就重试几次。
        for attempt in range(3):
            if attempt:
                page.wait_for_timeout(3_000)
            try:
                result = session.send(
                    "Page.printToPDF",
                    {
                        "landscape": False,
                        "displayHeaderFooter": False,
                        "printBackground": True,
                        "paperWidth": 8.27,
                        "paperHeight": 11.69,
                        "marginTop": 0.25,
                        "marginBottom": 0.25,
                        "marginLeft": 0.25,
                        "marginRight": 0.25,
                    },
                )
                temporary.write_bytes(base64.b64decode(result["data"], validate=True))
                if not is_valid_pdf(temporary):
                    raise FedExWebPodError(f"Edge 生成的 PDF 无效：{destination.name}")
                temporary.replace(destination)
                return
            except Exception as exc:
                last_error = exc
        raise last_error or FedExWebPodError("Edge 打印 PDF 失败")
    finally:
        try:
            session.detach()
        finally:
            temporary.unlink(missing_ok=True)


class FedExEdgePodSession:
    """One real Edge process reused for every delivered FedEx shipment in a run."""

    def __init__(
        self,
        playwright,
        output_dir: Any,
        *,
        edge_path: str = "",
        profile_dir: Any = None,
        minimize_browser: bool = True,
        timeout_seconds: int = 45,
        warmup_seconds: int = 30,
        overwrite: bool = True,
        log_func: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.playwright = playwright
        self.output_dir = Path(output_dir)
        self.edge_path = find_edge(edge_path)
        self.profile_dir = Path(profile_dir or (get_data_path() / "fedex_edge_profile"))
        self.minimize_browser = minimize_browser
        self.timeout_seconds = max(15, int(timeout_seconds))
        self.warmup_seconds = max(0, int(warmup_seconds))
        self.timeout_ms = min(self.timeout_seconds * 1000, 60_000)
        self.overwrite = overwrite
        self.log = log_func or (lambda _message: None)
        self.process = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self) -> None:
        if self.page is not None:
            return
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        port = _free_local_port()
        cdp_url = f"http://127.0.0.1:{port}"
        command = [
            self.edge_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.profile_dir}",
            "--remote-allow-origins=*",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
            "--no-first-run",
            "--no-default-browser-check",
            # 不恢复上次会话、不弹“恢复页面”气泡，避免多出没被最小化的窗口
            "--hide-crash-restore-bubble",
            "--disable-session-crashed-bubble",
            # 语言信号锁英文（FedEx 官网按浏览器语言给页面，中文会找不到英文选择器）
            "--lang=en-US",
            "--accept-lang=en-US,en;q=0.9",
        ]
        if self.minimize_browser:
            command.append("--start-minimized")
        command += ["--new-window", TRACKING_PAGE]
        self.log("启动真实 Microsoft Edge，准备保存 FedEx 网页 POD")
        self.process = subprocess.Popen(command, close_fds=True)
        register_browser_process(self.process)
        _wait_for_cdp(cdp_url)
        self.browser = self.playwright.chromium.connect_over_cdp(cdp_url)
        if not self.browser.contexts:
            raise FedExWebPodError("Edge 没有可用浏览器上下文")
        self.context = self.browser.contexts[0]
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(15_000)
        self._pin_chinese_english_locale()
        # 程序自己把站点切到 CN 英文版，不依赖用户手动选择
        self._ensure_chinese_english_page()
        # 预热会话：接受 cookie 同意并等它生效。冷会话下直达链接会被 FedEx
        # 重定向到 system-error（US 站），必须先建立会话状态。
        try:
            _dismiss_cookie_banner(self.page)
            self.page.wait_for_timeout(3_000)
        except Exception:
            pass
        self.minimize_window()

    def minimize_window(self) -> None:
        """最小化（只在启动时调用一次；用户手动点开后不再重复最小化）。"""
        if not self.minimize_browser:
            return
        try:
            cdp = self.context.new_cdp_session(self.page)
            info = cdp.send("Browser.getWindowForTarget")
            cdp.send(
                "Browser.setWindowBounds",
                {"windowId": info["windowId"], "bounds": {"windowState": "minimized"}},
            )
            cdp.detach()
        except Exception:
            pass

    def _ensure_chinese_english_page(self) -> bool:
        """确保站点是 CN 英文版（en-cn）：不是就重设语言 cookie 再进一次。"""
        lang = ""
        for attempt in range(2):
            try:
                lang = str(
                    self.page.evaluate("() => document.documentElement.lang || ''")
                ).casefold()
            except Exception:
                lang = ""
            if lang.startswith("en-cn"):
                self.log("FedEx 站点语言：CN 英文（en-cn）")
                return True
            if attempt == 0:
                self._pin_chinese_english_locale()
                try:
                    self.page.goto(
                        TRACKING_PAGE, wait_until="domcontentloaded", timeout=self.timeout_ms
                    )
                    _dismiss_cookie_banner(self.page)
                except Exception:
                    pass
        self.log(f"FedEx 站点语言为 {lang or '未知'}，继续按 CN 英文站链接查询")
        return False

    def _load_main_page(self, tracking_number: str) -> None:
        """先走 CN 英文站表单查询（和人工操作一致，并顺带把会话“预热”）。

        冷会话下直达链接会被 FedEx 重定向到 /fedextrack/system-error（US 站），
        所以先用表单流程建立会话状态，直达链接只作兜底。
        """
        last_error = None
        try:
            _submit_tracking_form(self.page, tracking_number, self.timeout_ms)
            _wait_for_main_page(self.page, tracking_number, self.timeout_seconds)
            return
        except Exception as exc:
            last_error = exc
            self.log(f"FedEx 表单查询未完成，改用官网直达链接：{exc}")
        for attempt in range(2):
            self.page.goto(
                TRACKING_RESULT_URL.format(quote(tracking_number)),
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            try:
                _wait_for_main_page(self.page, tracking_number, self.timeout_seconds)
                return
            except Exception as exc:
                last_error = exc
                if not _is_system_error_page(self.page):
                    break
                self.log(
                    f"FedEx 返回 US 站 system-error 页面，第 {attempt + 1} 次重试 CN 英文站"
                )
                self.page.wait_for_timeout(2_000)
                self._reopen_chinese_site()
        raise FedExWebPodError(
            "FedEx CN 英文站没有返回运单结果（表单查询与直达链接都失败）；"
            f"最后错误：{last_error}"
        )

    def _pin_chinese_english_locale(self) -> None:
        """固定 CN 英文站语言：US 站不稳，详情经常刷不出来。"""
        try:
            self.context.add_cookies([
                {
                    "name": "fdx_locale",
                    "value": "en_CN",
                    "domain": ".fedex.com",
                    "path": "/",
                }
            ])
        except Exception:
            pass

    def _reopen_chinese_site(self) -> None:
        """回到 CN 英文追踪页，顺带把语言 cookie 固定成 en_CN。"""
        self._pin_chinese_english_locale()
        try:
            self.page.goto(TRACKING_PAGE, wait_until="domcontentloaded", timeout=self.timeout_ms)
            _dismiss_cookie_banner(self.page)
        except Exception:
            pass

    def download(self, tracking_number: str) -> FedExWebPodResult:
        number = normalize_tracking_number(tracking_number)
        main_pdf, detail_pdf = output_paths(self.output_dir, number)
        if not self.overwrite and is_valid_pdf(main_pdf) and is_valid_pdf(detail_pdf):
            return FedExWebPodResult(number, True, str(main_pdf), str(detail_pdf))
        try:
            self.start()
            self._load_main_page(number)
            main_text = _body_text(self.page)
            _print_current_page(self.context, self.page, main_pdf)
            _open_details(self.page, main_text, self.timeout_seconds, number)
            _print_current_page(self.context, self.page, detail_pdf)
            return FedExWebPodResult(number, True, str(main_pdf), str(detail_pdf))
        except Exception as exc:
            return FedExWebPodResult(
                number,
                False,
                str(main_pdf) if is_valid_pdf(main_pdf) else "",
                str(detail_pdf) if is_valid_pdf(detail_pdf) else "",
                str(exc),
            )

    def close(self) -> None:
        """关掉这个 Edge（连同子进程），不在桌面上留窗口。"""
        browser, process = self.browser, self.process
        self.page = self.context = self.browser = self.process = None
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        terminate_browser_process(process)
