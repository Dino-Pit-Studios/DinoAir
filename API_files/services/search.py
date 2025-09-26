from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, cast

from fastapi import HTTPException
from pydantic import ValidationError
from starlette import status

from database.file_search_db import FileSearchDB

from ..schemas import (
    DirectorySettingsResponse,
    FileIndexStatsResponse,
    HybridSearchRequest,
    HybridSearchResponse,
    KeywordSearchRequest,
    KeywordSearchResponse,
    VectorSearchHit,
    VectorSearchRequest,
    VectorSearchResponse,
)

# Lazy import of vector engine to avoid heavy deps (numpy/torch/sentence-transformers) at API startup.
# We only instantiate it on-demand for vector/hybrid endpoints.
_engine_singleton: Any = None
_engine_error: Exception | None = None


def _get_engine(engine_singleton, engine_error):
    if engine_singleton is None and engine_error is None:
        try:
            # Resolve engine via factory (optimized with safe fallback)
            from rag import get_search_engine  # lightweight import via rag.__init__

            engine_singleton = get_search_engine(user_name=None, optimized=None)
            engine_error = None
        except Exception as e:
            engine_error = e
            engine_singleton = None
    return engine_singleton, engine_error


def _require_engine():
    eng = _get_engine(engine_error=None, engine_singleton=None)
    if eng is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Vector/hybrid search unavailable (optional ML dependencies not installed).",
        )
    return eng


log = logging.getLogger("api.services.search")

# Hard limits per spec
MAX_TOP_K = 50
SNIPPET_MAX_CHARS = 500


def _sanitize_file_types(file_types: list[str] | None) -> list[str] | None:
    if not file_types:
        return None
    sanitized = [s for ft in file_types[:20] if (s := ft.strip().lower()) and len(s) <= 20]
    return sanitized or None


def _truncate_snippet(text: str, limit: int = SNIPPET_MAX_CHARS) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _to_hit(result: Any) -> VectorSearchHit:
    def _get(obj: Any, key: str) -> Any:
        if hasattr(obj, key):
            return getattr(obj, key)
        if isinstance(obj, Mapping):
            m = cast("Mapping[str, Any]", obj)
            return m.get(key)
        return None

    # Prefer unified keys; fall back to alt names from DB rows
    file_path = _get(result, "file_path") or ""
    content = _get(result, "content") or ""
    score = _get(result, "score")
    if score is None:
        score = _get(result, "relevance_score") or 0.0
    chunk_index = _get(result, "chunk_index") or 0
    start_pos = _get(result, "start_pos") or 0
    end_pos = _get(result, "end_pos") or 0
    file_type = _get(result, "file_type")
    metadata = _get(result, "metadata")
    if isinstance(metadata, Mapping):
        metadata = dict(cast("Mapping[str, Any]", metadata))
    else:
        md_alt = _get(result, "chunk_metadata")
        metadata = dict(cast("Mapping[str, Any]", md_alt)) if isinstance(md_alt, Mapping) else None

    return VectorSearchHit(
        file_path=str(file_path),
        content=_truncate_snippet(str(content)),
        score=float(score),
        chunk_index=int(chunk_index),
        start_pos=int(start_pos),
        end_pos=int(end_pos),
        file_type=file_type,
        metadata=metadata,
    )


