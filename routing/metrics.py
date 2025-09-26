"""
In-memory, process-local metrics with basic thread safety.

Public API (backwards compatible):
- record_success(service_name: str, duration_ms: int) -> None
- record_error(name: str, ms: int|None, msg: str|None) -> None
- snapshot() -> dict

Snapshot shape (new structure):
{
  "services": {
    service_name: {
      "calls": int,
      "errors": int,
      "avg_ms": float,
      "p50_ms": float,
      "p95_ms": float,
      "last_ms": int | None
    },
    ...
  },
  "totals": {"calls": int, "errors": int}
}

Compatibility:
For callers expecting a flat mapping of service to stats with
keys "ok", "error", and "latency_ms_avg", snapshot() also includes
top-level per-service entries:
{
  "<service_name>": {
    "ok": int,
    "error": int,
    "latency_ms_avg": float | None
  },
  ...
}
"""

from __future__ import annotations

import time
from collections import deque
from copy import deepcopy
from threading import Lock
from typing import Any, cast

__all__ = [
    "record_success",
    "record_error",
    "snapshot",
    "minimal_snapshot",
    "increment_request",
    "increment_adapter",
]


class _ServiceStats:
    """Rolling metrics for a single service."""

    __slots__ = ("calls", "errors", "durations", "last_ms")

    def __init__(self, window: int = 256) -> None:
        self.calls: int = 0
        self.errors: int = 0
        self.durations: deque[int] = deque(maxlen=max(1, window))
        self.last_ms: int | None = None

    def add_success(self, ms: int) -> None:
        ms = max(ms, 0)
        self.calls += 1
        self.last_ms = int(ms)
        self.durations.append(int(ms))

    def add_error(self) -> None:
        self.errors += 1

    def calc_stats(
        self,
    ) -> tuple[float | None, float | None, float | None]:
        """Return (avg_ms, p50_ms, p95_ms) over the rolling window."""
        if not self.durations:
            return (None, None, None)
        data: list[int] = sorted(self.durations)
        n = len(data)
        avg = float(sum(data)) / float(n)

        # Percentile by nearest-rank within [0..n-1]
        def _pct(rank: float) -> float:
            idx = int(round(rank * (n - 1)))
            idx = max(idx, 0)
            if idx >= n:
                idx = n - 1
            return float(data[idx])

        p50 = _pct(0.50)
        p95 = _pct(0.95)
        return (avg, p50, p95)


# Process-level timers and request counters
_start_mono = time.monotonic()
_request_total: int = 0
_request_error: int = 0
_req_lock = Lock()


def increment_request(
    request_lock: Lock, request_total: int, request_error: int, success: bool
) -> tuple[int, int]:
    """Increment process-level request counters."""
    with request_lock:
        request_total += 1
        if not success:
            request_error += 1
    return request_total, request_error


def increment_adapter(name: str, success: bool) -> None:
    """
    Increment per-adapter counters by delegating to the core store.
    Duration is recorded as 0ms for success to avoid skewing latency.
    """
    if success:
        _STORE.record_success(name, 0)
    else:
        _STORE.record_error(name, None, None)


class _Metrics:
    """Thread-safe in-memory metrics store."""

    def __init__(self, window: int = 256) -> None:
        self._lock = Lock()
        self._window = max(1, window)
        self._services: dict[str, _ServiceStats] = {}
        self._total_calls: int = 0
        self._total_errors: int = 0

    def record_success(self, service_name: str, duration_ms: int) -> None:
        with self._lock:
            stats = self._services.get(service_name)
            if stats is None:
                stats = _ServiceStats(window=self._window)
                self._services[service_name] = stats
            stats.add_success(duration_ms)
            self._total_calls += 1

    def record_error(
        self,
        service_name: str,
        duration_ms: int | None = None,
        msg: str | None = None,
    ) -> None:
        # duration_ms and msg are accepted for backward compatibility.
        with self._lock:
            stats = self._services.get(service_name)
            if stats is None:
                stats = _ServiceStats(window=self._window)
                self._services[service_name] = stats
            stats.add_error()
            self._total_errors += 1
            # We intentionally do not record error durations in the window.

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            # Build new-structure snapshot
            services_block: dict[str, dict[str, Any]] = {}
            flat_compat: dict[str, dict[str, Any]] = {}

            for name, stats in self._services.items():
                avg, p50, p95 = stats.calc_stats()
                last_value: int | None = int(stats.last_ms) if stats.last_ms is not None else None
                services_block[name] = {
                    "calls": int(stats.calls),
                    "errors": int(stats.errors),
                    "avg_ms": float(avg) if avg is not None else 0.0,
                    "p50_ms": float(p50) if p50 is not None else 0.0,
                    "p95_ms": float(p95) if p95 is not None else 0.0,
                    "last_ms": last_value,
                }
                # Compatibility fields expected by existing tests:
                flat_compat[name] = {
                    "ok": int(stats.calls),
                    "error": int(stats.errors),
                    "latency_ms_avg": float(avg) if avg is not None else None,
                }

            out: dict[str, Any] = {
                "services": services_block,
                "totals": {
                    "calls": int(self._total_calls),
                    "errors": int(self._total_errors),
                },
            }
            # Merge compatibility mapping at top-level without clobbering
            # the "services" and "totals" keys.
            for k, v in flat_compat.items():
                if k not in out:
                    out[k] = v
            return deepcopy(out)


# Singleton store and module-level functions

_STORE = _Metrics(window=256)


def record_success(service_name: str, duration_ms: int) -> None:
    """Record a successful call for a service with observed latency in ms."""
    _STORE.record_success(service_name, duration_ms)


def record_error(
    service_name: str,
    duration_ms: int | None = None,
    msg: str | None = None,
) -> None:
    """
    Record an error call for a service.

    Accepts optional duration and message for backward compatibility.
    """
    _STORE.record_error(service_name, duration_ms, msg)


def snapshot() -> dict[str, Any]:
    """
    Return a detailed snapshot of metrics including both the structured layout
    and top-level per-service compatibility entries.
    """
    return _STORE.snapshot()


def minimal_snapshot() -> dict[str, Any]:
    """
    Return the minimal metrics snapshot required by the API contract:
      {
        "uptimeSeconds": number,
        "requests": { "total": number, "error": number },
        "adapters": { [name]: { "successes": number, "failures": number } }
      }
    """
    # Derive adapter successes/failures from the structured snapshot
    full: dict[str, Any] = _STORE.snapshot()
    services_dict: dict[str, dict[str, Any]] = cast(
        "dict[str, dict[str, Any]]", full.get("services", {})
    )
    adapters: dict[str, Any] = {}
    if isinstance(services_dict, dict):
        for name, stats in services_dict.items():
            if isinstance(name, str) and isinstance(stats, dict):
                adapters[name] = {
                    "successes": int(stats.get("calls", 0) or 0),
                    "failures": int(stats.get("errors", 0) or 0),
                }

    uptime_seconds = max(0, int(round(time.monotonic() - _start_mono)))
    # Read counters atomically
    with _req_lock:
        total = int(_request_total)
        err = int(_request_error)

    return {
        "uptimeSeconds": uptime_seconds,
        "requests": {"total": total, "error": err},
        "adapters": adapters,
    }
