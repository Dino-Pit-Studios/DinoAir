"""
Simplified configuration management for Pseudocode Translator

This module provides a simple, user-friendly configuration system with:
- Sensible defaults that work out of the box
- Clear validation with helpful error messages
- Environment variable support
- Configuration profiles (development, production, testing)
- Simple version handling without complex migrations
"""

import json
import logging
import os
import sys
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

if TYPE_CHECKING:
    from collections.abc import Callable

try:
    from typing import TypedDict
except ImportError:
    from typing import TypedDict

logger = logging.getLogger(__name__)


class ConfigInfo(TypedDict):
    """
    Information about the configuration file including its path,
    existence, version, validation status, issues, and migration requirement.
    """

    path: str
    exists: bool
    version: str
    is_valid: bool
    issues: list[str]
    needs_migration: bool


class ConfigProfile(Enum):
    """Configuration profiles for different use cases"""

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"
    CUSTOM = "custom"


@dataclass
class ModelConfig:
    """Configuration for a specific model"""

    name: str
    enabled: bool = True
    model_path: str | None = None
    temperature: float = 0.3
    max_tokens: int = 1024
    auto_download: bool = False

    def validate(self) -> list[str]:
        """Validate model configuration"""
        errors: list[str] = []

        if not self.name:
            errors.append("Model name cannot be empty")

        if not 0.0 <= self.temperature <= 2.0:
            errors.append(f"Temperature must be between 0.0 and 2.0, got {self.temperature}")

        if not 1 <= self.max_tokens <= 32768:
            errors.append(f"max_tokens must be between 1 and 32768, got {self.max_tokens}")

        return errors


