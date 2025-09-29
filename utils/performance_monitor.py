"""
Performance monitoring system for DinoAir 2.5

Provides comprehensive performance tracking including:
- Execution time monitoring
- Memory usage tracking
- CPU usage monitoring
- Custom metrics collection
- Decorators and context managers
- Configurable thresholds and alerts
- Integration with structured logging
"""

from __future__ import annotations

import functools
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

# Try to import enhanced logging, fallback to standard logging
try:
    from enhanced_logger import get_logger, update_log_context

    logger = get_logger(__name__)
    enhanced_logging_available = True
except ImportError:
    logger = logging.getLogger(__name__)
    enhanced_logging_available = False


@dataclass
class PerformanceMetrics:
    """Container for performance metrics data."""

    operation: str
    duration: float
    memory_usage: int | None = None
    cpu_usage: float | None = None
    custom_metrics: dict[str, Any] = field(default_factory=dict)
    timestamp: float | None = None
    thread_id: int | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.thread_id is None:
            self.thread_id = threading.get_ident()


@dataclass
class PerformanceConfig:
    """Configuration for performance monitoring."""

    enabled: bool = True
    sampling_rate: float = 1.0  # 1.0 = 100% sampling
    memory_threshold_mb: float | None = None
    cpu_threshold_percent: float | None = None
    duration_threshold_seconds: float | None = None
    max_metrics_retained: int = 1000
    alert_on_thresholds: bool = True
    log_level: str = "INFO"


class PerformanceMonitor:
    """Advanced performance monitoring and metrics collection."""

    def __init__(self, config: PerformanceConfig | None = None):
        self.config = config or PerformanceConfig()
        self._metrics: dict[str, deque[PerformanceMetrics]] = defaultdict(
            lambda: deque(maxlen=self.config.max_metrics_retained)
        )
        self._active_timers: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._custom_collectors: dict[str, Callable[[], Any]] = {}

    def add_custom_collector(self, name: str, collector_func: Callable[[], Any]) -> None:
        """Add a custom metrics collector function."""
        with self._lock:
            self._custom_collectors[name] = collector_func

    def remove_custom_collector(self, name: str) -> None:
        """Remove a custom metrics collector."""
        with self._lock:
            self._custom_collectors.pop(name, None)

    def _should_sample(self) -> bool:
        """Determine if this operation should be sampled."""
        if not self.config.enabled:
            return False
        # Use a cryptographically secure RNG when sampling might gate security-sensitive telemetry
        if self.config.sampling_rate >= 1.0:
            return True
        # Use secrets.randbelow for efficient cryptographic sampling
        return secrets.randbelow(10**6) < int(self.config.sampling_rate * 10**6)

    def _collect_system_metrics(self) -> dict[str, Any]:
        """Collect current system metrics."""
        metrics = {}

        if HAS_PSUTIL and psutil:
            try:
                process = psutil.Process()
                metrics["memory_mb"] = process.memory_info().rss / 1024 / 1024
                metrics["cpu_percent"] = process.cpu_percent(interval=None)
            except (psutil.Error, OSError):
                pass

        # Collect custom metrics
        for name, collector in self._custom_collectors.items():
            try:
                metrics[name] = collector()
            except Exception as e:
                if enhanced_logging_available:
                    logger.warning(
                        "Custom collector '%s' failed: %s",
                        name,
                        e,
                        extra={"collector_name": name, "error_type": type(e).__name__},
                    )
                else:
                    logger.warning("Custom collector '%s' failed: %s", name, e)

        return metrics

    def start_operation(self, operation: str, **context: Any) -> str:
        """Start timing an operation. Returns operation ID."""
        if not self._should_sample():
            return ""

        operation_id = f"{operation}_{threading.get_ident()}_{time.time_ns()}"

        with self._lock:
            start_time = time.perf_counter()
            initial_metrics = self._collect_system_metrics()

            self._active_timers[operation_id] = {
                "operation": operation,
                "start_time": start_time,
                "initial_memory": initial_metrics.get("memory_mb"),
                "initial_cpu": initial_metrics.get("cpu_percent"),
                "context": context,
            }

        return operation_id

    def end_operation(self, operation_id: str) -> PerformanceMetrics | None:
        """End timing an operation and record metrics."""
        if not operation_id or not self._should_sample():
            return None

        with self._lock:
            if operation_id not in self._active_timers:
                return None

            timer_data = self._active_timers.pop(operation_id)
            duration = time.perf_counter() - timer_data["start_time"]

            final_metrics = self._collect_system_metrics()
            memory_usage = None
            cpu_usage = None

            if timer_data["initial_memory"] is not None and "memory_mb" in final_metrics:
                memory_usage = int(
                    final_metrics["memory_mb"] * 1024 * 1024
                )  # Convert back to bytes

            if timer_data["initial_cpu"] is not None and "cpu_percent" in final_metrics:
                cpu_usage = final_metrics["cpu_percent"]

            # Collect custom metrics
            custom_metrics = {}
            for key, value in final_metrics.items():
                if key not in ("memory_mb", "cpu_percent"):
                    custom_metrics[key] = value

            # Add context to custom metrics
            custom_metrics.update(timer_data.get("context", {}))

            metric = PerformanceMetrics(
                operation=timer_data["operation"],
                duration=duration,
                memory_usage=memory_usage,
                cpu_usage=cpu_usage,
                custom_metrics=custom_metrics,
            )

            self._metrics[timer_data["operation"]].append(metric)

            # Check thresholds and alert if needed
            self._check_thresholds(metric)

            return metric

    def _check_thresholds(self, metric: PerformanceMetrics) -> None:
        """Check if metrics exceed configured thresholds."""
        if not self.config.alert_on_thresholds:
            return

        alerts = []

        if (
            self.config.duration_threshold_seconds
            and metric.duration > self.config.duration_threshold_seconds
        ):
            alerts.append(
                f"Duration {metric.duration:.3f}s exceeds threshold "
                f"{self.config.duration_threshold_seconds}s"
            )

        if (
            self.config.memory_threshold_mb
            and metric.memory_usage
            and metric.memory_usage > self.config.memory_threshold_mb * 1024 * 1024
        ):
            memory_mb = metric.memory_usage / 1024 / 1024
            alerts.append(
                f"Memory {memory_mb:.1f}MB exceeds threshold {self.config.memory_threshold_mb}MB"
            )

        if (
            self.config.cpu_threshold_percent
            and metric.cpu_usage
            and metric.cpu_usage > self.config.cpu_threshold_percent
        ):
            alerts.append(
                f"CPU {metric.cpu_usage:.1f}% exceeds threshold "
                f"{self.config.cpu_threshold_percent}%"
            )

        if alerts:
            alert_msg = f"Performance alert for {metric.operation}: {'; '.join(alerts)}"
            log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)

            if enhanced_logging_available:
                # Use enhanced logging with context
                update_log_context(
                    operation=metric.operation,
                    component="performance_monitor",
                    alert_type="threshold_exceeded",
                    threshold_details=alerts,
                )
                logger.log(
                    log_level,
                    alert_msg,
                    extra={
                        "operation": metric.operation,
                        "duration": metric.duration,
                        "memory_usage": metric.memory_usage,
                        "cpu_usage": metric.cpu_usage,
                        "custom_metrics": metric.custom_metrics,
                        "alerts": alerts,
                        "performance_data": {
                            "duration": metric.duration,
                            "memory_mb": (
                                metric.memory_usage / 1024 / 1024 if metric.memory_usage else None
                            ),
                            "cpu_percent": metric.cpu_usage,
                        },
                    },
                )
            else:
                logger.log(
                    log_level,
                    alert_msg,
                    extra={
                        "operation": metric.operation,
                        "duration": metric.duration,
                        "memory_usage": metric.memory_usage,
                        "cpu_usage": metric.cpu_usage,
                        "custom_metrics": metric.custom_metrics,
                    },
                )

    def get_metrics(self, operation: str | None = None) -> dict[str, Any]:
        """Get aggregated performance metrics."""
        with self._lock:
            if operation:
                metrics = list(self._metrics.get(operation, []))
                if not metrics:
                    return {}

                durations = [m.duration for m in metrics]
                memory_usages = [m.memory_usage for m in metrics if m.memory_usage is not None]
                cpu_usages = [m.cpu_usage for m in metrics if m.cpu_usage is not None]

                result = {
                    "count": len(metrics),
                    "avg_duration": sum(durations) / len(durations) if durations else 0,
                    "min_duration": min(durations) if durations else 0,
                    "max_duration": max(durations) if durations else 0,
                    "total_duration": sum(durations),
                    "latest": metrics[-1] if metrics else None,
                }

                if memory_usages:
                    result.update(
                        {
                            "avg_memory_mb": sum(memory_usages) / len(memory_usages) / 1024 / 1024,
                            "max_memory_mb": max(memory_usages) / 1024 / 1024,
                        }
                    )

                if cpu_usages:
                    result.update(
                        {
                            "avg_cpu_percent": sum(cpu_usages) / len(cpu_usages),
                            "max_cpu_percent": max(cpu_usages),
                        }
                    )

                return result
            return {op: self.get_metrics(op) for op in self._metrics}

    def clear_metrics(self, operation: str | None = None) -> None:
        """Clear stored metrics."""
        with self._lock:
            if operation:
                self._metrics.pop(operation, None)
            else:
                self._metrics.clear()

    def get_active_operations(self) -> list[str]:
        """Get list of currently active operations."""
        with self._lock:
            return list(self._active_timers.keys())

    def update_config(self, **kwargs: Any) -> None:
        """Update monitoring configuration."""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)


