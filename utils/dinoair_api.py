"""
DinoAir Performance and Telemetry API

Stable public API for performance monitoring and telemetry collection.
This module provides a clean interface while hiding internal implementation details.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

# Import internal modules with error handling
try:
    from utils import performance_monitor as _performance_monitor
    from utils import telemetry as _telemetry

    _HAS_PERFORMANCE_MONITOR = True
    _HAS_TELEMETRY = True
except ImportError as e:
    logging.warning("Failed to import performance/telemetry modules: %s", e)
    _performance_monitor = None
    _telemetry = None
    _HAS_PERFORMANCE_MONITOR = False
    _HAS_TELEMETRY = False

logger = logging.getLogger(__name__)

# Re-export key public types (hide internal prefixes)
if _HAS_PERFORMANCE_MONITOR:
    PerformanceConfig = _performance_monitor.PerformanceConfig
    PerformanceMetrics = _performance_monitor.PerformanceMetrics
else:
    # Stub classes if performance monitor not available
    class PerformanceConfig:
        """Stub configuration class for performance monitoring when the
        performance monitor is unavailable.
        """

        def __init__(self, **kwargs):
            pass
            # Intentionally empty constructor for stub configuration

    class PerformanceMetrics:
        """Stub metrics class for performance monitoring results when the
        performance monitor is unavailable.
        """

        def __init__(self, **kwargs):
            """No initialization required for stub metrics when monitor is unavailable."""


if _HAS_TELEMETRY:
    TelemetryConfig = _telemetry.TelemetryConfig
else:
    # Stub class if telemetry not available
    class TelemetryConfig:
        """Stub configuration class for telemetry when the internal telemetry
        module is unavailable.
        """

        def __init__(self, **kwargs):
            """Initialize stub telemetry config; no operation."""


class PerformanceMonitor:
    """
    Public API for performance monitoring.

    Provides a clean interface for measuring operation performance
    with optional telemetry export.
    """

    def __init__(self, config: PerformanceConfig | None = None):
        """Initialize performance monitor with optional configuration."""
        self._config = config
        self._monitor = None

        if _HAS_PERFORMANCE_MONITOR:
            try:
                self._monitor = _performance_monitor.get_performance_monitor()
                if config:
                    self._monitor.update_config(**config.__dict__)
            except Exception as e:
                logger.warning("Failed to initialize performance monitor: %s", e)

    def start_operation(self, operation: str, **metadata: Any) -> str:
        """
        Start monitoring a performance operation.

        Args:
            operation: Name of the operation to monitor
            **metadata: Additional metadata to attach to the operation

        Returns:
            Operation ID for tracking this specific operation instance
        """
        if self._monitor:
            return self._monitor.start_operation(operation, **metadata)
        return f"noop-{operation}"

    def end_operation(self, operation_id: str) -> PerformanceMetrics | None:
        """
        End monitoring an operation and get performance metrics.

        Args:
            operation_id: The operation ID returned by start_operation

        Returns:
            Performance metrics if monitoring is enabled, None otherwise
        """
        if self._monitor:
            return self._monitor.end_operation(operation_id)
        return None

    @staticmethod
    def record_custom_metric(operation: str, name: str, value: int | float) -> None:
        """
        Record a custom metric for an operation.

        Args:
            operation: Operation name
            name: Metric name
            value: Metric value
        """

    def get_metrics_summary(self) -> dict[str, Any]:
        """
        Get summary of all collected metrics.

        Returns:
            Dictionary containing metrics summary
        """
        if self._monitor:
            return self._monitor.get_metrics()
        return {}

    def clear_metrics(self) -> None:
        """Clear all collected metrics."""
        if self._monitor:
            self._monitor.clear_metrics()

    @contextmanager
    def monitor_operation(self, operation: str, **metadata: Any):
        """
        Context manager for monitoring operations.

        Args:
            operation: Name of the operation to monitor
            **metadata: Additional metadata to attach

        Yields:
            Operation ID for the monitored operation
        """
        operation_id = self.start_operation(operation, **metadata)
        try:
            yield operation_id
        finally:
            self.end_operation(operation_id)


class TelemetryManager:
    """
    Public API for telemetry collection and export.

    Provides opt-in telemetry with memory bounds to prevent leaks.
    """

    def __init__(self, config: TelemetryConfig | None = None):
        """Initialize telemetry manager with optional configuration."""
        self._config = config
        self._manager = None

        if _HAS_TELEMETRY:
            try:
                self._manager = _telemetry.get_telemetry_manager(self._lock, self._manager)
                if config:
                    self._manager.update_config(**config.__dict__)
            except Exception as e:
                logger.warning("Failed to initialize telemetry manager: %s", e)

    def enable(
        self,
        export_format: str = "json",
        export_destination: str = "file",
        output_file: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Enable telemetry collection and export.

        Args:
            export_format: Format for exported data (json, prometheus, csv)
            export_destination: Where to export (file, http, console)
            output_file: Output file path for file destination
            **kwargs: Additional configuration options
        """
        if self._manager:
            self._manager.update_config(
                enabled=True,
                export_format=export_format,
                export_destination=export_destination,
                output_file=output_file,
                **kwargs,
            )

    def disable(self) -> None:
        """Disable telemetry collection."""
        if self._manager:
            self._manager.update_config(enabled=False)

    def force_export(self) -> bool:
        """
        Force immediate export of all buffered telemetry data.

        Returns:
            True if export was successful, False otherwise
        """
        if self._manager:
            return self._manager.force_export()
        return False

    def get_metrics_count(self) -> dict[str, int]:
        """
        Get count of buffered metrics by operation.

        Returns:
            Dictionary mapping operation names to metric counts
        """
        if self._manager:
            return self._manager.get_metrics_count()
        return {}

    def configure(self, **kwargs: Any) -> None:
        """
        Update telemetry configuration.

        Args:
            **kwargs: Configuration options to update
        """
        if self._manager:
            self._manager.update_config(**kwargs)

    def clear_metrics(self) -> None:
        """Clear all buffered telemetry metrics."""
        if self._manager:
            self._manager.clear_metrics()


