"""
Versioned Configuration Manager for DinoAir
Provides schema validation, clear precedence (env>file>defaults), and centralized configuration management
"""

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import jsonschema
    from jsonschema import Draft7Validator, ValidationError, validate

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    ValidationError = Exception
    Draft7Validator = None

try:
    from ..utils.logger import Logger
except ImportError:
    # Simple fallback logger
    class Logger:
        """Simple fallback logger providing basic logging methods (info, warning, error, debug)."""

        @staticmethod
        def info(msg):
            """No-op fallback logger method."""

        @staticmethod
        def warning(msg):
            """No-op fallback logger method."""

        @staticmethod
        def error(msg):
            """No-op fallback logger method."""

        @staticmethod
        def debug(msg):
            """No-op fallback logger method."""


@dataclass
class ConfigSource:
    """Represents a configuration source with metadata"""

    name: str
    path: Path | None = None
    data: dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # Higher number = higher priority
    loaded: bool = False
    error: str | None = None


@dataclass
class ConfigValue:
    """Represents a configuration value with its source and metadata"""

    value: Any
    source: str
    path: str
    env_var: str | None = None
    default: Any = None
    schema_type: str | None = None


class ConfigurationError(Exception):
    """Configuration-specific exception"""


class SchemaValidationError(ConfigurationError):
    """Schema validation specific exception"""


