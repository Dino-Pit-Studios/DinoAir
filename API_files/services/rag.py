"""
RAG service providing ingestion, search delegation, context retrieval, and file monitoring
utilities.

Heavy rag.* dependencies are imported lazily inside methods so the API can start even if
optional ML components are unavailable. Lazy imports are deliberate to avoid optional ML
deps at import time (pylint: import-outside-toplevel is disabled inline where used).
"""

from __future__ import annotations

import inspect
import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..settings import Settings
from .common import resp as _resp
from .rag_context import RagContextService
from .rag_embeddings import RagEmbeddingMaintenanceService
from .rag_ingestion import RagIngestionService
from .rag_monitor import RagMonitorService

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import NotRequired  # type: ignore
else:  # pragma: no cover - runtime fallback
    try:
        from typing import NotRequired  # type: ignore[attr-defined]
    except Exception:
        try:
            from typing import NotRequired  # type: ignore
        except Exception:
            NotRequired = object  # type: ignore

log = logging.getLogger("api.services.rag")

RAG_UNAVAILABLE_MSG = "RAG components unavailable"


# TypedDicts to narrow free-form payloads accepted by router_* helpers and others.
class _ContextPayload(TypedDict, total=False):
    """Payload for requesting context retrieval, including query, filters, and options."""

    query: str
    file_types: NotRequired[list[str] | None]
    top_k: NotRequired[int]
    include_suggestions: NotRequired[bool]


class _IngestDirPayload(TypedDict, total=False):
    """Payload for ingesting directories with options for recursion, file types, and force reprocessing."""

    directory: str
    recursive: NotRequired[bool]
    file_types: NotRequired[list[str] | None]
    force_reprocess: NotRequired[bool]


class _IngestFilesPayload(TypedDict, total=False):
    """Payload for ingesting specific files with an option to force reprocessing."""

    paths: list[str]
    force_reprocess: NotRequired[bool]


class _BatchEmbPayload(TypedDict, total=False):
    """Payload for specifying batch size when embedding items."""

    batch_size: int


class _MonitorStartPayload(TypedDict, total=False):
    """Payload for starting directory monitoring with specified directories and file extensions."""

    directories: list[str]
    file_extensions: NotRequired[list[str] | None]


