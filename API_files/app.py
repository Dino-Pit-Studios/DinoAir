from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from anyio import move_on_after
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import Receive, Scope, Send

from .errors import register_exception_handlers
from .logging_config import RequestResponseLoggerMiddleware, setup_logging
from .middleware.auth import AuthMiddleware
from .middleware.body_limit import BodySizeLimitMiddleware
from .middleware.content_type import ContentTypeJSONMiddleware
from .middleware.request_id import RequestIDMiddleware
from .settings import Settings

# Define locally to avoid linter/editor issues with starlette.types.ASGIApp
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

log = logging.getLogger("api.app")


class TimeoutMiddleware:
    """Enforces a timeout for ASGI requests.

    Cancels requests that exceed the specified duration and returns a
    504 Gateway Timeout response.
    """

    def __init__(self, asgi_app: ASGIApp, timeout: float = 10.0):
        self.app = asgi_app
        self.timeout = timeout

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        async with move_on_after(self.timeout) as cancel_scope:
            await self.app(scope, receive, send)
        if cancel_scope.cancel_called:
            await self._send_timeout(scope, receive, send)

    @staticmethod
    async def _send_timeout(scope: Scope, receive: Receive, send: Send):
        from starlette import status

        from core_router.errors import error_response as core_error_response

        trace_id = scope.get("trace_id", "")
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        endpoint = f"{method} {path}"

        response = core_error_response(
            status=status.HTTP_504_GATEWAY_TIMEOUT,
            code="ERR_TIMEOUT",
            message="The request took too long to complete.",
            error="Timeout",
            details=None,
            endpoint=endpoint,
            operationId=None,
            requestId=str(trace_id) if isinstance(trace_id, str) and trace_id else None,
        )
        if trace_id:
            from contextlib import suppress

            with suppress(Exception):
                response.headers["X-Trace-Id"] = trace_id
        await response(scope, receive, send)


def _get_docs_urls(settings: Settings) -> tuple[str | None, str | None, str | None]:
    """
    Return the URL paths for the OpenAPI schema and interactive documentation based on the provided settings.

    If running in development mode with OpenAPI exposure enabled, returns the paths for the OpenAPI JSON, Swagger UI, and Redoc.
    Otherwise, returns None for each URL, disabling documentation endpoints in production.
    """
    if settings.is_dev and settings.expose_openapi_in_dev:
        return "/openapi.json", "/docs", "/redoc"
    return None, None, None


def _configure_cors(fastapi_app: FastAPI, settings: Settings) -> None:
    """
    Configure Cross-Origin Resource Sharing (CORS) middleware on the FastAPI application.

    Applies strict CORS policies using the allowed origins, methods, headers, and other parameters defined in settings.
    """
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "OPTIONS", "PUT", "PATCH"],
        allow_headers=["Content-Type", "X-DinoAir-Auth", "X-Request-ID", "X-Trace-Id"],
        expose_headers=["X-Trace-Id"],
        allow_credentials=False,
        max_age=600,
    )


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application with:
    - Strict CORS
    - Security middleware (Request ID, Body size limit, Auth)
    - Structured logging and request/response logging
    - Unified error handlers
    - Conditional OpenAPI/docs exposure in dev
    """
    settings = Settings()  # reads env with DINOAIR_ prefix

    # Initialize logging once per process
    setup_logging(settings)
    log.info(
        "Starting DinoAir API",
        extra={"env": settings.environment, "port": settings.port},
    )

    openapi_url, docs_url, redoc_url = _get_docs_urls(settings)

    fastapi_app = FastAPI(
        title="DinoAir Local API",
        version="0.1.0",
        openapi_url=openapi_url,
        docs_url=docs_url,
        redoc_url=redoc_url,
        default_response_class=ORJSONResponse,
    )

    # Register exception handlers (canonical ErrorResponse responses)
    register_exception_handlers(fastapi_app)

    # CORS - strict, no wildcards
    _configure_cors(fastapi_app, settings)

    # Request pipeline middlewares (order matters):
    # Add short-circuiting middlewares first, then logging, and finally
    # RequestID as OUTERMOST so it can stamp trace_id on all responses.
    # Enforce JSON content-type for POSTs before any parsing/validation
    fastapi_app.add_middleware(ContentTypeJSONMiddleware)
    fastapi_app.add_middleware(BodySizeLimitMiddleware, settings=settings)
    fastapi_app.add_middleware(AuthMiddleware, settings=settings)
    # Temporarily disabled: fastapi_app.add_middleware(TimeoutMiddleware, timeout=settings.request_timeout_seconds)

    # Add Datadog metrics collection middleware
    try:
        from .middleware.metrics import MetricsMiddleware

        fastapi_app.add_middleware(MetricsMiddleware)
        log.info("Added Datadog metrics middleware")
    except Exception:  # pragma: no cover
        log.warning("Failed to add metrics middleware - continuing without metrics")

    fastapi_app.add_middleware(RequestResponseLoggerMiddleware)
    fastapi_app.add_middleware(GZipMiddleware, minimum_size=1024)
    # Must be last-added to be outermost
    fastapi_app.add_middleware(RequestIDMiddleware)

    # Routers: import lazily to reduce import-time coupling and allow testing with stubs
    try:
        from .routes.health import router as health_router

        fastapi_app.include_router(health_router)
    except Exception:  # pragma: no cover
        log.exception("Failed to include health router")

    try:
        from .routes.translate import router as translate_router

        fastapi_app.include_router(translate_router)
    except Exception:  # pragma: no cover
        log.exception("Failed to include translate router")

    return fastapi_app


# Expose an ASGI application instance for servers (e.g., `uvicorn api.app:app`)
app: FastAPI = create_app()


# Also expose a factory for `--factory` usage:
#   uvicorn api.app:app_factory --factory
#   uvicorn api.app:create_app --factory
def app_factory() -> FastAPI:
    return create_app()
