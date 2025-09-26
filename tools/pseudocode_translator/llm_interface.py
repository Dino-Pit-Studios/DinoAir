"""
LLM Interface module for the Pseudocode Translator

This module manages interaction with language models using the new flexible
model management system. It supports multiple models through a plugin
architecture.

The interface maintains backward compatibility while adding support for:
- Multiple model backends (Qwen, GPT-2, CodeGen, etc.)
- Automatic model selection based on configuration
- Model switching at runtime
- Improved resource management
"""

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.shutdown_protocols import ShutdownMixin

from .config import LLMConfig
from .models.model_initializer import ModelInitializer
from .models.registry import list_available_models

# Avoid importing BaseModel here; use typing.Any for model type to keep imports robust.

# Try to import a concrete ModelManager from the models package with fallbacks
try:
    # common path in this repo
    from .models.manager import ModelManager as _ImportedModelManager
except ImportError:
    try:
        from .models import (
            ModelManager as _ImportedModelManager,  # fallback if models/__init__.py exposes it
        )
    except ImportError:
        _ImportedModelManager = None  # type: ignore[assignment]

# Fallback stub only if we couldn't import a real manager
if _ImportedModelManager is None:

    class _FallbackModelManager:
        """
        Lightweight fallback ModelManager used when the real manager is unavailable.
        Provides minimal stubs so this module can operate in a degraded mode.
        """

        def __init__(self, *args, **kwargs):
            """No-op initialization for fallback manager."""

        def get_model(self, *args, **kwargs):
            return None

        def load_model(self, *args, **kwargs):
            return None

        def unload_model(self, *args, **kwargs):
            return None

        def shutdown(self, *args, **kwargs):
            """No-op shutdown for fallback manager."""

        def close(self, *args, **kwargs):
            """No-op close for fallback manager."""

        def get_memory_usage(self, *args, **kwargs):
            return {}

    ModelManagerRef = _FallbackModelManager
else:
    ModelManagerRef = _ImportedModelManager  # type: ignore[assignment]

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class TranslationCache:
    """Simple cache for translation results"""

    max_size: int = 1000
    ttl_seconds: int = 86400  # 24 hours

    def __post_init__(self):
        self._cache: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        """Get cached translation if available and not expired"""
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl_seconds:
                    return value
                del self._cache[key]
        return None

    def put(self, key: str, value: str):
        """Store translation in cache"""
        with self._lock:
            # Simple LRU: remove oldest if at capacity
            if len(self._cache) >= self.max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]

            self._cache[key] = (value, time.time())

    def clear(self):
        """Clear all cached entries"""
        with self._lock:
            self._cache.clear()


