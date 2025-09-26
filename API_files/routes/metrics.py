from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from core_router import metrics as core_metrics

from ..services.router_client import get_router

router = APIRouter()


@router.get("/metrics", tags=["system"])
async def metrics() -> dict[str, Any]:
    """
    GET /metrics — Return minimal metrics snapshot:
      {
        "uptimeSeconds": number,
        "requests": { "total": number, "error": number },
        "adapters": { [name]: { "successes": number, "failures": number } }
      }
    """
    # Ensure router/registry are initialized (no-op if already created)
    _ = get_router()
    return core_metrics.minimal_snapshot()
