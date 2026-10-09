# -*- coding: utf-8 -*-
"""Bounded experimental automation for official FedEx webpage PDFs."""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable


AUTO_BATCH_LIMIT = 10
AUTO_BATCH_MAX = 1000
AUTO_INTERVAL_SECONDS = 8
BLOCK_MARKERS = (
    "too many requests",
    "access denied",
    "captcha",
    "unusual traffic",
    "system-error",
    "系统错误",
    "验证码",
    "访问被拒绝",
    "请求过多",
    "限流",
    "can't find that tracking number",
)


@dataclass(frozen=True)
class ExperimentalAutoRun:
    processed: int
    completed: int
    paused: int
    circuit_open: bool
    reason: str = ""


def is_site_block(error: object) -> bool:
    message = str(error or "").casefold()
    return any(marker in message for marker in BLOCK_MARKERS)


def normalize_batch_limit(value) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return AUTO_BATCH_LIMIT
    return min(max(1, number), AUTO_BATCH_MAX)


def run_experimental_auto(
    queue,
    session,
    *,
    batch_limit: int = AUTO_BATCH_LIMIT,
    interval_seconds: float = AUTO_INTERVAL_SECONDS,
    log: Callable[[str], None] | None = None,
    completed_callback: Callable[[object], None] | None = None,
    stop_requested: Callable[[], bool] | None = None,
    delay: Callable[[float], None] = time.sleep,
) -> ExperimentalAutoRun:
    """Process the configured batch; blocked pages open the circuit immediately."""
    write_log = log or (lambda _message: None)
    stopped = stop_requested or (lambda: False)
    limit = normalize_batch_limit(batch_limit)
    processed = completed = paused = consecutive_failures = 0
    circuit_open = False
    reason = ""

    while processed < limit and not stopped():
        task = queue.next_ready()
        if task is None:
            break
        processed += 1
        write_log(f"实验自动模式 [{processed}/{limit}] {task.number}")
        result = session.download(task.number)
        if result.ok:
            queue.mark_completed(
                task.number, result.main_pdf, result.detail_pdf
            )
            completed += 1
            consecutive_failures = 0
            if completed_callback:
                completed_callback(result)
            write_log(f"{task.number} 两份网页 PDF 已保存")
        else:
            if result.main_pdf:
                queue.mark_main_saved(task.number, result.main_pdf)
            queue.pause(task.number, result.error or "实验自动模式未完成")
            paused += 1
            consecutive_failures += 1
            reason = result.error or "实验自动模式未完成"
            write_log(f"{task.number} 已进入暂停列表：{reason}")
            if is_site_block(reason) or consecutive_failures >= 2:
                circuit_open = True
                write_log("实验自动模式已熔断，不再继续查询 FedEx 网站")
                break
        if processed < limit and queue.next_ready() is not None and not stopped():
            delay(max(0.0, float(interval_seconds)))

    return ExperimentalAutoRun(processed, completed, paused, circuit_open, reason)
