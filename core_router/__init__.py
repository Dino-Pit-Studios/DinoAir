"""
DinoAir core service routing package.

Synchronous, stdlib-first Service Manager / Router components.
This top-level package exposes minimal, lightweight conveniences.
"""

from __future__ import annotations

from .adapters import ServiceAdapter, make_adapter
from .errors import AdapterError, NoHealthyService, ServiceNotFound, ValidationError
from .health import HealthState
from .metrics import record_error, record_success
from .metrics import snapshot as metrics_snapshot
from .router import ServiceRouter, create_router, get_router, set_router

__all__ = [
    "__version__",
    # errors
    "ServiceNotFound",
    "NoHealthyService",
    "ValidationError",
    "AdapterError",
    # health
    "HealthState",
    # metrics
    "record_success",
    "record_error",
    "metrics_snapshot",
    # adapters
    "make_adapter",
    "ServiceAdapter",
    # router exports
    "ServiceRouter",
    "create_router",
    "get_router",
    "set_router",
]

__version__: str = "0.1.0"
