"""
Enhanced FastAPI middleware for Datadog metrics collection.
Integrates with the DinoAir API to collect custom business and performance metrics.
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from utils.metrics import get_metrics_client, track_api_request, track_security_event


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect API metrics for Datadog."""

    def __init__(self, app):
        super().__init__(app)
        self.metrics = get_metrics_client()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and collect metrics."""
        start_time = time.time()

        # Extract request information
        method = request.method
        path = request.url.path

        # Track the incoming request
        self.metrics.increment("api.requests.total", tags=[f"method:{method}", f"endpoint:{path}"])

        try:
            # Process the request
            response = await call_next(request)

            # Calculate response time
            duration_ms = (time.time() - start_time) * 1000

            # Track the completed request with all details
            track_api_request(
                endpoint=path,
                method=method,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

            # Track specific metrics based on endpoint
            if path.startswith("/health"):
                self.metrics.increment("health_checks.total")
            elif path.startswith("/translate"):
                self.metrics.increment("translation.requests.total")
            elif path.startswith("/docs"):
                self.metrics.increment("documentation.views")

            # Track response size if available
            if hasattr(response, "headers") and "content-length" in response.headers:
                size = int(response.headers["content-length"])
                self.metrics.histogram("api.response.size", size, tags=[f"endpoint:{path}"])

            return response

        except Exception as e:
            # Track errors
            duration_ms = (time.time() - start_time) * 1000

            self.metrics.increment(
                "api.errors.total",
                tags=[f"method:{method}", f"endpoint:{path}", f"error_type:{type(e).__name__}"],
            )

            # Track security events for certain error types
            if isinstance(e, (PermissionError, ValueError)):
                track_security_event(
                    event_type="api_error",
                    severity="medium",
                    details={"endpoint": path, "error": str(e)},
                )

            self.metrics.timing(
                "api.request_duration",
                duration_ms,
                tags=[f"method:{method}", f"endpoint:{path}", "status:error"],
            )

            raise