class LLMInterface(ShutdownMixin):
    """
    Handles all LLM operations with caching and optimization

    This class now uses the flexible model management system and supports
    multiple model backends.
    """

    def __init__(self, config: LLMConfig):
        """
        Initialize the LLM interface

        Args:
            config: LLM configuration object
        """
        super().__init__()
        self.config = config
        self.cache = TranslationCache(
            max_size=1000 if config.cache_enabled else 0,
            ttl_seconds=config.cache_ttl_hours * 3600,
        )
        self._model_lock = threading.Lock()
        self._current_model: Any | None = None
        self._model_name: str | None = None

        # Initialize model manager
        manager_config = {
            "model_dir": str(Path(config.model_path).parent),
            "default_model": config.model_type,
            "auto_download": getattr(config, "auto_download", False),
            "max_loaded_models": 1,  # LLMInterface manages one model at a time
            "model_configs": {config.model_type: self._get_model_config()},
        }
        # Use a robust reference that may be a real manager or a fallback; annotate as Any to avoid tight coupling.
        self._manager: Any = ModelManagerRef(manager_config)

        # Validate configuration
        issues = config.validate()
        if issues:
            logger.warning("Configuration issues: %s", ", ".join(issues))

    def _get_model_config(self) -> dict[str, Any]:
        """Convert LLMConfig to model-specific configuration"""
        return {
            "n_ctx": self.config.n_ctx,
            "n_batch": self.config.n_batch,
            "n_threads": self.config.n_threads,
            "n_gpu_layers": self.config.n_gpu_layers,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "top_k": self.config.top_k,
            "repeat_penalty": self.config.repeat_penalty,
            "max_tokens": self.config.max_tokens,
            "seed": -1,
            "validation_level": self.config.validation_level,
        }

    def initialize_model(self, model_name: str | None = None) -> None:
        """
        Initialize the language model

        Args:
            model_name: Optional model name to load (defaults to config)

        Raises:
            FileNotFoundError: If model file doesn't exist
            RuntimeError: If model loading fails
        """
        model_to_load = model_name or self.config.model_type

        # Skip if already initialized
        if ModelInitializer.should_skip_initialization(
            self._current_model, self._model_name, model_to_load
        ):
            return None

        # Determine model path
        model_path = self.config.get_model_path()
        if model_name and model_name != self.config.model_type:
            # Use a different path for different models
            model_dir = model_path.parent.parent / model_name
            model_path = model_dir / f"{model_name}.gguf"

        # Create model configuration
        model_config = {
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "timeout": self.config.timeout,
        }

        # Create and initialize model using shared utility
        try:
            self._current_model = ModelInitializer.create_and_initialize_model(
                model_to_load, model_config, model_path
            )
            self._model_name = model_to_load
            logger.info("LLM Interface initialized with model: %s", model_to_load)
        except Exception as e:
            logger.error("Failed to initialize LLM model '%s': %s", model_to_load, e)
            raise RuntimeError(f"LLM model initialization failed: {e}") from e

        logger.info("Loading model '%s' from: %s", model_to_load, model_path)

        try:
            with self._model_lock:
                # Unload current model if different
                if self._current_model and self._model_name and self._model_name != model_to_load:
                    self._manager.unload_model(self._model_name)

                # Load new model
                self._current_model = self._manager.load_model(model_to_load, model_path)
                self._model_name = model_to_load

                logger.info("Model '%s' loaded successfully", model_to_load)
            return self._current_model

        except Exception as e:
            raise RuntimeError(f"Failed to load model '{model_to_load}': {str(e)}") from e

    def translate(self, instruction: str, context: dict[str, Any] | None = None) -> str:
        """
        Translate an English instruction to Python code

        Args:
            instruction: English instruction to translate
            context: Optional context information (e.g., surrounding code)

        Returns:
            Generated Python code

        Raises:
            RuntimeError: If model is not initialized
        """
        if not self._current_model:
            self.initialize_model()

        # Create cache key
        cache_key = self._create_cache_key(instruction, context)

        # Check cache
        if self.config.cache_enabled:
            cached_result = self.cache.get(cache_key)
            if cached_result:
                logger.debug("Cache hit for instruction")
                return cached_result

        try:
            # Use the model's translate_instruction method
            if self._current_model:
                code = self._current_model.translate_instruction(instruction, context)
            else:
                raise RuntimeError("Model not initialized")

            # Cache result
            if self.config.cache_enabled and code:
                self.cache.put(cache_key, code)

            return code

        except Exception as e:
            logger.error("Translation failed: %s", str(e))
            raise RuntimeError(f"Failed to translate instruction: {str(e)}")

    def batch_translate(self, instructions: list[str]) -> list[str]:
        """
        Translate multiple instructions in batch

        Args:
            instructions: List of English instructions

        Returns:
            List of generated Python code snippets
        """
        if not self._current_model:
            self.initialize_model()

        # Use model's batch_translate if available, otherwise iterate
        if self._current_model and hasattr(self._current_model, "batch_translate"):
            return self._current_model.batch_translate(instructions)

        results = []
        for instruction in instructions:
            try:
                code = self.translate(instruction)
                results.append(code)
            except Exception as e:
                logger.error("Failed to translate: %s... - %s", instruction[:50], str(e))
                results.append(f"# Error: Failed to translate - {str(e)}")

        return results

    def refine_code(self, code: str, error_context: str) -> str:
        """
        Attempt to fix code based on error feedback

        Args:
            code: Code that needs fixing
            error_context: Error message or context

        Returns:
            Refined Python code
        """
        if not self._current_model:
            self.initialize_model()

        try:
            if self._current_model:
                return self._current_model.refine_code(code, error_context)
            return code
        except Exception as e:
            logger.error("Code refinement failed: %s", str(e))
            return code  # Return original code if refinement fails

    def switch_model(self, model_name: str) -> None:
        """
        Switch to a different model

        Args:
            model_name: Name of the model to switch to
        """
        logger.info("Switching from '%s' to '%s'", self._model_name, model_name)
        self.initialize_model(model_name)

        # Clear cache when switching models
        self.cache.clear()

    def list_available_models(self) -> list[str]:
        """
        List all available models

        Returns:
            List of model names
        """
        return list_available_models()

    def get_current_model(self) -> str | None:
        """
        Get the name of the currently loaded model

        Returns:
            Model name or None if no model loaded
        """
        return self._model_name

    def _cleanup_resources(self) -> None:
        """Cleanup model resources and cache during shutdown"""
        logger.info("Shutting down LLM interface")

        with self._model_lock:
            if self._current_model:
                mgr = getattr(self, "_manager", None)
                if mgr:
                    if hasattr(mgr, "shutdown"):
                        try:
                            mgr.shutdown()
                        except Exception as e:
                            logger.debug("Manager.shutdown() failed: %s", e)
                    elif hasattr(mgr, "close"):
                        try:
                            mgr.close()
                        except Exception as e:
                            logger.debug("Manager.close() failed: %s", e)
                self._current_model = None
                self._model_name = None

        # Clear cache
        self.cache.clear()

        logger.info("LLM interface shutdown complete")

    def get_model_info(self) -> dict[str, Any]:
        """Get information about the loaded model"""
        if not self._current_model:
            return {
                "status": "not_initialized",
                "model_name": None,
                "available_models": self.list_available_models(),
            }

        model_info = self._current_model.get_info()
        extra_info: dict[str, Any] = {
            "cache_enabled": self.config.cache_enabled,
            "cache_size": (self.cache.get_cache_size() if self.config.cache_enabled else 0),
        }
        mgr = getattr(self, "_manager", None)
        if mgr and hasattr(mgr, "get_memory_usage"):
            try:
                extra_info["manager_info"] = mgr.get_memory_usage()
            except Exception as e:
                logger.debug("Manager.get_memory_usage() failed: %s", e)
        model_info.update(extra_info)

        return model_info

    def warmup(self):
        """
        Warm up the model with a simple generation
        This can help with initial latency
        """
        if not self._current_model:
            self.initialize_model()

        logger.info("Warming up model...")
        try:
            if self._current_model:
                self._current_model.warmup()
                logger.info("Model warmup complete")
        except Exception as e:
            logger.warning("Warmup failed: %s", e)

    def _create_cache_key(self, instruction: str, context: dict[str, Any] | None) -> str:
        """Create a unique cache key for instruction + context"""
        key_data = {
            "instruction": instruction,
            "context": context or {},
            "model": self._model_name,
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()


# Convenience factory function
def create_llm_interface(
    config_path: str | None = None, model_name: str | None = None
) -> LLMInterface:
    """
    Create an LLM interface with configuration

    Args:
        config_path: Optional path to configuration file
        model_name: Optional model name to override config

    Returns:
        Initialized LLMInterface
    """
    from .config import ConfigManager

    config = ConfigManager.load(config_path)

    # Override model type if specified
    if model_name:
        config.llm.model_type = model_name

    interface = LLMInterface(config.llm)
    interface.initialize_model()

    return interface
