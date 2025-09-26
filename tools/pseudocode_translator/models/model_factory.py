"""
Model Factory for the Pseudocode Translator

This module implements a factory pattern for dynamic model loading,
supporting model registration, discovery, and configuration-based selection.
"""

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .base_model import BaseTranslationModel, OutputLanguage
from .model_info_provider import ModelInfoProvider

logger = logging.getLogger(__name__)


class ModelPriority(Enum):
    """Priority levels for model selection"""

    HIGH = 1
    MEDIUM = 2
    LOW = 3
    FALLBACK = 4


@dataclass
class ModelRegistration:
    """Registration entry for a model"""

    model_class: type[BaseTranslationModel]
    name: str
    aliases: list[str]
    priority: ModelPriority = ModelPriority.MEDIUM
    is_default: bool = False
    config_overrides: dict[str, Any] | None = None

    def __post_init__(self):
        if self.config_overrides is None:
            self.config_overrides = {}


class ModelFactory:
    """
    Factory class for creating and managing translation models

    This class provides:
    - Dynamic model registration and discovery
    - Configuration-based model selection
    - Fallback mechanisms for unavailable models
    - Plugin support
    """

    # Class-level registry
    _registry: dict[str, ModelRegistration] = {}
    _aliases: dict[str, str] = {}
    _initialized: bool = False
    _default_model: str | None = None
    _fallback_chain: list[str] = []

    @classmethod
    def initialize(cls, auto_discover: bool = True) -> None:
        """
        Initialize the factory

        Args:
            auto_discover: Whether to automatically discover models
        """
        if cls._initialized:
            return

        logger.info("Initializing ModelFactory")

        if auto_discover:
            cls.discover_models()

        cls._initialized = True
        logger.info("ModelFactory initialized with %s models", len(cls._registry))

    @classmethod
    def register_model(
        cls,
        model_class: type[BaseTranslationModel],
        name: str | None = None,
        aliases: list[str] | None = None,
        priority: ModelPriority = ModelPriority.MEDIUM,
        is_default: bool = False,
        config_overrides: dict[str, Any] | None = None,
    ) -> None:
        """
        Register a model with the factory

        Args:
            model_class: The model class to register
            name: Optional name override (defaults to class name)
            aliases: Optional list of aliases
            priority: Model priority for selection
            is_default: Whether this is the default model
            config_overrides: Optional config overrides
        """
        # Get model name
        if name is None:
            name = model_class.__name__.lower().replace("model", "")

        # Check if already registered
        if name in cls._registry:
            logger.warning("Model '%s' already registered, overwriting", name)

        # Create registration
        registration = ModelRegistration(
            model_class=model_class,
            name=name,
            aliases=aliases or [],
            priority=priority,
            is_default=is_default,
            config_overrides=config_overrides or {},
        )

        # Register the model
        cls._registry[name] = registration

        # Register aliases
        for alias in registration.aliases:
            cls._aliases[alias] = name

        # Update default if needed
        if is_default or cls._default_model is None:
            cls._default_model = name

        aliases_str = ", ".join(aliases or [])
        logger.info("Registered model: %s (aliases: %s)", name, aliases_str)

    @classmethod
    def unregister_model(cls, name: str) -> None:
        """
        Unregister a model

        Args:
            name: Model name to unregister
        """
        # Resolve alias if needed
        actual_name = cls._aliases.get(name, name)

        if actual_name not in cls._registry:
            logger.warning("Model '%s' not found in registry", name)
            return

        # Get registration for cleanup
        registration = cls._registry[actual_name]

        # Remove from registry
        del cls._registry[actual_name]

        # Remove aliases
        for alias in registration.aliases:
            if alias in cls._aliases:
                del cls._aliases[alias]

        # Update default if needed
        if cls._default_model == actual_name:
            cls._default_model = next(iter(cls._registry.keys()), None)

        logger.info("Unregistered model: %s", actual_name)

    @classmethod
    def create_model(
        cls,
        name: str | None = None,
        config: dict[str, Any] | None = None,
        fallback_enabled: bool = True,
        require_streaming: bool | None = None,
        language: str | None = "python",
    ) -> BaseTranslationModel:
        """
        Create a model instance

        Args:
            name: Model name (uses selection/default if not specified)
            config: Model configuration
            fallback_enabled: Whether to use fallback models
            require_streaming: If True, prefer/require streaming-capable models
            language: Desired output language (case-insensitive), defaults to "python"

        Returns:
            Model instance

        Raises:
            ValueError: If no model found and fallback disabled
        """
        # Initialize if needed
        if not cls._initialized:
            cls.initialize()

        # Determine target model
        if name:
            model_name = name
        else:
            selected = cls._select_model_by_capabilities(
                require_streaming=require_streaming, language=language
            )
            if selected is not None:
                model_name = selected
            else:
                # Fallback to existing default behavior
                model_name = cls._default_model or next(iter(cls._registry.keys()), None)
                if not model_name:
                    raise ValueError("No model name specified and no default set")
                logger.warning(
                    "No models matched requested capabilities (streaming=%s, language=%s); falling back to '%s'",
                    require_streaming,
                    language,
                    model_name,
                )

        # Try to create the requested model
        try:
            return cls._create_model_instance(model_name, config)
        except Exception as e:
            logger.error("Failed to create model '%s': %s", model_name, e)

            if not fallback_enabled:
                raise

            # Try fallback models
            for fallback_name in cls._get_fallback_chain(model_name):
                try:
                    logger.info("Trying fallback model: %s", fallback_name)
                    return cls._create_model_instance(fallback_name, config)
                except Exception as fallback_e:
                    logger.error("Fallback '%s' failed: %s", fallback_name, fallback_e)
                    continue

            raise ValueError(f"No suitable model found (tried {model_name} and fallbacks)")

    @classmethod
    def _create_model_instance(
        cls, name: str, config: dict[str, Any] | None = None
    ) -> BaseTranslationModel:
        """
        Internal method to create a model instance

        Args:
            name: Model name
            config: Model configuration

        Returns:
            Model instance
        """
        # Resolve alias
        actual_name = cls._aliases.get(name, name)

        if actual_name not in cls._registry:
            raise KeyError(f"Model '{name}' not found in registry")

        registration = cls._registry[actual_name]

        # Merge configurations
        final_config = {}
        if registration.config_overrides:
            final_config.update(registration.config_overrides)
        if config:
            final_config.update(config)

        # Create instance
        return registration.model_class(final_config)

    @classmethod
    def list_models(cls, include_aliases: bool = False) -> list[str]:
        """
        List all registered models

        Args:
            include_aliases: Whether to include aliases

        Returns:
            List of model names
        """
        models = list(cls._registry.keys())

        if include_aliases:
            models.extend(cls._aliases.keys())

        return sorted(models)

    @classmethod
    def get_model_info(cls, name: str) -> dict[str, Any]:
        """Get model information using shared provider."""
        return ModelInfoProvider.get_model_info_from_factory(cls, name)

    @classmethod
    def find_models_by_language(cls, language: OutputLanguage) -> list[str]:
        """
        Find models that support a specific output language

        Args:
            language: The output language to check

        Returns:
            List of model names supporting the language
        """
        supporting_models = []

        for name, registration in cls._registry.items():
            try:
                temp_instance = registration.model_class({})
                if temp_instance.metadata.supports_language(language):
                    supporting_models.append(name)
            except Exception as e:
                logger.warning("Error checking language support for %s: %s", name, e)

        return sorted(supporting_models)

    @classmethod
    def set_default_model(cls, name: str) -> None:
        """
        Set the default model

        Args:
            name: Model name to set as default
        """
        # Resolve alias
        actual_name = cls._aliases.get(name, name)

        if actual_name not in cls._registry:
            raise KeyError(f"Model '{name}' not found")

        # Update previous default
        if cls._default_model and cls._default_model in cls._registry:
            cls._registry[cls._default_model].is_default = False

        # Set new default
        cls._default_model = actual_name
        cls._registry[actual_name].is_default = True

        logger.info("Default model set to: %s", actual_name)

    @classmethod
    def set_fallback_chain(cls, models: list[str]) -> None:
        """
        Set the fallback model chain

        Args:
            models: Ordered list of fallback model names
        """
        # Validate all models exist
        for model in models:
            actual_name = cls._aliases.get(model, model)
            if actual_name not in cls._registry:
                raise KeyError(f"Model '{model}' not found")

        cls._fallback_chain = models
        logger.info("Fallback chain set to: %s", ", ".join(models))

    @classmethod
    def _get_fallback_chain(cls, failed_model: str) -> list[str]:
        """
        Get fallback models for a failed model

        Args:
            failed_model: The model that failed

        Returns:
            List of fallback model names
        """
        # Use configured fallback chain if available
        if cls._fallback_chain:
            return [m for m in cls._fallback_chain if m != failed_model]

        # Otherwise, build chain based on priority
        fallbacks = []

        # Get failed model priority (if it exists in registry)
        if failed_model in cls._registry:
            failed_priority = cls._registry[failed_model].priority
        else:
            # If model not in registry, we should try all available models
            # starting with the best priority
            failed_priority = ModelPriority.FALLBACK  # Worst priority to include all

        # Sort models by priority
        sorted_models = sorted(cls._registry.items(), key=lambda x: (x[1].priority.value, x[0]))

        # Add models with same or better priority
        for name, registration in sorted_models:
            if name != failed_model and registration.priority.value <= failed_priority.value:
                fallbacks.append(name)

        return fallbacks

    @classmethod
    def _select_model_by_capabilities(
        cls, require_streaming: bool | None, language: str | None
    ) -> str | None:
        """
        Select the best model from the registry based on normalized capability metadata.

        Args:
            require_streaming: If True, only consider streaming-capable models
            language: Desired output language (string)

        Returns:
            Selected model name or None if no match
        """
        if not cls._registry:
            return None

        desired_lang = (language or "python").lower()
        candidates: list[tuple[int, int, float, str]] = []

        for name, reg in cls._registry.items():
            caps = cls._extract_capabilities(reg)
            if not cls._matches_language(caps, desired_lang):
                continue
            if require_streaming and not cls._supports_streaming(caps):
                continue

            streaming_match = 1 if (require_streaming and cls._supports_streaming(caps)) else 0
            quality_score = cls._get_quality_score(caps)
            tps_max = cls._get_tps_max(caps)

            candidates.append((streaming_match, quality_score, tps_max, name))

        if candidates:
            return max(candidates)[3]
        return None

    @classmethod
    def _extract_capabilities(cls, reg) -> dict:
        temp = reg.model_class({})
        return temp.get_capabilities() or {}

    @classmethod
    def _supports_streaming(cls, caps: dict) -> bool:
        return bool(caps.get("supports_streaming", False))

    @classmethod
    def _matches_language(cls, caps: dict, desired_lang: str) -> bool:
        if not desired_lang:
            return True
        langs = [str(l).lower() for l in caps.get("supported_languages", [])]
        return not langs or desired_lang in langs

    @classmethod
    def _get_quality_score(cls, caps: dict) -> int:
        quality_rank = {"pro": 3, "base": 2, "mock": 1}
        quality = str(caps.get("quality", "")).lower()
        return quality_rank.get(quality, 0)

    @classmethod
    def _get_tps_max(cls, caps: dict) -> float:
        tps = caps.get("tokens_per_second")
        if isinstance(tps, (list, tuple)) and len(tps) >= 2:
            try:
                return float(max(tps[0], tps[1]))
            except Exception:
                return 0.0
        if isinstance(tps, (int, float)):
            return float(tps)
        return 0.0

    @classmethod
    def discover_models(cls, package_path: Path | None = None) -> int:
        """
        Discover and register models from a package

        Args:
            package_path: Path to models package (uses current package if None)

        Returns:
            Number of models discovered
        """
        if package_path is None:
            package_path = Path(__file__).parent

        discovered_count = 0

        # Skip these modules
        skip_modules = {"base_model", "model_factory", "plugin_system", "__init__"}

        logger.info("Discovering models in: %s", package_path)

        for _finder, module_name, ispkg in pkgutil.iter_modules([str(package_path)]):
            if module_name in skip_modules or ispkg:
                continue

            try:
                # Import the module
                module = importlib.import_module(
                    f".{module_name}", package="pseudocode_translator.models"
                )

                # Look for BaseTranslationModel subclasses
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseTranslationModel)
                        and attr != BaseTranslationModel
                    ):
                        # Check if it has a register decorator or auto-register
                        if not cls._is_model_registered(attr):
                            cls.register_model(attr)

                        discovered_count += 1

            except Exception as e:
                logger.warning("Failed to import model module '%s': %s", module_name, e)

        logger.info("Discovered %d models", discovered_count)
        return discovered_count

    @classmethod
    def _is_model_registered(cls, model_class: type[BaseTranslationModel]) -> bool:
        """Check if a model class is already registered"""
        return any(
            registration.model_class == model_class for registration in cls._registry.values()
        )

    @classmethod
    def validate_configuration(
        cls, model_name: str, config: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """
        Validate a configuration for a specific model

        Args:
            model_name: Model name
            config: Configuration to validate

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        try:
            # Create temporary instance
            model = cls._create_model_instance(model_name, config)

            # Let model validate its own config
            if hasattr(model, "validate_config"):
                from .base_model import TranslationConfig

                # Create a translation config from dict
                translation_config = TranslationConfig(**config)
                issues = model.validate_config(translation_config)
                return len(issues) == 0, issues

            return True, []

        except Exception as e:
            return False, [f"Failed to validate: {str(e)}"]

    @classmethod
    def clear_registry(cls) -> None:
        """Clear all registered models (mainly for testing)"""
        cls._registry.clear()
        cls._aliases.clear()
        cls._default_model = None
        cls._fallback_chain = []
        cls._initialized = False
        logger.info("Model registry cleared")


# Decorator for model registration
def register_model(
    name: str | None = None,
    aliases: list[str] | None = None,
    priority: ModelPriority = ModelPriority.MEDIUM,
    is_default: bool = False,
    config_overrides: dict[str, Any] | None = None,
):
    """
    Decorator to register a model with the factory

    Usage:
        @register_model(name="my_model", aliases=["mymodel", "mm"])
        class MyModel(BaseTranslationModel):
            ...

    Args:
        name: Optional model name
        aliases: Optional list of aliases
        priority: Model priority
        is_default: Whether this is the default model
        config_overrides: Optional config overrides

    Returns:
        Decorator function
    """

    def decorator(
        model_class: type[BaseTranslationModel],
    ) -> type[BaseTranslationModel]:
        ModelFactory.register_model(
            model_class,
            name=name,
            aliases=aliases,
            priority=priority,
            is_default=is_default,
            config_overrides=config_overrides,
        )
        return model_class

    return decorator


# Convenience functions
def create_model(
    name: str | None = None,
    config: dict[str, Any] | None = None,
    require_streaming: bool | None = None,
    language: str | None = "python",
) -> BaseTranslationModel:
    """
    Create a model instance

    Args:
        name: Model name (uses selection/default if not specified)
        config: Model configuration
        require_streaming: If True, prefer/require streaming-capable models
        language: Desired output language (defaults to "python")

    Returns:
        Model instance
    """
    return ModelFactory.create_model(
        name=name,
        config=config,
        fallback_enabled=True,
        require_streaming=require_streaming,
        language=language,
    )


def list_available_models() -> list[str]:
    """Get list of available model names"""
    return ModelFactory.list_models()


def get_default_model() -> str | None:
    """Get the default model name"""
    return ModelFactory.get_default_model()


# Initialize factory on import
ModelFactory.initialize(auto_discover=False)
