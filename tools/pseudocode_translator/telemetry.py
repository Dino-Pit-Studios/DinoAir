"""
Lightweight, dependency-free telemetry utilities for timing and counting key phases.

Enablement:
- Controlled by env var PSEUDOCODE_TELEMETRY in {"1", "true", "yes"} (case-insensitive).
- When disabled, a NoOp recorder is returned and all operations are no-ops (near-zero overhead).

Sampling:
- PSEUDOCODE_TELEMETRY_SAMPLE (int N ≥ 1). Default N=1 (no sampling).
- Implements deterministic per-process sampling: only every Nth recorded event is kept.
  The drop decision is applied in get_recorder() by wrapping record_event().

Optional JSON logging:
- PSEUDOCODE_TELEMETRY_LOG in {"1","true","yes"} (case-insensitive).
- If set (and telemetry enabled), each accepted record_event() call emits a single JSON line
  at logging.INFO using the stdlib logging module with:
  {"event": name, "ts": ISO-8601 UTC, "duration_ms": <float|None>, "extra": <dict|None>,
   "counters": <dict|None>, "pid": <int>, "sample_rate": <int>}

Design goals:
- Near-zero overhead when disabled.
- Minimal overhead when enabled: perf_counter and simple aggregate updates.
- JSON-serializable snapshot with simple aggregates per event name.

Snapshot schema (JSON-serializable):
{
  "telemetry_enabled": true,
  "pid": <int>,
  "start_time": <ISO-8601 UTC string>,
  "sample_rate": <int>,
  "events": {
    "<name>": {
      "count": <int>,
      "total_ms": <float>,
      "min_ms": <float|None>,
      "max_ms": <float|None>,
      "buckets": { "<upper_bound_ms>": <int>, ... },   # only present if any durations recorded
      "counters": { "<counter_name>": <int>, ... }    # only present if counters were recorded
    },
    ...
  }
}

Duration histogram buckets:
- Fixed upper-bound edges (ms): [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, inf]
- Stored under events[name]["buckets"] keyed by upper bound as strings (e.g., "0.5", "1", "2", "5", "inf").
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

_TRUTHY = {"1", "true", "yes"}
_BUCKET_EDGES_MS: list[float] = [
    0.5,
    1,
    2,
    5,
    10,
    20,
    50,
    100,
    200,
    500,
    1000,
    float("inf"),
]

_RECORDER: TelemetryRecorder | NoOpTelemetryRecorder | None = None
_RECLOCK = threading.Lock()


def telemetry_enabled() -> bool:
    """
    Return True if telemetry is enabled via env var PSEUDOCODE_TELEMETRY.

    Truthy values (case-insensitive): {"1", "true", "yes"}
    """
    val = os.getenv("PSEUDOCODE_TELEMETRY", "0").strip().lower()
    return val in _TRUTHY


class TelemetryRecorder:
    """
    Lightweight in-process telemetry recorder.

    Aggregates per event name:
      - count
      - total_ms
      - min_ms
      - max_ms
      - buckets (fixed edges) for duration_ms, if any durations recorded
      - counters (increment-only scalars), if provided

    Methods:
      - timed_section(name, extra=None): contextmanager timing using time.perf_counter()
      - record_event(name, duration_ms=None, extra=None, counters=None): direct event recording
      - snapshot(): return JSON-serializable snapshot with process metadata and aggregates
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # event aggregates: { name: {count,total_ms,min_ms,max_ms,buckets?,counters?} }
        self._events: dict[str, dict[str, Any]] = {}

        # Process metadata for snapshot/logging
        self._pid: int = os.getpid()
        self._start_time_iso: str = datetime.now(UTC).isoformat()
        self._sample_rate: int = 1  # may be overridden in get_recorder()
        self._seq: int = 0  # used by sampling wrapper (set in get_recorder())

        # Optional JSON logging flag (checked at construction time, only when enabled)
        self._do_log: bool = os.getenv("PSEUDOCODE_TELEMETRY_LOG", "").strip().lower() in _TRUTHY
        self._logger = logging.getLogger("pseudocode.telemetry")

        # Tiny internal sanity check (best-effort, never raises)
        self._self_check_basic()

    @contextmanager
    def timed_section(self, name: str, extra: dict | None = None):
        start = time.perf_counter()
        try:
            yield
        finally:
            end = time.perf_counter()
            duration_ms = (end - start) * 1000.0
            # Sampling (if any) is applied via record_event() wrapper created in get_recorder()
            self.record_event(name, duration_ms=duration_ms, extra=extra)

    def record_event(
        self,
        name: str,
        duration_ms: float | None = None,
        extra: dict | None = None,
        counters: dict[str, int] | None = None,
    ) -> None:
        """
        Record an event occurrence with optional duration and optional counter increments.

        - Always increments the per-name 'count'.
        - If duration_ms is provided:
            * add to total_ms, update min_ms/max_ms
            * add to the fixed-bucket histogram for that event name
        - If counters is provided:
            * aggregate each key via += value under name-level counters
        """
        # Minimal overhead aggregate updates
        with self._lock:
            agg = self._events.get(name)
            if agg is None:
                agg = {
                    "count": 0,
                    "total_ms": 0.0,
                    "min_ms": None,  # filled once a duration is recorded
                    "max_ms": None,  # filled once a duration is recorded
                    # dict[str,int], added when durations recorded
                    "buckets": {},
                }
                self._events[name] = agg

            # increment occurrence count
            agg["count"] = int(agg.get("count", 0)) + 1

            # update duration aggregates and buckets
            if duration_ms is not None:
                d = float(duration_ms)
                agg["total_ms"] = float(agg.get("total_ms", 0.0)) + d
                prev_min = agg.get("min_ms")
                prev_max = agg.get("max_ms")
                agg["min_ms"] = d if prev_min is None else float(min(float(prev_min), d))
                agg["max_ms"] = d if prev_max is None else float(max(float(prev_max), d))

                # histogram bucket
                bucket_key = TelemetryRecorder._bucket_label(d)
                buckets: dict = agg.get("buckets") or {}
                buckets[bucket_key] = int(buckets.get(bucket_key, 0)) + 1
                agg["buckets"] = buckets

            # counters aggregation
            if counters:
                ctrs: dict[str, int] = agg.get("counters") or {}
                for k, v in counters.items():
                    try:
                        ctrs[k] = int(ctrs.get(k, 0)) + int(v)
                    except (ValueError, TypeError):
                        # best-effort coercion; ignore bad values
                        pass
                agg["counters"] = ctrs

        # Optional JSON logging (only after successful aggregation and only if enabled)
        if self._do_log:
            try:
                line = {
                    "event": name,
                    "ts": datetime.now(UTC).isoformat(),
                    "duration_ms": (float(duration_ms) if duration_ms is not None else None),
                    "extra": extra,
                    "counters": counters,
                    "pid": self._pid,
                    "sample_rate": self._sample_rate,
                }
                # Use stdlib logging; message as a single compact JSON line
                self._logger.info(json.dumps(line, separators=(",", ":")))
            except (OSError, ValueError, TypeError):
                # Never raise from telemetry logging
                pass

    def snapshot(self) -> dict:
        # Return safe copy to avoid concurrent mutation issues
        with self._lock:
            events_copy: dict[str, dict[str, Any]] = {}
            for name, agg in self._events.items():
                item: dict[str, Any] = {
                    "count": int(agg.get("count", 0)),
                    "total_ms": float(agg.get("total_ms", 0.0)),
                    "min_ms": agg.get("min_ms", None),
                    "max_ms": agg.get("max_ms", None),
                }
                if "buckets" in agg and agg["buckets"]:
                    item["buckets"] = dict(agg["buckets"])
                if "counters" in agg and agg["counters"]:
                    item["counters"] = dict(agg["counters"])
                events_copy[name] = item

        return {
            "telemetry_enabled": True,
            "pid": self._pid,
            "start_time": self._start_time_iso,
            "sample_rate": self._sample_rate,
            "events": events_copy,
        }

    # -------- internal helpers --------

    @staticmethod
    def _bucket_label(duration_ms: float) -> str:
        for edge in _BUCKET_EDGES_MS:
            if duration_ms <= edge:
                # Ensure "inf" string for infinity and clean integer-like edges
                if edge == float("inf"):
                    return "inf"
                return str(edge)
        # Fallback (should not happen)
        return "inf"

    def _self_check_basic(self) -> None:
        # Minimal, non-raising sanity checks on bucket labeling and counters math
        try:
            if TelemetryRecorder._bucket_label(0.4) not in {"0.5"}:
                raise AssertionError("Bucket label for 0.4 is incorrect")
            if TelemetryRecorder._bucket_label(1.0) not in {"1"}:
                raise AssertionError("Bucket label for 1.0 is incorrect")

            # simple counters aggregation mimic
            tmp = {"counters": {}}
            for delta in [{"a": 1, "b": 2}, {"a": 3}]:
                for k, v in delta.items():
                    tmp["counters"][k] = int(tmp["counters"].get(k, 0)) + int(v)
            if tmp["counters"]["a"] != 4:
                raise AssertionError("Counter 'a' is incorrect")
        except (ValueError, TypeError, KeyError):
            # never raise; only defensive
            pass


