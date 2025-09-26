"""Configuration validator for the watchdog system.

This module provides validation for watchdog configuration parameters,
ensuring values are within safe ranges and applying sensible defaults
for invalid configurations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

from .logger import Logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = Logger()


class ValidationLevel(Enum):
    """Severity levels for validation issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ValidationRule:
    """Defines a validation rule for a configuration parameter."""

    name: str
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[Any] | None = None
    default_value: Any = None
    required: bool = False
    validator: Callable[[Any, ValidationResult, str], Any] | None = None
    description: str = ""


@dataclass
class ValidationResult:
    """Result of configuration validation."""

    is_valid: bool
    issues: list[tuple[str, ValidationLevel, str]] = field(
        default_factory=lambda: cast("list[tuple[str, ValidationLevel, str]]", [])
    )
    corrected_config: dict[str, Any] = field(default_factory=lambda: cast("dict[str, Any]", {}))

    def add_issue(self, param: str, level: ValidationLevel, message: str):
        """Add a validation issue."""
        self.issues.append((param, level, message))
        if level == ValidationLevel.ERROR:
            self.is_valid = False


class WatchdogConfigValidator:
    """Validates and corrects watchdog configuration parameters."""

    def __init__(self):
        """Initialize validator with default rules."""
        self.rules = self._create_default_rules()

    def _create_default_rules(self) -> dict[str, ValidationRule]:
        """Create default validation rules for watchdog configuration."""
        return {
            # Resource thresholds
            "vram_threshold": ValidationRule(
                name="vram_threshold",
                min_value=50.0,
                max_value=100.0,
                default_value=95.0,
                description="VRAM usage percentage threshold for warnings",
            ),
            "vram_threshold_percent": ValidationRule(
                name="vram_threshold_percent",
                min_value=50.0,
                max_value=100.0,
                default_value=95.0,
                description="Alternative name for VRAM threshold",
            ),
            # Process limits
            "max_processes": ValidationRule(
                name="max_processes",
                min_value=1,
                max_value=20,
                default_value=5,
                description="Maximum allowed DinoAir processes",
            ),
            "max_dinoair_processes": ValidationRule(
                name="max_dinoair_processes",
                min_value=1,
                max_value=20,
                default_value=5,
                description="Alternative name for max processes",
            ),
            # Timing parameters
            "check_interval": ValidationRule(
                name="check_interval",
                min_value=5,
                max_value=300,
                default_value=30,
                description="Seconds between system checks",
            ),
            "check_interval_seconds": ValidationRule(
                name="check_interval_seconds",
                min_value=5,
                max_value=300,
                default_value=30,
                description="Alternative name for check interval",
            ),
            # Safety parameters
            "self_terminate": ValidationRule(
                name="self_terminate",
                allowed_values=[True, False],
                default_value=False,
                description="Whether to perform emergency shutdown",
            ),
            "self_terminate_on_critical": ValidationRule(
                name="self_terminate_on_critical",
                allowed_values=[True, False],
                default_value=False,
                description="Alternative name for self terminate",
            ),
            # Circuit breaker parameters
            "circuit_breaker_config": ValidationRule(
                name="circuit_breaker_config",
                validator=self._validate_circuit_breaker_config,
                default_value={
                    "failure_threshold": 5,
                    "recovery_timeout": 60,
                    "success_threshold": 3,
                    "timeout": 5.0,
                },
                description="Circuit breaker configuration",
            ),
            # Health monitoring
            "health_check_interval": ValidationRule(
                name="health_check_interval",
                min_value=10,
                max_value=600,
                default_value=60,
                description="Seconds between health checks",
            ),
            # Performance tuning
            "metrics_buffer_size": ValidationRule(
                name="metrics_buffer_size",
                min_value=1,
                max_value=1000,
                default_value=10,
                description="Size of the metrics buffer",
            ),
            # CPU threshold
            "cpu_threshold": ValidationRule(
                name="cpu_threshold",
                min_value=50.0,
                max_value=100.0,
                default_value=90.0,
                description="CPU usage percentage threshold for warnings",
            ),
            # RAM threshold
            "ram_threshold": ValidationRule(
                name="ram_threshold",
                min_value=50.0,
                max_value=100.0,
                default_value=90.0,
                description="RAM usage percentage threshold for warnings",
            ),
            # Response time threshold
            "response_time_threshold": ValidationRule(
                name="response_time_threshold",
                min_value=0.1,
                max_value=10.0,
                default_value=2.0,
                description="Maximum allowed response time in seconds",
            ),
            # Max retries
            "max_retries": ValidationRule(
                name="max_retries",
                min_value=0,
                max_value=10,
                default_value=3,
                description="Maximum number of retries for failed operations",
            ),
            # Auto fallback
            "auto_fallback": ValidationRule(
                name="auto_fallback",
                allowed_values=[True, False],
                default_value=True,
                description="Enable automatic fallback on failure",
            ),
            # Fallback delay
            "fallback_delay": ValidationRule(
                name="fallback_delay",
                min_value=0,
                max_value=300,
                default_value=10,
                description="Seconds to wait before fallback",
            ),
        }

    def _check_unknown_params(self, config: dict[str, Any], result: ValidationResult) -> None:
        known_params = set(self.rules.keys())
        for param in config:
            if param not in known_params:
                result.add_issue(
                    param,
                    ValidationLevel.WARNING,
                    f"Unknown configuration parameter '{param}'",
                )

    def _validate_param(
        self,
        param_name: str,
        rule: ValidationRule,
        config: dict[str, Any],
        result: ValidationResult,
        corrected: dict[str, Any],
    ) -> None:
        value = config.get(param_name)

        if rule.required and value is None:
            result.add_issue(
                param_name,
                ValidationLevel.ERROR,
                f"Required parameter '{param_name}' is missing",
            )
            corrected[param_name] = rule.default_value
            return

        if value is None:
            return

        if rule.validator:
            validated_value = rule.validator(value, result, param_name)
            if validated_value != value:
                corrected[param_name] = validated_value
            return

        if rule.allowed_values is not None and value not in rule.allowed_values:
            result.add_issue(
                param_name,
                ValidationLevel.ERROR,
                f"Invalid value '{value}' for parameter '{param_name}'; "
                f"allowed values are {rule.allowed_values}",
            )
            corrected[param_name] = rule.default_value
            return

        if rule.min_value is not None and value < rule.min_value:
            result.add_issue(
                param_name,
                ValidationLevel.ERROR,
                f"Value {value} for '{param_name}' is below minimum {rule.min_value}",
            )
            corrected[param_name] = rule.default_value
            return

        if rule.max_value is not None and value > rule.max_value:
            result.add_issue(
                param_name,
                ValidationLevel.ERROR,
                f"Value {value} for '{param_name}' exceeds maximum {rule.max_value}",
            )
            corrected[param_name] = rule.default_value
            return

    def validate(self, config: dict[str, Any]) -> ValidationResult:
        """
        Validate watchdog configuration.

        Args:
            config: Configuration dictionary to validate

        Returns:
            ValidationResult with validation status and corrected config
        """
        result = ValidationResult(is_valid=True)
        corrected = config.copy()

        self._check_unknown_params(config, result)

        for param_name, rule in self.rules.items():
            self._validate_param(param_name, rule, config, result, corrected)

        # Apply corrections
        result.corrected_config = corrected

        # Log validation results
        if result.issues:
            logger.info(f"Configuration validation found {len(result.issues)} issues")
            for _, level, message in result.issues:
                if level == ValidationLevel.ERROR:
                    logger.error(f"Config validation: {message}")
                elif level == ValidationLevel.WARNING:
                    logger.warning(f"Config validation: {message}")
                else:
                    logger.info(f"Config validation: {message}")

        return result

    def _validate_circuit_breaker_config(
        self, value: Any, result: ValidationResult, param_name: str
    ) -> dict[str, Any]:
        """Validate circuit breaker configuration."""
        default_config = self.rules["circuit_breaker_config"].default_value

        if not isinstance(value, dict):
            result.add_issue(
                param_name,
                ValidationLevel.ERROR,
                f"Circuit breaker config must be a dictionary, got {type(value).__name__}",
            )
            return default_config

        validated: dict[str, Any] = cast("dict[str, Any]", value).copy()

        # Validate individual circuit breaker parameters
        cb_rules: dict[str, tuple[float, float, float]] = {
            "failure_threshold": (1.0, 20.0, 5.0),
            "recovery_timeout": (10.0, 300.0, 60.0),
            "success_threshold": (1.0, 10.0, 3.0),
            "timeout": (0.5, 30.0, 5.0),
        }

        for cb_param, (min_val, max_val, default_val) in cb_rules.items():
            if cb_param in validated:
                cb_value: Any = validated[cb_param]
                if not isinstance(cb_value, int | float):
                    result.add_issue(
                        f"{param_name}.{cb_param}",
                        ValidationLevel.ERROR,
                        f"Invalid type: expected number, got {type(cb_value).__name__}",
                    )
                    validated[cb_param] = default_val
                elif cb_value < min_val:
                    result.add_issue(
                        f"{param_name}.{cb_param}",
                        ValidationLevel.WARNING,
                        f"Value {cb_value} below minimum {min_val}",
                    )
                    validated[cb_param] = min_val
                elif cb_value > max_val:
                    result.add_issue(
                        f"{param_name}.{cb_param}",
                        ValidationLevel.WARNING,
                        f"Value {cb_value} exceeds maximum {max_val}",
                    )
                    validated[cb_param] = max_val
            else:
                # Add missing parameter with default
                validated[cb_param] = default_val

        return validated

    @staticmethod
    def merge_configs(*configs: dict[str, Any]) -> dict[str, Any]:
        """Merge multiple configuration dictionaries.

        Later configs override earlier ones. Common parameter name
        variations are normalized.

        Args:
            *configs: Configuration dictionaries to merge

        Returns:
            Merged configuration dictionary
        """
        merged: dict[str, Any] = {}

        # Parameter name normalization map
        name_map = {
            "vram_threshold_percent": "vram_threshold",
            "max_dinoair_processes": "max_processes",
            "check_interval_seconds": "check_interval",
            "self_terminate_on_critical": "self_terminate",
        }

        for config in configs:
            if not config:
                continue

            for key, value in config.items():
                # Normalize parameter names
                normalized_key = name_map.get(key, key)
                merged[normalized_key] = value

        return merged

    def get_safe_defaults(self) -> dict[str, Any]:
        """Get safe default configuration.

        Returns:
            Dictionary with all safe default values
        """
        defaults: dict[str, Any] = {}

        for param_name, rule in self.rules.items():
            if rule.default_value is not None:
                # Skip alternative parameter names
                if param_name not in [
                    "vram_threshold_percent",
                    "max_dinoair_processes",
                    "check_interval_seconds",
                    "self_terminate_on_critical",
                ]:
                    defaults[param_name] = rule.default_value

        return defaults

    @staticmethod
    def create_config_summary(config: dict[str, Any]) -> str:
        """Create a human-readable configuration summary.

        Args:
            config: Configuration dictionary

        Returns:
            Formatted configuration summary
        """
        lines = ["Watchdog Configuration Summary:", "=" * 40]

        # Group parameters by category
        categories = {
            "Resource Thresholds": ["vram_threshold", "cpu_threshold", "ram_threshold"],
            "Process Management": ["max_processes", "self_terminate"],
            "Timing": [
                "check_interval",
                "health_check_interval",
                "response_time_threshold",
            ],
            "Error Recovery": [
                "circuit_breaker_config",
                "max_retries",
                "auto_fallback",
                "fallback_delay",
            ],
            "Performance": ["metrics_buffer_size"],
        }

        for category, params in categories.items():
            lines.append(f"\n{category}:")
            for param in params:
                if param in config:
                    value = config[param]
                    if isinstance(value, dict):
                        lines.append(f"  {param}:")
                        items_dict: dict[str, Any] = cast("dict[str, Any]", value)
                        for k, v in items_dict.items():
                            lines.append(f"    {k}: {v}")
                    else:
                        lines.append(f"  {param}: {value}")

        return "\n".join(lines)


def validate_watchdog_config(config: dict[str, Any]) -> dict[str, Any]:
    """Convenience function to validate and correct watchdog configuration.

    Args:
        config: Configuration dictionary to validate

    Returns:
        Corrected configuration dictionary
    """
    validator = WatchdogConfigValidator()
    result = validator.validate(config)

    if not result.is_valid:
        logger.warning(
            f"Configuration validation failed with {len(result.issues)} issues. Using corrected values."
        )

    return result.corrected_config