class VersionedConfigManager:
    """
    Manages application configuration with:
    - Schema validation using JSON Schema
    - Clear precedence: environment > file > defaults
    - Versioned schema files
    - Environment variable mapping
    - Type conversion and validation
    """

    def __init__(
        self,
        schema_path: Path | None = None,
        config_file_path: Path | None = None,
        env_file_path: Path | None = None,
        validate_on_load: bool = True,
    ):
        """
        Initialize the configuration manager

        Args:
            schema_path: Path to schema.json file
            config_file_path: Path to configuration file
            env_file_path: Path to .env file
            validate_on_load: Whether to validate configuration on load
        """
        self.logger = Logger()

        # Set default paths
        base_dir = Path(__file__).parent.parent
        self.schema_path = schema_path or (base_dir / "config" / "schema.json")
        self.config_file_path = config_file_path or (base_dir / "config" / "app_config.json")
        self.env_file_path = env_file_path or (base_dir / ".env")

        # Configuration sources (ordered by priority: lowest to highest)
        # Precedence: environment variables > .env file > config file > defaults
        self.sources: list[ConfigSource] = [
            ConfigSource("defaults", priority=1),
            ConfigSource("file", self.config_file_path, priority=2),
            ConfigSource("env_file", self.env_file_path, priority=3),
            ConfigSource("environment", priority=4),  # Highest priority
        ]

        # Loaded configuration data
        self.schema: dict[str, Any] = {}
        self.merged_config: dict[str, Any] = {}
        self.env_mappings: dict[str, str] = {}  # env_var -> config.path
        self.validate_on_load = validate_on_load

        # Load configuration
        self._load_schema()
        self._extract_env_mappings()
        self._load_all_sources()
        self._merge_configuration()

        if self.validate_on_load:
            self.validate()

    def _load_schema(self) -> None:
        """Load and parse the configuration schema"""
        try:
            if not self.schema_path.exists():
                raise ConfigurationError(f"Schema file not found: {self.schema_path}")

            with open(self.schema_path, encoding="utf-8") as f:
                self.schema = json.load(f)

            # Validate schema format
            if "schema_version" not in self.schema:
                raise ConfigurationError("Schema missing 'schema_version' field")

            self.logger.info(f"Loaded configuration schema v{self.schema['schema_version']}")

        except (OSError, json.JSONDecodeError) as e:
            raise ConfigurationError(f"Failed to load schema: {e}") from e

    def _extract_env_mappings(self) -> None:
        """Extract environment variable mappings from schema"""
        self.env_mappings = {}
        self._extract_env_mappings_recursive(self.schema.get("properties", {}), [])

    def _extract_env_mappings_recursive(self, properties: dict[str, Any], path: list[str]) -> None:
        """Recursively extract environment variable mappings"""
        for key, value in properties.items():
            current_path = path + [key]

            if isinstance(value, dict):
                # Check for env_var mapping
                if "env_var" in value and value["env_var"]:
                    config_path = ".".join(current_path)
                    self.env_mappings[value["env_var"]] = config_path

                # Recurse into nested properties
                if "properties" in value:
                    self._extract_env_mappings_recursive(value["properties"], current_path)

    def _load_all_sources(self) -> None:
        """Load all configuration sources"""
        for source in self.sources:
            try:
                if source.name == "defaults":
                    self._load_defaults(source)
                elif source.name == "file":
                    self._load_file_config(source)
                elif source.name == "environment":
                    self._load_environment_config(source)
                elif source.name == "env_file":
                    self._load_env_file_config(source)

                source.loaded = True
                self.logger.debug(f"Loaded configuration source: {source.name}")

            except Exception as e:
                source.error = str(e)
                self.logger.warning(f"Failed to load {source.name}: {e}")

    def _load_defaults(self, source: ConfigSource) -> None:
        """Extract default values from schema"""
        source.data = self._extract_defaults_recursive(self.schema.get("properties", {}))

    def _extract_defaults_recursive(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Recursively extract default values from schema"""
        defaults = {}

        for key, value in properties.items():
            if isinstance(value, dict):
                if "default" in value:
                    defaults[key] = value["default"]
                elif "properties" in value:
                    # Recurse into nested objects
                    nested_defaults = self._extract_defaults_recursive(value["properties"])
                    if nested_defaults:
                        defaults[key] = nested_defaults

        return defaults

    def _load_file_config(self, source: ConfigSource) -> None:
        """Load configuration from JSON file"""
        if source.path and source.path.exists():
            try:
                with open(source.path, encoding="utf-8") as f:
                    source.data = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                raise ConfigurationError(f"Failed to load config file: {e}") from e

    def _load_environment_config(self, source: ConfigSource) -> None:
        """Load configuration from environment variables"""
        source.data = {}

        for env_var, config_path in self.env_mappings.items():
            if env_var in os.environ:
                raw_value = os.environ[env_var]

                # Convert to appropriate type based on schema
                try:
                    typed_value = self._convert_env_value(raw_value, config_path)
                    self._set_nested_value(source.data, config_path, typed_value)
                except Exception as e:
                    self.logger.warning(f"Failed to convert env var {env_var}: {e}")

    def _load_env_file_config(self, source: ConfigSource) -> None:
        """Load configuration from .env file"""
        source.data = {}

        if source.path and source.path.exists():
            try:
                env_vars = self._parse_env_file(source.path)

                for env_var, config_path in self.env_mappings.items():
                    if env_var in env_vars:
                        raw_value = env_vars[env_var]

                        try:
                            typed_value = self._convert_env_value(raw_value, config_path)
                            self._set_nested_value(source.data, config_path, typed_value)
                        except Exception as e:
                            self.logger.warning(f"Failed to convert .env var {env_var}: {e}")

            except Exception as e:
                raise ConfigurationError(f"Failed to load .env file: {e}") from e

    def _parse_env_file(self, env_path: Path) -> dict[str, str]:
        """Parse .env file and return key-value pairs"""
        env_vars = {}

        # Validate the env file name against a whitelist
        allowed_env_files = {".env", "config.env", "production.env"}
        if env_path.name not in allowed_env_files:
            raise ValueError(f"Invalid environment file: {env_path.name}")

        with open(env_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                if "=" not in line:
                    self.logger.warning(f"Invalid .env line {line_num}: {line}")
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")  # Remove quotes

                env_vars[key] = value

        return env_vars

    def _convert_env_value(self, raw_value: str, config_path: str) -> Any:
        """Convert environment variable string to appropriate type"""
        # Get expected type from schema
        schema_info = self._get_schema_info(config_path)
        expected_type = schema_info.get("type", "string")

        # Boolean conversion
        if expected_type == "boolean":
            return raw_value.lower() in ("true", "1", "yes", "on")

        # Integer conversion
        if expected_type == "integer":
            return int(raw_value)

        # Number (float) conversion
        if expected_type == "number":
            return float(raw_value)

        # Array conversion (JSON format expected)
        if expected_type == "array":
            try:
                return json.loads(raw_value)
            except json.JSONDecodeError:
                # Fallback: split by comma
                return [item.strip() for item in raw_value.split(",") if item.strip()]

        # Object conversion (JSON format expected)
        elif expected_type == "object":
            return json.loads(raw_value)

        # String (default)
        else:
            return raw_value

    def _get_schema_info(self, config_path: str) -> dict[str, Any]:
        """Get schema information for a configuration path"""
        keys = config_path.split(".")
        current = self.schema.get("properties", {})

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
                if "properties" in current:
                    current = current["properties"]
            else:
                return {}

        return current if isinstance(current, dict) else {}

    def _set_nested_value(self, data: dict[str, Any], path: str, value: Any) -> None:
        """Set a nested value in a dictionary using dot notation"""
        keys = path.split(".")
        current = data

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    def _merge_configuration(self) -> None:
        """Merge all configuration sources according to precedence"""
        self.merged_config = {}

        # Sort sources by priority (lowest to highest)
        sorted_sources = sorted(self.sources, key=lambda s: s.priority)

        for source in sorted_sources:
            if source.loaded and source.data:
                self._deep_merge(self.merged_config, source.data)

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> None:
        """Deep merge two dictionaries"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = copy.deepcopy(value)

    def validate(self) -> None:
        """Validate the merged configuration against the schema"""
        if not JSONSCHEMA_AVAILABLE:
            self.logger.warning("jsonschema not available, skipping validation")
            return

        try:
            validate(instance=self.merged_config, schema=self.schema)
            self.logger.info("Configuration validation passed")

        except ValidationError as e:
            error_msg = f"Configuration validation failed: {e.message}"
            if e.absolute_path:
                error_msg += f" at path: {'.'.join(str(p) for p in e.absolute_path)}"

            raise SchemaValidationError(error_msg) from e

    def get(self, path: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation

        Args:
            path: Configuration path (e.g., 'app.name')
            default: Default value if not found

        Returns:
            Configuration value or default
        """
        keys = path.split(".")
        current = self.merged_config

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current

    def get_with_source(self, path: str) -> ConfigValue:
        """
        Get a configuration value with source information

        Args:
            path: Configuration path (e.g., 'app.name')

        Returns:
            ConfigValue with metadata
        """
        value = self.get(path)
        source_name = self._get_value_source(path)
        schema_info = self._get_schema_info(path)

        return ConfigValue(
            value=value,
            source=source_name,
            path=path,
            env_var=schema_info.get("env_var"),
            default=schema_info.get("default"),
            schema_type=schema_info.get("type"),
        )

    def _get_value_source(self, path: str) -> str:
        """Determine which source provided a configuration value"""
        # Check sources in reverse priority order (highest to lowest)
        sorted_sources = sorted(self.sources, key=lambda s: s.priority, reverse=True)

        for source in sorted_sources:
            if source.loaded and self._has_path(source.data, path):
                return source.name

        return "unknown"

    def _has_path(self, data: dict[str, Any], path: str) -> bool:
        """Check if a path exists in a data dictionary"""
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return False

        return True

    def set(self, path: str, value: Any, source: str = "runtime") -> None:
        """
        Set a configuration value

        Args:
            path: Configuration path (e.g., 'app.name')
            value: Value to set
            source: Source name for tracking
        """
        self._set_nested_value(self.merged_config, path, value)

        # Re-validate if enabled
        if self.validate_on_load:
            self.validate()

    def save_config_file(self) -> None:
        """Save current configuration to file (excluding defaults and env)"""
        # Create config file data excluding defaults and environment
        file_config = {}

        # Only include non-default values from file source and runtime changes
        for source in self.sources:
            if source.name in ("file", "runtime") and source.loaded:
                self._deep_merge(file_config, source.data)

        # Ensure directory exists
        self.config_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Save to file
        with open(self.config_file_path, "w", encoding="utf-8") as f:
            json.dump(file_config, f, indent=2, sort_keys=True)

        self.logger.info(f"Configuration saved to {self.config_file_path}")

    def get_schema_version(self) -> str:
        """Get the schema version"""
        return self.schema.get("schema_version", "unknown")

    def list_all_settings(self) -> list[ConfigValue]:
        """List all configuration settings with their metadata"""
        settings = []
        self._collect_settings_recursive(self.schema.get("properties", {}), [], settings)
        return settings

    def _collect_settings_recursive(
        self, properties: dict[str, Any], path: list[str], settings: list[ConfigValue]
    ) -> None:
        """Recursively collect all configuration settings"""
        for key, value in properties.items():
            current_path = path + [key]
            path_str = ".".join(current_path)

            if isinstance(value, dict):
                if "type" in value and value["type"] != "object":
                    # This is a leaf setting
                    config_value = self.get_with_source(path_str)
                    settings.append(config_value)
                elif "properties" in value:
                    # Recurse into nested object
                    self._collect_settings_recursive(value["properties"], current_path, settings)

    def get_env_mappings(self) -> dict[str, str]:
        """Get all environment variable mappings"""
        return self.env_mappings.copy()

    def get_source_info(self) -> list[dict[str, Any]]:
        """Get information about all configuration sources"""
        return [
            {
                "name": source.name,
                "path": str(source.path) if source.path else None,
                "priority": source.priority,
                "loaded": source.loaded,
                "error": source.error,
                "keys_count": len(source.data) if source.data else 0,
            }
            for source in self.sources
        ]


# Create global instance for convenience
_global_config: VersionedConfigManager | None = None


def get_config() -> VersionedConfigManager:
    """Get the global configuration manager instance"""
    return VersionedConfigManager.get_global_instance()


def init_config(
    schema_path: Path | None = None,
    config_file_path: Path | None = None,
    env_file_path: Path | None = None,
    validate_on_load: bool = True,
) -> VersionedConfigManager:
    """Initialize the configuration manager"""
    config_manager = VersionedConfigManager(
        schema_path=schema_path,
        config_file_path=config_file_path,
        env_file_path=env_file_path,
        validate_on_load=validate_on_load,
    )
    return config_manager
