"""
Optimized File Processor for RAG File Search System
Implements performance improvements including parallel processing, caching,
and memory-efficient operations.
"""

import concurrent.futures
import gc
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from database.file_search_db import FileSearchDB

# Import DinoAir components
from utils.logger import Logger

from .embedding_generator import get_embedding_generator
from .file_processor import FileProcessor

# Import RAG components


class LRUCache:
    """Simple LRU cache implementation for embeddings and file metadata"""

    def __init__(self, max_size: int = 1000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        self.lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Get item from cache"""
        with self.lock:
            if key in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]
            self.misses += 1
            return None

    def put(self, key: str, value: Any) -> None:
        """Put item in cache"""
        with self.lock:
            if key in self.cache:
                # Update existing
                self.cache.move_to_end(key)
            # Add new
            elif len(self.cache) >= self.max_size:
                # Remove least recently used
                self.cache.popitem(last=False)
            self.cache[key] = value

    def clear(self) -> None:
        """Clear the cache"""
        with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        with self.lock:
            total = self.hits + self.misses
            hit_rate = self.hits / total if total > 0 else 0
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate,
            }


class OptimizedFileProcessor(FileProcessor):
    """
    Optimized version of FileProcessor with performance improvements:
    - Parallel file processing
    - Caching for embeddings and metadata
    - Batch database operations
    - Memory-efficient file handling
    - Progress tracking with time estimates
    """

    def __init__(
        self,
        user_name: str | None = None,
        max_file_size: int | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        generate_embeddings: bool = True,
        embedding_batch_size: int | None = None,
        max_workers: int | None = None,
        cache_size: int = 1000,
        enable_caching: bool = True,
    ):
        """
        Initialize the OptimizedFileProcessor.

        Additional Args:
            max_workers: Maximum number of parallel workers
            cache_size: Size of LRU cache for embeddings
            enable_caching: Whether to enable caching
        """
        super().__init__(
            user_name=user_name,
            max_file_size=max_file_size,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            generate_embeddings=generate_embeddings,
            embedding_batch_size=embedding_batch_size,
        )
        # Parallel processing settings
        self.max_workers = max_workers or min(4, os.cpu_count() or 1)

        # Initialize caches
        self.enable_caching = enable_caching
        if enable_caching:
            self.file_hash_cache = LRUCache(cache_size)
            self.embedding_cache = LRUCache(cache_size // 2)
            self.metadata_cache = LRUCache(cache_size // 2)

        # Performance tracking
        self.processing_times = []
        self._lock = threading.Lock()

        self.logger.info(
            f"OptimizedFileProcessor initialized with {self.max_workers} workers, caching={'enabled' if enable_caching else 'disabled'}"
        )

    def _gather_file_stats(self, file_path: str) -> tuple[int, datetime, str]:
        stat = os.stat(file_path)
        size = int(stat.st_size)
        modified_dt = datetime.fromtimestamp(stat.st_mtime)
        file_type = (os.path.splitext(file_path)[1] or "").lstrip(".").lower() or "unknown"
        return size, modified_dt, file_type

    def _should_skip(
        self, existing: dict[str, Any] | None, size: int, file_hash: str, force_reprocess: bool
    ) -> dict[str, Any] | None:
        if existing and not force_reprocess:
            try:
                existing_size = int(existing.get("size") or 0)
                existing_hash = str(existing.get("file_hash") or "")
                if existing_size == size and existing_hash == file_hash:
                    return {
                        "success": True,
                        "file_id": existing.get("id"),
                        "chunks": [],
                        "stats": {"action": "skipped"},
                        "message": "Unchanged file; skipped",
                    }
            except Exception:
                pass
        return None

    def _compute_chunk_params(self) -> tuple[int, int]:
        cs = max(100, int(self.chunk_size or 1000))
        ov = max(0, min(int(self.chunk_overlap or 200), cs - 1))
        return cs, ov

    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        start = 0
        n = len(text)
        idx = 0
        while start < n:
            end = min(n, start + chunk_size)
            chunks.append(
                {
                    "chunk_index": idx,
                    "content": text[start:end],
                    "start_pos": start,
                }
            )
            start = end - overlap if overlap and end < n else end
            idx += 1
        return chunks

    def process_file(self, file_path: str, **kwargs) -> dict[str, Any]:
        """
        Minimal concrete file processing:
        - Reads text content (utf-8) for simple text/markdown files
        - Chunks by characters using configured chunk_size/overlap
        - Stores file, chunks, and embeddings (when enabled) in DB
        """
        force_reprocess: bool = bool(kwargs.get("force_reprocess", False))

        error = self._check_file_exists(file_path)
        if error:
            return error

        size, modified_dt, file_type = self._gather_file_stats(file_path)
        file_hash = self._calculate_file_hash(
            file_path, chunk_size=getattr(self, "chunk_size", 65536)
        )
        existing = self.db.get_file_by_path(os.path.normpath(file_path))
        skip_resp = self._should_skip(existing, size, file_hash, force_reprocess)
        if skip_resp:
            return skip_resp

        text, read_error = self._safe_read_file(file_path)
        if read_error:
            return read_error

        norm_path = os.path.normpath(file_path)
        file_id, index_error = self._index_file(norm_path, file_hash, size, modified_dt, file_type)
        if index_error:
            return index_error

        cs, ov = self._compute_chunk_params()
        chunks = self._chunk_text(text, cs, ov)

        # Store chunks
        chunk_ids: list[str] = []
        for c in chunks:
            add_chunk_resp = self.db.add_chunk(
                file_id=file_id,
                chunk_index=c["chunk_index"],
                content=c["content"],
                start_pos=c["start_pos"],
                end_pos=c["end_pos"],
                metadata={"file_type": file_type},
            )
            if add_chunk_resp.get("success"):
                cid = add_chunk_resp.get("chunk_id")
                if isinstance(cid, str):
                    chunk_ids.append(cid)
                else:
                    self.logger.error(
                        f"Chunk ID missing or invalid for file {file_path}, index {c['chunk_index']}"
                    )
            else:
                # Continue but record failure
                self.logger.error(
                    f"Failed to add chunk {c['chunk_index']} for {file_path}: {add_chunk_resp.get('error')}"
                )

        # Optionally generate embeddings immediately
        embeddings_generated = 0
        try:
            if self.generate_embeddings and chunk_ids:
                # Ensure generator is available
                self._ensure_embedding_generator()
                if self._embedding_generator:
                    chunk_texts = [c["content"] for c in chunks]
                    embeddings_generated = self._generate_and_store_embeddings(
                        chunk_ids=chunk_ids,
                        chunk_texts=chunk_texts,
                        progress_callback=None,
                    )

            return {
                "success": True,
                "file_id": file_id,
                "chunks": [{"chunk_id": cid} for cid in chunk_ids],
                "stats": {
                    "action": "processed",
                    "embeddings_generated": embeddings_generated,
                    "chunk_count": len(chunk_ids),
                },
            }
        except Exception as e:
            self.logger.error(f"Unexpected error in process_file for {file_path}: {str(e)}")
            return {"success": False, "error": str(e)}

    # Adapter to ensure child dispatch for single-file ingestion
    def run_single(self, file_path: str, *, force_reprocess: bool = False) -> dict[str, Any]:
        """
        Adapter method used by API services to process a single file, ensuring
        this class's process_file implementation is invoked.
        """
        try:
            return self.process_file(file_path, force_reprocess=force_reprocess, store_in_db=True)
        except Exception as e:
            self.logger.error("run_single failed for %s: %s", file_path, str(e))
            return {"success": False, "error": str(e)}

    def process_directory(
        self,
        directory: str,
        recursive: bool = True,
        file_types: list[str] | None = None,
        force_reprocess: bool = False,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Process all files in a directory with parallel processing."""
        try:
            # Validate directory and get files (same as parent)
            if not os.path.isdir(directory):
                return {
                    "success": False,
                    "error": f"Directory not found: {directory}",
                }

            validation_result = self.directory_validator.validate_path(directory)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": f"Directory access denied: {validation_result['message']}",
                }

            if not file_types:
                file_types = self.extractor_factory.get_supported_extensions()

            all_files = self._find_files(directory, recursive, file_types)
            files_to_process = self.directory_validator.get_allowed_files(all_files)

            if not files_to_process:
                return {
                    "success": True,
                    "message": "No files found to process",
                    "stats": {
                        "total_files": 0,
                        "processed": 0,
                        "failed": 0,
                        "skipped": 0,
                    },
                }

            # Initialize results
            results = {
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
                    "processing_time": 0,
                    "files_per_second": 0,
                },
            }

            start_time = time.time()

            # Process files in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all files for processing
                future_to_file = {
                    executor.submit(
                        self._process_file_wrapper,
                        file_path,
                        force_reprocess,
                        i,
                        len(files_to_process),
                    ): file_path
                    for i, file_path in enumerate(files_to_process)
                }

                # Process completed futures
                for future in concurrent.futures.as_completed(future_to_file):
                    file_path = future_to_file[future]

                    try:
                        result = future.result()
                        self._update_results(results, file_path, result)

                        # Update progress
                        if progress_callback:
                            processed = (
                                results["stats"]["processed"]
                                + results["stats"]["failed"]
                                + results["stats"]["skipped"]
                            )
                            elapsed = time.time() - start_time
                            if processed > 0:
                                rate = processed / elapsed
                                remaining = (len(files_to_process) - processed) / rate
                                eta = datetime.now() + timedelta(seconds=remaining)

                                progress_callback(
                                    f"Processing files ({processed}/{len(files_to_process)}) ETA: {eta.strftime('%H:%M:%S')}",
                                    processed,
                                    len(files_to_process),
                                )

                    except Exception as e:
                        self.logger.error("Error processing %s: %s", file_path, str(e))
                        results["failed_files"].append({"file_path": file_path, "error": str(e)})
                        results["stats"]["failed"] += 1

            # Calculate final statistics
            end_time = time.time()
            results["stats"]["processing_time"] = end_time - start_time
            if results["stats"]["processing_time"] > 0:
                results["stats"]["files_per_second"] = (
                    len(files_to_process) / results["stats"]["processing_time"]
                )

            # Update success status
            if results["stats"]["failed"] > 0:
                results["success"] = False
                results["error"] = (
                    f"Failed to process {results['stats']['failed']} out of {results['stats']['total_files']} files"
                )

            # Add cache statistics if enabled
            if self.enable_caching:
                results["cache_stats"] = {
                    "file_hash_cache": self.file_hash_cache.get_stats(),
                    "embedding_cache": self.embedding_cache.get_stats(),
                    "metadata_cache": self.metadata_cache.get_stats(),
                }

            return results

        except Exception as e:
            self.logger.error("Error processing directory %s: %s", directory, str(e))
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def _process_file_wrapper(
        self, file_path: str, force_reprocess: bool, index: int, total: int
    ) -> dict[str, Any]:
        """Wrapper for process_file to handle progress tracking"""
        try:
            start_time = time.time()

            # Check cache first
            if self.enable_caching and not force_reprocess:
                cached_result = self._check_file_cache(file_path)
                if cached_result:
                    return cached_result

            result = self.process_file(file_path, force_reprocess=force_reprocess, store_in_db=True)

            # Track processing time
            processing_time = time.time() - start_time
            with self._lock:
                self.processing_times.append(processing_time)

            # Cache successful results
            if self.enable_caching and result["success"]:
                self._cache_file_result(file_path, result)

            return result

        except Exception as e:
            self.logger.error("Error in process_file_wrapper: %s", str(e))
            return {"success": False, "error": str(e)}

    def _check_file_cache(self, file_path: str) -> dict[str, Any] | None:
        """Check if file is in cache and still valid"""
        try:
            # Get current file metadata
            stat = os.stat(file_path)
            cache_key = f"{file_path}:{stat.st_mtime}:{stat.st_size}"

            # Check metadata cache
            cached_metadata = self.metadata_cache.get(cache_key)
            if cached_metadata:
                self.logger.debug("Cache hit for file: %s", file_path)
                return {
                    "success": True,
                    "file_id": cached_metadata["file_id"],
                    "chunks": [],  # Not stored in cache
                    "message": "Retrieved from cache",
                    "stats": {
                        "action": "cached",
                        "chunk_count": cached_metadata["chunk_count"],
                    },
                }

            return None

        except Exception as e:
            self.logger.debug("Cache check failed for %s: %s", file_path, str(e))
            return None

    def _cache_file_result(self, file_path: str, result: dict[str, Any]) -> None:
        """Cache successful file processing result"""
        try:
            stat = os.stat(file_path)
            cache_key = f"{file_path}:{stat.st_mtime}:{stat.st_size}"

            metadata = {
                "file_id": result.get("file_id"),
                "chunk_count": len(result.get("chunks", [])),
                "cached_at": datetime.now().isoformat(),
            }

            self.metadata_cache.put(cache_key, metadata)

        except Exception as e:
            self.logger.debug("Failed to cache result for %s: %s", file_path, str(e))

    def _calculate_file_hash(self, file_path: str, chunk_size: int = 1024 * 1024) -> str:
        """Calculate file hash with caching"""
        cache_key = None
        if self.enable_caching:
            # Check cache first
            stat = os.stat(file_path)
            cache_key = f"{file_path}:{stat.st_mtime}:{stat.st_size}"
            cached_hash = self.file_hash_cache.get(cache_key)
            if cached_hash:
                return cached_hash

        # Calculate hash
        file_hash = super()._calculate_file_hash(file_path, chunk_size=chunk_size)

        # Cache the result
        if self.enable_caching and cache_key is not None:
            self.file_hash_cache.put(cache_key, file_hash)

        return file_hash

    def _update_results(
        self, results: dict[str, Any], file_path: str, file_result: dict[str, Any]
    ) -> None:
        """Update results dictionary with file processing result"""
        with self._lock:
            if file_result["success"]:
                if (
                    file_result.get("stats", {}).get("action") == "skipped"
                    or file_result.get("stats", {}).get("action") == "cached"
                ):
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
                    results["stats"]["total_embeddings"] += file_result.get("stats", {}).get(
                        "embeddings_generated", 0
                    )
            else:
                results["failed_files"].append(
                    {
                        "file_path": file_path,
                        "error": file_result.get("error", "Unknown error"),
                    }
                )
                results["stats"]["failed"] += 1

    def _generate_and_store_embeddings(
        self,
        chunk_ids: list[str],
        chunk_texts: list[str],
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> int:
        """Generate embeddings with caching support."""
        if not self.generate_embeddings or not self._embedding_generator:
            return 0

        total_chunks = len(chunk_ids)
        embeddings_to_generate, cached_embeddings = self._partition_embeddings(
            chunk_ids, chunk_texts
        )

        new_embeddings = self._generate_batches(
            embeddings_to_generate, cached_embeddings, total_chunks, progress_callback
        )
        return self._store_embeddings(new_embeddings, cached_embeddings)

    def _partition_embeddings(
        self, chunk_ids: list[str], chunk_texts: list[str]
    ) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, Any]]]:
        embeddings_to_generate: list[tuple[int, str, str]] = []
        cached_embeddings: list[tuple[int, str, Any]] = []
        if self.enable_caching:
            for i, (chunk_id, chunk_text) in enumerate(zip(chunk_ids, chunk_texts, strict=False)):
                cached = self.embedding_cache.get(chunk_id)
                if cached:
                    cached_embeddings.append((i, chunk_id, cached))
                else:
                    embeddings_to_generate.append((i, chunk_id, chunk_text))
        else:
            embeddings_to_generate = [
                (i, chunk_id, chunk_text)
                for i, (chunk_id, chunk_text) in enumerate(
                    zip(chunk_ids, chunk_texts, strict=False)
                )
            ]
        return embeddings_to_generate, cached_embeddings

    def _generate_batches(
        self,
        embeddings_to_generate: list[tuple[int, str, str]],
        cached_embeddings: list[tuple[int, str, Any]],
        total_chunks: int,
        progress_callback: Callable[[str, int, int], None] | None,
    ) -> list[tuple[int, str, Any]]:
        new_embeddings: list[tuple[int, str, Any]] = []
        if embeddings_to_generate:
            batch_size = self.embedding_batch_size
            for start in range(0, len(embeddings_to_generate), batch_size):
                end = min(start + batch_size, len(embeddings_to_generate))
                batch = embeddings_to_generate[start:end]
                if progress_callback:
                    progress_callback(
                        f"Generating embeddings ({end}/{len(embeddings_to_generate)} new, {len(cached_embeddings)} cached)",
                        end + len(cached_embeddings),
                        total_chunks,
                    )
                texts = [text for _, _, text in batch]
                results = self._embedding_generator.generate(texts)
                for (i, chunk_id, _), embedding in zip(batch, results, strict=False):
                    new_embeddings.append((i, chunk_id, embedding))
        return new_embeddings

    def _store_embeddings(
        self,
        new_embeddings: list[tuple[int, str, Any]],
        cached_embeddings: list[tuple[int, str, Any]],
    ) -> int:
        count = 0
        for _, chunk_id, embedding in new_embeddings + cached_embeddings:
            if self.enable_caching:
                self.embedding_cache.put(chunk_id, embedding)
            self._save_embedding(chunk_id, embedding)
            count += 1
        return count

    def clear_caches(self) -> None:
        """Clear all caches"""
        if self.enable_caching:
            self.file_hash_cache.clear()
            self.embedding_cache.clear()
            self.metadata_cache.clear()
            self.logger.info("All caches cleared")

    def get_performance_stats(self) -> dict[str, Any]:
        """Get performance statistics"""
        stats = {
            "max_workers": self.max_workers,
            "caching_enabled": self.enable_caching,
        }

        if self.processing_times:
            stats.update(
                {
                    "average_file_time": sum(self.processing_times) / len(self.processing_times),
                    "total_files_processed": len(self.processing_times),
                    "min_file_time": min(self.processing_times),
                    "max_file_time": max(self.processing_times),
                }
            )

        if self.enable_caching:
            stats["cache_performance"] = {
                "file_hash_cache": self.file_hash_cache.get_stats(),
                "embedding_cache": self.embedding_cache.get_stats(),
                "metadata_cache": self.metadata_cache.get_stats(),
            }

        return stats

    def optimize_for_memory(self) -> None:
        """Optimize memory usage by clearing caches and forcing garbage collection"""
        if self.enable_caching:
            # Clear caches
            self.clear_caches()

        # Force garbage collection
        gc.collect()

        self.logger.info("Memory optimization completed")


