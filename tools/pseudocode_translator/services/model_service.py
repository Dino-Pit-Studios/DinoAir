"""
Model Service for Translation Management

This service provides a clean interface for managing translation models,
extracted from the monolithic TranslationManager.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from utils.shutdown_protocols import ShutdownMixin

from ..models.base_model import (
    BaseTranslationModel,
    OutputLanguage,
)
from ..models.base_model import TranslationConfig as ModelTranslationConfig
from ..models.model_factory import ModelFactory
from ..models.model_initializer import ModelInitializer
from .error_handler import ErrorCategory, ErrorHandler

if TYPE_CHECKING:
    from ..config import TranslatorConfig
    from .dependency_container import DependencyContainer

logger = logging.getLogger(__name__)


class ModelService(ShutdownMixin):
    """
    Service for managing translation models.

    Provides model lifecycle management, configuration, and translation
    capabilities in a focused, testable way.
    """

    def __init__(
        self,
        config: TranslatorConfig,
        error_handler: ErrorHandler | None = None,
        container: DependencyContainer | None = None,
    ):
        super().__init__()  # Initialize ShutdownMixin
        self.config = config
        self.error_handler = error_handler or ErrorHandler(logger_name=__name__)
        self.container = container

        # Model state
        self._current_model: BaseTranslationModel | None = None
        self._model_name: str | None = None
        self._target_language = OutputLanguage.PYTHON

        # Statistics
        self._translation_count = 0
        self._model_switches = 0

        logger.debug("ModelService initialized")

    def initialize_model(self, model_name: str | None = None) -> None:
        """
        Initialize or switch to a different model.

        Args:
            model_name: Name of the model to initialize. If None, uses config default.

        Raises:
            RuntimeError: If model initialization fails
        """
        try:
            # Determine model name
            if model_name is None:
                model_name = self._get_default_model_name()

            logger.info("Initializing model: %s", model_name)

            # Skip if already initialized
            if ModelInitializer.should_skip_initialization(
                self._current_model, self._model_name, model_name
            ):
                return

            # Create model configuration
            model_config = self._build_model_config()

            # Create and initialize model using shared utility
            model_path = self._get_model_path()
            model = ModelInitializer.create_and_initialize_model(
                model_name, model_config, model_path
            )

            # Update state
            old_model = self._current_model
            self._current_model = model
            self._model_name = model_name

            if old_model:
                self._model_switches += 1
                old_model.shutdown()

            logger.info("Model initialized successfully: %s", model_name)

        except Exception as e:
            self.error_handler.handle_exception(
                e, ErrorCategory.MODEL, additional_context="Model initialization"
            )

            raise RuntimeError(f"Failed to initialize model '{model_name}': {str(e)}") from e

    def translate_text(
        self,
        text: str,
        target_language: OutputLanguage | None = None,
        context: dict[str, Any] | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> Any:
        """
        Translate text using the current model.

        Args:
            text: Text to translate
            target_language: Target programming language
            context: Additional context for translation
            config_overrides: Configuration overrides

        Returns:
            Translation result from the model

        Raises:
            RuntimeError: If no model is initialized or translation fails
        """
        if not self._current_model:
            raise RuntimeError("No model initialized")

        try:
            self._translation_count += 1

            # Build translation config
            translation_config = self._build_translation_config(target_language, config_overrides)

            logger.debug("Translating text with model: %s", self._model_name)

            # Perform translation
            result = self._current_model.translate(
                instruction=text, config=translation_config, context=context or {}
            )

            logger.debug("Translation completed successfully")
            return result

        except Exception as e:
            self.error_handler.handle_exception(
                e, ErrorCategory.TRANSLATION, additional_context="Model translation"
            )

            raise RuntimeError(f"Translation failed: {str(e)}") from e

    def validate_input(self, text: str) -> tuple[bool, str | None]:
        """
        Validate input text for translation.

        Args:
            text: Text to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self._current_model:
            return False, "No model initialized"

        try:
            if hasattr(self._current_model, "validate_input"):
                return self._current_model.validate_input(text)
            # Default validation
            if not text or not text.strip():
                return False, "Input text is empty"
            return True, None

        except Exception as e:
            logger.warning("Input validation failed: %s", e)
            return False, f"Validation error: {str(e)}"

    def get_current_model(self) -> str | None:
        """Get the name of the current model."""
        return self._model_name

    def list_available_models(self) -> list[str]:
        """List all available models."""
        try:
            return ModelFactory.list_models()
        except Exception as e:
            logger.warning("Failed to list models: %s", e)
            return []

    def set_target_language(self, language: OutputLanguage) -> None:
        """Set the default target language."""
        self._target_language = language
        logger.debug("Target language set to: %s", language.value)

    def get_target_language(self) -> OutputLanguage:
        """Get the current target language."""
        return self._target_language

    def switch_model(self, model_name: str) -> None:
        """
        Switch to a different model.

        Args:
            model_name: Name of the model to switch to
        """
        if model_name == self._model_name:
            logger.debug("Model %s already active", model_name)
            return

        logger.info("Switching from %s to %s", self._model_name, model_name)
        self.initialize_model(model_name)

    def _cleanup_resources(self) -> None:
        """Clean up model resources during shutdown."""
        if self._current_model:
            try:
                self._current_model.shutdown()
            except Exception as e:
                logger.warning("Error shutting down model: %s", e)
            finally:
                self._current_model = None
                self._model_name = None

        logger.info("ModelService shutdown complete")

    def get_statistics(self) -> dict[str, Any]:
        """Get model service statistics."""
        return {
            "current_model": self._model_name,
            "target_language": self._target_language.value,
            "translation_count": self._translation_count,
            "model_switches": self._model_switches,
            "available_models": len(self.list_available_models()),
        }

    def reset_statistics(self) -> None:
        """Reset model service statistics."""
        self._translation_count = 0
        self._model_switches = 0
        logger.debug("Model statistics reset")

    def _get_default_model_name(self) -> str:
        """Get the default model name from configuration."""
        return getattr(
            self.config.llm, "model_type", getattr(self.config.llm, "model_name", "qwen")
        )

    def _get_model_path(self) -> Path | None:
        """Get model path from configuration."""
        if hasattr(self.config.llm, "model_path"):
            return Path(self.config.llm.model_path)
        return None

    def _build_model_config(self) -> dict[str, Any]:
        """Build model configuration dictionary."""
        config: dict[str, Any] = {
            "temperature": self.config.llm.temperature,
            "top_p": getattr(self.config.llm, "top_p", 0.9),
            "top_k": getattr(self.config.llm, "top_k", 40),
            "max_tokens": self.config.llm.max_tokens,
            "n_ctx": self.config.llm.n_ctx,
            "n_batch": getattr(self.config.llm, "n_batch", 512),
            "n_threads": self.config.llm.n_threads,
            "n_gpu_layers": self.config.llm.n_gpu_layers,
        }

        # Add model path if available
        model_path = self._get_model_path()
        if model_path:
            config["model_path"] = str(model_path)

        return config

    def _build_translation_config(
        self,
        target_language: OutputLanguage | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> ModelTranslationConfig:
        """Build translation configuration for model."""
        # Use provided language or default
        lang = target_language or self._target_language

        # Create base config
        translation_config = ModelTranslationConfig(
            target_language=lang,
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
            top_p=getattr(self.config.llm, "top_p", 0.9),
            top_k=getattr(self.config.llm, "top_k", 40),
            include_comments=True,
            follow_conventions=True,
        )

        # Apply overrides if provided
        if overrides:
            for key, value in overrides.items():
                if hasattr(translation_config, key):
                    setattr(translation_config, key, value)

        return translation_config
