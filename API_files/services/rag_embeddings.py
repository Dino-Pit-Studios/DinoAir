from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .common import guard_imports, resp

if TYPE_CHECKING:
    from ..settings import Settings

log = logging.getLogger("api.services.rag_embeddings")
RAG_UNAVAILABLE_MSG = "RAG components unavailable"


class RagEmbeddingMaintenanceService:
    """
    Service for generating and maintaining embeddings for retrieval-augmented generation (RAG).
    Provides batch processing of missing embeddings with error handling and availability checks.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_missing_embeddings(self, batch_size: int = 32) -> dict[str, Any]:
        if not getattr(self.settings, "rag_enabled", True):
            return resp(False, None, RAG_UNAVAILABLE_MSG, 501)

        guard = guard_imports(("rag.optimized_file_processor",))
        if guard is not None:
            return guard

        try:
            # pylint: disable=import-outside-toplevel
            from rag.optimized_file_processor import BatchEmbeddingProcessor  # type: ignore
        except ImportError:
            return resp(False, None, RAG_UNAVAILABLE_MSG, 501)

        try:
            bep = BatchEmbeddingProcessor(user_name="default_user", batch_size=batch_size)
            result = bep.generate_missing_embeddings()
            return resp(
                bool(result.get("success", True)),
                result,
                None if result.get("success") else result.get("error"),
                200,
            )
        except (RuntimeError, ValueError, TypeError, AttributeError) as e:
            log.exception("generate_missing_embeddings failed")
            return resp(False, None, str(e), 500)
