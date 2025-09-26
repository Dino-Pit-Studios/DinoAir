"""
DinoAir Metrics Collection Module
Provides custom metrics collection for monitoring business and performance metrics.
"""

import logging
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any

from datadog import DogStatsd


class DinoAirMetrics:
    """Central metrics collection class for DinoAir application."""

    def __init__(self, host: str = "localhost", port: int = 8125, prefix: str = "dinoair"):
        """
        Initialize the metrics client.

        Args:
            host: DogStatsD host (default: localhost)
            port: DogStatsD port (default: 8125)
            prefix: Metric name prefix (default: dinoair)
        """
        self.client = DogStatsd(host=host, port=port, namespace=prefix)
        self.logger = logging.getLogger(__name__)

        # Tags to add to all metrics
        self.default_tags = ["service:security_auth", "environment:prod", "version:1.0.0"]

        self.logger.info("Initialized DinoAir metrics client: %s:%s", host, port)

    def increment(self, metric_name: str, value: int = 1, tags: list[str] | None = None) -> None:
        """
        Increment a counter metric.

        Args:
            metric_name: Name of the metric
            value: Amount to increment (default: 1)
            tags: Additional tags for this metric
        """
        all_tags = self.default_tags + (tags or [])
        self.client.increment(metric_name, value=value, tags=all_tags)
        self.logger.debug("Incremented metric %s by %s", metric_name, value)

    def decrement(self, metric_name: str, value: int = 1, tags: list[str] | None = None) -> None:
        """
        Decrement a counter metric.

        Args:
            metric_name: Name of the metric
            value: Amount to decrement (default: 1)
            tags: Additional tags for this metric
        """
        all_tags = self.default_tags + (tags or [])
        self.client.decrement(metric_name, value=value, tags=all_tags)
        self.logger.debug("Decremented metric %s by %s", metric_name, value)

    def gauge(self, metric_name: str, value: float, tags: list[str] | None = None) -> None:
        """
        Set a gauge metric value.

        Args:
            metric_name: Name of the metric
            value: Gauge value
            tags: Additional tags for this metric
        """
        all_tags = self.default_tags + (tags or [])
        self.client.gauge(metric_name, value=value, tags=all_tags)
        self.logger.debug("Set gauge %s to %s", metric_name, value)

    def histogram(self, metric_name: str, value: float, tags: list[str] | None = None) -> None:
        """
        Record a histogram value.

        Args:
            metric_name: Name of the metric
            value: Value to record
            tags: Additional tags for this metric
        """
        all_tags = self.default_tags + (tags or [])
        self.client.histogram(metric_name, value=value, tags=all_tags)
        self.logger.debug("Recorded histogram %s value %s", metric_name, value)

    def timing(self, metric_name: str, value: float, tags: list[str] | None = None) -> None:
        """
        Record a timing metric in milliseconds.

        Args:
            metric_name: Name of the metric
            value: Duration in milliseconds
            tags: Additional tags for this metric
        """
        all_tags = self.default_tags + (tags or [])
        self.client.timing(metric_name, value=value, tags=all_tags)
        self.logger.debug("Recorded timing %s: %sms", metric_name, value)

    @contextmanager
    def timer(self, metric_name: str, tags: list[str] | None = None):
        """
        Context manager for timing operations.

        Args:
            metric_name: Name of the timing metric
            tags: Additional tags for this metric

        Usage:
            with metrics.timer('api.request_duration'):
                # do some work
                pass
        """
        start_time = time.time()
        try:
            yield
        finally:
            duration_ms = (time.time() - start_time) * 1000
            self.timing(metric_name, duration_ms, tags)

    def timed(self, metric_name: str, tags: list[str] | None = None):
        """
        Decorator for timing function execution.

        Args:
            metric_name: Name of the timing metric
            tags: Additional tags for this metric

        Usage:
            @metrics.timed('function.execution_time')
            def my_function():
                pass
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                with self.timer(metric_name, tags):
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    def close(self) -> None:
        """Close the metrics client."""
        if hasattr(self.client, "close"):
            self.client.close()
        self.logger.info("Closed DinoAir metrics client")


# Global metrics instance
_metrics_client: DinoAirMetrics | None = None


_metrics_client: DinoAirMetrics = None


def get_metrics_client() -> DinoAirMetrics:
    """Get the global metrics client instance."""
    global _metrics_client
    if _metrics_client is None:
        _metrics_client = DinoAirMetrics()
    return _metrics_client


# Convenience functions
def increment_counter(metric_name: str, value: int = 1, tags: list[str] | None = None) -> None:
    """Increment a counter metric using the global client."""
    get_metrics_client().increment(metric_name, value, tags)


def record_gauge(metric_name: str, value: float, tags: list[str] | None = None) -> None:
    """Record a gauge metric using the global client."""
    get_metrics_client().gauge(metric_name, value, tags)


def record_timing(metric_name: str, value: float, tags: list[str] | None = None) -> None:
    """Record a timing metric using the global client."""
    get_metrics_client().timing(metric_name, value, tags)


# Business metrics helpers
def track_page_view(page_name: str, user_id: str | None = None) -> None:
    """Track a page view."""
    tags = [f"page:{page_name}"]
    if user_id:
        tags.append(f"user:{user_id}")
    increment_counter("page.views", tags=tags)


def track_api_request(endpoint: str, method: str, status_code: int, duration_ms: float) -> None:
    """Track an API request."""
    tags = [f"endpoint:{endpoint}", f"method:{method}", f"status_code:{status_code}"]

    # Count the request
    increment_counter("api.requests", tags=tags)

    # Record the duration
    record_timing("api.request_duration", duration_ms, tags=tags)

    # Track error rates
    if status_code >= 400:
        increment_counter("api.errors", tags=tags)


def track_security_event(
    event_type: str, severity: str, details: dict[str, Any] | None = None
) -> None:
    """Track a security-related event."""
    tags = [f"event_type:{event_type}", f"severity:{severity}"]

    if details:
        for key, value in details.items():
            tags.append(f"{key}:{value}")

    increment_counter("security.events", tags=tags)


def track_translation_request(source_lang: str, target_lang: str, success: bool) -> None:
    """Track a translation request."""
    tags = [
        f"source_lang:{source_lang}",
        f"target_lang:{target_lang}",
        f"success:{str(success).lower()}",
    ]

    increment_counter("translation.requests", tags=tags)

    if success:
        increment_counter("translation.success", tags=tags)
    else:
        increment_counter("translation.errors", tags=tags)