class NoOpTelemetryRecorder:
    """No-op recorder used when telemetry is disabled."""

    @staticmethod
    @contextmanager
    def timed_section(name: str, extra: dict | None = None):
        yield

    @staticmethod
    def record_event(
        name: str,
        duration_ms: float | None = None,
        extra: dict | None = None,
        counters: dict[str, int] | None = None,
    ) -> None:  # noqa: D401
        return None

    @staticmethod
    def snapshot() -> dict:
        # Explicitly empty dictionary to satisfy "empty when disabled" requirement
        return {}


_recorder: TelemetryRecorder | NoOpTelemetryRecorder | None = None
_lock = threading.Lock()


_recorder: TelemetryRecorder | NoOpTelemetryRecorder | None = None


def get_recorder() -> TelemetryRecorder | NoOpTelemetryRecorder:
    """
    Return process-wide singleton recorder.

    - If telemetry is enabled, returns a TelemetryRecorder instance.
    - Otherwise, returns a NoOpTelemetryRecorder instance.

    Deterministic sampling:
    - Controlled by PSEUDOCODE_TELEMETRY_SAMPLE (int N = 1; default 1).
    - If N > 1, record_event is wrapped to keep only every Nth call.

    The decision is made on first call and cached for the process lifetime.
    """
    if getattr(get_recorder, "recorder", None) is not None:
        return get_recorder.recorder

    with _lock:
        if not hasattr(get_recorder, "recorder"):
            if telemetry_enabled():
                rec = TelemetryRecorder()

                # Configure sampling
                sample_env = os.getenv("PSEUDOCODE_TELEMETRY_SAMPLE", "1").strip()
                try:
                    sample_rate = int(sample_env)
                    sample_rate = max(sample_rate, 1)
                except (ValueError, TypeError):
                    sample_rate = 1
                rec.set_sample_rate(sample_rate)

                if sample_rate > 1:
                    # Wrap record_event to apply deterministic sampling
                    orig_record_event = rec.record_event

                    def _sampled_record_event(
                        name: str,
                        duration_ms: float | None = None,
                        extra: dict | None = None,
                        counters: dict[str, int] | None = None,
                    ) -> None:
                        # increment a simple sequence counter; only keep every Nth
                        seq = rec.increment_seq()
                        if seq % sample_rate != 0:
                            return None
                        return orig_record_event(
                            name,
                            duration_ms=duration_ms,
                            extra=extra,
                            counters=counters,
                        )

                    rec.record_event = _sampled_record_event

                get_recorder.recorder = rec
            else:
                get_recorder.recorder = NoOpTelemetryRecorder()
    return get_recorder.recorder


__all__ = [
    "telemetry_enabled",
    "TelemetryRecorder",
    "NoOpTelemetryRecorder",
    "get_recorder",
]
