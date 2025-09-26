"""
Shared typing for Watchdog metrics without coupling to concrete runtime classes.
Using a Protocol allows attribute access while remaining compatible with the
actual SystemMetrics dataclass provided by .Watchdog or local fallbacks.
"""

from __future__ import annotations

from typing import Protocol, TypeAlias, runtime_checkable


@runtime_checkable
class SystemMetricsProto(Protocol):
    """
    Protocol defining the system metrics attributes for Watchdog.
    Includes VRAM, CPU, and RAM usage statistics, process counts, and uptime.
    """

    vram_used_mb: float
    vram_total_mb: float
    vram_percent: float
    cpu_percent: float
    ram_used_mb: float
    ram_percent: float
    process_count: int
    dinoair_processes: int
    uptime_seconds: int


# Use an alias name that won't collide with the runtime dataclass "SystemMetrics"
SystemMetricsT: TypeAlias = "SystemMetricsProto"
