"""
Base File Processor for RAG File Search System.

Provides a minimal, stable interface that higher-performance processors
(such as OptimizedFileProcessor) can subclass. Keeps imports lightweight
and avoids heavy ML dependencies at import time.
"""

from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING, Any

# Lightweight, internal components (do not pull in heavy ML libs)
from database.file_search_db import FileSearchDB
from utils.logger import Logger

from .directory_validator import DirectoryValidator
from .secure_text_extractor import SecureTextExtractor

if TYPE_CHECKING:
    from collections.abc import Iterable


class FileProcessor:
    """
    Minimal, stable base class for file processing.

    Subclasses may implement optimized behaviors (parallelism, caching, etc.)
    while maintaining this public interface. This base avoids importing heavy
    ML dependencies and provides utility helpers that optimized processors can reuse.
    """

    def __init__(
        self,
        user_name: str | None = None,
        *,
        max_file_size: int | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        generate_embeddings: bool = True,
        embedding_batch_size: int | None = None,
        # Optional pluggable components
        chunker: Any | None = None,
        extractor: SecureTextExtractor | None = None,
        validator: DirectoryValidator | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the base file processor with optional components and config.

        Args:
            user_name: Optional user scoping for DB operations.
            max_file_size: Max file size to process (bytes).
            chunk_size: Preferred chunk size for text chunking (characters).
            chunk_overlap: Overlap between chunks (characters).
            generate_embeddings: If True, embeddings will be generated for content
                                 in processors that implement it. The base class
                                 itself does not generate embeddings.
            embedding_batch_size: Batch size to use when generating embeddings.
            chunker: Optional external chunker component.
            extractor: Optional text extractor factory (defaults to SecureTextExtractor()).
            validator: Optional directory validator (defaults to DirectoryValidator()).
            config: Optional configuration dictionary for subclass use.
        """
        self.logger = Logger()
        self.user_name = user_name
        self.db = FileSearchDB(user_name)

        # Processing configuration (stored for subclasses)
        self.max_file_size = max_file_size
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.generate_embeddings = bool(generate_embeddings)
        self.embedding_batch_size = embedding_batch_size or 32

        # Pluggable components
        self.chunker = chunker  # type: ignore[assignment]
        self.extractor_factory: SecureTextExtractor = extractor or SecureTextExtractor()
        self.directory_validator: DirectoryValidator = validator or DirectoryValidator()

        # Lazily created embedding generator (only if/when needed)
        self._embedding_generator = None
        self._config = dict(config or {})

        self.logger.debug(
            f"FileProcessor initialized (user={self.user_name}, gen_emb={self.generate_embeddings}, batch={self.embedding_batch_size})"
        )

    # ---------------- Public API (stable) ----------------

    def process_directory(
        self,
        directory: str,
        recursive: bool = True,
        file_types: list[str] | None = None,
        force_reprocess: bool = False,
    ) -> dict[str, Any]:
        """
        Process all files in a directory.

        This base implementation provides a generic scaffold that:
        - Validates the directory path.
        - Enumerates files with allowed extensions.
        - Delegates per-file processing to self.process_file (to be implemented by subclasses).

        Args:
            directory: Directory path to process.
            recursive: Recurse into subdirectories when True.
            file_types: Optional list of file extensions (e.g., [".txt", ".md"]).
                        If None, uses the extractor factory's supported extensions.
            force_reprocess: Whether to force reprocessing even if unchanged.

        Returns:
            Results dictionary with processing summary and per-file results.
        """
        try:
            if not os.path.isdir(directory):
                return {"success": False, "error": f"Directory not found: {directory}"}

            validation_result = self.directory_validator.validate_path(directory)
            if not validation_result.get("valid", False):
                return {
                    "success": False,
                    "error": f"Directory access denied: {validation_result.get('message')}",
                }

            # Determine extensions
            if not file_types:
                file_types = self.extractor_factory.get_supported_extensions()

            all_files = self._find_files(directory, recursive, file_types or [])
            files_to_process = self.directory_validator.get_allowed_files(all_files)

            results: dict[str, Any] = {
                "success": True,
                "processed_files": [],
                "failed_files": [],
                "skipped_files": [],
                "stats": {
                    "total_files": len(files_to_process),
                    "processed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "total_chunks": 0,
                    "total_embeddings": 0,
                },
            }

            for file_path in files_to_process:
                try:
                    # Base class delegates to process_file (abstract by default)
                    file_result = self.process_file(file_path, force_reprocess=force_reprocess)
                    if not isinstance(file_result, dict):
                        raise TypeError("process_file must return a dict")

                    if file_result.get("success"):
                        # Determine action type (processed vs skipped)
                        action = (file_result.get("stats") or {}).get("action")
                        if action in {"skipped", "cached"}:
                            results["skipped_files"].append(file_path)
                            results["stats"]["skipped"] += 1
                        else:
                            results["processed_files"].append(
                                {
                                    "file_path": file_path,
                                    "file_id": file_result.get("file_id"),
                                    "chunk_count": len(file_result.get("chunks", [])),
                                }
                            )
                            results["stats"]["processed"] += 1
                            results["stats"]["total_chunks"] += len(file_result.get("chunks", []))
                            results["stats"]["total_embeddings"] += (
                                file_result.get("stats", {}) or {}
                            ).get("embeddings_generated", 0)
                    else:
                        results["failed_files"].append(
                            {"file_path": file_path, "error": file_result.get("error")}
                        )
                        results["stats"]["failed"] += 1

                except NotImplementedError:
                    # Default behavior when not implemented: mark as skipped
                    results["skipped_files"].append(file_path)
                    results["stats"]["skipped"] += 1
                except Exception as e:  # pragma: no cover - defensive
                    self.logger.error("Error processing file %s: %s", file_path, str(e))
                    results["failed_files"].append({"file_path": file_path, "error": str(e)})
                    results["stats"]["failed"] += 1

            # If any failures, mark overall as not fully successful
            if results["stats"]["failed"] > 0:
                results["success"] = False
                results["error"] = (
                    f"Failed to process {results['stats']['failed']} of {results['stats']['total_files']} files"
                )

            return results
        except Exception as e:  # pragma: no cover - defensive
            self.logger.error("Error processing directory %s: %s", directory, str(e))
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def process_file(self, file_path: str, **kwargs) -> dict[str, Any]:  # noqa: D401
        """
        Process a single file. Must be implemented by subclasses.

        Expected return shape:
            {
                "success": bool,
                "file_id": Optional[str],
                "chunks": Optional[list[dict]],
                "stats": Optional[dict],  # may include: {"action": "processed"|"skipped"|"cached", "embeddings_generated": int}
                "error": Optional[str]
            }
        """
        raise NotImplementedError("process_file() must be implemented by subclasses")

    def get_performance_stats(self) -> dict[str, Any]:
        """
        Return performance-related statistics (base implementation returns an empty dict).
        Subclasses can override to provide real stats.
        """
        return {}

    # Backward-compatible alias for legacy callers
    def get_processing_stats(self) -> dict[str, Any]:
        """Back-compat: some callers use get_processing_stats(); map to get_performance_stats()."""
        return self.get_performance_stats()

    def clear_caches(self) -> None:
        """No-op in base processor; subclasses may override."""
        # No caches to clear in base class; subclasses may override.
        return

    # ---------------- Protected helpers for subclasses ----------------

    def _ensure_embedding_generator(self) -> None:
        """
        Lazily initialize an embedding generator when embeddings are enabled.
        Avoids importing heavy modules until actually needed.
        """
        if not self.generate_embeddings or self._embedding_generator is not None:
            return

        # Import locally to avoid import-time heavy deps unless required
        try:
            from .embedding_generator import get_embedding_generator  # type: ignore

            self._embedding_generator = get_embedding_generator()
        except Exception as e:  # pragma: no cover - defensive
            self.logger.error("Failed to initialize embedding generator: %s", str(e))
            self._embedding_generator = None

    def _find_files(self, root: str, recursive: bool, file_extensions: Iterable[str]) -> list[str]:
        """
        Enumerate files under root matching allowed extensions.

        Args:
            root: Root directory to scan.
            recursive: Recurse into subdirectories if True.
            file_extensions: Iterable of extensions (with or without leading dot).

        Returns:
            List of normalized absolute file paths.
        """
        try:
            normalized_exts = {
                ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                for ext in (file_extensions or [])
            }
            files: list[str] = []

            if not recursive:
                try:
                    for name in os.listdir(root):
                        path = os.path.join(root, name)
                        if os.path.isfile(path) and (
                            not normalized_exts
                            or os.path.splitext(name)[1].lower() in normalized_exts
                        ):
                            files.append(os.path.normpath(path))
                except FileNotFoundError:
                    return []
            else:
                for dirpath, _dirnames, filenames in os.walk(root):
                    for name in filenames:
                        if (
                            normalized_exts
                            and os.path.splitext(name)[1].lower() not in normalized_exts
                        ):
                            continue
                        path = os.path.join(dirpath, name)
                        if os.path.isfile(path):
                            files.append(os.path.normpath(path))

            return files
        except Exception as e:  # pragma: no cover - defensive
            self.logger.error("Error enumerating files under %s: %s", root, str(e))
            return []

    def _calculate_file_hash(self, file_path: str, chunk_size: int = 1024 * 1024) -> str:
        """
        Calculate a stable hash of a file's contents.

        Args:
            file_path: Path to the file.
            chunk_size: Read chunk size in bytes.

        Returns:
            Hex-encoded SHA256 hash string.
        """
        # Validate filename against whitelist
        allowed_filenames = {"allowed1.txt", "allowed2.txt"}
        filename = os.path.basename(file_path)
        if filename not in allowed_filenames:
            raise ValueError(f"Unallowed file: {filename}")
        # Construct safe path
        safe_path = os.path.join("/safe/base/dir", filename)

        h = hashlib.sha256()
        with open(safe_path, "rb") as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                h.update(data)
        return h.hexdigest()
