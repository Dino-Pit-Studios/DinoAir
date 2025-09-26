from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from core_router.errors import (
    AdapterError,
    NoHealthyService,
    ServiceNotFound,
)
from core_router.errors import ValidationError as CoreValidationError

from ..schemas import (
    ContextRequest,
    GenerateMissingEmbeddingsRequest,
    IngestDirectoryRequest,
    IngestFilesRequest,
    MonitorStartRequest,
)
from ..services.router_client import get_router

router = APIRouter(prefix="/rag", tags=["rag"])

SVC_INGEST_DIR = "rag.local.ingest_dir"
SVC_INGEST_FILES = "rag.local.ingest_files"
SVC_GENERATE_EMB = "rag.local.generate_missing_embeddings"
SVC_CONTEXT = "rag.local.context"
SVC_MONITOR_START = "rag.local.monitor_start"
SVC_MONITOR_STOP = "rag.local.monitor_stop"
SVC_MONITOR_STATUS = "rag.local.monitor_status"


def _exec(service_name: str, payload: dict[str, Any]) -> Any:
    r = get_router()
    try:
        return r.execute(service_name, payload)
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


@router.post("/ingest/directory", status_code=status.HTTP_200_OK)
async def ingest_directory(_request: Request, body: IngestDirectoryRequest) -> Any:
    payload = body.model_dump(mode="json", by_alias=False, exclude_none=True)
    return _exec(SVC_INGEST_DIR, payload)


@router.post("/ingest/files", status_code=status.HTTP_200_OK)
async def ingest_files(_request: Request, body: IngestFilesRequest) -> Any:
    payload = body.model_dump(mode="json", by_alias=False, exclude_none=True)
    return _exec(SVC_INGEST_FILES, payload)


@router.post("/embeddings/generate-missing", status_code=status.HTTP_200_OK)
async def generate_missing_embeddings(
    _request: Request, body: GenerateMissingEmbeddingsRequest
) -> Any:
    payload = body.model_dump(mode="json", by_alias=False, exclude_none=True)
    return _exec(SVC_GENERATE_EMB, payload)


@router.post("/context", status_code=status.HTTP_200_OK)
async def get_context(_request: Request, body: ContextRequest) -> Any:
    payload = body.model_dump(mode="json", by_alias=False, exclude_none=True)
    return _exec(SVC_CONTEXT, payload)


@router.post("/monitor/start", status_code=status.HTTP_200_OK)
async def monitor_start(_request: Request, body: MonitorStartRequest) -> Any:
    payload = body.model_dump(mode="json", by_alias=False, exclude_none=True)
    return _exec(SVC_MONITOR_START, payload)


@router.post("/monitor/stop", status_code=status.HTTP_200_OK)
async def monitor_stop() -> Any:
    return _exec(SVC_MONITOR_STOP, {})


@router.get("/monitor/status", status_code=status.HTTP_200_OK)
async def monitor_status() -> Any:
    return _exec(SVC_MONITOR_STATUS, {})
