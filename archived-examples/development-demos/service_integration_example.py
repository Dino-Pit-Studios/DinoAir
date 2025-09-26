"""
Service Architecture Integration Example

This module demonstrates how the service architecture works together
to provide a clean, testable, and modular translation system.
"""

from __future__ import annotations

import logging
from typing import Any

from ..models.base_model import OutputLanguage
from .dependency_container import DependencyContainer
from .translation_pipeline import TranslationPipeline

logger = logging.getLogger(__name__)


class ServiceIntegrationExample:
    """
    Example demonstrating service architecture integration.

    Shows how to initialize services, configure dependencies,
    and perform translations using the new architecture.
    """

    def __init__(self, config: Any = None):
        """
        Initialize the service integration example.

        Args:
            config: Configuration object (can be None for demo)
        """
        self.config = config or self._create_demo_config()
        self.container = DependencyContainer()
        self.pipeline = TranslationPipeline(self.config, self.container)

        logger.info("Service integration example initialized")

    def demonstrate_translation(self) -> dict[str, Any]:
        """
        Demonstrate the translation pipeline with sample input.

        Returns:
            Dictionary containing translation results and statistics
        """
        sample_pseudocode = """
        Create a function to calculate factorial
        If number is 0 or 1:
            Return 1
        Else:
            Return number * factorial(number - 1)
        """

        logger.info("Starting translation demonstration")

        # Translate to Python
        python_result = self.pipeline.translate(
            input_text=sample_pseudocode, target_language=OutputLanguage.PYTHON
        )

        # Translate to JavaScript
        js_result = self.pipeline.translate(
            input_text=sample_pseudocode, target_language=OutputLanguage.JAVASCRIPT
        )

        # Gather statistics
        pipeline_stats = self.pipeline.get_statistics()

        translation_results = {
            "python_translation": {
                "success": python_result.success,
                "code": python_result.code,
                "errors": python_result.errors,
                "warnings": python_result.warnings,
                "metadata": python_result.metadata,
            },
            "javascript_translation": {
                "success": js_result.success,
                "code": js_result.code,
                "errors": js_result.errors,
                "warnings": js_result.warnings,
                "metadata": js_result.metadata,
            },
            "pipeline_statistics": pipeline_stats,
            "service_architecture": self._get_service_info(),
        }

        logger.info("Translation demonstration completed")
        return translation_results

    def demonstrate_service_resolution(self) -> dict[str, Any]:
        """
        Demonstrate service resolution and dependency injection.

        Returns:
            Information about registered services
        """
        service_info = {
            "registered_types": [t.__name__ for t in self.container.get_registered_types()],
            "service_details": {},
        }

        # Try to resolve each service type
        service_types = [
            ("ModelService", self.pipeline.get_model_service_type()),
            ("LLMTranslationService", self.pipeline.get_llm_service_type()),
            ("StructuredParsingService", self.pipeline.get_structured_service_type()),
            ("EventBus", self.pipeline.get_event_bus_type()),
        ]

        for service_name, service_type in service_types:
            try:
                service = self.container.try_resolve(service_type)
                if service:
                    service_info["service_details"][service_name] = {
                        "resolved": True,
                        "type": type(service).__name__,
                        "has_statistics": hasattr(service, "get_statistics"),
                        "statistics": (
                            service.get_statistics() if hasattr(service, "get_statistics") else None
                        ),
                    }
                else:
                    service_info["service_details"][service_name] = {
                        "resolved": False,
                        "reason": "Service not registered",
                    }
            except Exception as e:
                service_info["service_details"][service_name] = {"resolved": False, "error": str(e)}

        return service_info

    def demonstrate_event_system(self) -> dict[str, Any]:
        """
        Demonstrate the event system functionality.

        Returns:
            Event system demonstration results
        """
        events_captured = []

        # Get the event bus
        try:
            event_bus = self.container.try_resolve(self.pipeline.get_event_bus_type())
            if not event_bus:
                from .event_bus import get_global_bus

                event_bus = get_global_bus()

            # Subscribe to events
            def capture_event(event):
                events_captured.append(
                    {
                        "type": event.type,
                        "data": event.data,
                        "source": event.source,
                        "timestamp": event.timestamp,
                    }
                )

            # Subscribe to translation events
            event_bus.subscribe("translation_started", capture_event)
            event_bus.subscribe("translation_completed", capture_event)
            event_bus.subscribe("translation_failed", capture_event)

            # Perform a translation to trigger events
            test_result = self.pipeline.translate(
                input_text="print('Hello, World!')", target_language=OutputLanguage.PYTHON
            )

            return {
                "events_captured": events_captured,
                "event_bus_stats": event_bus.get_statistics(),
                "translation_result": {
                    "success": test_result.success,
                    "has_code": test_result.code is not None,
                },
            }

        except Exception as e:
            return {
                "error": f"Event system demonstration failed: {str(e)}",
                "events_captured": events_captured,
            }

    def _create_demo_config(self) -> Any:
        """Create a demo configuration object."""

        class DemoConfig:
            """Configuration for demo usage, encapsulating language model settings."""

            class LLMConfig:
                """Configuration for the language model used in the demo, including generation parameters and model details."""

                temperature = 0.7
                max_tokens = 1000
                n_ctx = 2048
                n_threads = 4
                n_gpu_layers = 0
                model_type = "demo"
                model_name = "demo"

            llm = LLMConfig()

        return DemoConfig()

    def _get_service_info(self) -> dict[str, Any]:
        """Get information about the service architecture."""
        return {
            "architecture_pattern": "Dependency Injection with Service Locator",
            "key_components": [
                "TranslationPipeline - Main coordinator",
                "ModelService - Model lifecycle management",
                "LLMTranslationService - LLM-first approach",
                "StructuredParsingService - Rule-based approach",
                "EventBus - Decoupled communication",
                "DependencyContainer - Service resolution",
            ],
            "benefits": [
                "Testability - Services can be mocked/stubbed",
                "Modularity - Clear separation of concerns",
                "Flexibility - Services can be swapped/configured",
                "Maintainability - Easier to modify individual components",
                "Extensibility - New services can be added easily",
            ],
        }

    def run_full_demonstration(self) -> dict[str, Any]:
        """
        Run the complete service architecture demonstration.

        Returns:
            Comprehensive demonstration results
        """
        logger.info("Starting full service architecture demonstration")

        try:
            demo_results = {
                "translation_demo": self.demonstrate_translation(),
                "service_resolution_demo": self.demonstrate_service_resolution(),
                "event_system_demo": self.demonstrate_event_system(),
                "demonstration_summary": {
                    "total_services_registered": len(self.container.get_registered_types()),
                    "pipeline_initialized": True,
                    "demonstration_completed": True,
                },
            }

            logger.info("Full demonstration completed successfully")
            return demo_results

        except Exception as e:
            logger.error("Demonstration failed: %s", e)
            return {"error": str(e), "demonstration_completed": False}

    def cleanup(self) -> None:
        """Clean up resources used in the demonstration."""
        try:
            if hasattr(self.pipeline, "cleanup_resources"):
                self.pipeline.cleanup_resources()
            self.container.clear()
            logger.info("Service integration example cleanup completed")
        except Exception as e:
            logger.warning("Error during cleanup: %s", e)


def run_service_demo() -> dict[str, Any]:
    """
    Standalone function to run the service architecture demonstration.

    Returns:
        Demonstration results
    """
    demo = ServiceIntegrationExample()
    try:
        return demo.run_full_demonstration()
    finally:
        demo.cleanup()


if __name__ == "__main__":
    # Run the demonstration when executed directly
    import json

    print("Running Service Architecture Demonstration...")
    print("=" * 60)

    results = run_service_demo()

    print(json.dumps(results, indent=2, default=str))
    print("=" * 60)
    print("Demonstration completed!")
