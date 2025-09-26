"""
Local Python adapter for dotted function paths.

Configuration (adapter_config):
{
  "function_path": "package.module:function_name"
}

Behavior:
- ping() returns True if import/callable checks succeed; else False.
- invoke(...) imports and calls the function with a copy of payload.
  Any failure is wrapped as AdapterError(adapter="local_python", reason="...").

Compatibility:
- invoke supports:
  - invoke(payload: dict) -> object
  - invoke(service_desc: Any, payload: dict) -> object
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any

from ..errors import AdapterError
from .base import ServiceAdapter

__all__ = ["LocalPythonAdapter"]


def _resolve_function(path: str) -> Callable[[dict[str, Any]], object]:
    """Resolve "module.submodule:function" to a callable."""
    if ":" not in path:
        raise AdapterError(
            adapter="local_python",
            reason=f"invalid function_path: {path!r}",
        )
    module_name, func_name = path.split(":", 1)
    try:
        module = import_module(module_name)
    except Exception as exc:
        raise AdapterError(
            adapter="local_python",
            reason=f"import failed for module: {module_name!r}",
        ) from exc
    try:
        func = getattr(module, func_name)
    except AttributeError as exc:
        raise AdapterError(
            adapter="local_python",
            reason=f"function not found: {module_name!r}:{func_name!r}",
        ) from exc
    if not callable(func):
        raise AdapterError(
            adapter="local_python",
            reason=f"attribute not callable: {module_name!r}:{func_name!r}",
        )
    return func  # type: ignore[return-value]


def _extract_invoke_args(
    a: Any,
    b: Mapping[str, Any] | None,
) -> tuple[Any | None, dict[str, Any]]:
    """
    Support both invoke(payload) and invoke(service_desc, payload).
    Returns (service_desc_or_none, payload_dict).
    """
    if b is None and isinstance(a, Mapping):
        return None, dict(a)
    if b is not None and isinstance(b, Mapping):
        return a, dict(b)
    # Fallback for unexpected inputs
    return None, dict(a) if isinstance(a, Mapping) else {}


class LocalPythonAdapter(ServiceAdapter):
    """
    Adapter that invokes a local Python function resolved from a dotted path.

    Configuration:
        function_path: required string "module.submodule:function"
    """

    def __init__(self, adapter_config: Mapping[str, Any]) -> None:
        self._config = dict(adapter_config or {})
        self._path: str = str(self._config.get("function_path", "")).strip()
        if not self._path:
            raise AdapterError(
                adapter="local_python",
                reason="adapter_config['function_path'] must be non-empty",
            )

    def ping(self) -> bool:
        """
        Attempt to import and resolve the function. Never raises.
        Returns False on failure.
        """
        try:
            _resolve_function(self._path)
            return True
        except Exception:
            return False

    def invoke(self, a: Any, b: Mapping[str, Any] | None = None) -> object:
        """
        Invoke the target function with payload dict.

        Accepts either:
          - invoke(payload)
          - invoke(service_desc, payload)
        """
        _, payload = _extract_invoke_args(a, b)
        try:
            func = _resolve_function(self._path)
            return func(dict(payload))
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(
                adapter="local_python",
                reason=str(exc),
            ) from exc
