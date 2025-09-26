"""
Shared Model Initialization Utilities

This module provides centralized model initialization logic to eliminate
duplication between ModelService and LLMInterface.
"""

import logging
from pathlib import Path
from typing import Any

from .model_factory import create_model
from .registry import list_available_models, model_exists

logger = logging.getLogger(__name__)


class ModelInitializer:
    """Centralized model initialization logic."""

    @staticmethod
    def validate_model_name(model_name: str) -> None:
        """
        Validate that a model name exists in the registry.

        Args:
            model_name: Name of the model to validate

        Raises:
            ValueError: If model is not found
        """
        if not model_exists(model_name):
            available = ", ".join(list_available_models())
            raise ValueError(f"Model '{model_name}' not found. Available models: {available}")

    @staticmethod
    def create_and_initialize_model(
        model_name: str, model_config: dict[str, Any], model_path: Path | None = None
    ) -> Any:
        """
        Create and initialize a model with the given configuration.

        Args:
            model_name: Name of the model to create
            model_config: Configuration dictionary for the model
            model_path: Optional path to model files

        Returns:
            Initialized model instance

        Raises:
            RuntimeError: If model initialization fails
        """
        try:
            logger.info("Creating model: %s", model_name)

            # Validate model exists
            ModelInitializer.validate_model_name(model_name)

            # Create model instance
            model = create_model(model_name, model_config)

            # Initialize with path if provided
            if model_path and hasattr(model, "initialize"):
                logger.debug("Initializing model with path: %s", model_path)
                model.initialize(model_path)

            logger.info("Model '%s' initialized successfully", model_name)
            return model

        except Exception as e:
            logger.error("Failed to initialize model '%s': %s", model_name, e)
            raise RuntimeError(f"Model initialization failed: {e}") from e

    @staticmethod
    def should_skip_initialization(
        current_model: Any, current_model_name: str | None, target_model_name: str
    ) -> bool:
        """
        Check if model initialization can be skipped.

        Args:
            current_model: Currently loaded model instance
            current_model_name: Name of currently loaded model
            target_model_name: Name of target model

        Returns:
            True if initialization can be skipped
        """
        if current_model and current_model_name == target_model_name:
            logger.info("Model '%s' already initialized", target_model_name)
            return True
        return False
