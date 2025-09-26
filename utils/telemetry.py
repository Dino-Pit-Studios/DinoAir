"""
Telemetry export system for DinoAir performance monitoring.

Provides opt-in telemetry export with memory-bounded metrics to prevent leaks.
Supports multiple export formats and configurable memory limits.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    # Performance monitor integration available but imports handled dynamically
    _HAS_PERFORMANCE_MONITOR = True
except ImportError:
    _HAS_PERFORMANCE_MONITOR = False

logger = logging.getLogger(__name__)


@dataclass
class TelemetryConfig:
    """Configuration for telemetry export."""

    enabled: bool = False  # Opt-in by default
    export_interval_seconds: float = 60.0  # Export every minute
    max_metrics_per_operation: int = 100  # Memory bound per operation
    max_total_metrics: int = 10000  # Total memory bound
    batch_size: int = 500  # Export batch size
    export_format: str = "json"  # json, csv, prometheus
    export_destination: str = "file"  # file, http, console
    output_file: str | None = None
    http_endpoint: str | None = None
    include_system_metrics: bool = True
    include_custom_metrics: bool = True
    retention_hours: float = 24.0  # How long to keep metrics before cleanup


class TelemetryExporter(ABC):
    """Abstract base class for telemetry exporters."""

    @abstractmethod
    def export_metrics(self, metrics: list[dict[str, Any]]) -> bool:
        """Export a batch of metrics. Returns True if successful."""

    @abstractmethod
    def close(self) -> None:
        """Clean up exporter resources."""


class JSONFileExporter(TelemetryExporter):
    """Exports telemetry data to JSON files."""

    def __init__(self, output_file: str):
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def export_metrics(self, metrics: list[dict[str, Any]]) -> bool:
        """Export metrics to JSON file."""
        try:
            with self._lock:
                # Append to existing file or create new one
                existing_data = []
                if self.output_file.exists():
                    try:
                        with open(self.output_file, encoding="utf-8") as f:
                            content = f.read().strip()
                            if content:
                                existing_data = json.loads(content)
                    except (OSError, json.JSONDecodeError):
                        # File exists but is invalid, start fresh
                        existing_data = []

                existing_data.extend(metrics)

                with open(self.output_file, "w", encoding="utf-8") as f:
                    json.dump(existing_data, f, indent=2, default=str)

                logger.debug("Exported %d metrics to %s", len(metrics), self.output_file)
                return True

        except OSError as e:
            logger.error("Failed to export metrics to %s: %s", self.output_file, e)
            return False

    def close(self) -> None:
        """Clean up file exporter."""
        # Nothing to clean up for file exporter


class ConsoleExporter(TelemetryExporter):
    """Exports telemetry data to console/logs."""

    def export_metrics(self, metrics: list[dict[str, Any]]) -> bool:
        """Export metrics to console."""
        try:
            for metric in metrics:
                logger.info("TELEMETRY: %s", json.dumps(metric, default=str))
            return True
        except Exception as e:
            logger.error("Failed to export metrics to console: %s", e)
            return False

    def close(self) -> None:
        """Clean up console exporter."""


class PrometheusExporter(TelemetryExporter):
    """Exports telemetry data in Prometheus format."""

    def __init__(self, output_file: str):
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def export_metrics(self, metrics: list[dict[str, Any]]) -> bool:
        """Export metrics in Prometheus format."""
        try:
            prometheus_lines = []

            for metric in metrics:
                operation = metric.get("operation", "unknown").replace("-", "_").replace(".", "_")
                timestamp = int(metric.get("timestamp", time.time()) * 1000)

                # Duration metric
                if "duration" in metric:
                    prometheus_lines.append(
                        f'dinoair_operation_duration_seconds{{operation="{operation}"}} '
                        f"{metric['duration']} {timestamp}"
                    )

                # Memory metric
                if "memory_usage" in metric and metric["memory_usage"]:
                    memory_bytes = metric["memory_usage"]
                    prometheus_lines.append(
                        f'dinoair_operation_memory_bytes{{operation="{operation}"}} '
                        f"{memory_bytes} {timestamp}"
                    )

                # CPU metric
                if "cpu_usage" in metric and metric["cpu_usage"]:
                    prometheus_lines.append(
                        f'dinoair_operation_cpu_percent{{operation="{operation}"}} '
                        f"{metric['cpu_usage']} {timestamp}"
                    )

            with self._lock, open(self.output_file, "a") as f:
                f.write("\n".join(prometheus_lines) + "\n")

            logger.debug("Exported %d metrics to Prometheus format", len(metrics))
            return True

        except Exception as e:
            logger.error("Failed to export Prometheus metrics: %s", e)
            return False

    def close(self) -> None:
        """Clean up Prometheus exporter."""


class HTTPExporter(TelemetryExporter):
    """Exports telemetry data via HTTP POST."""

    def __init__(self, endpoint: str, timeout: float = 30.0):
        self.endpoint = endpoint
        self.timeout = timeout

        # Try to import requests, fall back gracefully
        try:
            import requests

            self.requests = requests
            self._has_requests = True
        except ImportError:
            self.requests = None  # type: ignore[assignment]
            self._has_requests = False
            logger.warning("requests library not available, HTTP export disabled")

    def export_metrics(self, metrics: list[dict[str, Any]]) -> bool:
        """Export metrics via HTTP."""
        if not self._has_requests:
            logger.error("Cannot export via HTTP: requests library not available")
            return False

        try:
            payload = {"metrics": metrics, "timestamp": time.time(), "source": "dinoair"}

            response = self.requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                logger.debug("Successfully exported %s metrics via HTTP", len(metrics))
                return True
            logger.error(
                "HTTP export failed with status %s: %s", response.status_code, response.text
            )
            return False

        except Exception as e:
            logger.error("Failed to export metrics via HTTP: %s", e)
            return False

    def close(self) -> None:
        """Clean up HTTP exporter."""


class TelemetryManager:
    """Manages telemetry collection and export with memory bounds."""

    def __init__(self, config: TelemetryConfig | None = None):
        self.config = config or TelemetryConfig()
        self._metrics_buffer: dict[str, deque] = {}
        self._total_metrics_count = 0
        self._lock = threading.RLock()
        self._exporter: TelemetryExporter | None = None
        self._export_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_cleanup = time.time()

        if self.config.enabled:
            self._initialize_exporter()
            self._start_export_thread()

    def _initialize_exporter(self) -> None:
        """Initialize the appropriate exporter based on configuration."""
        try:
            if self.config.export_destination == "file":
                if self.config.export_format == "json":
                    output_file = self.config.output_file or "telemetry_metrics.json"
                    self._exporter = JSONFileExporter(output_file)
                elif self.config.export_format == "prometheus":
                    output_file = self.config.output_file or "telemetry_metrics.prom"
                    self._exporter = PrometheusExporter(output_file)
                else:
                    raise ValueError(f"Unsupported export format: {self.config.export_format}")

            elif self.config.export_destination == "http":
                if not self.config.http_endpoint:
                    raise ValueError("HTTP endpoint must be configured for HTTP export")
                self._exporter = HTTPExporter(self.config.http_endpoint)

            elif self.config.export_destination == "console":
                self._exporter = ConsoleExporter()

            else:
                raise ValueError(
                    f"Unsupported export destination: {self.config.export_destination}"
                )

        except Exception as e:
            logger.error("Failed to initialize telemetry exporter: %s", e)
            self._exporter = None

    def _start_export_thread(self) -> None:
        """Start the background export thread."""
        if self._exporter and not self._export_thread:
            self._export_thread = threading.Thread(
                target=self._export_loop, name="TelemetryExporter", daemon=True
            )
            self._export_thread.start()

    def _export_loop(self) -> None:
        """Background thread loop for exporting metrics."""
        while not self._stop_event.wait(self.config.export_interval_seconds):
            try:
                self._export_batch()
                self._cleanup_old_metrics()
            except Exception as e:
                logger.error("Error in telemetry export loop: %s", e)

    def _export_batch(self) -> None:
        """Export a batch of metrics."""
        if not self._exporter:
            return

        metrics_to_export = []

        with self._lock:
            # Collect metrics from all operations
            for _operation, operation_metrics in self._metrics_buffer.items():
                batch_count = 0
                while operation_metrics and batch_count < self.config.batch_size:
                    metric = operation_metrics.popleft()
                    self._total_metrics_count -= 1
                    metrics_to_export.append(self._serialize_metric(metric))
                    batch_count += 1

                if batch_count >= self.config.batch_size:
                    break

        if metrics_to_export:
            success = self._exporter.export_metrics(metrics_to_export)
            if not success:
                logger.warning("Failed to export %d metrics", len(metrics_to_export))

    @staticmethod
    def _serialize_metric(metric: Any) -> dict[str, Any]:
        """Serialize a metric for export."""
        if hasattr(metric, "__dict__"):
            # Handle dataclass or object with attributes
            result = {}
            for key, value in vars(metric).items():
                if key.startswith("_"):
                    continue
                result[key] = value
            return result
        if isinstance(metric, dict):
            return metric.copy()
        return {"metric": str(metric), "timestamp": time.time()}

    def _cleanup_old_metrics(self) -> None:
        """Remove old metrics to prevent memory leaks."""
        current_time = time.time()

        # Only cleanup periodically to avoid overhead
        if current_time - self._last_cleanup < 3600:  # Cleanup hourly
            return

        self._last_cleanup = current_time
        retention_seconds = self.config.retention_hours * 3600
        cutoff_time = current_time - retention_seconds

        with self._lock:
            for operation, operation_metrics in self._metrics_buffer.copy().items():
                # Remove old metrics
                original_count = len(operation_metrics)
                while operation_metrics:
                    metric = operation_metrics[0]
                    metric_time = getattr(metric, "timestamp", current_time)
                    if metric_time < cutoff_time:
                        operation_metrics.popleft()
                        self._total_metrics_count -= 1
                    else:
                        break

                # Remove empty operation buffers
                if not operation_metrics:
                    del self._metrics_buffer[operation]

                cleaned_count = original_count - len(operation_metrics)
                if cleaned_count > 0:
                    logger.debug(
                        "Cleaned up %s old metrics for operation %s", cleaned_count, operation
                    )

    def add_metric(self, metric: Any) -> None:
        """Add a metric to the telemetry buffer with memory bounds."""
        if not self.config.enabled:
            return

        with self._lock:
            # Extract operation name
            operation = getattr(metric, "operation", "unknown")

            # Initialize operation buffer if needed
            if operation not in self._metrics_buffer:
                self._metrics_buffer[operation] = deque(
                    maxlen=self.config.max_metrics_per_operation
                )

            operation_buffer = self._metrics_buffer[operation]

            # Check total metrics limit
            if self._total_metrics_count >= self.config.max_total_metrics:
                # Remove oldest metric from largest operation buffer
                largest_operation = max(
                    self._metrics_buffer.keys(), key=lambda op: len(self._metrics_buffer[op])
                )
                if self._metrics_buffer[largest_operation]:
                    self._metrics_buffer[largest_operation].popleft()
                    self._total_metrics_count -= 1

            # Add new metric
            operation_buffer.append(metric)
            self._total_metrics_count += 1

    def force_export(self) -> bool:
        """Force immediate export of all buffered metrics."""
        if not self._exporter:
            return False

        try:
            all_metrics = []

            with self._lock:
                for operation_metrics in self._metrics_buffer.values():
                    while operation_metrics:
                        metric = operation_metrics.popleft()
                        all_metrics.append(self._serialize_metric(metric))

                self._total_metrics_count = 0

            if all_metrics:
                return self._exporter.export_metrics(all_metrics)

            return True

        except Exception as e:
            logger.error("Failed to force export metrics: %s", e)
            return False

    def get_metrics_count(self) -> dict[str, int]:
        """Get current metrics count by operation."""
        with self._lock:
            return {operation: len(metrics) for operation, metrics in self._metrics_buffer.items()}

    def get_total_metrics_count(self) -> int:
        """Get total number of buffered metrics."""
        return self._total_metrics_count

    def update_config(self, **kwargs: Any) -> None:
        """Update telemetry configuration."""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)

            # Restart exporter if needed
            if self.config.enabled and not self._export_thread:
                self._initialize_exporter()
                self._start_export_thread()
            elif not self.config.enabled and self._export_thread:
                self.stop()

    def stop(self) -> None:
        """Stop telemetry collection and export."""
        self._stop_event.set()

        if self._export_thread and self._export_thread.is_alive():
            self._export_thread.join(timeout=5.0)

        if self._exporter:
            # Force final export
            self.force_export()
            self._exporter.close()

        self._export_thread = None
        self._exporter = None

    def clear_metrics(self) -> None:
        """Clear all buffered metrics."""
        with self._lock:
            self._metrics_buffer.clear()
            self._total_metrics_count = 0


# Global telemetry manager instance
_global_telemetry_manager: TelemetryManager | None = None
_telemetry_lock = threading.Lock()


def get_telemetry_manager(
    manager: TelemetryManager | None, lock: threading.Lock
) -> TelemetryManager:
    """Get or create the telemetry manager."""
    with lock:
        if manager is None:
            manager = TelemetryManager()
        return manager


def configure_telemetry(**kwargs: Any) -> None:
    """Configure global telemetry settings."""
    manager = get_telemetry_manager(_global_telemetry_manager, _telemetry_lock)
    manager.update_config(**kwargs)


def enable_telemetry(
    export_format: str = "json",
    export_destination: str = "file",
    output_file: str | None = None,
    **kwargs: Any,
) -> None:
    """Enable telemetry collection and export."""
    configure_telemetry(
        enabled=True,
        export_format=export_format,
        export_destination=export_destination,
        output_file=output_file,
        **kwargs,
    )


def disable_telemetry() -> None:
    """Disable telemetry collection."""
    manager = get_telemetry_manager(_global_telemetry_manager, _telemetry_lock)
    manager.update_config(enabled=False)


def export_telemetry() -> bool:
    """Force export of all telemetry data."""
    manager = get_telemetry_manager(_global_telemetry_manager, _telemetry_lock)
    return manager.force_export()


def _add_telemetry_metric(metric: Any) -> None:
    """Add a metric to telemetry (internal use only)."""
    manager = get_telemetry_manager(_global_telemetry_manager, _telemetry_lock)
    manager.add_metric(metric)


# Integration with performance monitor if available
if _HAS_PERFORMANCE_MONITOR:

    def _integrate_with_performance_monitor() -> None:
        """Integrate telemetry with performance monitor."""
        try:
            from utils.performance_monitor import _global_performance_monitor

            # Add telemetry as a hook to performance monitor
            original_end_operation = _global_performance_monitor.end_operation

            def telemetry_enabled_end_operation(operation_id: str) -> Any:
                """Telemetry enabled end operation.

                Args:
                    operation_id: Unique identifier for the operation to end
                """
                result = original_end_operation(operation_id)
                if result:
                    _add_telemetry_metric(result)
                return result

            # Monkey patch the end_operation method
            _global_performance_monitor.end_operation = telemetry_enabled_end_operation

        except Exception as e:
            logger.debug("Failed to integrate with performance monitor: %s", e)

    # Auto-integrate if performance monitor is available
    _integrate_with_performance_monitor()

__all__ = [
    "TelemetryConfig",
    "TelemetryManager",
    "get_telemetry_manager",
    "configure_telemetry",
    "enable_telemetry",
    "disable_telemetry",
    "export_telemetry",
]