# Global performance monitor instance
_global_performance_monitor = PerformanceMonitor()


def performance_monitor_decorator(
    operation: str | None = None,
    monitor: PerformanceMonitor | None = None,
    **context: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for automatic performance monitoring of functions."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator.

        Args:
            func: Function to be wrapped with performance monitoring

        Returns:
            Wrapped function with automatic performance tracking
        """
        op_name = operation or f"{func.__module__}.{func.__qualname__}"
        mon = monitor or _global_performance_monitor

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Wrapper.

            Returns:
                Return value from the wrapped function
            """
            operation_id = mon.start_operation(op_name, **context)
            try:
                return func(*args, **kwargs)
            finally:
                mon.end_operation(operation_id)

        return wrapper

    return decorator


# Shorter alias for the decorator
performance_monitor = performance_monitor_decorator


@contextmanager
def performance_context(
    operation: str, monitor: PerformanceMonitor | None = None, **context: Any
) -> Generator[None, None, None]:
    """Context manager for scoped performance monitoring."""
    mon = monitor or _global_performance_monitor
    operation_id = mon.start_operation(operation, **context)
    try:
        yield
    finally:
        mon.end_operation(operation_id)


# Utility functions for easy access
def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    return _global_performance_monitor


def enable_performance_monitoring() -> None:
    """Enable performance monitoring globally."""
    _global_performance_monitor.config.enabled = True


def disable_performance_monitoring() -> None:
    """Disable performance monitoring globally."""
    _global_performance_monitor.config.enabled = False


def configure_performance_monitoring(**kwargs: Any) -> None:
    """Configure global performance monitoring settings."""
    _global_performance_monitor.update_config(**kwargs)
