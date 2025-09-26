from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.types import Message, Receive, Scope, Send

# Local alias to avoid linter/editor false positives on starlette.types.ASGIApp
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class RequestIDMiddleware:
    """
    ASGI middleware that assigns a per-request UUID trace_id and exposes it via:
      - scope["trace_id"]
      - response header "X-Trace-Id"
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        trace_id = str(uuid.uuid4())
        scope["trace_id"] = trace_id

        async def send_wrapper(message: Message):
            if message.get("type") == "http.response.start":
                headers = message.setdefault("headers", [])
                # Append our trace header
                headers.append((b"x-trace-id", trace_id.encode("utf-8")))
            await send(message)

        await self.app(scope, receive, send_wrapper)
        return None
