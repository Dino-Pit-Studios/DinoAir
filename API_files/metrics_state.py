from __future__ import annotations

import threading

_lock = threading.Lock()

counters: dict[str, int] = {
    "status_4xx": 0,
    "status_5xx": 0,
    "status_504": 0,
    "status_413": 0,
    "requests_total": 0,
}


def inc_counter(name: str) -> None:
    """Thread-safe increment of a named counter."""
    with _lock:
        if name not in counters:
            counters[name] = 0
        counters[name] += 1


def snapshot() -> dict[str, int]:
    """Return a thread-safe copy of the counters."""
    with _lock:
        return dict(counters)
