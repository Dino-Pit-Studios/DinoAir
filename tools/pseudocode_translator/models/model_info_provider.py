"""
Unified Model Information Interface

This module provides a consolidated interface for retrieving model information
from both ModelFactory and ModelRegistry systems, eliminating duplication.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ModelInfoProvider:
    """Unified interface for model information across different registry systems."""

    @staticmethod
    def get_model_info_from_factory(factory_class: Any, name: str) -> dict[str, Any]:
        """
        Get model info from ModelFactory-style registry.

        Args:
            factory_class: The factory class to query
            name: Model name or alias

        Returns:
            Model information dictionary
        """
        try:
            # Resolve alias
            actual_name = factory_class.resolve_alias(name)

            registration = factory_class.get_registration(actual_name)

            # Create temporary instance for metadata
            temp_instance = registration.model_class({})
            metadata = temp_instance.metadata

            return {
                "name": registration.name,
                "class": registration.model_class.__name__,
                "aliases": registration.aliases,
                "description": metadata.description,
                "version": metadata.version,
                "author": metadata.author,
                "source": "factory",
            }
        except Exception as e:
            logger.error("Failed to get model info from factory: %s", e)
            raise

    @staticmethod
    def get_model_info_from_registry(registry_class: Any, name: str) -> dict[str, Any]:
        """
        Get model info from ModelRegistry-style registry.

        Args:
            registry_class: The registry class to query
            name: Model name or alias

        Returns:
            Model information dictionary
        """
        try:
            model_class = registry_class.get_model_class(name)

            # Create temporary instance to get metadata
            temp_instance = model_class({})
            metadata = temp_instance.metadata
            capabilities = temp_instance.capabilities

            return {
                "name": metadata.name,
                "display_name": metadata.display_name,
                "description": metadata.description,
                "version": metadata.version,
                "author": metadata.author,
                "license": metadata.license,
                "format": metadata.format.value,
                "capabilities": {
                    "supports_streaming": capabilities.supports_streaming,
                    "supports_batching": capabilities.supports_batching,
                    "max_context": capabilities.max_context,
                    "supported_languages": capabilities.supported_languages,
                },
                "source": "registry",
            }
        except Exception as e:
            logger.error("Failed to get model info from registry: %s", e)
            raise

    @staticmethod
    def normalize_model_info(model_info: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize model info to a common format regardless of source.

        Args:
            model_info: Raw model info from either source

        Returns:
            Normalized model information
        """
        return {
            "name": model_info.get("name", "unknown"),
            "display_name": model_info.get("display_name", model_info.get("name", "unknown")),
            "description": model_info.get("description", "No description available"),
            "version": model_info.get("version", "unknown"),
            "author": model_info.get("author", "unknown"),
            "class": model_info.get("class", "unknown"),
            "aliases": model_info.get("aliases", []),
            "capabilities": model_info.get("capabilities", {}),
            "source": model_info.get("source", "unknown"),
        }
