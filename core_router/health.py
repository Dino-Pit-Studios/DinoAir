"""Health utilities and state modeling for services."""

from __future__ import annotations

from datetime import UTC
from enum import Enum
from typing import Protocol


class SupportsPing(Protocol):
    """Protocol for objects supporting a ping method to check availability and connectivity."""

    def ping(self) -> bool: ...


class HealthState(str, Enum):
    """Discrete service health states."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


# ping_with_timing moved to health_utils.py to avoid circular imports


# -------------------------
# HTTP health/version helpers (lightweight)
# -------------------------


def _now_iso8601() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def _adapter_registration_status() -> str:
    """
    Best-effort check for adapter registration presence via ServiceRegistry.
    Returns 'ok' if a registry is available (presence), else 'unknown'.

    Preference order:
      1) try core_router.router.get_router() first
      2) then fallback to api.services.router_client.get_router() for compatibility

    Notes:
    - All imports are local and guarded to avoid circular imports.
    - This is a lightweight readiness signal based on registry presence only;
      it does not force initialization if none exists.
    """
    # Prefer core_router's local singleton first
    try:
        from .router import get_router as _core_get_router  # local import to avoid cycles

        sr = _core_get_router()
        registry = getattr(sr, "_registry", None)
        from .registry import ServiceRegistry  # local import

        if isinstance(registry, ServiceRegistry):
            return "ok"
    except Exception:
        # ignore and attempt fallback
        pass

    # Fallback to API router client, if available
    try:
        from api.services.router_client import get_router as _api_get_router  # type: ignore

        sr = _api_get_router()
        registry = getattr(sr, "_registry", None)
        from .registry import ServiceRegistry  # local import

        if isinstance(registry, ServiceRegistry):
            return "ok"
    except Exception:
        # final fallback -> unknown
        pass

    return "unknown"


def health_response() -> tuple[dict[str, object], int]:
    """
    Compose health payload and corresponding HTTP status code.

    Returns:
      ({ "status": "ok" | "degraded" | "unhealthy",
         "checks": { "router": str, "adapters": str, "storage": str, "time": str } },
       http_status: 200|503)
    """
    checks: dict[str, object] = {
        "router": "ok",
        "adapters": _adapter_registration_status(),
        "storage": "unknown",
        "time": _now_iso8601(),
    }

    values = {k: v for k, v in checks.items() if k != "time"}
    # Normalize values to str for evaluation
    statuses = [str(v).lower() for v in values.values()]
    if "unhealthy" in statuses:
        status_text = "unhealthy"
    elif "degraded" in statuses:
        status_text = "degraded"
    else:
        status_text = "ok"

    http_status = 200 if status_text == "ok" else 503
    body: dict[str, object] = {"status": status_text, "checks": checks}
    return body, http_status


def version_info() -> dict[str, object]:
    """
    Return version payload: { version: string, build: string|null, commit: string|null }
    """
    version = None
    try:
        from api import get_version  # type: ignore

        version = get_version()
    except Exception:
        try:
            from core_router import __version__ as core_version  # type: ignore

            version = core_version
        except Exception:
            version = "0.0.0"

    import os

    build = os.getenv("DINO_BUILD") or None
    commit = os.getenv("DINO_COMMIT") or None
    return {"version": str(version), "build": build, "commit": commit}
