# -*- coding: utf-8 -*-
"""Launch installed Edge/Chrome as a real browser and attach through CDP."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import time
from typing import Callable, Optional
from urllib.error import URLError
from urllib.request import urlopen


class RealBrowserError(RuntimeError):
    pass


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
            f"--lang={self.locale}",
            "--new-window",
            "about:blank",
        ]
        self.log(f"启动实际 {self.browser_name} 浏览器")
        self.process = subprocess.Popen(command, close_fds=True)
        wait_for_cdp(cdp_url)
        self.browser = self.playwright.chromium.connect_over_cdp(cdp_url)
        if not self.browser.contexts:
            raise RealBrowserError(f"{self.browser_name} 没有可用浏览器上下文")
        self.context = self.browser.contexts[0]
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(15_000)
        if self.minimize:
            self._minimize_window()
        return self.context, self.page

    def _minimize_window(self):
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

    def close(self):
        browser, process = self.browser, self.process
        self.page = self.context = self.browser = self.process = None
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if process is not None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
