from __future__ import annotations

import hmac
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import TYPE_CHECKING

from starlette import status
from starlette.types import Receive, Scope, Send

from core_router.errors import error_response as core_error_response
from utils.asgi import get_header
from utils.log_sanitizer import sanitize_for_log

if TYPE_CHECKING:
    from ..settings import Settings


# Diagnostic logger for auth middleware issues
logger = logging.getLogger(__name__)

# Local alias to avoid linter/editor false positives on starlette.types.ASGIApp
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class AuthMiddleware:
    """
    ASGI middleware enforcing presence and correctness of X-DinoAir-Auth header
    for protected paths. Skips auth for:
      - GET /health
      - /openapi.json and /docs (only when environment == dev and expose_openapi_in_dev is True)
    """

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    def _is_auth_skipped(self, scope: Scope) -> bool:
        if scope.get("type") != "http":
            logger.debug("Auth skipped: non-HTTP request type")
            return True

        # noinspection PyCompatibility
        path: str = scope.get("path", "") or ""
        method: str = scope.get("method", "GET").upper()

        # Health is always public
        if method == "GET" and path == "/health":
            logger.debug("Auth skipped: health endpoint")
            return True

        # OpenAPI docs access - diagnostic logging for potential issues
        openapi_paths = {"/openapi.json", "/docs", "/docs/index.html", "/redoc"}
        if path in openapi_paths:
            safe_path = sanitize_for_log(path)
            logger.debug(
                "OpenAPI path requested: %s, is_dev=%s, expose_openapi_in_dev=%s",
                safe_path,
                self.settings.is_dev,
                self.settings.expose_openapi_in_dev,
            )
            if self.settings.is_dev and self.settings.expose_openapi_in_dev:
                logger.debug("Auth skipped: OpenAPI docs in dev mode")
                return True
            logger.warning(
                "OpenAPI path %s blocked: dev=%s, expose=%s",
                safe_path,
                self.settings.is_dev,
                self.settings.expose_openapi_in_dev,
            )

        # If auth is globally not required (dev + allow_no_auth with no token), skip all
        auth_skip_result = not self.settings.auth_required
        logger.debug(
            "Auth required setting: %s, skipping auth: %s",
            self.settings.auth_required,
            auth_skip_result,
        )
        return auth_skip_result

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        method = scope.get("method", "GET")
        logger.debug("Auth middleware processing: %s %s", method, path)

        if self._is_auth_skipped(scope):
            logger.debug("Auth skipped for: %s %s", method, path)
            return await self.app(scope, receive, send)

        # Enforce header on protected paths
        provided = get_header(scope, "x-dinoair-auth")
        trace_id = scope.get("trace_id", "")
        logger.debug("Auth validation for: %s %s, header_present=%s", method, path, bool(provided))

        # Use constant-time comparison to avoid timing attacks; normalize None -> ""
        expected = self.settings.auth_token or ""
        provided_norm = provided or ""
        if not hmac.compare_digest(provided_norm, expected):
            logger.warning("Auth failed for: %s %s, trace_id=%s", method, path, trace_id)
            endpoint = f"{method} {path}"
            response = core_error_response(
                status=status.HTTP_401_UNAUTHORIZED,
                code="ERR_UNAUTHORIZED",
                message="Missing or invalid authentication header.",
                error="Unauthorized",
                details=None,
                endpoint=endpoint,
                operationId=None,
                requestId=(str(trace_id) if isinstance(trace_id, str) and trace_id else None),
            )
            if trace_id:
                with suppress(Exception):
                    response.headers["X-Trace-Id"] = trace_id
            await response(scope, receive, send)
            return None

        logger.debug("Auth successful for: %s %s", method, path)
        await self.app(scope, receive, send)
        return None
