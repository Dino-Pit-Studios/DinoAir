from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette import status

from core_router import metrics as core_metrics
from core_router.errors import (
    AdapterError,
    NoHealthyService,
    ServiceNotFound,
)
from core_router.errors import ValidationError as CoreValidationError

from ..services import router_client

router = APIRouter()


# Optional Pydantic schemas (validation + OpenAPI)
class ExecuteRequest(BaseModel):
    """
    Model for execute requests, containing the target service name and request payload.
    """

    serviceName: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


PolicyLiteral = Literal["first_healthy", "round_robin", "lowest_latency"]


class ExecuteByRequest(BaseModel):
    """
    Model for execute-by requests, containing a service tag, optional selection policy, and request payload.
    """

    tag: str = Field(..., min_length=1)
    policy: PolicyLiteral | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/router/execute", tags=["router"])
async def router_execute(req: ExecuteRequest) -> Any:
    """
    POST /router/execute
    Body: { serviceName: str, payload: dict }
    Calls core router.execute(...) and returns the result (JSON-serializable).
    """
    r = router_client.get_router()
    try:
        return r.execute(req.serviceName, req.payload or {})
    except ServiceNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoHealthyService as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except CoreValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except AdapterError as exc:
        # Upstream adapter error
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/router/executeBy", tags=["router"])
async def router_execute_by(req: ExecuteByRequest) -> Any:
    """
    POST /router/executeBy
    Body: { tag: str, policy?: 'first_healthy'|'round_robin'|'lowest_latency', payload: dict }
    Calls core router.execute_by(...) and returns the result (JSON-serializable).
    """
    r = router_client.get_router()
    policy = req.policy or "first_healthy"
    try:
        return r.execute_by(req.tag, req.payload or {}, policy)
    except ServiceNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoHealthyService as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except CoreValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except AdapterError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/router/metrics", tags=["router"])
async def router_metrics() -> dict[str, Any]:
    """
    GET /router/metrics
    Returns a snapshot of router metrics. Ensures router is initialized.
    """
    _ = router_client.get_router()  # ensure initialization
    return core_metrics.snapshot()
