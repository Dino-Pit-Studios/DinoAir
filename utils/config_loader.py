"""
Configuration Loader for DinoAir
Handles loading and managing application configuration
"""

import json
import os
from pathlib import Path
from typing import Any, cast

import aiofiles

try:
    from .logger import Logger
except ImportError:
    from logger import Logger


def load_env_file(env_path: Path) -> dict[str, str]:
    """Load environment variables from .env file"""

    env_vars: dict[str, str] = {}
    if env_path.exists():
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        # Remove quotes if present
                        value = value.strip().strip('"').strip("'")
                        env_vars[key.strip()] = value
        except (OSError, UnicodeDecodeError) as e:
            Logger().error(f"Error loading .env file: {e}")
    return env_vars


async def load_env_file_async(env_path: Path) -> dict[str, str]:
    """Load environment variables from .env file asynchronously"""
    env_vars: dict[str, str] = {}
    if env_path.exists():
        try:
            async with aiofiles.open(env_path, encoding="utf-8") as f:
                async for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        # Remove quotes if present
                        value = value.strip().strip('"').strip("'")
                        env_vars[key.strip()] = value
        except (OSError, UnicodeDecodeError) as e:
            Logger().error(f"Error loading .env file: {e}")
    return env_vars


class ConfigLoader:
    """Loads and manages application configuration"""

    def __init__(self, config_path: Path | None = None):
        self.config_path = (
            config_path or Path(__file__).parent.parent.parent / "config" / "app_config.json"
        )
        # DIAGNOSTIC: Log paths for debugging
        Logger().debug(f"ConfigLoader init - config_path: {self.config_path}")

        # FIX: Set env_path relative to config_path directory if custom path provided
        if config_path is not None:
            self.env_path = config_path.parent / ".env"
        else:
            self.env_path = Path(__file__).parent.parent.parent / ".env"

        Logger().debug(f"ConfigLoader init - env_path: {self.env_path}")

        self.config_data: dict[str, Any] = {}
        self.env_vars: dict[str, str] = {}
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from file and environment"""
        # Load .env file first
        self.env_vars = load_env_file(self.env_path)

        try:
            # Always start with defaults
            self.create_default_config(save=False)

            # Merge config file if it exists
            if self.config_path.exists():
                with open(self.config_path, encoding="utf-8") as f:
                    file_config = json.load(f)
                    self._merge_config(file_config)

            # Override with environment variables (highest priority)
            self._apply_env_overrides()

        except (OSError, json.JSONDecodeError) as e:
            Logger().error(f"Error loading config: {e}")
            self.create_default_config(save=False)
            self._apply_env_overrides()

    def _merge_config(self, file_config: dict[str, Any]) -> None:
        """Merge config file data with existing config data (defaults)"""

        def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
            """Deep merge override into base dictionary, handling dicts, lists, and non-dict types"""
            for key, value in override.items():
                if key in base:
                    if isinstance(base[key], dict) and isinstance(value, dict):
                        deep_merge(base[key], value)
                    elif isinstance(base[key], list) and isinstance(value, list):
                        # Merge lists: concatenate and deduplicate, preserving order
                        merged_list = base[key] + [item for item in value if item not in base[key]]
                        base[key] = merged_list
                    else:
                        # For non-dict, non-list types, override
                        base[key] = value
                else:
                    base[key] = value

        deep_merge(self.config_data, file_config)

    async def load_config_async(self) -> None:
        """Load configuration from file and environment asynchronously"""
        # Load .env file first
        self.env_vars = await load_env_file_async(self.env_path)

        try:
            if self.config_path.exists():
                async with aiofiles.open(self.config_path, encoding="utf-8") as f:
                    content = await f.read()
                    self.config_data = json.loads(content)
            else:
                self.create_default_config()

            # Override with environment variables
            self._apply_env_overrides()

        except (OSError, json.JSONDecodeError) as e:
            Logger().error(f"Error loading config: {e}")
            self.create_default_config()

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides to config"""
        env_mappings = {
            "DEBUG": "app.debug",
            "LOG_LEVEL": "logging.level",
            "DISABLE_WATCHDOG": "app.disable_watchdog",
            "DB_TIMEOUT": "database.connection_timeout",
            "DB_HOST": "database.host",
            # AI configuration
            "TEMPERATURE": "ai.temperature",
            "MAX_TOKENS": "ai.max_tokens",
            # LM Studio configuration
            "LMSTUDIO_BASE_URL": "lmstudio.base_url",
            "LMSTUDIO_MODEL": "lmstudio.model",
            "LMSTUDIO_TIMEOUT": "lmstudio.timeout_s",
            "LMSTUDIO_HEADERS": "lmstudio.headers",
            "LMSTUDIO_OPTIONS": "lmstudio.options",
            # Other features
            "ENABLE_PROFANITY_FILTER": "input_processing.enable_profanity_filter",
            "ENABLE_PATTERN_DETECTION": "input_processing.enable_pattern_detection",
            "CACHE_ENABLED": "pseudocode_translator.cache_enabled",
            "ENABLE_DEBUG_SIGNALS": "ui.enable_debug_signals",
        }

        for env_key, config_key in env_mappings.items():
            if env_key in self.env_vars or env_key in os.environ:
                raw_value = self.env_vars.get(env_key, os.environ.get(env_key, ""))
                value: Any = raw_value
                # Convert string values to appropriate types
                lv = raw_value.lower()
                if lv in ("true", "false"):
                    value = lv == "true"
                else:
                    try:
                        value = int(raw_value)
                    except ValueError:
                        try:
                            value = float(raw_value)
                        except ValueError:
                            value = raw_value  # keep as string when not a number
                self.set(config_key, value, save=False)

    def create_default_config(self, save: bool = True) -> None:
        """Create default configuration"""
        self.config_data = {
            "app": {
                "name": "DinoAir 2.0",
                "version": "2.0.0",
                "theme": "light",
                "auto_save": True,
                "backup_interval": 300,
            },
            "database": {
                "backup_on_startup": True,
                "cleanup_interval": 3600,
                "max_backup_files": 10,
            },
            "ai": {"model": "gpt-3.5-turbo", "max_tokens": 2000, "temperature": 0.7},
            "ui": {
                "window_width": 1200,
                "window_height": 800,
                "font_size": 12,
                "show_sidebar": True,
            },
            "async": {
                "enabled": True,
                "file_operations": {
                    "use_async": True,
                    "concurrent_limit": 10,
                },
                "network_operations": {
                    "use_async": True,
                    "timeout": 30.0,
                    "max_concurrent_requests": 5,
                },
                "pdf_processing": {
                    "use_async": True,
                    "timeout": 60.0,
                    "max_concurrent_pages": 3,
                },
            },
            "error_handling": {
                "retry": {
                    "max_attempts": 3,
                    "initial_delay": 1.0,
                    "max_delay": 30.0,
                    "backoff_factor": 2.0,
                    "jitter": True,
                },
                "circuit_breaker": {
                    "failure_threshold": 5,
                    "recovery_timeout": 60.0,
                    "success_threshold": 3,
                    "timeout": 5.0,
                },
                "timeout": {
                    "default_timeout": 10.0,
                },
                "logging": {
                    "log_errors": True,
                    "aggregate_errors": True,
                },
            },
        }
        if save:
            self.save_config()

    def save_config(self) -> None:
        """Save configuration to file"""
        save_json_config(self.config_data, self.config_path)

    async def save_config_async(self) -> None:
        """Save configuration to file asynchronously"""
        await save_json_config_async(self.config_data, self.config_path)
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self.config_path, "w", encoding="utf-8") as f:
                content = json.dumps(self.config_data, indent=4)
                await f.write(content)
        except (OSError, TypeError, ValueError) as e:
            Logger().error(f"Error saving config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'app.name')"""
        keys = key.split(".")
        current: Any = self.config_data

        for k in keys:
            if isinstance(current, dict):
                mapping: dict[str, Any] = cast("dict[str, Any]", current)
                if k in mapping:
                    current = mapping[k]
                else:
                    return default
            else:
                return default

        return current

    def get_env(self, key: str, default: str = "") -> str:
        """Get environment variable value"""
        return self.env_vars.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        """Set configuration value using dot notation"""
        keys = key.split(".")
        config = self.config_data

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value
        if save:
            self.save_config()

    def is_async_enabled(self) -> bool:
        """Check if async operations are enabled globally"""
        return self.get("async.enabled", True)

    def should_use_async_file_ops(self) -> bool:
        """Check if async file operations should be used"""
        return self.get("async.file_operations.use_async", True)

    def should_use_async_network_ops(self) -> bool:
        """Check if async network operations should be used"""
        return self.get("async.network_operations.use_async", True)

    def should_use_async_pdf_processing(self) -> bool:
        """Check if async PDF processing should be used"""
        return self.get("async.pdf_processing.use_async", True)

    def get_async_concurrent_limit(self) -> int:
        """Get the concurrent limit for async file operations"""
        return self.get("async.file_operations.concurrent_limit", 10)

    def get_async_network_timeout(self) -> float:
        """Get the timeout for async network operations"""
        return self.get("async.network_operations.timeout", 30.0)

    def get_async_pdf_timeout(self) -> float:
        """Get the timeout for async PDF processing"""
        return self.get("async.pdf_processing.timeout", 60.0)


def save_json_config(config_data: Any, config_path: Path, indent: int = 4) -> bool:
    """
    Centralized utility for saving configuration data to JSON files.

    Args:
        config_data: Data to save (dict, dataclass, or serializable object)
        config_path: Path where to save the configuration
        indent: JSON indentation level

    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Handle different data types
        if hasattr(config_data, "__dict__"):
            # Convert objects with __dict__ to dict
            data_to_save = config_data.__dict__
        elif hasattr(config_data, "_asdict"):
            # Handle namedtuples
            data_to_save = config_data._asdict()
        else:
            # Assume it's already serializable (dict, etc.)
            data_to_save = config_data

        with config_path.open("w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=indent, default=str)
        return True
    except (OSError, TypeError, ValueError, AttributeError) as e:
        Logger().error(f"Error saving config to {config_path}: {e}")
        return False


async def save_json_config_async(config_data: Any, config_path: Path, indent: int = 4) -> bool:
    """
    Async version of save_json_config.

    Args:
        config_data: Data to save (dict, dataclass, or serializable object)
        config_path: Path where to save the configuration
        indent: JSON indentation level

    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Handle different data types
        if hasattr(config_data, "__dict__"):
            data_to_save = config_data.__dict__
        elif hasattr(config_data, "_asdict"):
            data_to_save = config_data._asdict()
        else:
            data_to_save = config_data

        async with aiofiles.open(config_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data_to_save, indent=indent, default=str))
        return True
    except (OSError, TypeError, ValueError, AttributeError) as e:
        Logger().error(f"Error saving config to {config_path}: {e}")
        return False
