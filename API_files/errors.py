from __future__ import annotations

import logging
from collections.abc import Iterable
from contextlib import suppress
from typing import TYPE_CHECKING, Any, cast

from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException

from core_router.errors import error_response as core_error_response

from .metrics_state import inc_counter

if TYPE_CHECKING:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse


log = logging.getLogger("api.errors")

# Error message constants to avoid duplication and improve consistency
VALIDATION_ERROR = "Validation Error"
VALIDATION_MESSAGE = "One or more validation errors occurred."


def _trace_id_from_request(request: Request) -> str:
    # Prefer the middleware-assigned trace_id in scope
    trace_id = request.scope.get("trace_id")
    if isinstance(trace_id, str) and trace_id:
        return trace_id
    # Fallback to standard request id headers if present
    header_rid = request.headers.get("X-Request-ID") or request.headers.get("X-Trace-Id")
    return header_rid if isinstance(header_rid, str) else ""


def _normalize_loc(v: Any) -> list[str]:
    # Treat strings as a single location element instead of an iterable of chars
    if isinstance(v, str):
        return [v]
    if isinstance(v, Iterable):
        return [str(x) for x in cast("Iterable[Any]", v)]
    return []


def _flatten_validation_errors(exc: Any) -> list[dict[str, Any]]:
    errors_attr = getattr(exc, "errors", None)
    if not callable(errors_attr):
        return []
    raw: Any = []
    with suppress(Exception):
        raw = errors_attr()
    if not isinstance(raw, Iterable):
        return []
    return [
        {
            "loc": _normalize_loc(e.get("loc", [])),
            "msg": str(e.get("msg", "")),
            "type": str(e.get("type", "")),
        }
        for e in cast("Iterable[Mapping[str, Any]]", raw)
    ]


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register API exception handlers.

    Reduced complexity by moving handler logic into top-level helpers and
    centralizing metrics and response formatting.
    """
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


def _record_metrics(status_code: int) -> None:
    try:
        inc_counter("requests_total")
        if 400 <= status_code < 500:
            inc_counter("status_4xx")
        if 500 <= status_code < 600:
            inc_counter("status_5xx")
        if status_code in {504, 413}:
            inc_counter(f"status_{status_code}")
    except Exception as e:
        # Do not fail request flow due to metrics issues; log at debug level for diagnosis
        log.debug(
            "Metrics increment failed",
            extra={"status": status_code, "error": str(e)},
            exc_info=False,
        )


def _json_error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    error: str,
    message: str,
    details: Any | None = None,
) -> JSONResponse:
    # Derive identifiers and context
    # Use unified helper that prefers scope 'trace_id', then headers
    rid = _trace_id_from_request(request)
    endpoint = f"{request.method} {request.url.path}"
    operation_id: str | None = None
    try:
        route = request.scope.get("route")
        # FastAPI APIRoute provides operation_id; fallback to name
        operation_id = getattr(route, "operation_id", None) or getattr(route, "name", None)
    except Exception:
        operation_id = None

    return core_error_response(
        status=status_code,
        code=code,
        message=message,
        error=error,
        details=details,
        endpoint=endpoint,
        operationId=operation_id,
        requestId=rid or None,
    )


def http_exception_handler(request: Request, exc: Exception):
    exc_obj = cast("StarletteHTTPException", exc)
    status_code = exc_obj.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR
    message = str(exc_obj.detail)

    # Map common statuses to canonical error/code
    if status_code == status.HTTP_404_NOT_FOUND:
        err = "Not Found"
        code = "ERR_NOT_FOUND"
    elif status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
        err = VALIDATION_ERROR
        code = "ERR_VALIDATION"
    elif status_code == status.HTTP_502_BAD_GATEWAY:
        err = "Bad Gateway"
        code = "ERR_BAD_GATEWAY"
    elif status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        err = "Service Unavailable"
        code = "ERR_UNAVAILABLE"
    else:
        err = "HTTP Error" if status_code < 500 else "Internal Error"
        code = "ERR_HTTP" if status_code < 500 else "ERR_INTERNAL"

    _record_metrics(status_code)

    log.warning(
        "HTTPException",
        extra={
            "trace_id": _trace_id_from_request(request),
            "path": request.url.path,
            "method": request.method,
            "status": status_code,
        },
        exc_info=False,
    )

    return _json_error_response(
        request=request,
        status_code=status_code,
        code=code,
        error=err,
        message=message,
        details=None,
    )


def request_validation_exception_handler(request: Request, exc: Exception):
    exc_obj = cast("RequestValidationError", exc)
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    errors = _flatten_validation_errors(exc_obj)

    _record_metrics(status_code)

    log.warning(
        "RequestValidationError",
        extra={
            "trace_id": _trace_id_from_request(request),
            "path": request.url.path,
            "method": request.method,
            "status": status_code,
            "errors": errors,
        },
        exc_info=False,
    )

    return _json_error_response(
        request=request,
        status_code=status_code,
        code="ERR_VALIDATION",
        error=VALIDATION_ERROR,
        message=VALIDATION_MESSAGE,
        details=errors,
    )


def validation_exception_handler(request: Request, exc: Exception):
    exc_obj = cast("ValidationError", exc)
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    errors = _flatten_validation_errors(exc_obj)

    _record_metrics(status_code)

    log.warning(
        "ValidationError",
        extra={
            "trace_id": _trace_id_from_request(request),
            "path": request.url.path,
            "method": request.method,
            "status": status_code,
            "errors": errors,
        },
        exc_info=False,
    )

    return _json_error_response(
        request=request,
        status_code=status_code,
        code="ERR_VALIDATION",
        error=VALIDATION_ERROR,
        message=VALIDATION_MESSAGE,
        details=errors,
    )


def unhandled_exception_handler(request: Request, _exc: Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    _record_metrics(status_code)

    # Log stack trace with correlation ID if present
    log.exception(
        "UnhandledException",
        extra={
            "trace_id": _trace_id_from_request(request),
            "path": request.url.path,
            "method": request.method,
            "status": status_code,
        },
    )

    return _json_error_response(
        request=request,
        status_code=status_code,
        code="ERR_INTERNAL",
        error="Internal Error",
        message="An unexpected error occurred.",
        details=None,
    )
