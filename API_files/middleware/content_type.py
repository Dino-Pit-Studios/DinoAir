from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress

from starlette import status
from starlette.types import Receive, Scope, Send

from utils.asgi import get_header

try:
    # type: ignore[import]
    from core_router.errors import error_response as core_error_response
except ImportError:  # pragma: no cover
    from fastapi.responses import JSONResponse as _JSONResponse

    def core_error_response(
        *,
        status_code: int,
        code: str,
        message: str,
        error: str,
        _details: str | None,
        _endpoint: str | None,
        _operationId: str | None,
        _requestId: str | None,
    ) -> _JSONResponse:
        payload = {
            "detail": message,
            "code": code,
            "message": message,
            "error": error,
        }
        return _JSONResponse(status_code=status_code, content=payload)


# Local alias to avoid linter/editor false positives on starlette.types.ASGIApp
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class ContentTypeJSONMiddleware:
    """
    Enforce application/json Content-Type for POST requests.
    Returns 415 Unsupported Media Type early (before body parsing).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = (scope.get("method") or "GET").upper()
        if method == "POST":
            ct = (get_header(scope, "content-type") or "").lower()
            if not ct.startswith("application/json"):
                trace_id = scope.get("trace_id", "")
                method = scope.get("method") or "GET"
                path = scope.get("path", "")
                endpoint = f"{method} {path}"
                response = core_error_response(
                    status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    code="ERR_UNSUPPORTED_MEDIA_TYPE",
                    message="Content-Type must be application/json",
                    error="Unsupported Media Type",
                    details=None,
                    endpoint=endpoint,
                    operationId=None,
                    requestId=(str(trace_id) if isinstance(trace_id, str) and trace_id else None),
                )
                if trace_id:
                    with suppress(Exception):
                        response.headers["X-Trace-Id"] = trace_id
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
        # no explicit return needed
