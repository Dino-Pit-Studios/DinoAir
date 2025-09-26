from __future__ import annotations

from fastapi import APIRouter, HTTPException
from starlette import status

from core_router.errors import (
    AdapterError,
    NoHealthyService,
    ServiceNotFound,
)
from core_router.errors import ValidationError as CoreValidationError

from ..schemas import TranslateRequest, TranslateResponse
from ..services.router_client import get_router

router = APIRouter()


@router.post(
    "/translate",
    tags=["translate"],
    response_model=TranslateResponse,
    status_code=status.HTTP_200_OK,
)
async def translate(req: TranslateRequest) -> TranslateResponse:
    """
    POST /translate
    - Safe, non-streaming pseudocode → code translation
    - Auth enforced globally by middleware
    - Input validated via DTO (size/enum)
    - Runs within app-configured timeout window
    """
    service_router = get_router()

    payload = {"pseudocode": req.pseudocode}
    if req.target_language is not None:
        try:
            payload["target_language"] = req.target_language.value
        except AttributeError:
            payload["target_language"] = str(req.target_language)

    try:
        result = service_router.execute("translator.local.default", payload)
        return TranslateResponse.model_validate(result)
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
