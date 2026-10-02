# -*- coding: utf-8 -*-
"""Persistent queue for resumable FedEx webpage POD work."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Iterable, Optional

from openpyxl import load_workbook

from modules.fedex_web_pod import is_valid_pdf, normalize_tracking_number, output_paths


READY_STATES = ("pending", "main_saved")
TERMINAL_STATES = ("completed", "skipped")


@dataclass(frozen=True)
class FedExPodTask:
    number: str
    state: str
    main_pdf: str = ""
    detail_pdf: str = ""
    reason: str = ""
    source: str = ""
    position: int = 0
    updated_at: str = ""

    @property
    def expected_page(self) -> str:
        return "detail" if self.state == "main_saved" else "main"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class FedExPodQueue:
    """Small SQLite queue; every public operation opens its own connection."""

    def __init__(self, path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS fedex_pod_tasks (
                    position INTEGER PRIMARY KEY AUTOINCREMENT,
                    number TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL DEFAULT 'pending',
                    main_pdf TEXT NOT NULL DEFAULT '',
                    detail_pdf TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _row_to_task(row) -> FedExPodTask:
        return FedExPodTask(
            number=row["number"],
            state=row["state"],
            main_pdf=row["main_pdf"],
            detail_pdf=row["detail_pdf"],
            reason=row["reason"],
            source=row["source"],
            position=int(row["position"]),
            updated_at=row["updated_at"],
        )

    def add_numbers(self, numbers: Iterable[object], source: str = "") -> list[str]:
        added = []
        seen = set()
        with self._connect() as connection:
            for raw in numbers:
                try:
                    number = normalize_tracking_number(raw)
                except ValueError:
                    continue
                if number in seen:
                    continue
                seen.add(number)
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO fedex_pod_tasks
                        (number, state, source, updated_at)
                    VALUES (?, 'pending', ?, ?)
                    """,
                    (number, str(source or ""), _now()),
                )
                if cursor.rowcount:
                    added.append(number)
        return added

    def import_excel(self, path) -> list[str]:
        source = Path(path)
        workbook = load_workbook(source, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            headers = {
                str(cell.value or "").strip(): cell.column for cell in sheet[1]
            }
            column = headers.get("运单号")
            if not column:
                raise ValueError("Excel 缺少“运单号”列表头")
            numbers = [
                sheet.cell(row, column).value
                for row in range(2, sheet.max_row + 1)
                if sheet.cell(row, column).value not in (None, "")
            ]
        finally:
            workbook.close()
        return self.add_numbers(numbers, source=str(source.resolve()))

    def tasks(self, states: Optional[Iterable[str]] = None) -> list[FedExPodTask]:
        query = "SELECT * FROM fedex_pod_tasks"
        params = []
        if states:
            values = tuple(states)
            query += " WHERE state IN ({})".format(",".join("?" for _ in values))
            params.extend(values)
        query += " ORDER BY position"
        with self._connect() as connection:
            return [self._row_to_task(row) for row in connection.execute(query, params)]

    def get(self, number: str) -> Optional[FedExPodTask]:
        number = normalize_tracking_number(number)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM fedex_pod_tasks WHERE number = ?", (number,)
            ).fetchone()
        return self._row_to_task(row) if row else None

    def next_ready(self) -> Optional[FedExPodTask]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM fedex_pod_tasks
                WHERE state IN ('pending', 'main_saved')
                ORDER BY position LIMIT 1
                """
            ).fetchone()
        return self._row_to_task(row) if row else None

    def mark_main_saved(self, number: str, path: str) -> None:
        self._update(number, "main_saved", main_pdf=str(path), reason="")

    def mark_completed(self, number: str, main_pdf: str, detail_pdf: str) -> None:
        self._update(
            number,
            "completed",
            main_pdf=str(main_pdf),
            detail_pdf=str(detail_pdf),
            reason="",
        )

    def pause(self, number: str, reason: str) -> None:
        self._update(number, "paused", reason=str(reason or "等待人工处理"))

    def skip(self, number: str, reason: str = "用户跳过") -> None:
        self._update(number, "skipped", reason=reason)

    def resume(self, number: str) -> None:
        task = self.get(number)
        if task is None:
            raise KeyError(number)
        state = "main_saved" if task.main_pdf and is_valid_pdf(Path(task.main_pdf)) else "pending"
        self._update(number, state, reason="")

    def sync_existing_pdfs(self, output_dir) -> None:
        root = Path(output_dir)
        for task in self.tasks():
            main_pdf, detail_pdf = output_paths(root, task.number)
            if is_valid_pdf(main_pdf) and is_valid_pdf(detail_pdf):
                self.mark_completed(task.number, str(main_pdf), str(detail_pdf))
            elif is_valid_pdf(main_pdf) and task.state != "completed":
                self.mark_main_saved(task.number, str(main_pdf))

    def counts(self) -> dict[str, int]:
        result = {key: 0 for key in ("total", "pending", "main_saved", "completed", "paused", "skipped")}
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT state, COUNT(*) AS count FROM fedex_pod_tasks GROUP BY state"
            ).fetchall()
        for row in rows:
            result[row["state"]] = int(row["count"])
            result["total"] += int(row["count"])
        return result

    def _update(self, number: str, state: str, **values) -> None:
        number = normalize_tracking_number(number)
        assignments = ["state = ?", "updated_at = ?"]
        params = [state, _now()]
        for key in ("main_pdf", "detail_pdf", "reason"):
            if key in values:
                assignments.append(f"{key} = ?")
                params.append(str(values[key] or ""))
        params.append(number)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE fedex_pod_tasks SET {', '.join(assignments)} WHERE number = ?",
                params,
            )
            if not cursor.rowcount:
                raise KeyError(number)