@dataclass
class LLMConfig:
    """Language model configuration"""

    model_type: str = "qwen"
    model_path: str = "./models"
    n_ctx: int = 2048
    n_threads: int = 4
    n_gpu_layers: int = 0
    temperature: float = 0.3
    max_tokens: int = 1024
    # Legacy/deprecated interface support (kept for backward compatibility)
    top_p: float = 0.9
    top_k: int = 40
    n_batch: int = 512
    repeat_penalty: float = 1.1
    cache_enabled: bool = True
    timeout_seconds: int = 30
    models: dict[str, ModelConfig] = field(default_factory=dict)

    # For backward compatibility
    model_file: str = "qwen-7b-q4_k_m.gguf"
    model_configs: dict[str, Any] = field(default_factory=dict)
    available_models: list[str] = field(default_factory=list)
    validation_level: str = "strict"
    cache_size_mb: int = 500
    cache_ttl_hours: int = 24
    auto_download: bool = False
    max_loaded_models: int = 1
    model_ttl_minutes: int = 60

    def __post_init__(self):
        """Initialize with default model if none provided"""
        if not self.models:
            self.models[self.model_type] = ModelConfig(
                name=self.model_type,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

        # Backward compatibility: convert model_configs to models
        if self.model_configs and not self.models:
            for name, cfg in self.model_configs.items():
                if isinstance(cfg, dict):
                    cfg_d = cast("dict[str, Any]", cfg)
                    params_raw = cfg_d.get("parameters")
                    params = (
                        cast("dict[str, Any]", params_raw) if isinstance(params_raw, dict) else {}
                    )
                    self.models[name] = ModelConfig(
                        name=name,
                        enabled=bool(cfg_d.get("enabled", True)),
                        model_path=cast("str | None", cfg_d.get("model_path")),
                        temperature=cast("float", params.get("temperature", self.temperature)),
                        max_tokens=cast("int", params.get("max_tokens", self.max_tokens)),
                        auto_download=bool(cfg_d.get("auto_download", False)),
                    )

    def validate(self, strict: bool = False) -> dict[str, list[str]] | list[str]:
        """
        Validate LLM configuration.

        Returns:
            - Backward-compatible mode (strict=False when called by Config.validate):
              list[str] of errors
            - New structured mode: {"errors": [...], "warnings": [...]}
              when used directly
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Validate basic settings
        if not self.model_type:
            errors.append("model_type cannot be empty")

        if not 512 <= self.n_ctx <= 32768:
            errors.append(f"n_ctx must be between 512 and 32768, got {self.n_ctx}")

        if not 1 <= self.n_threads <= 32:
            errors.append(f"n_threads must be between 1 and 32, got {self.n_threads}")

        if not 0 <= self.n_gpu_layers <= 100:
            errors.append(f"n_gpu_layers must be between 0 and 100, got {self.n_gpu_layers}")

        if not 0.0 <= self.temperature <= 2.0:
            errors.append(f"temperature must be between 0.0 and 2.0, got {self.temperature}")

        if self.timeout_seconds < 0:
            errors.append(f"timeout_seconds must be >= 0, got {self.timeout_seconds}")
        elif self.timeout_seconds == 0:
            warnings.append("timeout_seconds is 0; operations may hang indefinitely")

        # Validate model configurations
        if self.model_type not in self.models:
            errors.append(f"Primary model '{self.model_type}' not found in models configuration")

        for name, model in self.models.items():
            model_errors = model.validate()
            errors.extend([f"Model '{name}': {e}" for e in model_errors])

        result = {"errors": errors, "warnings": warnings}

        # If used in new strict mode via manager, raise on critical invalids
        if strict and errors:
            # Limit the number of errors surfaced in the exception message
            preview = "; ".join(errors[:3])
            # Local import to avoid circular dependency; keep in function scope.
            from .exceptions import ConfigurationError  # local import to avoid cycles

            raise ConfigurationError(f"Invalid LLM configuration: {preview}")

        # Preserve backward compatibility: if called from legacy path without structured handling,
        # return the list of errors
        return result if strict else errors

    def get_model_config(self, model_name: str) -> ModelConfig:
        """Get configuration for a specific model"""
        if model_name not in self.models:
            # Return default config
            return ModelConfig(name=model_name)
        return self.models[model_name]

    def get_model_path(self, model_name: str | None = None) -> Path:
        """Get the full path to a model file (backward compatibility)"""
        name = model_name or self.model_type

        # Check if there's a specific path configured
        if name in self.models:
            model_config = self.models[name]
            if model_config.model_path:
                return Path(model_config.model_path)

        # Use default path structure
        base_path = Path(self.model_path)

        # For backward compatibility with the old structure
        if name == "qwen" and self.model_file:
            return base_path / "qwen-7b" / self.model_file

        # New structure: models/{model_name}/{model_name}.gguf
        return base_path / name / f"{name}.gguf"


@dataclass
class StreamingConfig:
    """Streaming configuration for large files"""

    enabled: bool = True
    enable_streaming: bool = True  # Backward compatibility alias
    chunk_size: int = 4096
    max_memory_mb: int = 100

    # Additional fields for backward compatibility
    auto_enable_threshold: int = 102400
    max_chunk_size: int = 8192
    min_chunk_size: int = 512
    overlap_size: int = 256
    respect_boundaries: bool = True
    max_lines_per_chunk: int = 100
    buffer_compression: bool = True
    eviction_policy: str = "lru"
    max_concurrent_chunks: int = 3
    chunk_timeout: float = 30.0
    enable_backpressure: bool = True
    max_queue_size: int = 10
    progress_callback_interval: float = 0.5
    enable_memory_monitoring: bool = True
    maintain_context_window: bool = True
    context_window_size: int = 1024

    # Adaptive chunking (feature-flagged; default off)
    adaptive_chunking_enabled: bool = False
    adaptive_target_latency_ms: int = 600
    adaptive_min_chunk_size: int = 200
    adaptive_max_chunk_size: int = 2000
    adaptive_hysteresis_pct: float = 0.2
    adaptive_cooldown_chunks: int = 3
    adaptive_smoothing_alpha: float = 0.2
    adaptive_initial_chunk_size: int | None = None

    def __post_init__(self):
        """Handle backward compatibility"""
        if hasattr(self, "enable_streaming"):
            self.enabled = self.enable_streaming

    @staticmethod
    def _validate_range(
        value: int | float,
        name: str,
        error_threshold: int | float,
        warn_range: tuple[int | float, int | float],
        errors: list[str],
        warnings: list[str],
    ) -> None:
        """
        Validate that 'value' is greater than 'error_threshold' and within 'warn_range'.
        Append error messages to 'errors' or warnings to 'warnings' as appropriate.
        """
        if value <= error_threshold:
            errors.append(f"{name} must be > {error_threshold}, got {value}")
        elif not warn_range[0] <= value <= warn_range[1]:
            warnings.append(
                f"{name} should be between {warn_range[0]} and {warn_range[1]}, got {value}"
            )

    @staticmethod
    def _validate_min(
        name: str,
        value: int | float,
        min_value: int | float,
        errors: list[str],
    ) -> None:
        """
        Ensure that 'value' is at least 'min_value'.
        Append an error message to 'errors' if the value is below the minimum.
        """
        if value < min_value:
            errors.append(f"{name} must be >= {min_value}, got {value}")

    def validate(self, strict: bool = False) -> dict[str, list[str]] | list[str]:
        """Validate streaming configuration with warnings and errors."""
        errors: list[str] = []
        warnings: list[str] = []

        self._validate_range(
            self.chunk_size,
            "chunk_size",
            0,
            (512, 65536),
            errors,
            warnings,
        )
        self._validate_range(
            self.max_memory_mb,
            "max_memory_mb",
            0,
            (10, 1000),
            errors,
            warnings,
        )

        self._validate_min("max_concurrent_chunks", self.max_concurrent_chunks, 1, errors)
        self._validate_min("max_queue_size", self.max_queue_size, 0, errors)
        self._validate_min("chunk_timeout", self.chunk_timeout, 0, errors)
        self._validate_min("progress_callback_interval", self.progress_callback_interval, 0, errors)
        self._validate_min("context_window_size", self.context_window_size, 0, errors)

        allowed_evictions = {"lru", "fifo", "none"}
        if self.eviction_policy not in allowed_evictions:
            errors.append(
                f"eviction_policy must be one of {sorted(allowed_evictions)}, "
                f"got '{self.eviction_policy}'"
            )

        if self.adaptive_min_chunk_size <= 0:
            errors.append("adaptive_min_chunk_size must be > 0")

        if self.adaptive_max_chunk_size < self.adaptive_min_chunk_size:
            errors.append("adaptive_max_chunk_size must be >= adaptive_min_chunk_size")
        if self.adaptive_target_latency_ms <= 0:
            errors.append("adaptive_target_latency_ms must be > 0")
        if not 0.0 < self.adaptive_smoothing_alpha <= 1.0:
            errors.append("adaptive_smoothing_alpha must be in (0.0, 1.0]")
        if self.adaptive_cooldown_chunks < 0:
            errors.append("adaptive_cooldown_chunks must be >= 0")
        if self.adaptive_hysteresis_pct < 0.0:
            errors.append("adaptive_hysteresis_pct must be >= 0.0")

        if self.adaptive_hysteresis_pct > 0.5:
            warnings.append("adaptive_hysteresis_pct is high (> 0.5); may reduce responsiveness")
        if (
            self.adaptive_initial_chunk_size is not None
            and not self.adaptive_min_chunk_size
            <= int(self.adaptive_initial_chunk_size)
            <= self.adaptive_max_chunk_size
        ):
            warnings.append(
                "adaptive_initial_chunk_size will be clamped to "
                "[adaptive_min_chunk_size, adaptive_max_chunk_size] at runtime"
            )

        result = {"errors": errors, "warnings": warnings}

        if strict and errors:
            preview = "; ".join(errors[:3])
            # Local import to avoid circular dependency; keep in function scope.
            from .exceptions import ConfigurationError

            raise ConfigurationError(f"Invalid streaming configuration: {preview}")

        return result if strict else errors


@dataclass
class ExecutionConfig:
    """Execution/offload configuration for CPU-heavy operations."""

    # Feature flag and targeting
    process_pool_enabled: bool = False
    process_pool_max_workers: int | None = (
        None  # None -> resolve at runtime to max(2, os.cpu_count() or 2)
    )
    process_pool_target: str = "parse_validate"

    # Task constraints
    process_pool_task_timeout_ms: int = 5000
    process_pool_job_max_chars: int = 50000

    # Process start behavior
    process_pool_start_method: str | None = None  # None -> platform default

    # Retry behavior
    process_pool_retry_on_timeout: bool = True
    process_pool_retry_limit: int = 1

    def validate(self, strict: bool = False) -> dict[str, list[str]] | list[str]:
        """Validate execution configuration with strict errors and soft clamps."""
        errors: list[str] = []
        warnings: list[str] = []

        # Allowed targets
        allowed_targets = {"parse_validate", "parse_only", "validate_only"}
        if self.process_pool_target not in allowed_targets:
            errors.append(
                f"process_pool_target must be one of {sorted(allowed_targets)}, "
                f"got '{self.process_pool_target}'"
            )

        # Timeouts and limits
        if self.process_pool_task_timeout_ms <= 0:
            errors.append(
                f"process_pool_task_timeout_ms must be > 0, got {self.process_pool_task_timeout_ms}"
            )
        if self.process_pool_job_max_chars <= 0:
            errors.append(
                f"process_pool_job_max_chars must be > 0, got {self.process_pool_job_max_chars}"
            )
        if self.process_pool_retry_limit < 0:
            errors.append(
                f"process_pool_retry_limit must be >= 0, got {self.process_pool_retry_limit}"
            )

        # Max workers
        if self.process_pool_max_workers is not None and self.process_pool_max_workers < 1:
            errors.append(
                f"process_pool_max_workers must be >= 1 when set, got "
                f"{self.process_pool_max_workers}"
            )

        result = {"errors": errors, "warnings": warnings}

        if strict and errors:
            # Local import to avoid circular dependency; keep in function scope.
            from .exceptions import ConfigurationError

            preview = "; ".join(errors[:3])
            raise ConfigurationError(f"Invalid execution configuration: {preview}")

        # Backward-compat behavior: return only list[str] when called from legacy path
        return result if strict else errors


@dataclass
class CacheConfig:
    """Cache configuration for ASTCache

    Configuration module for ASTCache used in pseudocode translator.
    This module provides the CacheConfig class for configuring and validating
    cache behavior such as eviction mode, size limits, TTL, memory usage,
    and persistence.
    """

    eviction_mode: str = "lru"  # {"lru","lfu_lite"}
    max_size: int = 500
    ttl_seconds: int | None = 3600
    max_memory_mb: float = 200.0
    persistent_path: str | None = None
    enable_compression: bool = True

    def validate(self, strict: bool = False) -> dict[str, list[str]] | list[str]:
        """Validate cache configuration parameters.

        Args:
            strict (bool): If True, return both errors and warnings as a dict;
                otherwise, return only the list of errors.

        Returns:
            dict[str, list[str]] | list[str]: Validation issues found in the configuration.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if self.eviction_mode not in {"lru", "lfu_lite"}:
            errors.append(
                f"cache.eviction_mode must be one of ['lru', 'lfu_lite'], got '"
                f"{self.eviction_mode}'"
            )
        if self.max_size < 1:
            errors.append(f"cache.max_size must be >= 1, got {self.max_size}")
        if self.ttl_seconds is not None and self.ttl_seconds < 1:
            errors.append(f"cache.ttl_seconds must be None or >= 1, got {self.ttl_seconds}")
        if self.max_memory_mb <= 0:
            errors.append(f"cache.max_memory_mb must be > 0, got {self.max_memory_mb}")

        result = {"errors": errors, "warnings": warnings}
        return result if strict else errors


@dataclass
class Config:
    """Main configuration class"""

    # Core settings
    llm: LLMConfig = field(default_factory=LLMConfig)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)

    # Translation settings
    preserve_comments: bool = True
    preserve_docstrings: bool = True
    use_type_hints: bool = True
    indent_size: int = 4
    max_line_length: int = 88
    max_context_length: int = 2048
    auto_import_common: bool = True

    # Validation settings
    validate_imports: bool = True
    check_undefined_vars: bool = True
    allow_unsafe_operations: bool = False

    # GUI settings (for backward compatibility)
    gui_theme: str = "dark"
    gui_font_size: int = 12
    syntax_highlighting: bool = True

    # Version (for compatibility checking)
    version: str = "3.0"
    _version: str = "3.0"  # Backward compatibility

    def validate(self) -> list[str]:
        """Validate entire configuration (backward-compatible: returns only errors)."""
        errors: list[str] = []

        # Validate nested configs (call in non-strict mode and consume only errors to preserve API)
        llm_res = self.llm.validate(strict=False)
        if isinstance(llm_res, dict):
            errors.extend(llm_res.get("errors", []))
            # warnings intentionally ignored here to preserve legacy behavior
        else:
            errors.extend(llm_res)

        streaming_res = self.streaming.validate(strict=False)
        if isinstance(streaming_res, dict):
            errors.extend(streaming_res.get("errors", []))
        else:
            errors.extend(streaming_res)

        # Cache validation (lenient aggregation)
        cache_res = self.cache.validate(strict=False)
        if isinstance(cache_res, dict):
            errors.extend(cache_res.get("errors", []))
        else:
            errors.extend(cache_res)

        # Execution/offload validation (lenient)
        try:
            exec_res = self.execution.validate(strict=False)
            if isinstance(exec_res, dict):
                errors.extend(exec_res.get("errors", []))
            else:
                errors.extend(exec_res)
        except (AttributeError, ValueError, TypeError):
            # Preserve legacy behavior: never raise from nested section validation here
            pass

        # Validate basic settings
        if self.indent_size not in [2, 4, 8]:
            errors.append(f"indent_size should be 2, 4, or 8, got {self.indent_size}")

        if not 50 <= self.max_line_length <= 120:
            errors.append(
                f"max_line_length should be between 50 and 120, got {self.max_line_length}"
            )

        return errors

    # ---- Private helpers for environment overrides (used only by apply_env_overrides) ----
    def _collect_env_overrides(self, prefix: str) -> dict[str, str]:
        """Collect applicable environment variables for overrides."""
        allowed_keys = {
            "PSEUDOCODE_LLM_MODEL_TYPE",
            "PSEUDOCODE_LLM_TEMPERATURE",
            "PSEUDOCODE_LLM_THREADS",
            "PSEUDOCODE_LLM_GPU_LAYERS",
            "PSEUDOCODE_STREAMING_ENABLED",
            "PSEUDOCODE_STREAMING_CHUNK_SIZE",
            "PSEUDOCODE_VALIDATE_IMPORTS",
            "PSEUDOCODE_CHECK_UNDEFINED_VARS",
            # Adaptive streaming overrides
            "PSEUDOCODE_STREAMING_ADAPTIVE_ENABLED",
            "PSEUDOCODE_STREAMING_ADAPTIVE_TARGET_MS",
            "PSEUDOCODE_STREAMING_ADAPTIVE_MIN_SIZE",
            "PSEUDOCODE_STREAMING_ADAPTIVE_MAX_SIZE",
            "PSEUDOCODE_STREAMING_ADAPTIVE_HYSTERESIS",
            "PSEUDOCODE_STREAMING_ADAPTIVE_COOLDOWN",
            "PSEUDOCODE_STREAMING_ADAPTIVE_ALPHA",
            "PSEUDOCODE_STREAMING_ADAPTIVE_INITIAL",
            # Execution/process pool overrides
            "PSEUDOCODE_EXEC_POOL_ENABLED",
            "PSEUDOCODE_EXEC_POOL_MAX_WORKERS",
            "PSEUDOCODE_EXEC_POOL_TARGET",
            "PSEUDOCODE_EXEC_POOL_TIMEOUT_MS",
            "PSEUDOCODE_EXEC_POOL_JOB_MAX_CHARS",
            "PSEUDOCODE_EXEC_POOL_RETRY_ON_TIMEOUT",
            "PSEUDOCODE_EXEC_POOL_RETRY_LIMIT",
            "PSEUDOCODE_EXEC_POOL_START_METHOD",
            # Cache overrides
            "PSEUDOCODE_CACHE_EVICTION_MODE",
            "PSEUDOCODE_CACHE_MAX_SIZE",
            "PSEUDOCODE_CACHE_TTL_SECONDS",
            "PSEUDOCODE_CACHE_MAX_MEMORY_MB",
            "PSEUDOCODE_CACHE_PERSISTENT_PATH",
            "PSEUDOCODE_CACHE_ENABLE_COMPRESSION",
        }
        overrides: dict[str, str] = {}
        for key in allowed_keys:
            val = os.getenv(key)
            if val is not None:
                overrides[key] = val
        return overrides

    def _normalize_override_key(self, key: str) -> str | None:
        """Map environment variable name to config path."""
        mapping = {
            "PSEUDOCODE_LLM_MODEL_TYPE": "llm.model_type",
            "PSEUDOCODE_LLM_TEMPERATURE": "llm.temperature",
            "PSEUDOCODE_LLM_THREADS": "llm.n_threads",
            "PSEUDOCODE_LLM_GPU_LAYERS": "llm.n_gpu_layers",
            "PSEUDOCODE_STREAMING_ENABLED": "streaming.enabled",
            "PSEUDOCODE_STREAMING_CHUNK_SIZE": "streaming.chunk_size",
            "PSEUDOCODE_VALIDATE_IMPORTS": "validate_imports",
            "PSEUDOCODE_CHECK_UNDEFINED_VARS": "check_undefined_vars",
            # Adaptive streaming overrides
            "PSEUDOCODE_STREAMING_ADAPTIVE_ENABLED": "streaming.adaptive_chunking_enabled",
            "PSEUDOCODE_STREAMING_ADAPTIVE_TARGET_MS": "streaming.adaptive_target_latency_ms",
            "PSEUDOCODE_STREAMING_ADAPTIVE_MIN_SIZE": "streaming.adaptive_min_chunk_size",
            "PSEUDOCODE_STREAMING_ADAPTIVE_MAX_SIZE": "streaming.adaptive_max_chunk_size",
            "PSEUDOCODE_STREAMING_ADAPTIVE_HYSTERESIS": "streaming.adaptive_hysteresis_pct",
            "PSEUDOCODE_STREAMING_ADAPTIVE_COOLDOWN": "streaming.adaptive_cooldown_chunks",
            "PSEUDOCODE_STREAMING_ADAPTIVE_ALPHA": "streaming.adaptive_smoothing_alpha",
            "PSEUDOCODE_STREAMING_ADAPTIVE_INITIAL": "streaming.adaptive_initial_chunk_size",
            # Execution/process pool overrides
            "PSEUDOCODE_EXEC_POOL_ENABLED": "execution.process_pool_enabled",
            "PSEUDOCODE_EXEC_POOL_MAX_WORKERS": "execution.process_pool_max_workers",
            "PSEUDOCODE_EXEC_POOL_TARGET": "execution.process_pool_target",
            "PSEUDOCODE_EXEC_POOL_TIMEOUT_MS": "execution.process_pool_task_timeout_ms",
            "PSEUDOCODE_EXEC_POOL_JOB_MAX_CHARS": "execution.process_pool_job_max_chars",
            "PSEUDOCODE_EXEC_POOL_RETRY_ON_TIMEOUT": "execution.process_pool_retry_on_timeout",
            "PSEUDOCODE_EXEC_POOL_RETRY_LIMIT": "execution.process_pool_retry_limit",
            "PSEUDOCODE_EXEC_POOL_START_METHOD": "execution.process_pool_start_method",
            # Cache overrides
            "PSEUDOCODE_CACHE_EVICTION_MODE": "cache.eviction_mode",
            "PSEUDOCODE_CACHE_MAX_SIZE": "cache.max_size",
            "PSEUDOCODE_CACHE_TTL_SECONDS": "cache.ttl_seconds",
            "PSEUDOCODE_CACHE_MAX_MEMORY_MB": "cache.max_memory_mb",
            "PSEUDOCODE_CACHE_PERSISTENT_PATH": "cache.persistent_path",
            "PSEUDOCODE_CACHE_ENABLE_COMPRESSION": "cache.enable_compression",
        }
        return mapping.get(key)

    def _coerce_override_value(self, path: str, raw: str) -> tuple[bool, Any]:
        """Coerce raw env value to expected type with identical error logging."""

        # Helpers to preserve original warning messages
        def _try_float(val: str, warn_msg: str) -> tuple[bool, Any]:
            """Try to convert a string to a float.
            Returns (True, float) on success.
            Logs warning and returns (False, None) on failure.
            """
            try:
                return True, float(val)
            except ValueError:
                logger.warning(warn_msg)
                return False, None

        def _try_int(val: str, warn_msg: str) -> tuple[bool, Any]:
            """
            Try to convert a string to an integer.

            Returns (True, int) on success; logs warning and
            returns (False, None) on failure.
            """
            try:
                return True, int(val)
            except ValueError:
                logger.warning(warn_msg)
                return False, None

        truthy = ("true", "1", "yes", "on")

        coercers: dict[str, Callable[[str], tuple[bool, Any]]] = {
            "llm.model_type": lambda v: (True, v),
            "llm.temperature": lambda v: _try_float(v, f"Invalid temperature value from env: {v}"),
            "llm.n_threads": lambda v: _try_int(v, f"Invalid threads value from env: {v}"),
            "llm.n_gpu_layers": lambda v: _try_int(v, f"Invalid GPU layers value from env: {v}"),
            "streaming.enabled": lambda v: (True, v.lower() in truthy),
            "streaming.chunk_size": lambda v: _try_int(
                v, f"Invalid chunk size value from env: {v}"
            ),
            "validate_imports": lambda v: (True, v.lower() in truthy),
            "check_undefined_vars": lambda v: (True, v.lower() in truthy),
            # Adaptive streaming overrides
            "streaming.adaptive_chunking_enabled": lambda v: (
                True,
                v.lower() in truthy,
            ),
            "streaming.adaptive_target_latency_ms": lambda v: _try_int(
                v, f"Invalid adaptive target ms from env: {v}"
            ),
            "streaming.adaptive_min_chunk_size": lambda v: _try_int(
                v, f"Invalid adaptive min size from env: {v}"
            ),
            "streaming.adaptive_max_chunk_size": lambda v: _try_int(
                v, f"Invalid adaptive max size from env: {v}"
            ),
            "streaming.adaptive_hysteresis_pct": lambda v: _try_float(
                v, f"Invalid adaptive hysteresis from env: {v}"
            ),
            "streaming.adaptive_cooldown_chunks": lambda v: _try_int(
                v, f"Invalid adaptive cooldown from env: {v}"
            ),
            "streaming.adaptive_smoothing_alpha": lambda v: _try_float(
                v, f"Invalid adaptive alpha from env: {v}"
            ),
            "streaming.adaptive_initial_chunk_size": lambda v: _try_int(
                v, f"Invalid adaptive initial size from env: {v}"
            ),
            # Execution/process pool coercers
            "execution.process_pool_enabled": lambda v: (True, v.lower() in truthy),
            "execution.process_pool_max_workers": lambda v: _try_int(
                v, f"Invalid pool max workers value from env: {v}"
            ),
            "execution.process_pool_target": lambda v: (True, v),
            "execution.process_pool_task_timeout_ms": lambda v: _try_int(
                v, f"Invalid pool timeout ms value from env: {v}"
            ),
            "execution.process_pool_job_max_chars": lambda v: _try_int(
                v, f"Invalid pool job max chars value from env: {v}"
            ),
            "execution.process_pool_retry_on_timeout": lambda v: (
                True,
                v.lower() in truthy,
            ),
            "execution.process_pool_retry_limit": lambda v: _try_int(
                v, f"Invalid pool retry limit value from env: {v}"
            ),
            "execution.process_pool_start_method": lambda v: (True, v),
            # Cache coercers
            "cache.eviction_mode": lambda v: (True, v),
            "cache.max_size": lambda v: _try_int(v, f"Invalid cache max size from env: {v}"),
            "cache.ttl_seconds": lambda v: _try_int(v, f"Invalid cache ttl seconds from env: {v}"),
            "cache.max_memory_mb": lambda v: _try_float(
                v, f"Invalid cache max memory MB from env: {v}"
            ),
            "cache.persistent_path": lambda v: (True, v),
            "cache.enable_compression": lambda v: (True, v.lower() in truthy),
        }

        fn = coercers.get(path)
        return fn(raw) if fn else (False, None)

    def _get_value_by_path(self, path: str) -> Any:
        """Read current config value by dotted path."""
        target: Any = self
        parts = path.split(".")
        for p in parts:
            target = getattr(target, p)
        return target

    def _apply_override(self, path: str, value: Any) -> None:
        """Apply a single override to the nested config structure."""
        target: Any = self
        parts = path.split(".")
        for p in parts[:-1]:
            target = getattr(target, p)
        setattr(target, parts[-1], value)

    def _log_override_effect(self, key: str, old: Any, new: Any) -> None:
        """No-op: original implementation did not log per-override effects."""
        # Intentionally empty to preserve original logging behavior.
        return

    def apply_env_overrides(self):
        """Apply environment variable overrides"""
        overrides_raw = self._collect_env_overrides("PSEUDOCODE_")
        if not overrides_raw:
            return

        for env_key, raw in overrides_raw.items():
            path = self._normalize_override_key(env_key)
            if not path:
                continue
            ok, value = self._coerce_override_value(path, raw)
            if not ok:
                # Either unsupported key or invalid value (warning already logged)
                continue
            old = self._get_value_by_path(path)
            self._apply_override(path, value)
            self._log_override_effect(env_key, old, value)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        # Ensure Path objects are converted to strings
        if "llm" in data and "model_path" in data["llm"]:
            data["llm"]["model_path"] = str(data["llm"]["model_path"])
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create from dictionary"""
        # Handle nested dataclasses
        if "llm" in data and isinstance(data["llm"], dict):
            llm_data = cast("dict[str, Any]", data["llm"])
            models_raw = llm_data.pop("models", {})
            models: dict[str, Any] = (
                cast("dict[str, Any]", models_raw) if isinstance(models_raw, dict) else {}
            )
            data["llm"] = LLMConfig(**llm_data)
            # Recreate model configs
            for name, model_data_raw in models.items():
                if isinstance(model_data_raw, dict):
                    model_data = cast("dict[str, Any]", model_data_raw)
                    data["llm"].models[name] = ModelConfig(**model_data)

        if "streaming" in data and isinstance(data["streaming"], dict):
            streaming_data = cast("dict[str, Any]", data["streaming"])
            data["streaming"] = StreamingConfig(**streaming_data)

        if "execution" in data and isinstance(data["execution"], dict):
            execution_data = cast("dict[str, Any]", data["execution"])
            data["execution"] = ExecutionConfig(**execution_data)

        return cls(**data)


class ConfigManager:
    """Simple configuration manager"""

    DEFAULT_CONFIG_PATH = Path.home() / ".pseudocode_translator" / "config.yaml"

    def __init__(self) -> None:
        """Initialize the configuration manager.

        No state is required at construction time; methods are provided as
        statics/classmethods for convenience, but having an explicit
        constructor improves clarity and tooling compatibility.
        """
        # Intentionally no instance state

    @staticmethod
    def _truthy_env(name: str) -> bool:
        """Return True if the environment variable with the given name is truthy.

        Retrieves the environment variable's value and returns True if it is non-empty
        and its stripped, lowercase representation is one of {"1", "true", "yes", "on"}.
        """
        val = os.getenv(name)
        return bool(val) and val.strip().lower() in {"1", "true", "yes", "on"}

    def _validate_all(self, cfg: Config, strict: bool = False) -> dict[str, list[str]]:
        """
        Aggregate validation across config sections.

        Returns:
            {"errors": [...], "warnings": [...]}
        If strict=True and any errors, raises ConfigurationError.
        """
        all_errors: list[str] = []
        all_warnings: list[str] = []

        # LLM validation
        res_llm = cfg.llm.validate(strict=strict)
        if isinstance(res_llm, dict):
            all_errors.extend(res_llm.get("errors", []))
            all_warnings.extend(res_llm.get("warnings", []))
        else:
            all_errors.extend(res_llm)

        # Streaming validation
        res_stream = cfg.streaming.validate(strict=strict)
        if isinstance(res_stream, dict):
            all_errors.extend(res_stream.get("errors", []))
            all_warnings.extend(res_stream.get("warnings", []))
        else:
            all_errors.extend(res_stream)

        # Execution validation
        res_exec = cfg.execution.validate(strict=strict)
        if isinstance(res_exec, dict):
            all_errors.extend(res_exec.get("errors", []))
            all_warnings.extend(res_exec.get("warnings", []))
        else:
            all_errors.extend(res_exec)

        # Cache validation
        res_cache = cfg.cache.validate(strict=strict)
        if isinstance(res_cache, dict):
            all_errors.extend(res_cache.get("errors", []))
            all_warnings.extend(res_cache.get("warnings", []))
        else:
            all_errors.extend(res_cache)

        # Top-level config constraints
        if cfg.indent_size not in [2, 4, 8]:
            all_errors.append(f"indent_size should be 2, 4, or 8, got {cfg.indent_size}")

        if not 50 <= cfg.max_line_length <= 120:
            all_errors.append(
                f"max_line_length should be between 50 and 120, got {cfg.max_line_length}"
            )

        result = {"errors": all_errors, "warnings": all_warnings}

        if strict and all_errors:
            # Local import to avoid circular dependency; keep in function scope.
            from .exceptions import ConfigurationError

            preview = "; ".join(all_errors[:3])
            raise ConfigurationError(f"Invalid configuration: {preview}")

        return result

    @staticmethod
    def create_profile(profile: ConfigProfile) -> Config:
        """Create configuration from profile"""
        config = Config()

        if profile == ConfigProfile.DEVELOPMENT:
            # Development: Fast iteration, more verbose
            config.llm.temperature = 0.5
            config.llm.n_threads = min((os.cpu_count() or 4), 32)
            config.llm.timeout_seconds = 60
            config.streaming.enabled = True
            config.validate_imports = False  # Faster development

        elif profile == ConfigProfile.PRODUCTION:
            # Production: Stable, optimized
            config.llm.temperature = 0.3
            config.llm.n_gpu_layers = 20  # Use GPU if available
            config.llm.cache_enabled = True
            config.streaming.max_memory_mb = 200
            config.validate_imports = True
            config.check_undefined_vars = True

        elif profile == ConfigProfile.TESTING:
            # Testing: Minimal, fast
            config.llm.n_ctx = 512
            config.llm.max_tokens = 256
            config.llm.timeout_seconds = 10
            config.streaming.enabled = False
            config.llm.cache_enabled = False

        return config

    @staticmethod
    def load(path: str | Path | None = None) -> Config:
        """
        Load configuration from file or create default.

        Precedence: defaults < file < env
        - Build defaults from dataclass defaults
        - Merge file values on top (if file exists)
        - Apply environment variable overrides last (env wins)
        """
        config_path = Path(path) if path else ConfigManager.DEFAULT_CONFIG_PATH

        # 1) Start with defaults
        config = Config()

        # 2) If file exists, merge file values on top of defaults
        if config_path.exists():
            try:
                if "../" in str(config_path) or "..\\" in str(config_path):
                    raise Exception("Invalid file path")
                with open(config_path) as f:
                    if config_path.suffix in [".yaml", ".yml"]:
                        data = yaml.safe_load(f)
                    else:
                        data = json.load(f)

                # Merge by creating from_dict which applies provided values over defaults
                config = Config.from_dict(data)

                # Handle version upgrades
                if "version" not in data or data["version"] != config.version:
                    old_ver = data.get("version", "1.0")
                    logger.info(
                        "Upgrading configuration from version %s to %s", old_ver, config.version
                    )
                    ConfigManager._upgrade_config(config, old_ver)

            except Exception as e:
                logger.error("Failed to load config from %s: %s", config_path, e)
                logger.info("Using default configuration")
        else:
            logger.info("No configuration file found, using defaults")

        # 3) Apply environment overrides last so env always wins
        config.apply_env_overrides()

        # Strictness gating via env flag (lenient opt-out)
        # If PSEUDOCODE_LENIENT_CONFIG in {"1","true","yes"}, downgrade strict to False
        strict_default = not ConfigManager._truthy_env("PSEUDOCODE_LENIENT_CONFIG")

        # Validate and fail-fast on critical invalids
        mgr = ConfigManager()
        result = mgr._validate_all(config, strict=strict_default)

        # Log warnings when present (do not abort on warnings)
        for w in result.get("warnings", []):
            logger.warning("Config warning: %s", w)

        return config

    @staticmethod
    def save(config: Config, path: str | Path | None = None):
        """Save configuration to file."""
        config_path = Path(path) if path else ConfigManager.DEFAULT_CONFIG_PATH

        # Ensure directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Save based on file extension
        if "../" in str(config_path) or "..\\" in str(config_path):
            raise Exception("Invalid file path")
        with open(config_path, "w") as f:
            if config_path.suffix in [".yaml", ".yml"]:
                yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)
            else:
                json.dump(config.to_dict(), f, indent=2)

        logger.info("Configuration saved to %s", config_path)

    @staticmethod
    def _upgrade_config(config: Config, old_version: str):
        """Simple config upgrade logic."""
        # Version 1.0 -> 3.0: Move flat settings to nested structure
        if old_version in {"1.0", "2.0"} and not config.llm.models:
            config.llm.models[config.llm.model_type] = ModelConfig(
                name=config.llm.model_type,
                temperature=config.llm.temperature,
                max_tokens=config.llm.max_tokens,
            )

    @staticmethod
    def create_wizard() -> Config:
        """Interactive configuration wizard with validation and non-interactive safe defaults."""

        def safe_input(prompt: str) -> str:
            """Read user input safely, returning an empty string on EOF or error."""
            with suppress(EOFError):
                return input(prompt)
            return ""

        def _prompt_number(
            prompt: str,
            default,
            parse_fn,
            min_val: float | int | None = None,
            max_val: float | int | None = None,
        ):
            """Prompt the user for a number using default on invalid input and enforce optional bounds."""
            raw = safe_input(prompt).strip()
            if not raw:
                return default
            try:
                val = parse_fn(raw)
            except ValueError:
                return default
            if min_val is not None and val < min_val:
                return min_val
            if max_val is not None and val > max_val:
                return max_val
            return val

        def prompt_int(
            prompt: str,
            default: int,
            min_val: int | None = None,
            max_val: int | None = None,
        ) -> int:
            """Prompt the user for an integer, using default on invalid input and enforcing optional bounds."""
            return _prompt_number(prompt, default, int, min_val, max_val)

        def prompt_float(
            prompt: str,
            default: float,
            min_val: float | None = None,
            max_val: float | None = None,
        ) -> float:
            """Prompt the user for a float, using default on invalid input and enforcing optional bounds."""
            return _prompt_number(prompt, default, float, min_val, max_val)

        def prompt_yes_no(prompt: str, default: bool) -> bool:
            """Prompt the user for a yes/no question, returning True for yes and
            False for no, with a default.
            """
            default_str = "y" if default else "n"
            raw = safe_input(f"{prompt} (y/n) [{default_str}]: ").strip().lower()
            return (raw or default_str).startswith("y")

        # Non-interactive environments: return sensible defaults without prompting
        is_tty = True
        with suppress(Exception):
            is_tty = bool(getattr(sys.stdin, "isatty", lambda: False)())
        if not is_tty:
            return ConfigManager.create_profile(ConfigProfile.DEVELOPMENT)

        # Profile selection

        choice = safe_input("\nEnter choice [1-4] (default: 1): ").strip() or "1"

        profile_map = {
            "1": ConfigProfile.DEVELOPMENT,
            "2": ConfigProfile.PRODUCTION,
            "3": ConfigProfile.TESTING,
            "4": ConfigProfile.CUSTOM,
        }
        profile = profile_map.get(choice, ConfigProfile.DEVELOPMENT)
        config = ConfigManager.create_profile(profile)

        if profile == ConfigProfile.CUSTOM:
            default_model = config.llm.model_type
            model_type_raw = safe_input(f"Model type [{default_model}]: ").strip()
            config.llm.model_type = model_type_raw or default_model

            config.llm.n_threads = prompt_int(
                f"CPU threads [{config.llm.n_threads}] (1-32): ",
                config.llm.n_threads,
                1,
                32,
            )

            config.llm.n_gpu_layers = prompt_int(
                f"GPU layers (0 for CPU only) [{config.llm.n_gpu_layers}] (0-100): ",
                config.llm.n_gpu_layers,
                0,
                100,
            )

            config.llm.temperature = prompt_float(
                f"Temperature (0.0-2.0) [{config.llm.temperature}]: ",
                config.llm.temperature,
                0.0,
                2.0,
            )

        config.use_type_hints = prompt_yes_no("Use type hints?", config.use_type_hints)
        config.validate_imports = prompt_yes_no("Validate imports?", config.validate_imports)

        return config

    @staticmethod
    def get_config_info(config_path: str | None = None) -> dict[str, Any]:
        """Get information about a configuration file"""
        path = Path(config_path or ConfigManager.DEFAULT_CONFIG_PATH)

        info: ConfigInfo = {
            "path": str(path),
            "exists": path.exists(),
            "version": "unknown",
            "is_valid": False,
            "issues": [],
            "needs_migration": False,
        }

        if not path.exists():
            info["issues"].append("Configuration file does not exist")
            return cast("dict[str, Any]", info)

        try:
            if "../" in str(path) or "..\\" in str(path):
                raise Exception("Invalid file path")
            with open(path) as f:
                data = yaml.safe_load(f) if path.suffix in [".yaml", ".yml"] else json.load(f)

            version = data.get("version", data.get("_version", "1.0"))
            info["version"] = version
            info["needs_migration"] = version not in ["3.0"]

            # Try to validate
            config = Config.from_dict(cast("dict[str, Any]", data))
            errors = config.validate()
            info["is_valid"] = len(errors) == 0
            info["issues"].extend(errors)

        except Exception as e:
            info["issues"].append(f"Error loading config: {str(e)}")

        return cast("dict[str, Any]", info)

    @staticmethod
    def create_default_config_file():
        """Create a default configuration file"""
        config = ConfigManager.create_profile(ConfigProfile.DEVELOPMENT)
        ConfigManager.save(config)
        return ConfigManager.DEFAULT_CONFIG_PATH

    @staticmethod
    def add_model_config(
        config: Config,
        model_name: str,
        model_path: str | None = None,
        parameters: dict[str, Any] | None = None,
        auto_download: bool = False,
    ) -> None:
        """Add or update a model configuration"""
        model_config = ModelConfig(
            name=model_name,
            model_path=model_path,
            temperature=(parameters.get("temperature", 0.3) if parameters else 0.3),
            max_tokens=(parameters.get("max_tokens", 1024) if parameters else 1024),
            auto_download=auto_download,
        )
        config.llm.models[model_name] = model_config

    @staticmethod
    def validate(config: Config) -> list[str]:
        """Validate configuration (backward compatibility)"""
        return config.validate()


# Export simplified API
__all__ = [
    "Config",
    "LLMConfig",
    "StreamingConfig",
    "ModelConfig",
    "ConfigManager",
    "ConfigProfile",
]
