"""
LLM Translation Service

This service provides LLM-first translation approach using the model service
for pseudocode to programming language translation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from utils.shutdown_protocols import ShutdownMixin

from ..models.base_model import OutputLanguage
from .error_handler import ErrorCategory, ErrorHandler

if TYPE_CHECKING:
    from .model_service import ModelService
    from .translation_pipeline import TranslationContext, TranslationResult

logger = logging.getLogger(__name__)


class LLMTranslationService(ShutdownMixin):
    """
    Service for LLM-first translation approach.

    Uses language models to directly translate pseudocode to target programming
    languages with minimal preprocessing.
    """

    def __init__(self, model_service: ModelService, error_handler: ErrorHandler | None = None):
        super().__init__()
        self.model_service = model_service
        self.error_handler = error_handler or ErrorHandler(logger_name=__name__)

        # Statistics
        self._successful_translations = 0
        self._failed_translations = 0
        self._total_processing_time = 0.0

        logger.debug("LLMTranslationService initialized")

    def translate(self, context: TranslationContext) -> TranslationResult:
        """
        Translate pseudocode using LLM-first approach.

        Args:
            context: Translation context with input text and metadata

        Returns:
            TranslationResult with translated code or errors
        """
        import time

        from .translation_pipeline import TranslationResult

        start_time = time.time()

        try:
            logger.debug("Starting LLM translation for ID: %s", context.translation_id)

            # Validate input
            is_valid, validation_error = self.model_service.validate_input(context.input_text)
            if not is_valid:
                self._failed_translations += 1
                return TranslationResult(
                    success=False,
                    code=None,
                    errors=[f"Input validation failed: {validation_error}"],
                    warnings=[],
                    metadata=self._create_metadata(context, start_time, False),
                )

            # Prepare translation prompt
            translation_prompt = self._build_translation_prompt(
                context.input_text, context.target_language
            )

            # Set target language in model service
            self.model_service.set_target_language(context.target_language)

            # Perform translation
            model_result = self.model_service.translate_text(
                text=translation_prompt,
                target_language=context.target_language,
                context={
                    "translation_id": context.translation_id,
                    "approach": "llm_first",
                    "input_length": len(context.input_text),
                },
            )

            # Process model result
            if model_result and hasattr(model_result, "code") and model_result.code:
                code = self._post_process_code(model_result.code, context.target_language)

                # Validate generated code
                warnings = self._validate_generated_code(code, context.target_language)

                self._successful_translations += 1
                end_time = time.time()
                self._total_processing_time += end_time - start_time

                return TranslationResult(
                    success=True,
                    code=code,
                    errors=[],
                    warnings=warnings,
                    metadata=self._create_metadata(context, start_time, True),
                )
            self._failed_translations += 1
            return TranslationResult(
                success=False,
                code=None,
                errors=["Model returned empty or invalid result"],
                warnings=[],
                metadata=self._create_metadata(context, start_time, False),
            )

        except Exception as e:
            self._failed_translations += 1
            error_info = self.error_handler.handle_exception(
                e, ErrorCategory.TRANSLATION, additional_context="LLM translation"
            )

            return TranslationResult(
                success=False,
                code=None,
                errors=[self.error_handler.format_error_message(error_info)],
                warnings=[],
                metadata=self._create_metadata(context, start_time, False),
            )

    def _build_translation_prompt(self, input_text: str, target_language: OutputLanguage) -> str:
        """
        Build a translation prompt for the LLM.

        Args:
            input_text: Original pseudocode text
            target_language: Target programming language

        Returns:
            Formatted prompt for the LLM
        """
        language_name = target_language.value.title()

        prompt = f"""Translate the following pseudocode to {language_name}:

Pseudocode:
{input_text}

Requirements:
- Generate clean, readable {language_name} code
- Include appropriate comments for clarity
- Follow {language_name} naming conventions
- Ensure proper syntax and structure
- Handle edge cases appropriately

{language_name} Code:"""

        return prompt

    def _post_process_code(self, raw_code: str, target_language: OutputLanguage) -> str:
        """
        Post-process generated code for better quality.

        Args:
            raw_code: Raw code from the model
            target_language: Target programming language

        Returns:
            Cleaned and formatted code
        """
        # Remove common LLM artifacts
        code = raw_code.strip()

        # Remove markdown code blocks if present
        if code.startswith("```"):
            lines = code.split("\n")
            if len(lines) > 1:
                # Remove first line (```python, ```javascript, etc.)
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                # Remove last line if it's just ```
                lines = lines[:-1]
            code = "\n".join(lines)

        # Remove extra whitespace
        code = code.strip()

        # Add basic language-specific formatting
        if target_language == OutputLanguage.PYTHON:
            # Ensure proper Python indentation consistency
            code = self._normalize_python_indentation(code)

        return code

    def _normalize_python_indentation(self, code: str) -> str:
        """Normalize Python code indentation."""
        lines = code.split("\n")
        normalized_lines = []

        for line in lines:
            # Convert tabs to 4 spaces
            line = line.expandtabs(4)
            normalized_lines.append(line)

        return "\n".join(normalized_lines)

    def _validate_generated_code(self, code: str, target_language: OutputLanguage) -> list[str]:
        """
        Validate generated code and return warnings.

        Args:
            code: Generated code to validate
            target_language: Target programming language

        Returns:
            List of validation warnings
        """
        warnings = []

        if not code.strip():
            warnings.append("Generated code is empty")
            return warnings

        # Basic syntax validation for Python
        if target_language == OutputLanguage.PYTHON:
            try:
                import ast

                ast.parse(code)
            except SyntaxError as e:
                warnings.append(f"Python syntax error: {str(e)}")
            except Exception as e:
                warnings.append(f"Code validation error: {str(e)}")

        # Check for common issues
        if len(code.splitlines()) < 2:
            warnings.append("Generated code seems too short")

        if "TODO" in code or "FIXME" in code:
            warnings.append("Generated code contains TODO/FIXME comments")

        return warnings

    def _create_metadata(
        self, context: TranslationContext, start_time: float, success: bool
    ) -> dict[str, Any]:
        """Create metadata for translation result."""
        import time

        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "translation_id": context.translation_id,
            "approach": "llm_first",
            "duration_ms": duration_ms,
            "target_language": context.target_language.value,
            "input_length": len(context.input_text),
            "success": success,
            "service": "LLMTranslationService",
        }

    def get_statistics(self) -> dict[str, Any]:
        """Get service statistics."""
        total_translations = self._successful_translations + self._failed_translations
        success_rate = (
            self._successful_translations / total_translations * 100
            if total_translations > 0
            else 0.0
        )
        avg_processing_time = (
            self._total_processing_time / self._successful_translations
            if self._successful_translations > 0
            else 0.0
        )

        return {
            "successful_translations": self._successful_translations,
            "failed_translations": self._failed_translations,
            "total_translations": total_translations,
            "success_rate_percent": round(success_rate, 2),
            "average_processing_time_seconds": round(avg_processing_time, 3),
            "total_processing_time_seconds": round(self._total_processing_time, 3),
        }

    def reset_statistics(self) -> None:
        """Reset service statistics."""
        self._successful_translations = 0
        self._failed_translations = 0
        self._total_processing_time = 0.0
        logger.debug("LLM translation statistics reset")

    def _cleanup_resources(self) -> None:
        """Clean up service resources during shutdown."""
        logger.debug("LLMTranslationService shutdown complete")