class BatchEmbeddingProcessor:
    """
    Specialized processor for batch embedding generation with progress tracking
    """

    def __init__(self, user_name: str, batch_size: int = 32):
        self.logger = Logger()
        self.user_name = user_name
        self.batch_size = batch_size
        self.db = FileSearchDB(user_name)
        self.embedding_generator = get_embedding_generator()

    def generate_missing_embeddings(
        self, progress_callback: Callable[[str, int, int], None] | None = None
    ) -> dict[str, Any]:
        """Generate embeddings for all chunks that don't have embeddings yet."""
        try:
            # Get chunks without embeddings
            chunks_without_embeddings = self._get_chunks_without_embeddings()

            if not chunks_without_embeddings:
                return {
                    "success": True,
                    "message": "All chunks already have embeddings",
                    "stats": {"total_chunks": 0, "embeddings_generated": 0},
                }

            total_chunks = len(chunks_without_embeddings)
            embeddings_generated = 0
            start_time = time.time()

            # Process in batches
            for i in range(0, total_chunks, self.batch_size):
                batch_end = min(i + self.batch_size, total_chunks)
                batch = chunks_without_embeddings[i:batch_end]

                # Update progress
                if progress_callback:
                    elapsed = time.time() - start_time
                    if i > 0:
                        rate = i / elapsed
                        remaining = (total_chunks - i) / rate
                        eta = datetime.now() + timedelta(seconds=remaining)

                        progress_callback(
                            f"Generating embeddings ({i}/{total_chunks}) ETA: {eta.strftime('%H:%M:%S')}",
                            i,
                            total_chunks,
                        )

                # Generate embeddings for batch
                chunk_texts = [chunk["content"] for chunk in batch]

                try:
                    embeddings = self.embedding_generator.generate_embeddings_batch(
                        chunk_texts, batch_size=self.batch_size, show_progress=False
                    )

                    # Store embeddings
                    for chunk, embedding in zip(batch, embeddings, strict=False):
                        result = self.db.add_embedding(
                            chunk_id=chunk["chunk_id"],
                            embedding_vector=embedding.tolist(),
                            model_name=self.embedding_generator.model_name,
                        )

                        if result["success"]:
                            embeddings_generated += 1

                except Exception as e:
                    self.logger.error("Error generating batch embeddings: %s", str(e))

            end_time = time.time()

            return {
                "success": True,
                "stats": {
                    "total_chunks": total_chunks,
                    "embeddings_generated": embeddings_generated,
                    "processing_time": end_time - start_time,
                    "embeddings_per_second": embeddings_generated / (end_time - start_time),
                },
            }

        except Exception as e:
            self.logger.error("Error in batch embedding generation: %s", str(e))
            return {"success": False, "error": str(e)}

    def _get_chunks_without_embeddings(self) -> list[dict[str, Any]]:
        """Get all chunks that don't have embeddings"""
        try:
            # Use the new public method on FileSearchDB instead of accessing the private method
            return self.db.get_chunks_without_embeddings()
        except Exception as e:
            self.logger.error("Error getting chunks without embeddings: %s", str(e))
            return []
