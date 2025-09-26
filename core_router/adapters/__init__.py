"""
Adapter factory and protocol exports.

This module intentionally avoids importing concrete adapters at module import
time to keep imports lightweight. Adapters are imported lazily inside the
factory function.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import AdapterError
from .base import ServiceAdapter

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["ServiceAdapter", "make_adapter"]


def make_adapter(kind: str, adapter_config: Mapping[str, Any]) -> ServiceAdapter:
    """
    Construct a ServiceAdapter for the given kind.

    Supported kinds:
      - "local_python" -> LocalPythonAdapter
      - "lmstudio"     -> LMStudioAdapter

    Raises:
        AdapterError: if kind is unknown.
    """
    k = (kind or "").strip().lower()
    if k == "local_python":
        from .local_python import (  # lazy import  # pylint: disable=import-outside-toplevel
            LocalPythonAdapter,
        )

        return LocalPythonAdapter(adapter_config)
    if k == "lmstudio":
        from .lmstudio import (  # lazy import  # pylint: disable=import-outside-toplevel
            LMStudioAdapter,
        )

        return LMStudioAdapter(adapter_config)
    raise AdapterError(
        adapter="factory",
        reason=f"unknown adapter kind: {kind!r}",
    )
