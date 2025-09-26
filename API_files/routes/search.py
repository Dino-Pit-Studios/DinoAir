from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from core_router.errors import (
    AdapterError,
    NoHealthyService,
    ServiceNotFound,
)
from core_router.errors import ValidationError as CoreValidationError

from ..schemas import (
    FileIndexStatsResponse,
    HybridSearchRequest,
    HybridSearchResponse,
    KeywordSearchRequest,
    KeywordSearchResponse,
    VectorSearchRequest,
    VectorSearchResponse,
)
from ..services.router_client import get_router
from ..services.search import index_stats as svc_index_stats

router = APIRouter()

SEARCH_LOCAL_DEFAULT = "search.local.default"


def svc_keyword(body: KeywordSearchRequest) -> KeywordSearchResponse:
    """
    Dispatch keyword search via ServiceRouter.
    Returns a typed KeywordSearchResponse, mirroring translator route usage.
    """
    r = get_router()
    payload = body.model_dump(mode="json", by_alias=False, exclude_none=True)
    try:
        result = r.execute(SEARCH_LOCAL_DEFAULT, payload)
        return KeywordSearchResponse.model_validate(result)
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


def svc_vector(body: VectorSearchRequest) -> VectorSearchResponse:
    """
    Dispatch vector search via ServiceRouter.
    Returns a typed VectorSearchResponse.
    """
    r = get_router()
    payload = body.model_dump(mode="json", by_alias=False, exclude_none=True)
    try:
        result = r.execute(SEARCH_LOCAL_DEFAULT, payload)
        return VectorSearchResponse.model_validate(result)
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


def svc_hybrid(body: HybridSearchRequest) -> HybridSearchResponse:
    """
    Dispatch hybrid search via ServiceRouter.
    Returns a typed HybridSearchResponse.
    """
    r = get_router()
    payload = body.model_dump(mode="json", by_alias=False, exclude_none=True)
    try:
        result = r.execute(SEARCH_LOCAL_DEFAULT, payload)
        return HybridSearchResponse.model_validate(result)
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


@router.post(
    "/file-search/keyword",
    tags=["file-search"],
    response_model=KeywordSearchResponse,
    status_code=status.HTTP_200_OK,
)
async def keyword_search(_request: Request, body: KeywordSearchRequest) -> KeywordSearchResponse:
    return svc_keyword(body)


@router.post(
    "/file-search/vector",
    tags=["file-search"],
    response_model=VectorSearchResponse,
    status_code=status.HTTP_200_OK,
)
async def vector_search(_request: Request, body: VectorSearchRequest) -> VectorSearchResponse:
    return svc_vector(body)


@router.post(
    "/file-search/hybrid",
    tags=["file-search"],
    response_model=HybridSearchResponse,
    status_code=status.HTTP_200_OK,
)
async def hybrid_search(_request: Request, body: HybridSearchRequest) -> HybridSearchResponse:
    return svc_hybrid(body)


@router.get(
    "/file-index/stats",
    tags=["file-index"],
    response_model=FileIndexStatsResponse,
    status_code=status.HTTP_200_OK,
)
async def file_index_stats() -> FileIndexStatsResponse:
    return svc_index_stats()
