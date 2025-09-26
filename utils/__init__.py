"""
Utils Package - Core utilities for DinoAir
Contains configuration, logging, and enumeration utilities
"""

from typing import TYPE_CHECKING, Any

from .config_loader import ConfigLoader
from .dependency_container import (
    CircularDependencyError,
    DependencyContainer,
    DependencyInfo,
    DependencyResolutionError,
    LifecycleState,
    Scope,
    ScopeContext,
)

# Import globals directly to avoid circular imports
from .dependency_globals import get_container, resolve, resolve_type
from .enums import Enums
from .logger import Logger as _Logger
from .safe_pdf_extractor import SafePDFProcessor, extract_pdf_text_safe
from .sql import enforce_limit, normalize_like_pattern
from .state_machine import StateMachine

__all__ = [
    "ConfigLoader",
    "Logger",
    "Enums",
    "SafePDFProcessor",
    "extract_pdf_text_safe",
    "enforce_limit",
    "normalize_like_pattern",
    "StateMachine",
    "DependencyContainer",
    "Scope",
    "LifecycleState",
    "DependencyInfo",
    "DependencyResolutionError",
    "CircularDependencyError",
    "ScopeContext",
    "get_container",
    "resolve",
    "resolve_type",
]

# Type-checker-only import to provide symbol visibility without runtime side effects
if TYPE_CHECKING:
    from .logger import Logger  # pragma: no cover  # pylint: disable=reimported


def __getattr__(name: str) -> Any:
    """
    Lazy attribute access for selected public API symbols.
    Defers importing heavy/optional modules until actually requested.

    Only 'Logger' is lazily imported. Other symbols are already imported at module level.
    """
    if name == "Logger":
        try:
            # Local import avoids import-time cost and reduces circular import risk
            return _Logger
        except ImportError as exc:
            # Provide clear guidance and preserve the original traceback
            raise ImportError(
                "Failed to import 'Logger' from '.logger'. "
                "Ensure logger.py is present and its dependencies are installed."
            ) from exc
    elif name in __all__:
        # Already imported at module level, return from globals
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    # Keep introspection consistent with __all__
    return sorted(list(globals().keys()) + list(__all__))