def monitor_performance(operation: str, **metadata: Any):
    """
    Convenience function for monitoring operations.

    Args:
        operation: Name of the operation to monitor
        **metadata: Additional metadata to attach

    Returns:
        Context manager that yields operation ID
    """
    monitor = get_performance_monitor()
    return monitor.monitor_operation(operation, **metadata)


def performance_decorator(operation: str | None = None, **metadata: Any):
    """
    Decorator for automatically monitoring function performance.

    Args:
        operation: Custom operation name (defaults to function name)
        **metadata: Additional metadata to attach

    Returns:
        Decorated function with performance monitoring
    """
    if _HAS_PERFORMANCE_MONITOR:
        return _performance_monitor.performance_monitor_decorator(operation, **metadata)

    # Return no-op decorator if performance monitor not available
    def decorator(func):
        """No-op decorator when performance monitor is not available.

        Args:
            func: The function to be decorated.

        Returns:
            The original function unchanged.
        """
        return func

    return decorator


def enable_performance_monitoring(_config: PerformanceConfig | None = None) -> None:
    """
    Enable global performance monitoring.

    Args:
        config: Optional configuration for performance monitoring
    """
    if _HAS_PERFORMANCE_MONITOR:
        _performance_monitor.enable_performance_monitoring()


def disable_performance_monitoring() -> None:
    """Disable global performance monitoring."""
    if _HAS_PERFORMANCE_MONITOR:
        _performance_monitor.disable_performance_monitoring()


def get_performance_monitor() -> PerformanceMonitor:
    """
    Get the global performance monitor instance.

    Returns:
        PerformanceMonitor instance
    """
    return PerformanceMonitor()


def get_telemetry_manager() -> TelemetryManager:
    """
    Get the global telemetry manager instance.

    Returns:
        TelemetryManager instance
    """
    return TelemetryManager()


def enable_telemetry(
    export_format: str = "json",
    export_destination: str = "file",
    output_file: str | None = None,
    **kwargs: Any,
) -> None:
    """
    Enable global telemetry collection and export.

    Args:
        export_format: Format for exported data (json, prometheus, csv)
        export_destination: Where to export (file, http, console)
        output_file: Output file path for file destination
        **kwargs: Additional configuration options
    """
    manager = get_telemetry_manager()
    manager.enable(export_format, export_destination, output_file, **kwargs)


def disable_telemetry() -> None:
    """Disable global telemetry collection."""
    manager = get_telemetry_manager()
    manager.disable()


def export_telemetry() -> bool:
    """
    Force export of all telemetry data.

    Returns:
        True if export was successful, False otherwise
    """
    manager = get_telemetry_manager()
    return manager.force_export()


def configure_performance(**kwargs: Any) -> None:
    """
    Configure global performance monitoring settings.

    Args:
        **kwargs: Configuration options to update
    """
    if _HAS_PERFORMANCE_MONITOR:
        monitor = _performance_monitor.get_performance_monitor()
        monitor.update_config(**kwargs)


def configure_telemetry(**kwargs: Any) -> None:
    """
    Configure global telemetry settings.

    Args:
        **kwargs: Configuration options to update
    """
    manager = get_telemetry_manager()
    manager.configure(**kwargs)


# Public API exports - only expose clean public interface
__all__ = [
    # Core classes
    "PerformanceMonitor",
    "TelemetryManager",
    "PerformanceConfig",
    "PerformanceMetrics",
    "TelemetryConfig",
    # Performance monitoring functions
    "get_performance_monitor",
    "enable_performance_monitoring",
    "disable_performance_monitoring",
    "monitor_performance",
    "performance_decorator",
    "configure_performance",
    # Telemetry functions
    "get_telemetry_manager",
    "enable_telemetry",
    "disable_telemetry",
    "export_telemetry",
    "configure_telemetry",
]
