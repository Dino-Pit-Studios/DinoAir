"""
Error types used across the core_router package.

These are intentionally simple and typed for clear error handling paths.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ServiceNotFound(Exception):
    """Raised when a service is not found in the registry by name."""


class NoHealthyService(Exception):
    """Raised when no healthy service is available for a given tag/policy."""


class ValidationError(Exception):
    """
    Raised when input or output data fails schema validation.

    Attributes:
        details: Optional structured details (dict or str)
                 describing validation violations.
    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | str | None = None,
    ) -> None:
        super().__init__(message)
        self.details: dict[str, Any] | str | None = details


class AdapterError(Exception):
    """
    Raised when an adapter invocation or ping encounters an error.

    Attributes:
        adapter: Adapter kind/name (e.g., "local_python", "lmstudio").
        reason: Optional human-readable reason.
    """

    def __init__(
        self,
        message: str | None = None,
        *,
        adapter: str | None = None,
        reason: str | None = None,
    ) -> None:
        # Construct a concise message while preserving adapter/reason context.
        if not message:
            if adapter and reason:
                message = f"{adapter}: {reason}"
            elif reason:
                message = reason
            elif adapter:
                message = f"{adapter}: adapter error"
            else:
                message = "adapter error"
        super().__init__(message)
        self.adapter: str | None = adapter
        self.reason: str | None = reason


class RetryableError(Exception):
    """
    Raised by adapters to signal that an operation should be retried.

    This is used internally by adapter retry logic to distinguish between
    retryable conditions and actual errors that should be propagated.
    """


# === Canonical ErrorResponse model and helpers (normalized API errors) ===


class ErrorResponse(BaseModel):
    """A Pydantic model representing a standardized API error response.

    Contains fields for error category, HTTP status, error code, message, and optional details.
    """

    # Short, human category (e.g. "Not Implemented", "Validation Error", "Not Found")
    error: str = Field(...)
    # HTTP status code
    status: int = Field(...)
    # Machine-usable code (e.g., "ERR_NOT_IMPLEMENTED", "ERR_VALIDATION", "ERR_NOT_FOUND", "ERR_INTERNAL")
    code: str = Field(...)
    # Human-readable message
    message: str = Field(...)
    # Optional details for validation issues or adapter-specific info
    details: Any | None = Field(default=None)
    # Optional request ID; generate if missing
    requestId: str | None = Field(default=None)
    # "METHOD PATH"
    endpoint: str = Field(...)
    # Optional when available from route
    operationId: str | None = Field(default=None)
    # RFC3339 timestamp
    timestamp: str = Field(...)

    model_config = {"populate_by_name": True}


def _now_rfc3339() -> str:
    return datetime.now(UTC).isoformat()


def error_response(
    status: int,
    code: str,
    message: str,
    *,
    error: str,
    details: Any | None = None,
    endpoint: str,
    operationId: str | None = None,
    requestId: str | None = None,
) -> JSONResponse:
    rid = requestId or str(uuid4())
    body = ErrorResponse(
        error=error,
        status=status,
        code=code,
        message=message,
        details=details,
        requestId=rid,
        endpoint=endpoint,
        operationId=operationId,
        timestamp=_now_rfc3339(),
    )
    return JSONResponse(
        content=body.model_dump(by_alias=True, exclude_none=True), status_code=status
    )


def not_implemented(method: str, path: str, operationId: str | None = None) -> JSONResponse:
    """Canonical 501 Not Implemented payload for unimplemented HTTP endpoints."""
    return error_response(
        status=501,
        code="ERR_NOT_IMPLEMENTED",
        message="Defined in OpenAPI but not yet implemented",
        error="Not Implemented",
        details=None,
        endpoint=f"{method} {path}",
        operationId=operationId,
        requestId=None,
    )
