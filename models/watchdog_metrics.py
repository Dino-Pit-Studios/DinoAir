"""Watchdog metrics DTOs and in-memory manager used by database.initialize_db."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any


@dataclass
class WatchdogMetric:
    """Data class representing a single watchdog metric sample, including resource usage and process counts."""

    id: str
    timestamp: str
    vram_used_mb: float | None = None
    vram_total_mb: float | None = None
    vram_percent: float | None = None
    cpu_percent: float | None = None
    ram_used_mb: float | None = None
    ram_percent: float | None = None
    process_count: int | None = None
    dinoair_processes: int | None = None
    uptime_seconds: int | None = None


class WatchdogMetricsManager:
    """Manager for recording and retrieving WatchdogMetric entries in a database."""

    def __init__(self, conn: Any):
        # conn: sqlite3.Connection-compatible (execute, executemany, commit)
        self.conn = conn

    def record(self, metric: WatchdogMetric) -> None:
        self.conn.execute(
            """
            INSERT INTO watchdog_metrics (
                id, timestamp, vram_used_mb, vram_total_mb, vram_percent,
                cpu_percent, ram_used_mb, ram_percent, process_count,
                dinoair_processes, uptime_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metric.id,
                metric.timestamp,
                metric.vram_used_mb,
                metric.vram_total_mb,
                metric.vram_percent,
                metric.cpu_percent,
                metric.ram_used_mb,
                metric.ram_percent,
                metric.process_count,
                metric.dinoair_processes,
                metric.uptime_seconds,
            ),
        )
        with contextlib.suppress(Exception):
            self.conn.commit()

    def recent(self, limit: int = 100) -> list[WatchdogMetric]:
        cur = self.conn.execute(
            """
            SELECT id, timestamp, vram_used_mb, vram_total_mb, vram_percent,
                   cpu_percent, ram_used_mb, ram_percent, process_count,
                   dinoair_processes, uptime_seconds
            FROM watchdog_metrics
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            WatchdogMetric(
                id=row[0],
                timestamp=row[1],
                vram_used_mb=row[2],
                vram_total_mb=row[3],
                vram_percent=row[4],
                cpu_percent=row[5],
                ram_used_mb=row[6],
                ram_percent=row[7],
                process_count=row[8],
                dinoair_processes=row[9],
                uptime_seconds=row[10],
            )
            for row in rows
        ]

    def purge_before(self, cutoff_iso: str) -> int:
        cur = self.conn.execute(
            "DELETE FROM watchdog_metrics WHERE timestamp < ?",
            (cutoff_iso,),
        )
        with contextlib.suppress(Exception):
            self.conn.commit()
        return cur.rowcount if hasattr(cur, "rowcount") else 0
