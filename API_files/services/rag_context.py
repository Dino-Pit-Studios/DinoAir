from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any, cast

from .common import resp

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..settings import Settings

log = logging.getLogger("api.services.rag_context")
RAG_UNAVAILABLE_MSG = "RAG components unavailable"


class RagContextService:
    """
    Service for retrieving context for queries using RAG (Retrieval-Augmented Generation) providers.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_context(
        self,
        query: str,
        file_types: list[str] | None = None,
        top_k: int = 10,
        include_suggestions: bool = True,
    ) -> dict[str, Any]:
        if not getattr(self.settings, "rag_enabled", True):
            return resp(False, None, RAG_UNAVAILABLE_MSG, 501)

        method, unavailable = self._load_context_method()
        if unavailable:
            return resp(False, None, RAG_UNAVAILABLE_MSG, 501)
        if method is None:
            return resp(False, None, "Context provider missing method", 500)

        kwargs: dict[str, Any] = {
            "query": query,
            "file_types": file_types,
            "max_results": top_k,
            "include_suggestions": include_suggestions,
        }
        call_args = self._filtered_kwargs(method, kwargs)

        try:
            data: Any = method(**call_args)
            keys_preview = self._preview_dict_keys(data, limit=10)
            log.debug(
                "get_context provider returned type=%s keys=%s",
                type(data).__name__,
                keys_preview,
            )
        except (AttributeError, TypeError, ValueError) as e:
            log.exception("get_context provider invocation failed")
            return resp(False, None, str(e), 500)

        success_val, normalized_data, error_msg = self._normalize_context_data(data)
        return resp(success_val, normalized_data, error_msg, 200)

    # -------------------------
    # Internal helpers (copied semantics from api/services/rag.py)
    # -------------------------
    @staticmethod
    def _load_context_method() -> tuple[Callable[..., Any] | None, bool]:
        try:
            # pylint: disable=import-outside-toplevel
            from rag import get_context_provider  # type: ignore[attr-defined]
        except ImportError:
            return None, True
        # type: ignore[assignment]
        provider_factory: Callable[..., Any] = get_context_provider
        prov = provider_factory(user_name="default_user", enhanced=None)
        method = getattr(prov, "get_context_for_query", None)
        return (method if callable(method) else None), False

    @staticmethod
    def _filtered_kwargs(method: Callable[..., Any], kwargs: dict[str, Any]) -> dict[str, Any]:
        try:
            sig = inspect.signature(method)
            return {k: v for k, v in kwargs.items() if k in sig.parameters}
        except (ValueError, TypeError):
            return kwargs

    @staticmethod
    def _preview_dict_keys(data: Any, limit: int = 10) -> list[str] | None:
        try:
            if isinstance(data, dict):
                d = cast("dict[str, Any]", data)
                return [str(k) for k in list(d.keys())[:limit]]
            return None
        except Exception:  # pragma: no cover - defensive
            return None

    @staticmethod
    def _normalize_context_data(data: Any) -> tuple[bool, dict[str, Any], str | None]:
        if isinstance(data, dict):
            data_dict: dict[str, Any] = cast("dict[str, Any]", data)
            success_val: bool = bool(data_dict.get("success", True))
            error_val_raw: Any = data_dict.get("error")
            error_msg: str | None
            if success_val:
                error_msg = None
            elif error_val_raw not in (None, ""):
                error_msg = str(error_val_raw)
            else:
                error_msg = None
            return success_val, data_dict, error_msg

        if hasattr(data, "__iter__") and not isinstance(data, str | bytes):
            results: list[Any] = list(data)
        else:
            results = []
        return True, {"results": results}, None
