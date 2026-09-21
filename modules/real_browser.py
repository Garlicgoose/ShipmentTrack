# -*- coding: utf-8 -*-
"""Launch installed Edge/Chrome as a real browser and attach through CDP."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Callable, Optional
from urllib.error import URLError
from urllib.request import urlopen


class RealBrowserError(RuntimeError):
    pass


# 本程序启动过的浏览器进程，用于应用退出时兜底清理（否则窗口会留在桌面上）。
_LAUNCHED_PROCESSES: set = set()


def _terminate_process_tree(process) -> None:
    """结束浏览器进程树：先用 taskkill /T 整棵树强杀（含渲染器等子进程），
    主进程若还活着再 terminate/kill 兜底。"""
    if process is None:
        return
    pid = getattr(process, "pid", None)
    # 先杀整棵树（必须在主进程还活着时执行，否则 taskkill /T 枚举不到子进程）。
    if pid and sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass
    # taskkill 之后主进程若仍在，再兜底 terminate/kill。
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    except Exception:
        pass


def close_all_launched_browsers() -> None:
    """应用退出时兜底：把所有由本程序启动的浏览器窗口关掉。"""
    for process in list(_LAUNCHED_PROCESSES):
        _terminate_process_tree(process)
    _LAUNCHED_PROCESSES.clear()


def register_browser_process(process) -> None:
    """登记浏览器进程，交给应用退出时的兜底清理。"""
    if process is not None:
        _LAUNCHED_PROCESSES.add(process)


def terminate_browser_process(process) -> None:
    """结束登记过的浏览器进程树。"""
    _LAUNCHED_PROCESSES.discard(process)
    _terminate_process_tree(process)


# DSV / EI 官网不像 DHL(hk-en) 和 UPS(loc=en_US) 那样把语言写进 URL，
# 它们跟随浏览器语言。中文页面会让模块里按英文写的选择器（Cookie 弹窗、
# Summary / Shipment Progress / Completed 等）匹配失败，因此统一锁英文。
TARGET_LOCALE = "en-US"
TARGET_ACCEPT_LANGUAGE = "en-US,en;q=0.9"

# 页面脚本能读到的 navigator.language 需要单独覆盖（Edge 的 --lang 只改界面语言）。
LANG_OVERRIDE_SCRIPT = """
(() => {
  const languages = ['en-US', 'en'];
  try {
    Object.defineProperty(navigator, 'language', {get: () => 'en-US', configurable: true});
    Object.defineProperty(navigator, 'languages', {get: () => Object.freeze(languages.slice()), configurable: true});
  } catch (error) {}
})();
"""

CHINESE_SAMPLE_LIMIT = 40


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_cdp(cdp_url: str, timeout_seconds: float = 20) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Optional[BaseException] = None
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{cdp_url}/json/version", timeout=1) as response:
                document = json.loads(response.read().decode("utf-8"))
            if document.get("webSocketDebuggerUrl"):
                return
        except (OSError, ValueError, URLError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise RealBrowserError(f"无法连接实际浏览器：{last_error}")


CHINESE_COUNT_SCRIPT = """
() => {
  const text = document.body ? (document.body.innerText || '') : '';
  return (text.match(/[\\u4e00-\\u9fff]/g) || []).length;
}
"""


def page_is_chinese(page) -> bool:
    """判断当前页面是否以中文渲染（html lang 或正文中文字符数）。"""
    try:
        lang = str(page.evaluate("() => document.documentElement.lang || ''")).casefold()
    except Exception:
        lang = ""
    if lang.startswith("zh"):
        return True
    try:
        count = page.evaluate(CHINESE_COUNT_SCRIPT)
    except Exception:
        return False
    try:
        return int(count) >= CHINESE_SAMPLE_LIMIT
    except (TypeError, ValueError):
        return False


class RealBrowserController:
    """Own one installed browser process and its Playwright CDP connection."""

    def __init__(
        self,
        playwright,
        executable_path,
        profile_dir,
        *,
        browser_name="Edge",
        locale="en-US",
        minimize=False,
        log_func: Optional[Callable[[str], None]] = None,
    ):
        self.playwright = playwright
        self.executable_path = str(Path(executable_path))
        self.profile_dir = Path(profile_dir)
        self.browser_name = str(browser_name)
        self.locale = str(locale or "en-US")
        self.minimize = bool(minimize)
        self.log = log_func or (lambda _message: None)
        self.process = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        executable = Path(self.executable_path)
        if not executable.is_file():
            raise FileNotFoundError(f"找不到已安装的 {self.browser_name}：{executable}")
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        port = _free_local_port()
        cdp_url = f"http://127.0.0.1:{port}"
        command = [
            str(executable),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.profile_dir}",
            "--remote-allow-origins=*",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
            "--no-first-run",
            "--no-default-browser-check",
            # 不恢复上次会话、不弹“恢复页面”气泡：否则会多出没被最小化的窗口
            "--hide-crash-restore-bubble",
            "--disable-session-crashed-bubble",
            f"--lang={self.locale}",
            f"--accept-lang={TARGET_ACCEPT_LANGUAGE}",
        ]
        if self.minimize:
            command.append("--start-minimized")
        command += ["--new-window", "about:blank"]
        self.log(f"启动实际 {self.browser_name} 浏览器")
        try:
            self.process = subprocess.Popen(command, close_fds=True)
        except Exception:
            raise
        _LAUNCHED_PROCESSES.add(self.process)
        try:
            wait_for_cdp(cdp_url)
            self.browser = self.playwright.chromium.connect_over_cdp(cdp_url)
            if not self.browser.contexts:
                raise RealBrowserError(f"{self.browser_name} 没有可用浏览器上下文")
            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self._lock_english_locale(self.page)
            self.page.set_default_timeout(15_000)
            self._prepare_windows()
            return self.context, self.page
        except Exception:
            self.close()
            raise

    def _prepare_windows(self) -> None:
        """只保留一个页面，并按需把所有窗口最小化。"""
        try:
            pages = list(self.context.pages)
        except Exception:
            pages = []
        for extra in pages[1:]:
            try:
                extra.close()
            except Exception:
                pass
        if self.minimize:
            windows = self.minimize_windows()
            if windows:
                self.log(f"{self.browser_name} 已最小化 {windows} 个窗口")

    def minimize_windows(self) -> int:
        """最小化该浏览器下所有窗口，返回处理的窗口数。"""
        count = 0
        seen = set()
        try:
            pages = list(self.context.pages) or [self.page]
        except Exception:
            pages = [self.page]
        for page in pages:
            if page is None:
                continue
            try:
                cdp = self.context.new_cdp_session(page)
            except Exception:
                continue
            try:
                info = cdp.send("Browser.getWindowForTarget")
                window_id = info.get("windowId")
                if window_id and window_id not in seen:
                    seen.add(window_id)
                    cdp.send(
                        "Browser.setWindowBounds",
                        {"windowId": window_id, "bounds": {"windowState": "minimized"}},
                    )
                    count += 1
            except Exception:
                pass
            finally:
                try:
                    cdp.detach()
                except Exception:
                    pass
        return count

    def _lock_english_locale(self, page=None):
        """把请求语言和页面语言都锁成英文（CDP 上下文只能用这种方式）。"""
        try:
            self.context.set_extra_http_headers(
                {"Accept-Language": TARGET_ACCEPT_LANGUAGE}
            )
        except Exception:
            pass
        for target in (self.context, page):
            if target is None:
                continue
            try:
                target.add_init_script(LANG_OVERRIDE_SCRIPT)
            except Exception:
                pass

    def ensure_english_page(self, page=None):
        """页面仍是中文时，尝试点站点自带的 English 选项。

        只做兜底：页面本来就是英文（DSV 公开追踪页、EI 落地页）时直接返回 False，
        不会产生任何多余点击。
        """
        page = page or self.page
        if page is None or not page_is_chinese(page):
            return False
        for selector in (
            "li:has-text('English')",
            ".menu-option-label:has-text('English')",
            "a:has-text('English')",
            "button:has-text('English')",
            "text=English",
        ):
            try:
                option = page.locator(selector).first
                if not option.is_visible(timeout=800):
                    continue
                option.click(timeout=2500)
                page.wait_for_timeout(2500)
                if not page_is_chinese(page):
                    self.log("已把页面语言切换为英文")
                    return True
            except Exception:
                continue
        return False

    def close(self):
        """关闭该浏览器：断开 CDP，并把进程树一起结束掉（不留窗口）。"""
        browser, process = self.browser, self.process
        self.page = self.context = self.browser = self.process = None
        _LAUNCHED_PROCESSES.discard(process)
        _terminate_process_tree(process)
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
