# -*- coding: utf-8 -*-
"""Conservative segmented FedEx webpage POD automation."""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable


SEGMENTED_MAX_JOBS = 100
SEGMENT_SIZE = 25
SPLIT_THRESHOLD = 50
ITEM_INTERVAL_SECONDS = 15
SEGMENT_PAUSE_SECONDS = 5 * 60
SITE_BLOCK_MARKERS = (
    "too many requests",
    "access denied",
    "captcha",
    "unusual traffic",
    "system-error",
    "temporarily unavailable",
    "service unavailable",
    "系统错误",
    "验证码",
    "访问被拒绝",
    "请求过多",
    "限流",
    "can't find that tracking number",
)


@dataclass(frozen=True)
class SegmentedAutoRun:
    target: int
    completed: int
    paused: int
    requests: int
    segments_completed: int
    stopped: bool
    site_blocked: bool
    reason: str = ""
    failed_number: str = ""


def plan_segments(total_jobs: int) -> tuple[int, ...]:
    total = min(max(0, int(total_jobs)), SEGMENTED_MAX_JOBS)
    if total <= 0:
        return ()
    if total <= SPLIT_THRESHOLD:
        return (total,)
    full, remainder = divmod(total, SEGMENT_SIZE)
    parts = [SEGMENT_SIZE] * full
    if remainder:
        parts.append(remainder)
    return tuple(parts)


def is_site_block(error: object) -> bool:
    message = str(error or "").casefold()
    return any(marker in message for marker in SITE_BLOCK_MARKERS)


def run_segmented_auto(
    queue,
    session,
    *,
    item_interval_seconds: float = ITEM_INTERVAL_SECONDS,
    segment_pause_seconds: float = SEGMENT_PAUSE_SECONDS,
    log: Callable[[str], None] | None = None,
    completed_callback: Callable[[object], None] | None = None,
    stop_requested: Callable[[], bool] | None = None,
    delay: Callable[[float], None] = time.sleep,
) -> SegmentedAutoRun:
    """Run at most 100 direct-link jobs; the first failure stops the run."""
    write_log = log or (lambda _message: None)
    stopped = stop_requested or (lambda: False)
    target = min(len(queue.tasks(("pending", "main_saved"))), SEGMENTED_MAX_JOBS)
    segments = plan_segments(target)
    completed = paused = requests = segments_completed = 0
    site_blocked = False
    reason = ""

    for segment_index, segment_size in enumerate(segments, 1):
        if stopped():
            break
        write_log(
            f"分段自动下载：第 {segment_index}/{len(segments)} 段，"
            f"本段 {segment_size} 票"
        )
        finished_in_segment = 0
        while finished_in_segment < segment_size and not stopped():
            task = queue.next_ready()
            if task is None:
                break
            requests += 1
            write_log(
                f"分段自动下载 [{completed + paused + 1}/{target}] {task.number}"
            )
            result = session.download_direct(task.number)
            if result.ok:
                queue.mark_completed(task.number, result.main_pdf, result.detail_pdf)
                completed += 1
                finished_in_segment += 1
                if completed_callback:
                    completed_callback(result)
                write_log(f"{task.number} 两份网页 PDF 已保存")
            else:
                if result.main_pdf:
                    queue.mark_main_saved(task.number, result.main_pdf)
                reason = result.error or "分段自动下载未完成"
                queue.pause(task.number, reason)
                paused += 1
                site_blocked = is_site_block(reason)
                write_log(
                    f"{task.number} 下载失败，已停止分段下载并进入暂停列表：{reason}"
                )
                return SegmentedAutoRun(
                    target, completed, paused, requests,
                    segments_completed, False, site_blocked, reason, task.number,
                )

            if finished_in_segment < segment_size and not stopped():
                delay(max(0.0, float(item_interval_seconds)))

        if finished_in_segment >= segment_size:
            segments_completed += 1
        if (
            segment_index < len(segments)
            and queue.next_ready() is not None
            and not stopped()
        ):
            write_log(
                f"第 {segment_index} 段结束，主动休息 "
                f"{int(segment_pause_seconds // 60)} 分钟"
            )
            delay(max(0.0, float(segment_pause_seconds)))

    return SegmentedAutoRun(
        target,
        completed,
        paused,
        requests,
        segments_completed,
        bool(stopped()),
        site_blocked,
        reason,
        "",
    )
