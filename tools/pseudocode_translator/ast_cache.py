"""
AST Cache module for the Pseudocode Translator

Provides a thread-safe LRU cache with TTL, size limits, and persistent storage
for AST parsing results to improve performance by avoiding redundant parsing.
"""

import ast
import hashlib

# Use the standard library 'json' module for serialization instead of 'pickle' to avoid
# arbitrary code execution vulnerabilities. JSON only allows safe data types.
import json
import logging
import shutil
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _ast_to_dict(node: ast.AST, max_depth: int = 500) -> dict[str, Any]:
    """
    Convert an AST node to a JSON-serializable dictionary with enhanced safety and performance.

    This is a security improvement: replaced unsafe pickle with safe JSON serialization.
    Also includes common AST attributes such as 'lineno', 'col_offset', 'end_lineno', and 'end_col_offset'.

    Args:
        node: The AST node to convert
        max_depth: Maximum recursion depth to prevent stack overflow (default: 500)

    Returns:
        A JSON-serializable dictionary representation of the AST

    Raises:
        ValueError: If max_depth is exceeded or invalid input provided
        TypeError: If node is not a valid AST object
    """
    if not isinstance(node, ast.AST):
        raise TypeError(f"Expected ast.AST object, got {type(node).__name__}")

    if max_depth <= 0:
        raise ValueError("max_depth must be positive")

    def _convert_ast_node(n: ast.AST, current_depth: int) -> dict[str, Any]:
        result: dict[str, Any] = {"_ast_type": n.__class__.__name__}
        for field_name in n._fields:
            try:
                value = getattr(n, field_name, None)
                if value is not None:
                    result[field_name] = _convert_node(value, current_depth + 1)
            except Exception as e:
                logger.debug("Failed to serialize field '%s': %s", field_name, e)
                result[field_name] = None
        for attr in ("lineno", "col_offset", "end_lineno", "end_col_offset"):
            if hasattr(n, attr):
                try:
                    result[attr] = getattr(n, attr)
                except Exception as e:
                    logger.debug("Failed to serialize attribute '%s': %s", attr, e)
        return result

    def _handle_depth_exceeded(obj: Any) -> dict[str, Any]:
        return {
            "_truncated": True,
            "_reason": "max_depth_exceeded",
            "_type": type(obj).__name__,
        }

    _convertors: list[tuple[type | tuple[type, ...], Any]] = [
        (ast.AST, _convert_ast_node),
        (list, lambda o, d: [_convert_node(item, d + 1) for item in o]),
        (tuple, lambda o, d: tuple(_convert_node(item, d + 1) for item in o)),
        ((str, int, float, bool), lambda o, d: o),
        (bytes, lambda o, d: o.decode("utf-8", "replace")),
    ]

    def _convert_node(obj: Any, current_depth: int = 0) -> Any:
        if current_depth > max_depth:
            logger.warning("AST conversion exceeded max depth %s, truncating", max_depth)
            return _handle_depth_exceeded(obj)
        for typ, func in _convertors:
            if isinstance(obj, typ):
                return func(obj, current_depth)
        if obj is None:
            return None
        return str(obj)

    return _convert_node(node, 0)


def _dict_to_ast(data: dict[str, Any]) -> ast.AST:
    """
    Convert a dictionary back to an AST node.
    This is a security improvement: replaced unsafe pickle with safe JSON deserialization.
    """

    def _convert_value(obj: Any) -> Any:
        if isinstance(obj, dict) and "_ast_type" in obj:
            ast_type = obj["_ast_type"]
            if hasattr(ast, ast_type):
                cls = getattr(ast, ast_type)
                node = cls()
                valid_fields = getattr(cls, "_fields", ())
                for field_name, value in obj.items():
                    if field_name != "_ast_type" and field_name in valid_fields:
                        setattr(node, field_name, _convert_value(value))
                return node
            raise ValueError(f"Unknown AST node type: {ast_type}")
        if isinstance(obj, list):
            return [_convert_value(item) for item in obj]
        return obj

    return _convert_value(data)


@dataclass
class CacheEntry:
    """Represents a single cache entry with metadata"""

    ast_obj: Any
    timestamp: float = field(default_factory=time.time)
    size_bytes: int = 0
    access_count: int = 0
    last_access: float = field(default_factory=time.time)

    def update_access(self):
        """Update access statistics"""
        self.access_count += 1
        self.last_access = time.time()


