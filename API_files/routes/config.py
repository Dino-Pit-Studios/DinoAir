from __future__ import annotations

from fastapi import APIRouter
from starlette import status

from ..schemas import DirectorySettingsResponse
from ..services.search import directory_settings as svc_directory_settings

router = APIRouter()


@router.get(
    "/config/dirs",
    tags=["config"],
    response_model=DirectorySettingsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_config_dirs() -> DirectorySettingsResponse:
    """
    GET /config/dirs
    - Returns safe, read-only directory settings derived from the index configuration.
    - Read-only, idempotent.
    """
    return svc_directory_settings()
