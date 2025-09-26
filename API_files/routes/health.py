from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core_router.health import health_response, version_info

router = APIRouter()


@router.get("/health", tags=["system"])
async def health() -> JSONResponse:
    """
    GET /health — Returns:
      {
        "status": "ok" | "degraded" | "unhealthy",
        "checks": {
          "router": "ok" | "degraded" | "unhealthy" | "unknown",
          "adapters": "ok" | "degraded" | "unhealthy" | "unknown",
          "storage": "ok" | "degraded" | "unhealthy" | "unknown",
          "time": ISO8601
        }
      }
    HTTP 200 when ok, 503 when degraded/unhealthy.
    """
    body, status_code = health_response()
    return JSONResponse(content=body, status_code=status_code)


@router.get("/capabilities", tags=["system"])
async def capabilities() -> dict[str, Any]:
    """GET /capabilities — Enumerate supported features for this API/process."""
    return {
        "capabilities": [
            "ipc_registry_v1",
            "openapi_sdk",
            "problem_details",
            "request_id",
            "auth_middleware",
            "body_limit",
            "content_type",
            "timeout",
            "metrics_counters",
        ]
    }


@router.get("/version", tags=["system"])
async def version() -> dict[str, Any]:
    """GET /version — Return { version, build, commit }."""
    return version_info()
