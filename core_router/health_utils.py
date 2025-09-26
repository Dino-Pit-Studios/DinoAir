"""
Health utilities for adapter pinging and state management.

This module provides standalone utilities for health checking that don't
depend on other core_router modules to avoid circular imports.
"""

from __future__ import annotations

from time import perf_counter
from typing import Protocol


class SupportsPing(Protocol):
    """Protocol for objects supporting a ping method to check availability and connectivity."""

    def ping(self) -> bool:
        pass


def ping_with_timing(adapter: SupportsPing) -> tuple[str, int]:
    """
    Call adapter.ping() and measure wall time in milliseconds.

    - 'HEALTHY' if ping returns True
    - 'DEGRADED' if ping returns False
    - 'DOWN' if ping raises

    Always returns a tuple (state_str, duration_ms) and never raises.

    Returns state as string to avoid importing HealthState enum and
    creating circular dependencies.
    """
    start = perf_counter()
    try:
        ok = bool(adapter.ping())
        duration_ms = int(round((perf_counter() - start) * 1000))
        state = "HEALTHY" if ok else "DEGRADED"
        return (state, duration_ms)
    except Exception:
        duration_ms = int(round((perf_counter() - start) * 1000))
        return ("DOWN", duration_ms)
