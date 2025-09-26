"""
Simple, dependency-free adaptive chunk sizing benchmark simulation.

This script simulates chunk processing with an AdaptiveChunkSizer controller, using
a seeded RNG for determinism. It prints a JSON summary to stdout:

{
  "flag": true,
  "throughput_bytes_per_s": float,
  "p50_ms": int,
  "p95_ms": int,
  "size_timeline": [int],
  "decisions": {"inc": N, "dec": N, "noop": N}
}

Run:
  python examples/adaptive_benchmark.py
"""

from __future__ import annotations

import random
import statistics

# Local import; no heavy deps
from pseudocode_translator.streaming.adaptive import AdaptiveChunkSizer


def p50(values: list[float]) -> float:
    if not values:
        return 0.0
    return statistics.median(sorted(values))


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    idx = int(round(0.95 * (len(vals) - 1)))
    return float(vals[idx])


def simulate(flag: bool = True, seed: int = 1337) -> dict:
    rnd = random.Random(seed)

    # Controller configuration
    min_size = 200
    max_size = 2000
    target_ms = 600
    alpha = 0.2
    hysteresis = 0.2
    cooldown = 3
    init_size = 500
    default_chunk_size = init_size

    # Fake "environment" latency model:
    # Latency grows sublinearly with size plus noise.
    # Base at 350ms for 500 bytes; scale roughly by sqrt(size/500).
    def latency_model(size: int) -> float:
        if size <= 0:
            return 5.0
        base = 350.0 * (size / 500.0) ** 0.5
        noise = rnd.uniform(-30.0, 30.0)
        # Add occasional spikes
        if rnd.random() < 0.05:
            base *= rnd.uniform(1.5, 2.0)
        return max(1.0, base + noise)

    sizer = AdaptiveChunkSizer(
        min_size=min_size,
        max_size=max_size,
        target_ms=target_ms,
        alpha=alpha,
        hysteresis_pct=hysteresis,
        cooldown_chunks=cooldown,
        step_pct=0.2,
        initial_size=init_size,
    )

    sizes: list[int] = []
    latencies: list[float] = []
    decisions = {"inc": 0, "dec": 0, "noop": 0}

    total_bytes = 0
    total_time_ms = 0.0

    # Simulate 100 chunks
    prev_size = None
    for _ in range(100):
        desired = (
            sizer.get_next_chunk_size(default_chunk_size=default_chunk_size)
            if flag
            else default_chunk_size
        )
        sizes.append(desired)

        # Decision accounting
        if prev_size is None or desired == prev_size:
            decisions["noop"] += 1
        elif desired > prev_size:
            decisions["inc"] += 1
        else:
            decisions["dec"] += 1
        prev_size = desired

        # "Process" chunk and observe latency
        obs_ms = latency_model(desired)
        latencies.append(obs_ms)

        total_bytes += desired
        total_time_ms += obs_ms

        # Update feedback (no backpressure; no TPS ceiling here)
        if flag:
            sizer.update_feedback(
                last_chunk_chars=desired,
                observed_latency_ms=obs_ms,
                queue_utilization=0.0,
                model_tps=None,
            )

    throughput_bps = (total_bytes / (total_time_ms / 1000.0)) if total_time_ms > 0 else 0.0
    return {
        "flag": bool(flag),
        "throughput_bytes_per_s": float(round(throughput_bps, 2)),
        "p50_ms": int(round(p50(latencies))),
        "p95_ms": int(round(p95(latencies))),
        "size_timeline": sizes,
        "decisions": decisions,
    }


if __name__ == "__main__":
    # Print two summaries for quick comparison: adaptive on vs. off
    res_on = simulate(flag=True, seed=1337)
    res_off = simulate(flag=False, seed=1337)
