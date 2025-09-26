"""
Lightweight RAG factory for centralizing provider/engine selection.

- Keeps imports lazy to avoid heavy import costs at module import time
- Defensively falls back to baseline implementations when optimized/enhanced
  variants are unavailable
- Reads feature flags from environment with sensible defaults
"""

from __future__ import annotations

import inspect
import logging
import os
from importlib import import_module
from typing import Any

logger = logging.getLogger(__name__)


def _parse_bool_env(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    v = value.strip().lower()
    if v in {"1", "true", "yes", "y", "on", "t"}:
        return True
    if v in {"0", "false", "no", "n", "off", "f"}:
        return False
    return default


def _filter_kwargs_for_callable(callable_obj: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """
    Filter kwargs to only those accepted by callable_obj's signature.
    Safe-forward only supported parameters to avoid TypeErrors.
    """
    try:
        sig = inspect.signature(callable_obj)
        accepted: dict[str, Any] = {}
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if name in kwargs and (param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)):
                accepted[name] = kwargs[name]
        return accepted
    except (TypeError, AttributeError, ValueError):
        # If inspection fails for any reason, pass through as-is (best effort)
        return kwargs


def get_search_engine(
    user_name: str | None = None,
    optimized: bool | None = None,
    embedding_generator=None,
    cache_size: int = 100,
    cache_ttl: int = 3600,
    enable_caching: bool = True,
    max_workers: int | None = None,
) -> object:
    """
    Create a RAG search engine instance.

    Selection rules:
    - If optimized is None, read env DINOAIR_RAG_USE_OPTIMIZED_ENGINE (truthy/falsy), default True
    - Prefer OptimizedVectorSearchEngine when enabled and importable
    - Fall back to VectorSearchEngine on ImportError or init failure

    Returns:
        Engine instance
    """
    # Determine optimized setting (default True)
    if optimized is None:
        env_val = os.getenv("DINOAIR_RAG_USE_OPTIMIZED_ENGINE")
        use_optimized = _parse_bool_env(env_val, True)
    else:
        use_optimized = bool(optimized)

    if use_optimized:
        try:
            module = import_module("rag.optimized_vector_search")
            OptimizedVectorSearchEngine = module.OptimizedVectorSearchEngine
            init_kwargs = {
                "user_name": user_name,
                "embedding_generator": embedding_generator,
                "cache_size": cache_size,
                "cache_ttl": cache_ttl,
                "enable_caching": enable_caching,
                "max_workers": max_workers,
            }
            init_kwargs = _filter_kwargs_for_callable(
                OptimizedVectorSearchEngine.__init__, init_kwargs
            )
            logger.debug("Creating OptimizedVectorSearchEngine via factory")
            return OptimizedVectorSearchEngine(**init_kwargs)
        except ImportError as e:
            logger.info(
                "OptimizedVectorSearchEngine unavailable, falling back to VectorSearchEngine: %s",
                e,
            )
        except Exception as e:
            logger.warning(
                "OptimizedVectorSearchEngine init failed, falling back to VectorSearchEngine: %s",
                e,
            )

    # Fallback to baseline engine
    try:
        module = import_module("rag.vector_search")
        VectorSearchEngine = module.VectorSearchEngine
        init_kwargs = {
            "user_name": user_name,
            "embedding_generator": embedding_generator,
        }
        init_kwargs = _filter_kwargs_for_callable(VectorSearchEngine.__init__, init_kwargs)
        logger.debug("Creating VectorSearchEngine via factory")
        return VectorSearchEngine(**init_kwargs)
    except Exception as e:
        logger.error("Failed to initialize VectorSearchEngine: %s", e)
        raise


def get_context_provider(
    user_name: str | None = None,
    enhanced: bool | None = None,
    **kwargs,
) -> object:
    """
    Create a RAG context provider instance.

    Selection rules:
    - If enhanced is None, default True
    - Prefer EnhancedContextProvider when enabled and importable
    - Fall back to ContextProvider on ImportError or init failure

    Returns:
        Provider instance
    """
    use_enhanced = True if enhanced is None else bool(enhanced)

    if use_enhanced:
        try:
            module = import_module("rag.enhanced_context_provider")
            EnhancedContextProvider = module.EnhancedContextProvider
            init_kwargs = {"user_name": user_name, **kwargs}
            init_kwargs = _filter_kwargs_for_callable(EnhancedContextProvider.__init__, init_kwargs)
            logger.debug("Creating EnhancedContextProvider via factory")
            return EnhancedContextProvider(**init_kwargs)
        except ImportError as e:
            logger.info(
                "EnhancedContextProvider unavailable, falling back to ContextProvider: %s",
                e,
            )
        except Exception as e:
            logger.warning(
                "EnhancedContextProvider init failed, falling back to ContextProvider: %s",
                e,
            )

    # Fallback to baseline provider
    module = import_module("rag.context_provider")
    ContextProvider = module.ContextProvider
    init_kwargs = {"user_name": user_name, **kwargs}
    init_kwargs = _filter_kwargs_for_callable(ContextProvider.__init__, init_kwargs)
    logger.debug("Creating ContextProvider via factory")
    return ContextProvider(**init_kwargs)
