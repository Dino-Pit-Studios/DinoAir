"""
Model registry system for the Pseudocode Translator

This module provides a plugin-based registry for language models, allowing
dynamic discovery and registration of model implementations.
"""

import logging
from pathlib import Path
from typing import Any

from .base import BaseModel
from .model_info_provider import ModelInfoProvider

logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Central registry for all available language models

    This class manages model registration, discovery, and instantiation.
    Models can be registered using the @register_model decorator or
    by calling register() directly.
    """

    _models: dict[str, type[BaseModel]] = {}
    _aliases: dict[str, str] = {}

    @classmethod
    def register(
        cls,
        model_class: type[BaseModel],
        name: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        """
        Register a model class

        Args:
            model_class: The model class to register
            name: Optional name override (defaults to class name)
            aliases: Optional list of aliases for the model

        Raises:
            ValueError: If model is already registered
        """
        if not issubclass(model_class, BaseModel):
            raise ValueError(f"{model_class.__name__} must inherit from BaseModel")

        # Get model name
        model_name = name or model_class.__name__.lower()

        # Check if already registered
        if model_name in cls._models:
            existing = cls._models[model_name]
            if existing != model_class:
                raise ValueError(f"Model '{model_name}' already registered as {existing.__name__}")
            return  # Same class, skip re-registration

        # Register the model
        cls._models[model_name] = model_class
        logger.info("Registered model: %s", model_name)

        # Register aliases
        if aliases:
            for alias in aliases:
                if alias in cls._aliases and cls._aliases[alias] != model_name:
                    logger.warning(
                        "Alias '%s' already points to '%s', skipping", alias, cls._aliases[alias]
                    )
                else:
                    cls._aliases[alias] = model_name
                    logger.debug("Registered alias '%s' -> '%s'", alias, model_name)

    @classmethod
    def unregister(cls, name: str) -> None:
        """
        Unregister a model

        Args:
            name: Model name to unregister
        """
        # Resolve alias if needed
        actual_name = cls._aliases.get(name, name)

        if actual_name in cls._models:
            del cls._models[actual_name]
            logger.info("Unregistered model: %s", actual_name)

            # Remove associated aliases
            aliases_to_remove = [
                alias for alias, target in cls._aliases.items() if target == actual_name
            ]
            for alias in aliases_to_remove:
                del cls._aliases[alias]

    @classmethod
    def get_model_class(cls, name: str) -> type[BaseModel]:
        """
        Get a model class by name

        Args:
            name: Model name or alias

        Returns:
            The model class

        Raises:
            KeyError: If model not found
        """
        # Resolve alias if needed
        actual_name = cls._aliases.get(name, name)

        if actual_name not in cls._models:
            available = ", ".join(sorted(cls._models.keys()))
            raise KeyError(f"Model '{name}' not found. Available models: {available}")

        return cls._models[actual_name]

    @classmethod
    def create_model(cls, name: str, config: dict) -> BaseModel:
        """
        Create a model instance

        Args:
            name: Model name or alias
            config: Model configuration

        Returns:
            Instantiated model
        """
        model_class = cls.get_model_class(name)
        return model_class(config)

    @classmethod
    def list_models(cls) -> list[str]:
        """
        List all registered model names

        Returns:
            List of model names
        """
        return sorted(cls._models.keys())

    @classmethod
    def list_aliases(cls) -> dict[str, str]:
        """
        List all model aliases

        Returns:
            Dictionary mapping aliases to model names
        """
        return dict(cls._aliases)

    @classmethod
    def get_model_info(cls, name: str) -> dict[str, Any]:
        """Get model information using shared provider."""
        return ModelInfoProvider.get_model_info_from_registry(cls, name)

    @classmethod
    def get_all_models_info(cls) -> dict[str, dict]:
        """
        Get information about all registered models

        Returns:
            Dictionary mapping model names to their info
        """
        return {name: cls.get_model_info(name) for name in cls.list_models()}

    @classmethod
    def find_models_by_capability(
        cls,
        language: str | None = None,
        min_context: int | None = None,
        supports_gpu: bool | None = None,
        max_memory_gb: float | None = None,
    ) -> list[str]:
        """
        Find models matching specific capabilities

        Args:
            language: Required language support
            min_context: Minimum context length
            supports_gpu: GPU support requirement
            max_memory_gb: Maximum memory requirement

        Returns:
            List of model names matching criteria
        """
        matching_models = []

        for name, model_class in cls._models.items():
            try:
                # Create temporary instance
                temp = model_class({})
                caps = temp.capabilities

                # Check criteria
                if language and language not in caps.supported_languages:
                    continue

                if min_context and caps.max_context_length < min_context:
                    continue

                if supports_gpu is not None and caps.supports_gpu != supports_gpu:
                    continue

                if max_memory_gb and caps.min_memory_gb > max_memory_gb:
                    continue

                matching_models.append(name)

            except Exception as e:
                logger.warning("Error checking capabilities for %s: %s", name, e)

        return sorted(matching_models)

    @classmethod
    def clear(cls) -> None:
        """Clear all registered models (mainly for testing)"""
        cls._models.clear()
        cls._aliases.clear()


def register_model(name: str | None = None, aliases: list[str] | None = None):
    """
    Decorator to register a model class

    Usage:
        @register_model()
        class MyModel(BaseModel):
            ...

        @register_model(name="custom_name", aliases=["alias1", "alias2"])
        class AnotherModel(BaseModel):
            ...

    Args:
        name: Optional custom name for the model
        aliases: Optional list of aliases

    Returns:
        Decorator function
    """

    def decorator(model_class: type[BaseModel]) -> type[BaseModel]:
        ModelRegistry.register(model_class, name, aliases)
        return model_class

    return decorator


# Convenience functions
def get_model(name: str, config: dict | None = None) -> BaseModel:
    """
    Get a model instance by name

    Args:
        name: Model name or alias
        config: Model configuration (optional)

    Returns:
        Model instance
    """
    return ModelRegistry.create_model(name, config or {})


def list_available_models() -> list[str]:
    """Get list of available model names"""
    return ModelRegistry.list_models()


def model_exists(name: str) -> bool:
    """Check if a model is registered"""
    try:
        ModelRegistry.get_model_class(name)
        return True
    except KeyError:
        return False


# Auto-discovery helper
def discover_models(package_path: Path) -> int:
    """
    Discover and import all model modules in a package

    Args:
        package_path: Path to the models package

    Returns:
        Number of models discovered
    """
    import importlib
    import pkgutil

    discovered = 0

    # Skip these modules as they're not model implementations
    skip_modules = {"base", "registry", "manager", "downloader", "__init__"}

    for _finder, module_name, ispkg in pkgutil.iter_modules([str(package_path)]):
        if module_name in skip_modules or ispkg:
            continue

        try:
            # Import the module (which should trigger registration)
            importlib.import_module(f".{module_name}", package="pseudocode_translator.models")
            discovered += 1
            logger.debug("Discovered model module: %s", module_name)
        except Exception as e:
            logger.warning("Failed to import model module '%s': %s", module_name, e)

    return discovered
