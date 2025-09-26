from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .common import guard_imports, resp

if TYPE_CHECKING:
    from ..settings import Settings

log = logging.getLogger("api.services.rag_ingestion")
RAG_UNAVAILABLE_MSG = "RAG components unavailable"


class RagIngestionService:
    """
    Service responsible for ingesting documents from a directory using RAG components.

    This class handles directory validation, optimized file processing, and embedding
    generation to support retrieval-augmented generation workflows.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ingest_directory(
        self,
        directory: str,
        recursive: bool = True,
        file_types: list[str] | None = None,
        force_reprocess: bool = False,
    ) -> dict[str, Any]:
        if not getattr(self.settings, "rag_enabled", True):
            return resp(False, None, RAG_UNAVAILABLE_MSG, 501)

        guard = guard_imports(("rag.directory_validator", "rag.optimized_file_processor"))
        if guard is not None:
            return guard

        try:
            # pylint: disable=import-outside-toplevel
            from rag.directory_validator import DirectoryValidator  # type: ignore

            # pylint: disable=import-outside-toplevel
            from rag.optimized_file_processor import OptimizedFileProcessor  # type: ignore
        except ImportError:
            return resp(False, None, RAG_UNAVAILABLE_MSG, 501)

        try:
            validator = DirectoryValidator(
                allowed_dirs=getattr(self.settings, "rag_allowed_dirs", []) or None,
                excluded_dirs=getattr(self.settings, "rag_excluded_dirs", []) or None,
            )
            v = validator.validate_path(directory)
            if not v.get("valid"):
                return resp(
                    False,
                    None,
                    f"Directory invalid or not allowed: {v.get('message')}",
                    400,
                )

            proc = OptimizedFileProcessor(
                user_name=None,
                chunk_size=getattr(self.settings, "rag_chunk_size", 1000),
                chunk_overlap=getattr(self.settings, "rag_chunk_overlap", 200),
                generate_embeddings=True,
                embedding_batch_size=None,
                max_workers=getattr(self.settings, "rag_watchdog_max_workers", 2),
                cache_size=getattr(self.settings, "rag_cache_size", 100),
                enable_caching=True,
            )
            result = proc.process_directory(
                directory=directory,
                recursive=recursive,
                file_types=file_types,
                force_reprocess=force_reprocess,
            )
            return resp(
                bool(result.get("success", True)),
                result,
                None if result.get("success") else result.get("error"),
                200,
            )
        except (OSError, ValueError, RuntimeError) as e:
            log.exception("ingest_directory failed")
            return resp(False, None, str(e), 500)

    def ingest_files(self, paths: list[str], force_reprocess: bool = False) -> dict[str, Any]:
        if not getattr(self.settings, "rag_enabled", True):
            return resp(False, None, RAG_UNAVAILABLE_MSG, 501)

        guard = guard_imports(("rag.directory_validator", "rag.optimized_file_processor"))
        if guard is not None:
            return guard

        try:
            # pylint: disable=import-outside-toplevel
            from rag.directory_validator import DirectoryValidator  # type: ignore

            # pylint: disable=import-outside-toplevel
            from rag.optimized_file_processor import OptimizedFileProcessor  # type: ignore
        except ImportError:
            return resp(False, None, RAG_UNAVAILABLE_MSG, 501)

        try:
            return self._process_ingest_file_paths(
                DirectoryValidator, paths, OptimizedFileProcessor, force_reprocess
            )
        except (OSError, ValueError, RuntimeError, AttributeError, TypeError) as e:
            log.exception("ingest_files failed")
            return resp(False, None, str(e), 500)

    # -------------------------
    # Private helpers (copied semantics from api/services/rag.py)
    # -------------------------
    def _make_validator(self, directory_validator_cls: Any) -> Any:
        allowed = getattr(self.settings, "rag_allowed_dirs", []) or None
        excluded = getattr(self.settings, "rag_excluded_dirs", []) or None
        try:
            return directory_validator_cls(allowed_dirs=allowed, excluded_dirs=excluded)
        except (TypeError, ValueError):
            return directory_validator_cls(allowed_dirs=None, excluded_dirs=excluded)

    def _make_processor(self, optimized_file_processor_cls: Any) -> Any:
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

    @staticmethod
    def _process_files(
        proc: Any,
        files: list[str],
        force_reprocess: bool,
        has_run_single: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
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
        # Validate and filter incoming paths against allow/deny lists
        validator = self._make_validator(directory_validator_cls)
        allowed = validator.get_allowed_files(paths or [])
        if not allowed:
            return resp(
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
        return resp(
            bool(out["success"]),
            out,
            None if out["success"] else "One or more files failed",
            200,
        )
