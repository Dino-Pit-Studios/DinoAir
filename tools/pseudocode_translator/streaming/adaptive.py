"""
Adaptive chunk sizing controller with hysteresis, smoothing, and cooldown.

This module provides a pure-Python controller that adjusts the desired chunk size
for streaming pipelines based on observed processing latency and (optional) backpressure.

Key features:
- Exponential smoothing of observed latencies
- Hysteresis bands around a target latency to avoid oscillation
- Cooldown in "chunks" between adjustments to prevent thrashing
- Optional backpressure guard to block increases when queues are full
- Optional throughput ceiling using model tokens-per-second (TPS)

Usage pattern (controller-level):
    sizer = AdaptiveChunkSizer(min_size=200, max_size=2000, target_ms=600, alpha=0.2,
                               hysteresis_pct=0.2, cooldown_chunks=3, step_pct=0.2,
                               initial_size=512)

    # First decision (will initialize to initial/default and no-op until feedback is present)
    size = sizer.get_next_chunk_size(default_chunk_size=512)

    # After processing a chunk, provide feedback
    sizer.update_feedback(last_chunk_chars=size, observed_latency_ms=450.0,
                          queue_utilization=0.1, model_tps=None)

    # Next desired size
    size = sizer.get_next_chunk_size(default_chunk_size=512)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _ConfigSnapshot:
    """Holds immutable configuration parameters for AdaptiveChunkSizer."""

    min_size: int
    max_size: int
    target_ms: int
    alpha: float
    hysteresis_pct: float
    cooldown_chunks: int
    step_pct: float


class AdaptiveChunkSizer:
    """
    Adaptive chunk sizing controller.

    State:
      - current_size: int | None
      - cooldown_remaining: int
      - smoothed_latency_ms: float | None
      - config snapshot: min_size, max_size, target_ms, alpha, hysteresis_pct,
                         cooldown_chunks, step_pct

    Algorithm:
      - Exponential smoothing: s = alpha * observed + (1 - alpha) * prev
        If prev is None, s := observed.
      - Hysteresis bands:
          lower = target * (1 - hysteresis_pct)
          upper = target * (1 + hysteresis_pct)
        If smoothed > upper: decrease by step_pct
        If smoothed < lower and queue_utilization < 0.8: increase by step_pct
        Else: no-op
      - Cooldown: when a change occurs, set cooldown_remaining = cooldown_chunks.
        While cooldown_remaining > 0, decisions are frozen (no-op). The counter
        decrements once per feedback update (i.e., after each processed chunk).
      - Optional TPS ceiling: if model_tps is known, cap new_size to
            int(model_tps * (target_ms / 1000.0))
    """

    def __init__(
        self,
        min_size: int,
        max_size: int,
        target_ms: int,
        alpha: float,
        hysteresis_pct: float,
        cooldown_chunks: int,
        step_pct: float = 0.2,
        initial_size: int | None = None,
    ) -> None:
        """
        Initialize the controller.

        Args:
            min_size: Minimum allowed chunk size (inclusive).
            max_size: Maximum allowed chunk size (inclusive).
            target_ms: Target per-chunk processing latency in milliseconds.
            alpha: Exponential smoothing factor (0 < alpha ≤ 1).
            hysteresis_pct: Fractional hysteresis band width (e.g., 0.2 for ±20%).
            cooldown_chunks: Number of chunks to wait between adjustments.
            step_pct: Fractional step size for adjustments (default 0.2, i.e., 20%).
            initial_size: Optional starting size; will be clamped into [min, max].
        """
        if min_size <= 0:
            raise ValueError("min_size must be > 0")
        if max_size < min_size:
            raise ValueError("max_size must be ≥ min_size")
        if target_ms <= 0:
            raise ValueError("target_ms must be > 0")
        if not (0.0 < alpha <= 1.0):
            raise ValueError("alpha must satisfy 0 < alpha ≤ 1.0")
        if hysteresis_pct < 0.0:
            raise ValueError("hysteresis_pct must be ≥ 0.0")
        if cooldown_chunks < 0:
            raise ValueError("cooldown_chunks must be ≥ 0")
        if step_pct <= 0.0:
            raise ValueError("step_pct must be > 0")

        self.config = _ConfigSnapshot(
            min_size=int(min_size),
            max_size=int(max_size),
            target_ms=int(target_ms),
            alpha=float(alpha),
            hysteresis_pct=float(hysteresis_pct),
            cooldown_chunks=int(cooldown_chunks),
            step_pct=float(step_pct),
        )

        self.current_size: int | None = (
            int(self._clamp(initial_size)) if initial_size is not None else None
        )
        self.cooldown_remaining: int = 0
        self.smoothed_latency_ms: float | None = None

        # Most recent signals (used by get_next decision)
        self._last_queue_util: float = 0.0
        self._last_model_tps: float | None = None  # tokens/sec ceiling (optional)

    def update_feedback(
        self,
        last_chunk_chars: int,
        observed_latency_ms: float,
        queue_utilization: float,
        model_tps: float | None = None,
    ) -> None:
        """
        Update controller with feedback from the last processed chunk.

        Args:
            last_chunk_chars: Size (in characters/bytes) of the last chunk.
            observed_latency_ms: Observed processing time of the last chunk.
            queue_utilization: Backpressure indicator in [0.0, 1.0] (approx).
            model_tps: Optional tokens-per-second ceiling for throughput capping.
        """
        # Exponential smoothing
        obs = float(observed_latency_ms)
        if self.smoothed_latency_ms is None:
            self.smoothed_latency_ms = obs
        else:
            a = self.config.alpha
            self.smoothed_latency_ms = a * obs + (1.0 - a) * float(self.smoothed_latency_ms)

        # Record signals for next decision
        self._last_queue_util = float(max(0.0, min(1.0, queue_utilization)))
        self._last_model_tps = float(model_tps) if model_tps is not None else None

        # Cooldown decrements once per processed chunk
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= 1
            self.cooldown_remaining = max(self.cooldown_remaining, 0)

    def get_next_chunk_size(self, default_chunk_size: int) -> int:
        """
        Compute the desired chunk size for the next chunk.

        Behavior:
          - Initialize current_size if None using initial or default, clamped.
          - If cooldown_remaining > 0 or no smoothed latency yet: return current_size (or initialized).
          - Otherwise:
              * Compute hysteresis band around target.
              * If smoothed > upper: decrease by step_pct of current_size.
              * If smoothed < lower and queue_utilization < 0.8: increase by step_pct.
              * Else: no-op.
              * If model_tps is set, cap new_size ≤ int(model_tps * (target_ms / 1000)).
          - Clamp to [min, max].
          - If changed, set cooldown_remaining to cooldown_chunks and update current_size.

        Args:
            default_chunk_size: Fallback size to initialize from if current_size is None.

        Returns:
            Desired chunk size for the next chunk.
        """
        # Initialize if needed
        if self.current_size is None:
            self.current_size = int(self._clamp(default_chunk_size))
            return self.current_size

        # If no smoothed data yet, or in cooldown, hold steady
        if self.smoothed_latency_ms is None or self.cooldown_remaining > 0:
            return int(self.current_size)

        # Hysteresis band
        target = float(self.config.target_ms)
        lower = target * (1.0 - float(self.config.hysteresis_pct))
        upper = target * (1.0 + float(self.config.hysteresis_pct))

        cur = int(self.current_size)
        step = max(1, int(round(cur * float(self.config.step_pct))))

        new_size = cur
        s = float(self.smoothed_latency_ms)

        if s > upper:
            # Too slow: decrease
            new_size = cur - step
        elif s < lower and self._last_queue_util < 0.8:
            # Faster than needed and no backpressure: increase
            new_size = cur + step
        else:
            # No change
            return int(self.current_size)

        # Optional TPS ceiling
        if self._last_model_tps is not None and self._last_model_tps > 0.0:
            ceiling = int(self._last_model_tps * (self.config.target_ms / 1000.0))
            if ceiling > 0:
                new_size = min(new_size, ceiling)

        # Clamp to bounds
        new_size = int(self._clamp(new_size))

        if new_size != cur:
            self.current_size = new_size
            self.cooldown_remaining = int(self.config.cooldown_chunks)

        return int(self.current_size)

    # ---------------- internal helpers ----------------

    def _clamp(self, size: int | None) -> int:
        """Clamp size into [min_size, max_size]; if None, return min of (default-ish) bounds."""
        if size is None:
            # Reasonable initialization: midpoint between min and max
            return int((self.config.min_size + self.config.max_size) // 2)
        s = int(size)
        if s < self.config.min_size:
            return int(self.config.min_size)
        if s > self.config.max_size:
            return int(self.config.max_size)
        return s


__all__ = ["AdaptiveChunkSizer"]
