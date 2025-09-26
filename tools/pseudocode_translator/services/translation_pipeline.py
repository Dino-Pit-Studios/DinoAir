"""
Translation Pipeline Coordinator

This module provides a clean, orchestrated approach to managing the translation
workflow, replacing the monolithic TranslationManager with focused coordination.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from utils.dataclass_mixins import init_metadata_field, init_validation_fields
from utils.shutdown_protocols import ShutdownMixin

from ..models.base_model import OutputLanguage
from .dependency_container import DependencyContainer
from .error_handler import ErrorCategory, ErrorHandler

if TYPE_CHECKING:
    from ..config import TranslatorConfig

logger = logging.getLogger(__name__)


@dataclass
class TranslationContext:
    """Context information for a translation operation."""

    translation_id: int
    start_time: float
    target_language: OutputLanguage
    input_text: str
    metadata: dict[str, Any]

    def __post_init__(self):
        init_metadata_field(self)


@dataclass
class TranslationResult:
    """Result of a translation operation."""

    success: bool
    code: str | None
    errors: list[str]
    warnings: list[str]
    metadata: dict[str, Any]

    def __post_init__(self):
        init_validation_fields(self)

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0


class TranslationPipeline(ShutdownMixin):
    """
    Coordinates the translation pipeline workflow.

    This class orchestrates the translation process by delegating to specialized
    services while maintaining a clean separation of concerns.
    """

    def __init__(self, config: TranslatorConfig, container: DependencyContainer | None = None):
        super().__init__()  # Initialize ShutdownMixin
        self.config = config
        self.container = container or DependencyContainer()
        self.error_handler = ErrorHandler(logger_name=__name__)

        # Translation counter for unique IDs
        self._translation_counter = 0

        # Initialize services
        self._initialize_services()

        logger.info("Translation Pipeline initialized")

    def translate(
        self, input_text: str, target_language: OutputLanguage | None = None
    ) -> TranslationResult:
        """
        Translate pseudocode to the target language.

        Args:
            input_text: The pseudocode text to translate
            target_language: Target programming language

        Returns:
            TranslationResult containing the translated code and metadata
        """
        # Create translation context
        context = self._create_translation_context(input_text, target_language)

        try:
            # Emit translation started event
            self._emit_event(
                "translation_started",
                {
                    "id": context.translation_id,
                    "mode": "pipeline",
                    "target_language": context.target_language.value,
                },
            )

            # Try LLM-first approach
            llm_result = self._try_llm_first_translation(context)
            if llm_result and llm_result.success:
                self._emit_event(
                    "translation_completed",
                    {"id": context.translation_id, "approach": "llm_first", "success": True},
                )
                return llm_result

            # Fallback to structured parsing approach
            logger.info("LLM-first failed, falling back to structured parsing")
            structured_result = self._try_structured_translation(context)

            if structured_result and structured_result.success:
                self._emit_event(
                    "translation_completed",
                    {
                        "id": context.translation_id,
                        "approach": "structured_parsing",
                        "success": True,
                    },
                )
            else:
                self._emit_event(
                    "translation_failed",
                    {"id": context.translation_id, "error": "Both translation approaches failed"},
                )

            return structured_result or self._create_failure_result(
                context, "All translation approaches failed"
            )

        except Exception as e:
            error_info = self.error_handler.handle_exception(
                e, ErrorCategory.TRANSLATION, additional_context="Pipeline execution"
            )

            self._emit_event("translation_failed", {"id": context.translation_id, "error": str(e)})

            return TranslationResult(
                success=False,
                code=None,
                errors=[self.error_handler.format_error_message(error_info)],
                warnings=[],
                metadata=self._create_metadata(context, 0, 0, False),
            )

    def _create_translation_context(
        self, input_text: str, target_language: OutputLanguage | None
    ) -> TranslationContext:
        """Create context for a new translation operation."""
        self._translation_counter += 1

        return TranslationContext(
            translation_id=self._translation_counter,
            start_time=time.time(),
            target_language=target_language or OutputLanguage.PYTHON,
            input_text=input_text,
            metadata={},
        )

    def _try_llm_first_translation(self, context: TranslationContext) -> TranslationResult | None:
        """Attempt LLM-first translation approach."""
        try:
            # Resolve LLM translation service from container
            llm_service = self.container.try_resolve(self._get_llm_service_type())
            if not llm_service:
                logger.debug("LLM translation service not available")
                return None

            logger.debug("Attempting LLM-first translation")
            result = llm_service.translate(context)

            if result.success:
                logger.info("LLM-first translation successful")
            else:
                logger.warning("LLM-first translation failed: %s", result.errors)

            return result

        except Exception as e:
            self.error_handler.handle_exception(
                e, ErrorCategory.TRANSLATION, additional_context="LLM-first approach"
            )
            logger.warning("LLM-first translation failed: %s", str(e))
            return None

    def _try_structured_translation(self, context: TranslationContext) -> TranslationResult | None:
        """Attempt structured parsing translation approach."""
        try:
            # Resolve structured parsing service from container
            structured_service = self.container.try_resolve(self._get_structured_service_type())
            if not structured_service:
                logger.debug("Structured parsing service not available, creating fallback")
                structured_service = self._create_fallback_structured_service()

            logger.debug("Attempting structured parsing translation")
            result = structured_service.translate(context)

            if result.success:
                logger.info("Structured translation successful")
            else:
                logger.warning("Structured translation failed: %s", result.errors)

            return result

        except Exception as e:
            self.error_handler.handle_exception(
                e, ErrorCategory.TRANSLATION, additional_context="Structured parsing approach"
            )
            logger.error("Structured translation failed: %s", str(e))
            return self._create_failure_result(context, str(e))

    def _create_failure_result(
        self, context: TranslationContext, error_message: str
    ) -> TranslationResult:
        """Create a failure translation result."""
        return TranslationResult(
            success=False,
            code=None,
            errors=[error_message],
            warnings=[],
            metadata=self._create_metadata(context, 0, 0, False),
        )

    def _create_metadata(
        self,
        context: TranslationContext,
        blocks_processed: int,
        blocks_translated: int,
        validation_passed: bool,
    ) -> dict[str, Any]:
        """Create metadata for translation result."""
        duration_ms = int((time.time() - context.start_time) * 1000)

        return {
            "translation_id": context.translation_id,
            "duration_ms": duration_ms,
            "blocks_processed": blocks_processed,
            "blocks_translated": blocks_translated,
            "validation_passed": validation_passed,
            "target_language": context.target_language.value,
            "pipeline_version": "2.0",
        }

    def _emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit an event through the event system."""
        try:
            # Resolve event bus from container or use global bus
            event_bus = self.container.try_resolve(self._get_event_bus_type())
            if not event_bus:
                from .event_bus import get_global_bus

                event_bus = get_global_bus()

            event_bus.emit(event_type=event_type, data=data, source="TranslationPipeline")
            logger.debug("Event emitted: %s with data: %s", event_type, data)
        except Exception as e:
            logger.debug("Failed to emit event %s: %s", event_type, e)

    def _initialize_services(self) -> None:
        """Initialize required services in the container."""
        logger.debug("Initializing pipeline services")

        try:
            # Initialize model service if not already registered
            if not self.container.is_registered(self._get_model_service_type()):
                model_service = self._create_model_service()
                self.container.register_singleton(self._get_model_service_type(), model_service)
                logger.debug("Model service registered")

            # Initialize LLM translation service if not already registered
            if not self.container.is_registered(self._get_llm_service_type()):
                llm_service = self._create_llm_service()
                self.container.register_singleton(self._get_llm_service_type(), llm_service)
                logger.debug("LLM translation service registered")

            # Initialize structured parsing service if not already registered
            if not self.container.is_registered(self._get_structured_service_type()):
                structured_service = self._create_structured_service()
                self.container.register_singleton(
                    self._get_structured_service_type(), structured_service
                )
                logger.debug("Structured parsing service registered")

            # Initialize event bus if not already registered
            if not self.container.is_registered(self._get_event_bus_type()):
                from .event_bus import EventBus

                event_bus = EventBus()
                self.container.register_singleton(self._get_event_bus_type(), event_bus)
                logger.debug("Event bus registered")

        except Exception as e:
            logger.warning("Error initializing services: %s", e)

    def get_statistics(self) -> dict[str, Any]:
        """Get pipeline statistics."""
        return {
            "total_translations": self._translation_counter,
            "error_summary": self.error_handler.get_error_summary(),
        }

    def _cleanup_resources(self) -> None:
        """Clean up pipeline resources during shutdown."""
        try:
            # Clear error statistics
            self.error_handler.clear_error_stats()
        except Exception as e:
            logger.warning("Error during pipeline cleanup: %s", e)

    # Service creation and type resolution helper methods

    def _get_model_service_type(self) -> type:
        """Get the ModelService type for dependency resolution."""
        from .model_service import ModelService

        return ModelService

    def _get_llm_service_type(self) -> type:
        """Get the LLMTranslationService type for dependency resolution."""
        from .llm_translation_service import LLMTranslationService

        return LLMTranslationService

    def _get_structured_service_type(self) -> type:
        """Get the StructuredParsingService type for dependency resolution."""
        from .structured_parsing_service import StructuredParsingService

        return StructuredParsingService

    def _get_event_bus_type(self) -> type:
        """Get the EventBus type for dependency resolution."""
        from .event_bus import EventBus

        return EventBus

    def _create_model_service(self):
        """Create a new ModelService instance."""
        from .model_service import ModelService

        return ModelService(
            config=self.config, error_handler=self.error_handler, container=self.container
        )

    def _create_llm_service(self):
        """Create a new LLMTranslationService instance."""
        from .llm_translation_service import LLMTranslationService

        # Get or create model service
        model_service = self.container.try_resolve(self._get_model_service_type())
        if not model_service:
            model_service = self._create_model_service()
            self.container.register_singleton(self._get_model_service_type(), model_service)

        return LLMTranslationService(model_service=model_service, error_handler=self.error_handler)

    def _create_structured_service(self):
        """Create a new StructuredParsingService instance."""
        from .structured_parsing_service import StructuredParsingService

        return StructuredParsingService(error_handler=self.error_handler)

    def _create_fallback_structured_service(self):
        """Create a fallback structured parsing service when container resolution fails."""
        return self._create_structured_service()