class ASTCache:
    """
    Thread-safe cache for AST parsing results with:
    - Configurable eviction policy: LRU (default) or LFU-lite
    - TTL (Time-To-Live) based eviction
    - Size/memory-based limits
    - Persistent disk storage
    - Comprehensive statistics
    """

    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: float | None = None,
        max_memory_mb: float = 100.0,
        persistent_path: str | Path | None = None,
        enable_compression: bool = True,
        eviction_mode: str = "lru",
    ):
        """
        Initialize the AST cache.

        Args:
            max_size: Maximum number of entries to store (default: 100)
            ttl_seconds: Time-to-live for cache entries in seconds
                (None = no TTL)
            max_memory_mb: Maximum memory usage in MB (default: 100.0)
            persistent_path: Path for persistent cache storage
                (None = memory only)
            enable_compression: Enable compression for persistent storage
            eviction_mode: Eviction policy to use: "lru" (default) or "lfu_lite"
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.max_memory_bytes = int(max_memory_mb * 1024 * 1024)
        self.enable_compression = enable_compression
        # Eviction policy
        self.eviction_mode = eviction_mode if eviction_mode in ("lru", "lfu_lite") else "lru"
        # Bound on LFU-lite scan window (first K items of OrderedDict)
        self._lfu_scan_limit = 64

        # Cache storage
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._current_memory_usage = 0

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._ttl_evictions = 0
        self._size_evictions = 0

        # Persistent storage setup
        self.persistent_path = None
        if persistent_path:
            self.persistent_path = Path(persistent_path)
            self._setup_persistent_storage()
            self._load_from_disk()

        # Background cleanup thread
        self._cleanup_thread = None
        self._stop_cleanup = threading.Event()
        if ttl_seconds:
            self._start_cleanup_thread()

    def parse(self, source: str | bytes, filename: str = "<unknown>", mode: str = "exec") -> Any:
        """
        Parse source code into an AST, using the cache when possible.

        Args:
            source: Source code to parse
            filename: Filename to use for error messages
            mode: Parsing mode ('exec', 'eval', or 'single')

        Returns:
            Parsed AST object

        Raises:
            SyntaxError: If the source code contains syntax errors
        """
        # Generate cache key
        cache_key = self._generate_cache_key(source, filename, mode)

        with self._lock:
            # Check if already in cache
            entry = self._get_valid_entry(cache_key)
            if entry:
                # Move to end (most recently used)
                self._cache.move_to_end(cache_key)
                entry.update_access()
                self._hits += 1
                # Telemetry: increment-only cache hit counter.
                # This is effectively free when telemetry is disabled because get_recorder() returns a no-op.
                from pseudocode_translator.telemetry import (  # lazy import to avoid overhead when disabled
                    get_recorder,
                )

                get_recorder().record_event("cache", counters={"hit": 1})  # counters: "hit"
                return entry.ast_obj

            # Not in cache, parse it
            self._misses += 1
            # Telemetry: increment-only cache miss counter.
            # Negligible cost when telemetry is disabled due to no-op recorder.
            from pseudocode_translator.telemetry import (  # lazy import to avoid overhead when disabled
                get_recorder,
            )

            get_recorder().record_event("cache", counters={"miss": 1})  # counters: "miss"

        # Parse outside the lock to avoid blocking
        ast_obj = ast.parse(source, filename, mode)

        # Calculate size
        size_bytes = self._estimate_ast_size(ast_obj)

        # Create cache entry with explicit timestamp to support test-time clock patching
        now_ts = time.time()
        entry = CacheEntry(
            ast_obj=ast_obj, size_bytes=size_bytes, timestamp=now_ts, last_access=now_ts
        )

        # Store in cache
        with self._lock:
            self._add_entry(cache_key, entry)

        return ast_obj

    def get(
        self, source: str | bytes, filename: str = "<unknown>", mode: str = "exec"
    ) -> Any | None:
        """
        Get a cached AST if available, without parsing.

        Args:
            source: Source code
            filename: Filename used when parsing
            mode: Parsing mode used

        Returns:
            Cached AST object if available, None otherwise
        """
        cache_key = self._generate_cache_key(source, filename, mode)

        with self._lock:
            entry = self._get_valid_entry(cache_key)
            if entry:
                # Move to end (most recently used)
                self._cache.move_to_end(cache_key)
                entry.update_access()
                self._hits += 1
                # Telemetry: increment-only cache hit counter (no-op when disabled).
                from pseudocode_translator.telemetry import (  # lazy import to avoid overhead when disabled
                    get_recorder,
                )

                get_recorder().record_event("cache", counters={"hit": 1})  # counters: "hit"
                return entry.ast_obj

            self._misses += 1
            # Telemetry: increment-only cache miss counter (no-op when disabled).
            from pseudocode_translator.telemetry import (  # lazy import to avoid overhead when disabled
                get_recorder,
            )

            get_recorder().record_event("cache", counters={"miss": 1})  # counters: "miss"
            return None

    def put(
        self,
        source: str | bytes,
        ast_obj: Any,
        filename: str = "<unknown>",
        mode: str = "exec",
    ) -> None:
        """
        Store an AST object in the cache.

        Args:
            source: Source code that was parsed
            ast_obj: The parsed AST object
            filename: Filename used when parsing
            mode: Parsing mode used
        """
        cache_key = self._generate_cache_key(source, filename, mode)
        size_bytes = self._estimate_ast_size(ast_obj)

        now_ts = time.time()
        entry = CacheEntry(
            ast_obj=ast_obj, size_bytes=size_bytes, timestamp=now_ts, last_access=now_ts
        )

        with self._lock:
            self._add_entry(cache_key, entry)

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()
            self._current_memory_usage = 0

        # Clear persistent storage if enabled
        if self.persistent_path and self.persistent_path.exists():
            try:
                shutil.rmtree(self.persistent_path)
                self._setup_persistent_storage()
            except Exception as e:
                logger.warning("Failed to clear persistent cache: %s", e)

    def get_stats(self) -> dict[str, Any]:
        """
        Get comprehensive cache statistics.

        Returns:
            Dictionary containing cache statistics
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

            # Calculate average entry size
            avg_entry_size = self._current_memory_usage / len(self._cache) if self._cache else 0

            # Find hottest entries
            hot_entries = sorted(
                self._cache.items(), key=lambda x: x[1].access_count, reverse=True
            )[:5]

            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "ttl_evictions": self._ttl_evictions,
                "size_evictions": self._size_evictions,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hit_rate": round(hit_rate, 2),
                "memory_usage_mb": round(self._current_memory_usage / 1024 / 1024, 2),
                "max_memory_mb": round(self.max_memory_bytes / 1024 / 1024, 2),
                "avg_entry_size_kb": round(avg_entry_size / 1024, 2),
                "ttl_enabled": self.ttl_seconds is not None,
                "ttl_seconds": self.ttl_seconds,
                "persistent_enabled": self.persistent_path is not None,
                "eviction_mode": self.eviction_mode,
                "hot_entries": [
                    {
                        "key": key[:8] + "...",
                        "access_count": entry.access_count,
                        "size_kb": round(entry.size_bytes / 1024, 2),
                    }
                    for key, entry in hot_entries
                ],
            }

    def reset_stats(self) -> None:
        """Reset cache statistics without clearing the cache."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            self._ttl_evictions = 0
            self._size_evictions = 0

    def save_to_disk(self) -> bool:
        """
        Save current cache to disk.

        Returns:
            True if successful, False otherwise
        """
        if not self.persistent_path:
            return False

        try:
            with self._lock:
                # Create temporary file
                temp_file = self.persistent_path / "cache.tmp"

                # Prepare data for serialization
                cache_data = {
                    "version": 1,
                    "entries": {},
                    "stats": {
                        "hits": self._hits,
                        "misses": self._misses,
                        "evictions": self._evictions,
                    },
                }

                # Persist AST nodes directly (format v2): store "ast" instead of legacy "code"
                # This aligns with loader expectations and avoids mismatches.
                for key, entry in self._cache.items():
                    try:
                        # Persist the AST node as JSON-serializable dict (security improvement)
                        # Replaced unsafe pickle with secure JSON serialization
                        cache_data["entries"][key] = {
                            "ast": _ast_to_dict(entry.ast_obj),
                            "timestamp": entry.timestamp,
                            "size_bytes": entry.size_bytes,
                            "access_count": entry.access_count,
                        }
                    except Exception as e:
                        logger.debug("Skipping cache entry %s...: %s", key[:8], e)

                # Save to disk using secure JSON serialization instead of unsafe pickle
                # Security improvement: JSON cannot execute arbitrary code during deserialization
                if self.enable_compression:
                    import gzip

                    gz_file = temp_file.with_suffix(".json.gz")
                    with gzip.open(gz_file, "wt", encoding="utf-8") as gz:
                        json.dump(cache_data, gz, indent=None, separators=(",", ":"))
                    gz_file.rename(self.persistent_path / "cache.json.gz")
                else:
                    with open(temp_file.with_suffix(".json"), "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, indent=None, separators=(",", ":"))
                    temp_file.with_suffix(".json").rename(self.persistent_path / "cache.json")

                logger.info("Saved %d entries to disk", len(cache_data["entries"]))
                return True

        except Exception as e:
            logger.error("Failed to save cache to disk: %s", e)
            return False

    def _setup_persistent_storage(self) -> None:
        """Setup persistent storage directory"""
        if not self.persistent_path:
            return
        try:
            self.persistent_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error("Failed to create persistent cache directory: %s", e)
            self.persistent_path = None

    def _load_from_disk(self) -> None:
        """Load cache from disk if available"""
        if not self.persistent_path:
            return

        cache_file = self.persistent_path / "cache.json"
        if self.enable_compression:
            cache_file = cache_file.with_suffix(".json.gz")

        if not cache_file.exists():
            return

        try:
            # Load using secure JSON deserialization instead of unsafe pickle
            # Security improvement: JSON cannot execute arbitrary code
            if self.enable_compression:
                import gzip

                with gzip.open(cache_file, "rt", encoding="utf-8") as gz:
                    cache_data = json.load(gz)
            else:
                with open(cache_file, encoding="utf-8") as f:
                    cache_data = json.load(f)

            # Restore cache entries
            loaded_count = 0
            for key, data in cache_data.get("entries", {}).items():
                try:
                    # Handle both new JSON-serialized "ast" entries and legacy entries
                    # Security improvement: safe JSON deserialization instead of pickle
                    ast_data = data.get("ast")
                    if ast_data and isinstance(ast_data, dict) and "_ast_type" in ast_data:
                        # New JSON format - deserialize from dict to AST
                        try:
                            ast_obj = _dict_to_ast(ast_data)
                            entry = CacheEntry(
                                ast_obj=ast_obj,
                                timestamp=data["timestamp"],
                                size_bytes=data["size_bytes"],
                                access_count=data["access_count"],
                            )
                        except Exception as e:
                            logger.debug("Failed to deserialize AST for key %s...: %s", key[:8], e)
                            continue
                    elif isinstance(ast_data, ast.AST):
                        # Direct AST object (should not happen with JSON, but handle gracefully)
                        entry = CacheEntry(
                            ast_obj=ast_data,
                            timestamp=data["timestamp"],
                            size_bytes=data["size_bytes"],
                            access_count=data["access_count"],
                        )
                    elif "code" in data:
                        # Legacy incompatible entry (compiled code object) – skip without crashing.
                        logger.debug(
                            "Ignoring legacy 'code' cache entry for key %s...; expecting AST node",
                            key[:8],
                        )
                        continue
                    else:
                        # Unknown entry format – skip quietly.
                        logger.debug("Unknown cache entry format for key %s..., skipping", key[:8])
                        continue

                    # Check if entry is still valid
                    if self._is_entry_valid(entry):
                        self._cache[key] = entry
                        self._current_memory_usage += entry.size_bytes
                        loaded_count += 1

                except Exception as e:
                    logger.debug("Failed to restore cache entry: %s", e)

            # Restore stats
            stats = cache_data.get("stats", {})
            self._hits = stats.get("hits", 0)
            self._misses = stats.get("misses", 0)
            self._evictions = stats.get("evictions", 0)

            logger.info("Loaded %s entries from disk", loaded_count)

        except Exception as e:
            logger.warning("Failed to load cache from disk: %s", e)

    def _add_entry(self, cache_key: str, entry: CacheEntry) -> None:
        """Add an entry to the cache with eviction handling"""
        # Check if we need to evict based on memory (policy-based eviction)
        while self._current_memory_usage + entry.size_bytes > self.max_memory_bytes and self._cache:
            self._evict_one(reason="memory")

        # Check if we need to evict based on count (policy-based eviction)
        while len(self._cache) >= self.max_size:
            self._evict_one(reason="capacity")

        # Add the new entry
        self._cache[cache_key] = entry
        self._cache.move_to_end(cache_key)
        self._current_memory_usage += entry.size_bytes

        # Save to disk if persistent storage is enabled
        if self.persistent_path and len(self._cache) % 10 == 0:
            # Save every 10 entries
            threading.Thread(target=self.save_to_disk, daemon=True).start()

    def _select_victim(self, reason: str) -> tuple[str, CacheEntry] | None:
        """
        Select a victim key/entry for eviction based on the configured policy.
        - For 'lru': choose the oldest (head of OrderedDict)
        - For 'lfu_lite': bounded scan of the head (first K items), choose smallest access_count;
                          tie-break by oldest (iteration order)
        Returns:
            (key, entry) or None if cache is empty.
        """
        if not self._cache:
            return None

        if self.eviction_mode == "lru":
            # Peek the oldest without popping
            key = next(iter(self._cache.keys()))
            return key, self._cache[key]

        # lfu_lite
        limit = min(self._lfu_scan_limit, len(self._cache))
        best_key: str | None = None
        best_entry: CacheEntry | None = None
        best_freq: int | None = None

        for idx, (k, e) in enumerate(self._cache.items()):
            if idx >= limit:
                break
            freq = int(e.access_count)
            if best_freq is None or freq < best_freq:
                best_key = k
                best_entry = e
                best_freq = freq
            # tie-breaker: keep current best (older) when freq equal

        if best_key is None:
            # Fallback safety: evict oldest
            key = next(iter(self._cache.keys()))
            return key, self._cache[key]
        return best_key, best_entry  # type: ignore[return-value]

    def _evict_one(self, reason: str) -> None:
        """Evict a single entry based on policy ('capacity' or 'memory')."""
        sel = self._select_victim(reason=reason)
        if not sel:
            return
        key, _ = sel
        # Pop the selected key (may not be at head; pop by key)
        popped = self._cache.pop(key, None)
        if popped is None:
            return
        self._current_memory_usage -= popped.size_bytes
        self._evictions += 1
        if reason == "memory":
            self._size_evictions += 1

        # Telemetry: record policy-based eviction
        try:
            from pseudocode_translator.telemetry import get_recorder  # lazy import

            get_recorder().record_event(
                "cache.eviction",
                counters={"eviction": 1},
                extra={"policy": self.eviction_mode, "reason": reason},
            )
        except Exception:
            # Never raise from telemetry
            pass

    def _get_valid_entry(self, cache_key: str) -> CacheEntry | None:
        """Get entry if it exists and is still valid"""
        if cache_key not in self._cache:
            return None

        entry = self._cache[cache_key]

        # Check TTL if enabled
        if self.ttl_seconds and self._is_entry_expired(entry):
            # Remove expired entry
            del self._cache[cache_key]
            self._current_memory_usage -= entry.size_bytes
            self._ttl_evictions += 1
            return None

        return entry

    def _is_entry_valid(self, entry: CacheEntry) -> bool:
        """Check if an entry is still valid"""
        return not (self.ttl_seconds and self._is_entry_expired(entry))

    def _is_entry_expired(self, entry: CacheEntry) -> bool:
        """Check if an entry has expired based on TTL"""
        if not self.ttl_seconds:
            return False
        return (time.time() - entry.timestamp) > self.ttl_seconds

    def _cleanup_expired_entries(self) -> None:
        """Remove expired entries (called by background thread)"""
        with self._lock:
            expired_keys = []
            for key, entry in self._cache.items():
                if self._is_entry_expired(entry):
                    expired_keys.append(key)

            for key in expired_keys:
                entry = self._cache.pop(key)
                self._current_memory_usage -= entry.size_bytes
                self._ttl_evictions += 1

    def _start_cleanup_thread(self) -> None:
        """Start background thread for cleaning up expired entries"""

        def cleanup_loop():
            while not self._stop_cleanup.is_set():
                self._cleanup_expired_entries()
                # Check every 60 seconds or 1/10 of TTL, whichever is smaller
                sleep_time = min(60, self.ttl_seconds / 10 if self.ttl_seconds else 60)
                self._stop_cleanup.wait(sleep_time)

        self._cleanup_thread = threading.Thread(
            target=cleanup_loop, daemon=True, name="ASTCache-Cleanup"
        )
        self._cleanup_thread.start()

    def _estimate_ast_size(self, ast_obj: Any) -> int:
        """Estimate the memory size of an AST object"""
        # This is a rough estimation
        # In production, you might want to use sys.getsizeof recursively
        try:
            # Count nodes
            node_count = sum(1 for _ in ast.walk(ast_obj))
            # Estimate ~200 bytes per node (rough average)
            return node_count * 200
        except Exception:
            # Default size if estimation fails
            return 1024

    def _generate_cache_key(self, source: str | bytes, filename: str, mode: str) -> str:
        """Generate a cache key for the given source code and parameters"""
        # Convert source to bytes if necessary
        source_bytes = source.encode("utf-8") if isinstance(source, str) else source

        # Create a hash of the source code and parameters
        hasher = hashlib.sha256()
        hasher.update(source_bytes)
        hasher.update(filename.encode("utf-8"))
        hasher.update(mode.encode("utf-8"))

        return hasher.hexdigest()

    def __len__(self) -> int:
        """Return the current size of the cache"""
        with self._lock:
            return len(self._cache)

    def __contains__(self, source: str | bytes) -> bool:
        """Check if source code is in the cache"""
        cache_key = self._generate_cache_key(source, "<unknown>", "exec")
        with self._lock:
            return cache_key in self._cache and self._get_valid_entry(cache_key) is not None

    def __del__(self):
        """Cleanup when cache is destroyed"""
        # Stop cleanup thread
        if self._cleanup_thread:
            self._stop_cleanup.set()

        # Save to disk one final time
        if self.persistent_path:
            self.save_to_disk()


# Global cache instance with enhanced configuration
_global_cache = ASTCache(
    max_size=500,  # Increased from 100
    ttl_seconds=3600,  # 1 hour TTL
    max_memory_mb=200,  # 200MB memory limit
    persistent_path=None,  # Can be configured by user
)


# Convenience functions that use the global cache
def parse_cached(source: str | bytes, filename: str = "<unknown>", mode: str = "exec") -> Any:
    """
    Parse source code using the global AST cache.

    This is a convenience function that uses a global cache instance.
    For more control, create your own ASTCache instance.

    Args:
        source: Source code to parse
        filename: Filename to use for error messages
        mode: Parsing mode ('exec', 'eval', or 'single')

    Returns:
        Parsed AST object
    """
    return _global_cache.parse(source, filename, mode)


def get_cache_stats() -> dict[str, Any]:
    """Get statistics from the global AST cache."""
    return _global_cache.get_stats()


def clear_cache() -> None:
    """Clear the global AST cache."""
    _global_cache.clear()


def reset_cache_stats() -> None:
    """Reset statistics for the global AST cache."""
    _global_cache.reset_stats()


def configure_global_cache(
    cache: ASTCache,
    max_size: int | None = None,
    ttl_seconds: float | None = None,
    max_memory_mb: float | None = None,
    persistent_path: str | Path | None = None,
    eviction_mode: str | None = None,
) -> ASTCache:
    """
    Configure the global cache instance.

    Args:
        max_size: Maximum number of entries
        ttl_seconds: Time-to-live in seconds
        max_memory_mb: Maximum memory usage in MB
        persistent_path: Path for persistent storage
        eviction_mode: Optional eviction policy ("lru" | "lfu_lite"); if None, keep existing
    """
    # Create new cache with updated configuration
    return ASTCache(
        max_size=max_size or cache.max_size,
        ttl_seconds=(ttl_seconds if ttl_seconds is not None else cache.ttl_seconds),
        max_memory_mb=(max_memory_mb or (cache.max_memory_bytes / 1024 / 1024)),
        persistent_path=persistent_path,
        enable_compression=True,
        eviction_mode=(
            eviction_mode if eviction_mode is not None else getattr(cache, "eviction_mode", "lru")
        ),
    )