class RagService:
    """
    Stable service surface for router-facing RAG operations.

    Notes:
    - Do NOT import heavy rag.* modules at import time. Import inside methods.
    - For search, delegate to SearchService to preserve existing behavior and avoid ML deps here.
    - Ingestion/context/monitor are guarded; return 501-style payloads when unavailable.
    """

    def __init__(self) -> None:
        """Initialize service with settings and sub-services."""
        self.settings = Settings()
        # Delegated to sub-services
        self._ingest = RagIngestionService(self.settings)
        self._embed = RagEmbeddingMaintenanceService(self.settings)
        self._context = RagContextService(self.settings)
        self._monitor = RagMonitorService(self.settings)
        log.info(
            "RagService initialized",
            extra={
                "rag_enabled": getattr(self.settings, "rag_enabled", True),
                "watchdog_enabled": getattr(self.settings, "rag_watchdog_enabled", False),
            },
        )

    # -------------------------
    # Ingestion
    # -------------------------
    def ingest_directory(
        self,
        directory: str,
        recursive: bool = True,
        file_types: list[str] | None = None,
        force_reprocess: bool = False,
    ) -> dict[str, Any]:
        """Ingest all files in a directory, returning a standard response envelope."""
        # delegated to sub-service
        return self._ingest.ingest_directory(
            directory=directory,
            recursive=recursive,
            file_types=file_types,
            force_reprocess=force_reprocess,
        )

    def ingest_files(self, paths: list[str], force_reprocess: bool = False) -> dict[str, Any]:
        """Ingest a list of file paths.

        Validates against allowed/excluded directories, processes each file, and returns
        a unified response envelope with per-file results and aggregate stats.
        """
        # delegated to sub-service
        return self._ingest.ingest_files(paths=paths, force_reprocess=force_reprocess)

    def generate_missing_embeddings(self, batch_size: int = 32) -> dict[str, Any]:
        """Generate missing embeddings in batches."""
        # delegated to sub-service
        return self._embed.generate_missing_embeddings(batch_size=batch_size)

    # -------------------------
    # Read-only/search/context
    # -------------------------
    @staticmethod
    def index_stats() -> dict[str, Any]:
        """Return index statistics from the search subsystem.

        Returns:
            Envelope with keys: success, data, error, code.
        """
        try:
            # pylint: disable=import-outside-toplevel
            from .search import SearchService  # local import to avoid circular dependency

            svc = SearchService()
            resp = svc.get_index_stats()
            return _resp(
                True,
                resp.model_dump(by_alias=False, exclude_none=True),
                None,
                200,
            )
        except (ImportError, AttributeError, TypeError, RuntimeError) as e:
            log.exception("index_stats failed")
            return _resp(False, None, str(e), 500)

    def search_keyword(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run keyword search and return a standard response envelope.

        Args:
            payload: Dict matching KeywordSearchRequest fields.

        Returns:
            Envelope with keys: success, data, error, code.
        """
        try:
            # pylint: disable=import-outside-toplevel
            from ..schemas import KeywordSearchRequest  # pydantic model

            # pylint: disable=import-outside-toplevel
            from .search import SearchService

            req = KeywordSearchRequest(**(payload or {}))
            svc = SearchService()
            resp = svc.search_keyword(req)
            return _resp(
                True,
                resp.model_dump(by_alias=False, exclude_none=True),
                None,
                200,
            )
        except (ImportError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            log.exception("search_keyword failed")
            return _resp(False, {"hits": []}, str(e), 500)

    def search_vector(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run vector search and return a standard response envelope.

        Args:
            payload: Dict matching VectorSearchRequest fields.

        Returns:
            Envelope with keys: success, data, error, code.
        """
        try:
            # pylint: disable=import-outside-toplevel
            from ..schemas import VectorSearchRequest

            # pylint: disable=import-outside-toplevel
            from .search import SearchService

            req = VectorSearchRequest(**(payload or {}))
            svc = SearchService()
            resp = svc.search_vector(req)
            return _resp(
                True,
                resp.model_dump(by_alias=False, exclude_none=True),
                None,
                200,
            )
        except (ImportError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            log.exception("search_vector failed")
            return _resp(False, {"hits": []}, str(e), 500)

    def search_hybrid(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run hybrid search and return a standard response envelope.

        Args:
            payload: Dict matching HybridSearchRequest fields.

        Returns:
            Envelope with keys: success, data, error, code.
        """
        try:
            # pylint: disable=import-outside-toplevel
            from ..schemas import HybridSearchRequest

            # pylint: disable=import-outside-toplevel
            from .search import SearchService

            req = HybridSearchRequest(**(payload or {}))
            svc = SearchService()
            resp = svc.search_hybrid(req)
            return _resp(
                True,
                resp.model_dump(by_alias=False, exclude_none=True),
                None,
                200,
            )
        except (ImportError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            log.exception("search_hybrid failed")
            return _resp(False, {"hits": []}, str(e), 500)

    def get_context(
        self,
        query: str,
        file_types: list[str] | None = None,
        top_k: int = 10,
        include_suggestions: bool = True,
    ) -> dict[str, Any]:
        """Retrieve contextual documents/snippets for a query."""
        # delegated to sub-service
        return self._context.get_context(
            query=query,
            file_types=file_types,
            top_k=top_k,
            include_suggestions=include_suggestions,
        )

    # -------------------------
    # Monitoring
    # -------------------------
    def monitor_start(
        self, directories: list[str], file_extensions: list[str] | None = None
    ) -> dict[str, Any]:
        """Start monitoring directories for changes."""
        # delegated to sub-service
        return self._monitor.monitor_start(directories=directories, file_extensions=file_extensions)

    def monitor_stop(self) -> dict[str, Any]:
        """Stop the file monitor if running."""
        # delegated to sub-service
        return self._monitor.monitor_stop()

    def monitor_status(self) -> dict[str, Any]:
        """Return current monitor status.

        Returns:
            Envelope with keys: success, data, error, code.
        """
        # delegated to sub-service
        return self._monitor.monitor_status()

    # -------------------------
    # Internal helpers (private)
    # -------------------------
    def _make_validator(self, directory_validator_cls: Any) -> Any:
        """Build a DirectoryValidator configured from Settings."""
        allowed = getattr(self.settings, "rag_allowed_dirs", []) or None
        excluded = getattr(self.settings, "rag_excluded_dirs", []) or None
        try:
            return directory_validator_cls(allowed_dirs=allowed, excluded_dirs=excluded)
        except (TypeError, ValueError):
            return directory_validator_cls(allowed_dirs=None, excluded_dirs=excluded)

    def _make_processor(self, optimized_file_processor_cls: Any) -> Any:
        """Build an OptimizedFileProcessor with settings-derived parameters."""
        return optimized_file_processor_cls(
            user_name=None,
            chunk_size=getattr(self.settings, "rag_chunk_size", 1000),
            chunk_overlap=getattr(self.settings, "rag_chunk_overlap", 200),
            generate_embeddings=True,
            embedding_batch_size=None,
            max_workers=getattr(self.settings, "rag_watchdog_max_workers", 2),
            cache_size=getattr(self.settings, "rag_cache_size", 100),
            enable_caching=True,
        )

    def _process_files(
        self,
        proc: Any,
        files: list[str],
        force_reprocess: bool,
        has_run_single: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Process a list of files, aggregating per-file results and stats."""
        results: list[dict[str, Any]] = []
        stats = {"processed": 0, "failed": 0, "skipped": 0}

        for path in files:
            try:
                if has_run_single:
                    res = proc.run_single(path, force_reprocess=force_reprocess)
                else:
                    # Align with FileProcessor signature to ensure DB storage
                    res = proc.process_file(path, force_reprocess=force_reprocess, store_in_db=True)

                # Normalize and collect minimal stable shape for the response
                success = bool(res.get("success"))
                res_stats: dict[str, Any] = res.get("stats") or {}
                action: str = str(res_stats.get("action", ""))
                if success:
                    if action in {"skipped", "cached"}:
                        stats["skipped"] += 1
                    else:
                        stats["processed"] += 1
                else:
                    stats["failed"] += 1

                results.append(
                    {
                        "file": path,
                        "success": success,
                        "error": res.get("error"),
                        "stats": res.get("stats"),
                        "file_id": res.get("file_id"),
                        "chunks": res.get("chunks"),
                    }
                )
            except (OSError, ValueError, RuntimeError, AttributeError, TypeError) as e:
                stats["failed"] += 1
                results.append({"file": path, "success": False, "error": str(e)})

        return results, stats

    def _process_ingest_file_paths(
        self,
        directory_validator_cls: Any,
        paths: list[str],
        optimized_file_processor_cls: Any,
        force_reprocess: bool,
    ) -> dict[str, Any]:
        """Validate, process each file, and aggregate stats (helper for ingest_files)."""
        # Validate and filter incoming paths against allow/deny lists
        validator = self._make_validator(directory_validator_cls)
        allowed = validator.get_allowed_files(paths or [])
        if not allowed:
            return _resp(
                True,
                {
                    "success": True,
                    "message": "No files allowed or matched",
                    "stats": {
                        "total_files": 0,
                        "processed": 0,
                        "failed": 0,
                        "skipped": 0,
                    },
                },
                None,
                200,
            )

        # Prepare processor once; decide strategy outside the loop
        proc = self._make_processor(optimized_file_processor_cls)
        has_run_single = hasattr(proc, "run_single")

        # Process files with reduced branching
        results, stats = self._process_files(proc, allowed, force_reprocess, has_run_single)

        out: dict[str, Any] = {
            "success": stats["failed"] == 0,
            "results": results,
            "stats": {
                "total_files": len(allowed),
                "processed": stats["processed"],
                "failed": stats["failed"],
                "skipped": stats["skipped"],
            },
        }
        return _resp(
            bool(out["success"]),
            out,
            None if out["success"] else "One or more files failed",
            200,
        )

    def _load_context_method(self) -> tuple[Callable[..., Any] | None, bool]:
        """Load provider method for context; returns (method, unavailable_flag)."""
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
        """Filter kwargs to only those accepted by the callable."""
        try:
            sig = inspect.signature(method)
            return {k: v for k, v in kwargs.items() if k in sig.parameters}
        except (ValueError, TypeError):
            return kwargs

    @staticmethod
    def _preview_dict_keys(data: Any, limit: int = 10) -> list[str] | None:
        """Return a preview list of dict keys for logging; avoid large payload logs."""
        try:
            if isinstance(data, dict):
                d = cast("dict[str, Any]", data)
                return [str(k) for k in list(d.keys())[:limit]]
            return None
        except Exception:  # pragma: no cover - defensive
            return None

    @staticmethod
    def _normalize_context_data(data: Any) -> tuple[bool, dict[str, Any], str | None]:
        """Normalize provider output into (success, data, error_msg)."""
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

        # Handle non-dict responses
        if hasattr(data, "__iter__") and not isinstance(data, str | bytes):
            results: list[Any] = list(data)
        else:
            results = []
        return True, {"results": results}, None


# -------------------------
# Module-level singleton + router-facing functions
# -------------------------
@lru_cache(maxsize=1)
def get_rag_service() -> RagService:
    """Return a cached RagService instance (singleton via LRU cache)."""
    return RagService()


def _safe_exec(func_name: str, **kwargs: Any) -> dict[str, Any]:
    """Safely execute a RagService method by name with kwargs, returning the envelope."""
    try:
        svc = get_rag_service()
        func = getattr(svc, func_name)
        return func(**kwargs)
    except (AttributeError, TypeError, RuntimeError) as e:
        log.exception("router call failed: %s", func_name)
        return _resp(False, None, str(e), 500)


def router_ingest_directory(payload: dict[str, Any]) -> dict[str, Any]:
    """Router: ingest a directory."""
    p = cast("_IngestDirPayload", dict(payload or {}))
    return _safe_exec(
        "ingest_directory",
        directory=str(p.get("directory", "")),
        recursive=bool(p.get("recursive", True)),
        file_types=p.get("file_types"),
        force_reprocess=bool(p.get("force_reprocess", False)),
    )


def router_ingest_files(payload: dict[str, Any]) -> dict[str, Any]:
    """Router: ingest specific files."""
    p = cast("_IngestFilesPayload", dict(payload or {}))
    return _safe_exec(
        "ingest_files",
        paths=(p.get("paths") or []),
        force_reprocess=bool(p.get("force_reprocess", False)),
    )


def router_generate_missing_embeddings(payload: dict[str, Any]) -> dict[str, Any]:
    """Router: generate missing embeddings."""
    p = cast("_BatchEmbPayload", dict(payload or {}))
    return _safe_exec(
        "generate_missing_embeddings",
        batch_size=int(p.get("batch_size", 32)),
    )


def router_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Router: get context for a query."""
    p = cast("_ContextPayload", dict(payload or {}))
    return _safe_exec(
        "get_context",
        query=str(p.get("query", "")),
        file_types=p.get("file_types"),
        top_k=int(p.get("top_k", 10)),
        include_suggestions=bool(p.get("include_suggestions", True)),
    )


def router_monitor_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Router: start file monitor."""
    p = cast("_MonitorStartPayload", dict(payload or {}))
    return _safe_exec(
        "monitor_start",
        directories=(p.get("directories") or []),
        file_extensions=p.get("file_extensions"),
    )


def router_monitor_stop(_payload: dict[str, Any]) -> dict[str, Any]:
    """Router: stop file monitor. Payload is ignored but kept for signature consistency."""
    return _safe_exec("monitor_stop")


def router_monitor_status(_payload: dict[str, Any]) -> dict[str, Any]:
    """Router: get file monitor status. Payload is ignored but kept for compatibility."""
    return _safe_exec("monitor_status")