class SearchService:
    """
    Safe wrapper over RAG search/index modules.
    Read-only and bounded behavior per v0 spec.
    """

    def __init__(self) -> None:
        # Default user scoping left as None/default per underlying libs.
        # Delay vector engine creation to avoid heavy optional deps unless needed.
        self._db = FileSearchDB()
        self._engine = None  # resolved lazily via _require_engine()

    # -------- Keyword --------
    def search_keyword(self, req: KeywordSearchRequest) -> KeywordSearchResponse:
        top_k = min(MAX_TOP_K, max(1, req.top_k))
        file_types = _sanitize_file_types(req.file_types)

        try:
            # Direct DB-backed keyword search that requires no ML libraries.
            rows = self._db.search_by_keywords(
                keywords=[req.query],
                limit=top_k,
                file_types=file_types,
            )
            raw_rows = rows or []
            typed_rows: list[Mapping[str, Any]] = [
                cast("Mapping[str, Any]", r) for r in raw_rows[:top_k]
            ]
            # Map DB rows to a uniform shape for _to_hit
            mapped: list[dict[str, Any]] = [
                {
                    "file_path": r.get("file_path", ""),
                    "content": r.get("content", ""),
                    "score": float(r.get("relevance_score") or 0.0),
                    "chunk_index": int(r.get("chunk_index") or 0),
                    "start_pos": int(r.get("start_pos") or 0),
                    "end_pos": int(r.get("end_pos") or 0),
                    "file_type": r.get("file_type"),
                    "metadata": (
                        r.get("chunk_metadata")
                        if isinstance(r.get("chunk_metadata"), dict)
                        else None
                    ),
                }
                for r in typed_rows
            ]
            hits: list[VectorSearchHit] = [_to_hit(m) for m in mapped]
            return KeywordSearchResponse(hits=hits)
        except ValidationError as ve:
            log.warning("KeywordSearchResponse validation error", extra={"errors": ve.errors()})
            return KeywordSearchResponse(hits=[])

    # -------- Vector --------
    def _ensure_vector_index_available(self) -> None:
        """
        If no embeddings exist, vector/hybrid are not implemented yet.
        Raise 501 to be translated by global error handlers.
        """
        try:
            stats = self._db.get_indexed_files_stats() or {}
            total_embeddings = int(stats.get("total_embeddings") or 0)
            if total_embeddings <= 0:
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail="Vector index not available; embeddings are not present.",
                )
        except Exception as e:
            # On any unexpected failure to check, respond conservatively with 501
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Vector index not available.",
            ) from e

    def search_vector(self, req: VectorSearchRequest) -> VectorSearchResponse:
        # Check availability first
        self._ensure_vector_index_available()

        top_k = min(MAX_TOP_K, max(1, req.top_k))
        file_types = _sanitize_file_types(req.file_types)
        similarity_threshold = (
            req.similarity_threshold if req.similarity_threshold is not None else 0.5
        )
        metric = req.distance_metric.value

        try:
            engine = _require_engine()
            results = engine.search(
                query=req.query,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                file_types=file_types,
                distance_metric=metric,
            )
            hits = [_to_hit(r) for r in results[:top_k]]
            return VectorSearchResponse(hits=hits)
        except HTTPException:
            # Re-raise HTTP errors (e.g., 501)
            raise
        except ValidationError as ve:
            log.warning("VectorSearchResponse validation error", extra={"errors": ve.errors()})
            return VectorSearchResponse(hits=[])

    # -------- Hybrid --------
    def search_hybrid(self, req: HybridSearchRequest) -> HybridSearchResponse:
        # Check availability first (hybrid depends on vector)
        self._ensure_vector_index_available()

        top_k = min(MAX_TOP_K, max(1, req.top_k))
        file_types = _sanitize_file_types(req.file_types)
        similarity_threshold = (
            req.similarity_threshold if req.similarity_threshold is not None else 0.5
        )
        vector_weight = float(req.vector_weight)
        keyword_weight = float(req.keyword_weight)
        # Ensure non-degenerate weights (avoid direct float equality; treat near-zero as zero)
        if abs(vector_weight + keyword_weight) < 1e-6:
            vector_weight = 0.7
            keyword_weight = 0.3

        try:
            engine = _require_engine()
            results = engine.hybrid_search(
                query=req.query,
                top_k=top_k,
                vector_weight=vector_weight,
                keyword_weight=keyword_weight,
                similarity_threshold=similarity_threshold,
                file_types=file_types,
                rerank=bool(req.rerank),
            )
            hits = [_to_hit(r) for r in results[:top_k]]
            return HybridSearchResponse(hits=hits)
        except HTTPException:
            raise
        except ValidationError as ve:
            log.warning("HybridSearchResponse validation error", extra={"errors": ve.errors()})
            return HybridSearchResponse(hits=[])

    # -------- Index stats --------
    def get_index_stats(self) -> FileIndexStatsResponse:
        data = self._db.get_indexed_files_stats() or {}
        try:
            return FileIndexStatsResponse(
                total_files=int(data.get("total_files") or 0),
                files_by_type=dict(data.get("files_by_type") or {}),
                total_size_bytes=int(data.get("total_size_bytes") or 0),
                total_size_mb=float(data.get("total_size_mb") or 0.0),
                total_chunks=int(data.get("total_chunks") or 0),
                total_embeddings=int(data.get("total_embeddings") or 0),
                last_indexed_date=data.get("last_indexed_date"),
            )
        except ValidationError as ve:
            log.warning("FileIndexStatsResponse validation error", extra={"errors": ve.errors()})
            # Return zeros if coercion fails
            return FileIndexStatsResponse(
                total_files=0,
                files_by_type={},
                total_size_bytes=0,
                total_size_mb=0.0,
                total_chunks=0,
                total_embeddings=0,
                last_indexed_date=None,
            )

    # -------- Directory settings --------
    def get_directory_settings(self) -> DirectorySettingsResponse:
        data = self._db.get_directory_settings() or {}
        if (err := data.get("error")) and not data.get("success", True):
            # If backend reported error, surface as 501 for now (read-only metadata not available)
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=str(err),
            )
        try:
            allowed = list(data.get("allowed_directories") or [])
            excluded = list(data.get("excluded_directories") or [])
            return DirectorySettingsResponse(
                allowed_directories=allowed,
                excluded_directories=excluded,
                total_allowed=len(allowed),
                total_excluded=len(excluded),
            )
        except ValidationError as ve:
            log.warning(
                "DirectorySettingsResponse validation error",
                extra={"errors": ve.errors()},
            )
            return DirectorySettingsResponse(
                allowed_directories=[],
                excluded_directories=[],
                total_allowed=0,
                total_excluded=0,
            )


