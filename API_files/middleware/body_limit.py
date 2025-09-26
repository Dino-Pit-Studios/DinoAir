"""
ASGI middleware for enforcing request body size limits.

This module provides middleware that checks the Content-Length header
and rejects requests that exceed the configured maximum body size.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse
from starlette import status
from starlette.types import Message, Receive, Scope, Send

from utils.asgi import get_header

if TYPE_CHECKING:
    from ..settings import Settings

try:
    # type: ignore[import]
    from core_router.errors import error_response as core_error_response
except ImportError:  # pragma: no cover

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
    ) -> JSONResponse:
        payload = {
            "detail": message,
            "code": code,
            "message": message,
            "error": error,
        }
        return JSONResponse(status_code=status_code, content=payload)


# Local alias to avoid linter/editor false positives on starlette.types.ASGIApp
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

# Message type constants
HTTP_REQUEST = "http.request"


class BodySizeLimitMiddleware:
    """
    ASGI middleware that checks Content-Length and rejects when it exceeds
    settings.max_request_body_bytes. If Content-Length is absent, request passes through.
    """

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    @staticmethod
    def _is_http_scope(scope: Scope) -> bool:
        return scope.get("type") == "http"

    @staticmethod
    def _method_allows_body(scope: Scope) -> bool:
        method = (scope.get("method") or "GET").upper()
        return method in ("POST", "PUT", "PATCH")

    def _max_bytes(self) -> int:
        return int(self.settings.max_request_body_bytes)

    @staticmethod
    def _parse_content_length(value: str) -> int | None:
        try:
            return int(value)
        except ValueError:
            return None

    def _too_large_response(self, scope: Scope) -> JSONResponse:
        trace_id = scope.get("trace_id", "")
        method = scope.get("method") or "GET"
        path = scope.get("path", "")
        endpoint = f"{method} {path}"
        response = core_error_response(
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="ERR_PAYLOAD_TOO_LARGE",
            message=(
                f"Request body exceeds the maximum allowed size of "
                f"{self.settings.max_request_body_bytes} bytes."
            ),
            error="Payload Too Large",
            details=None,
            endpoint=endpoint,
            operationId=None,
            requestId=(str(trace_id) if isinstance(trace_id, str) and trace_id else None),
        )
        if trace_id:
            with suppress(Exception):
                response.headers["X-Trace-Id"] = trace_id
        return response

    @staticmethod
    def _process_body_chunk(
        chunk: bytes, total: int, max_bytes: int, parts: list[bytes]
    ) -> tuple[int, bool]:
        """Process a body chunk and return updated total and whether limit exceeded."""
        new_total = total + len(chunk)
        if new_total > max_bytes:
            return new_total, True
        parts.append(chunk)
        return new_total, False

    async def _drain_body(self, receive: Receive) -> tuple[list[bytes], Message | None, int]:
        """Drain request body into memory up to limit."""
        max_bytes = self._max_bytes()
        total = 0
        parts: list[bytes] = []
        extra_message: Message | None = None

        while True:
            message: Message = await receive()
            if message.get("type") != HTTP_REQUEST:
                extra_message = message
                break

            if chunk := (message.get("body") or b""):
                total, limit_exceeded = self._process_body_chunk(chunk, total, max_bytes, parts)
                if limit_exceeded:
                    return parts, extra_message, total

            if not message.get("more_body", False):
                extra_message = None
                break

        return parts, extra_message, total

    @staticmethod
    def _create_replay_queue(
        body_parts: list[bytes], extra_message: Message | None
    ) -> list[Message]:
        """Create a replay queue for the request body."""
        replay_queue: list[Message] = []

        if body_parts:
            replay_queue.extend(
                [
                    {
                        "type": HTTP_REQUEST,
                        "body": part,
                        "more_body": i < (len(body_parts) - 1),
                    }
                    for i, part in enumerate(body_parts)
                ]
            )
        else:
            # No body provided; send a single empty-final chunk
            replay_queue.append(
                {
                    "type": HTTP_REQUEST,
                    "body": b"",
                    "more_body": False,
                }
            )

        # If we saw a non http.request message after the body, enqueue it
        if extra_message is not None:
            replay_queue.append(extra_message)

        return replay_queue

    async def _drain_and_forward(self, scope: Scope, receive: Receive, send: Send) -> None:
        body_parts, extra_message, total = await self._drain_body(receive)
        if total > self._max_bytes():
            response = self._too_large_response(scope)
            await response(scope, receive, send)
            return None

        # Prepare a small queue to replay the drained body to downstream app
        replay_queue = self._create_replay_queue(body_parts, extra_message)

        async def replay_receive() -> Message:
            return replay_queue.pop(0) if replay_queue else await receive()

        return await self.app(scope, replay_receive, send)

    async def _handle_request_with_content_length(
        self, scope: Scope, receive: Receive, send: Send, content_length_str: str
    ) -> None:
        """Handle requests that have a Content-Length header."""
        length = self._parse_content_length(content_length_str)
        if length is not None and length > self._max_bytes():
            response = self._too_large_response(scope)
            await response(scope, receive, send)
            return
        # Header present (valid or invalid) and not exceeding limit: pass through
        await self.app(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._is_http_scope(scope):
            await self.app(scope, receive, send)
            return

        if not self._method_allows_body(scope):
            await self.app(scope, receive, send)
            return

        if content_length_str := get_header(scope, "content-length"):
            await self._handle_request_with_content_length(scope, receive, send, content_length_str)
            return

        # No Content-Length header: drain and enforce limit before passing downstream
        await self._drain_and_forward(scope, receive, send)
