"""RAG package public API.

Provides a stable, lightweight import surface via lazy re-exports to avoid
heavy dependencies at import time. Components are imported on first access.
"""

# pylint: disable=undefined-all-variable  # __all__ exports are provided lazily via __getattr__

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

# Public factory functions (lightweight import)
from .factory import get_context_provider, get_search_engine

# Type-only sentinel for linters; resolved lazily via __getattr__
DefaultContextProvider: Any

__version__ = "1.0.0"

# Public API (lazy-loaded)
__all__ = [
    # Engines and results
    "VectorSearchEngine",
    "OptimizedVectorSearchEngine",
    "SearchResult",
    # Embeddings
    "EmbeddingGenerator",
    "get_embedding_generator",
    # Providers
    "ContextProvider",
    "EnhancedContextProvider",
    "DefaultContextProvider",  # pylint: disable=undefined-all-variable
    # Processing / Monitoring
    "FileProcessor",
    "OptimizedFileProcessor",
    "FileMonitor",
    # Utilities
    "DirectoryValidator",
    "SecureTextExtractor",
    "create_secure_text_extractor",
    "extract_text_secure",
    # Factory
    "get_search_engine",
    "get_context_provider",
]

# Typing-only imports for static analyzers; do not impact runtime lazy loading
if TYPE_CHECKING:
    from .context_provider import ContextProvider
    from .directory_validator import DirectoryValidator
    from .embedding_generator import EmbeddingGenerator, get_embedding_generator
    from .enhanced_context_provider import EnhancedContextProvider
    from .file_monitor import FileMonitor
    from .file_processor import FileProcessor
    from .optimized_file_processor import OptimizedFileProcessor
    from .optimized_vector_search import OptimizedVectorSearchEngine
    from .secure_text_extractor import (
        SecureTextExtractor,
        create_secure_text_extractor,
        extract_text_secure,
    )
    from .vector_search import SearchResult, VectorSearchEngine

# Map public names to (module, attribute)
_EXPORTS: dict[str, tuple[str, str]] = {
    # Engines
    "VectorSearchEngine": ("rag.vector_search", "VectorSearchEngine"),
    "SearchResult": ("rag.vector_search", "SearchResult"),
    "OptimizedVectorSearchEngine": (
        "rag.optimized_vector_search",
        "OptimizedVectorSearchEngine",
    ),
    # Embeddings
    "EmbeddingGenerator": ("rag.embedding_generator", "EmbeddingGenerator"),
    "get_embedding_generator": ("rag.embedding_generator", "get_embedding_generator"),
    # Providers
    "ContextProvider": ("rag.context_provider", "ContextProvider"),
    "EnhancedContextProvider": (
        "rag.enhanced_context_provider",
        "EnhancedContextProvider",
    ),
    # Processing / Monitoring
    "FileProcessor": ("rag.file_processor", "FileProcessor"),
    "OptimizedFileProcessor": (
        "rag.optimized_file_processor",
        "OptimizedFileProcessor",
    ),
    "FileMonitor": ("rag.file_monitor", "FileMonitor"),
    # Utilities
    "DirectoryValidator": ("rag.directory_validator", "DirectoryValidator"),
    "SecureTextExtractor": ("rag.secure_text_extractor", "SecureTextExtractor"),
    "create_secure_text_extractor": (
        "rag.secure_text_extractor",
        "create_secure_text_extractor",
    ),
    "extract_text_secure": ("rag.secure_text_extractor", "extract_text_secure"),
}


def __getattr__(name: str) -> Any:  # PEP 562 lazy loader
    if name == "DefaultContextProvider":
        module = import_module("rag.enhanced_context_provider")
        return module.EnhancedContextProvider

    try:
        module_name, attr = _EXPORTS[name]
    except KeyError as e:
        raise AttributeError(f"module 'rag' has no attribute {name!r}") from e

    module = import_module(module_name)
    return getattr(module, attr)


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