# Module-level singleton accessors
_search_singleton: SearchService | None = None


_search_service_singleton: SearchService = None


@lru_cache()
def get_search_service() -> SearchService:
    return SearchService()


# Facade functions
def keyword(req: KeywordSearchRequest) -> KeywordSearchResponse:
    return get_search_service().search_keyword(req)


def vector(req: VectorSearchRequest) -> VectorSearchResponse:
    return get_search_service().search_vector(req)


def hybrid(req: HybridSearchRequest) -> HybridSearchResponse:
    return get_search_service().search_hybrid(req)


def index_stats() -> FileIndexStatsResponse:
    return get_search_service().get_index_stats()


def directory_settings() -> DirectorySettingsResponse:
    return get_search_service().get_directory_settings()


def _infer_search_op(payload: dict[str, Any]) -> str:
    if op := str(payload.get("op") or payload.get("_op") or "").strip().lower():
        return op
    keys = payload.keys()
    if {"vector_weight", "keyword_weight", "rerank"} & keys:
        return "hybrid"
    if {"similarity_threshold", "distance_metric"} & keys:
        return "vector"
    return "keyword"


def _extract_kwargs(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: payload[k] for k in keys if k in payload}


def _handle_hybrid(payload: dict[str, Any]) -> dict[str, Any]:
    req_kwargs: dict[str, Any] = {"query": payload["query"]}
    req_kwargs |= _extract_kwargs(
        payload,
        (
            "top_k",
            "vector_weight",
            "keyword_weight",
            "similarity_threshold",
            "file_types",
            "rerank",
        ),
    )
    req = HybridSearchRequest(**req_kwargs)
    resp = hybrid(req)
    return resp.model_dump(by_alias=False, exclude_none=True)


def _handle_vector(payload: dict[str, Any]) -> dict[str, Any]:
    req_kwargs: dict[str, Any] = {"query": payload["query"]}
    req_kwargs |= _extract_kwargs(payload, ("top_k", "similarity_threshold", "file_types"))
    if "distance_metric" in payload:
        req_kwargs["distance_metric"] = payload["distance_metric"]
    req = VectorSearchRequest(**req_kwargs)
    resp = vector(req)
    return resp.model_dump(by_alias=False, exclude_none=True)


def _handle_keyword(payload: dict[str, Any]) -> dict[str, Any]:
    req_kwargs: dict[str, Any] = {"query": payload["query"]}
    req_kwargs |= _extract_kwargs(payload, ("top_k", "file_types"))
    req = KeywordSearchRequest(**req_kwargs)
    resp = keyword(req)
    return resp.model_dump(by_alias=False, exclude_none=True)


def router_search(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Adapter entry point for core_router.adapters.local_python.

    Input:
        input_data: dict for keyword/vector/hybrid search:

          keyword:
            {{ "query": str, "top_k"?: int, "file_types"?: list[str] }}

          vector:
            {{ "query": str, "top_k"?: int,
               "similarity_threshold"?: float,
               "file_types"?: list[str],
               "distance_metric"?: str }}

          hybrid:
            {{ "query": str, "top_k"?: int,
               "vector_weight"?: float,
               "keyword_weight"?: float,
               "similarity_threshold"?: float,
               "file_types"?: list[str],
               "rerank"?: bool }}

        Optionally 'op' or '_op' may be provided with one of
        'keyword' | 'vector' | 'hybrid'. If absent, dispatch is
        inferred by present keys.

    Behavior:
        Builds the appropriate request model and calls the
        corresponding facade. Returns a plain dict with the
        same shape as the response model. On unexpected errors,
        logs and returns a minimal valid response (e.g., {"hits": []}).
    """
    payload: dict[str, Any] = dict(input_data or {})
    op = _infer_search_op(payload)

    try:
        if op == "hybrid":
            return _handle_hybrid(payload)
        return _handle_vector(payload) if op == "vector" else _handle_keyword(payload)
    except Exception:
        # Translator-like minimal error handling:
        # return a minimal typed shape on error.
        log.exception("search.router_search failed")
        return {"hits": []}
