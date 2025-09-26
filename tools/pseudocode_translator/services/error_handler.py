"""
Centralized Error Handling Service for the Pseudocode Translator

This module provides consistent error handling, formatting, and recovery
mechanisms throughout the translation pipeline.
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..exceptions import ErrorContext, TranslatorError

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error category types."""

    VALIDATION = "validation"
    TRANSLATION = "translation"
    PARSING = "parsing"
    ASSEMBLY = "assembly"
    STREAMING = "streaming"
    MODEL = "model"
    SYSTEM = "system"


@dataclass
class ErrorInfo:
    """Comprehensive error information."""

    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    context: ErrorContext | None = None
    cause: Exception | None = None
    suggestions: list[str] | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []
        if self.metadata is None:
            self.metadata = {}


class ErrorHandler:
    """
    Centralized error handling service.

    Provides consistent error formatting, logging, and recovery mechanisms
    across all translation components.
    """

    def __init__(self, logger_name: str | None = None):
        self._logger = logging.getLogger(logger_name or __name__)
        self._error_counts: dict[str, int] = {}

    def create_error(
        self,
        message: str,
        category: ErrorCategory,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: ErrorContext | None = None,
        cause: Exception | None = None,
        suggestions: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ErrorInfo:
        """Create a structured error info object."""
        return ErrorInfo(
            message=message,
            category=category,
            severity=severity,
            context=context,
            cause=cause,
            suggestions=suggestions or [],
            metadata=metadata or {},
        )

    def handle_exception(
        self,
        exception: Exception,
        category: ErrorCategory,
        context: ErrorContext | None = None,
        additional_context: str | None = None,
    ) -> ErrorInfo:
        """Handle and format an exception into structured error info."""
        # Determine severity based on exception type
        severity = self._determine_severity(exception)

        # Create base message
        message = str(exception)
        if additional_context:
            message = f"{additional_context}: {message}"

        # Generate suggestions based on exception type and category
        suggestions = self._generate_suggestions(exception, category)

        # Create metadata
        metadata: dict[str, Any] = {
            "exception_type": type(exception).__name__,
            "exception_module": type(exception).__module__,
        }

        # Add stack trace for debugging if needed
        if severity in (ErrorSeverity.HIGH, ErrorSeverity.CRITICAL):
            metadata["stack_trace"] = "".join(
                traceback.format_exception(type(exception), exception, exception.__traceback__)
            )

        # Track error frequency
        error_key = f"{category.value}_{type(exception).__name__}"
        self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
        metadata["occurrence_count"] = self._error_counts[error_key]

        error_info = ErrorInfo(
            message=message,
            category=category,
            severity=severity,
            context=context,
            cause=exception,
            suggestions=suggestions,
            metadata=metadata,
        )

        # Log the error
        self._log_error(error_info)

        return error_info

    def create_translator_error(
        self, error_info: ErrorInfo, add_context: bool = True
    ) -> TranslatorError:
        """Convert ErrorInfo to a TranslatorError with proper formatting."""
        translator_error = TranslatorError(
            error_info.message,
            context=error_info.context if add_context else None,
            cause=error_info.cause,
        )

        # Add suggestions
        if error_info.suggestions:
            for suggestion in error_info.suggestions:
                translator_error.add_suggestion(suggestion)

        return translator_error

    def format_error_message(self, error_info: ErrorInfo) -> str:
        """Format error info into a human-readable message."""
        parts = [f"[{error_info.category.value.upper()}] {error_info.message}"]

        # Add context if available
        if error_info.context:
            parts.append(f"Context: Line {error_info.context.line_number}")
            if error_info.context.code_snippet:
                parts.append(f"Code: {error_info.context.code_snippet}")

        # Add suggestions
        if error_info.suggestions:
            parts.append("Suggestions:")
            for i, suggestion in enumerate(error_info.suggestions, 1):
                parts.append(f"  {i}. {suggestion}")

        # Add cause details if available
        if error_info.cause:
            parts.append(f"Caused by: {type(error_info.cause).__name__}: {error_info.cause}")

        return "\n".join(parts)

    def get_error_summary(self) -> dict[str, Any]:
        """Get summary of all handled errors."""
        return {
            "total_errors": sum(self._error_counts.values()),
            "error_breakdown": dict(self._error_counts),
            "most_common_errors": sorted(
                self._error_counts.items(), key=lambda x: x[1], reverse=True
            )[:5],
        }

    def clear_error_stats(self) -> None:
        """Clear error tracking statistics."""
        self._error_counts.clear()

    def _determine_severity(self, exception: Exception) -> ErrorSeverity:
        """Determine error severity based on exception type."""
        if isinstance(exception, SystemError | MemoryError | KeyboardInterrupt):
            return ErrorSeverity.CRITICAL
        if isinstance(exception, ImportError | ModuleNotFoundError | FileNotFoundError):
            return ErrorSeverity.HIGH
        if isinstance(exception, ValueError | TypeError | AttributeError):
            return ErrorSeverity.MEDIUM
        return ErrorSeverity.LOW

    def _generate_suggestions(self, exception: Exception, category: ErrorCategory) -> list[str]:
        """Generate helpful suggestions based on exception type and category."""
        suggestions: list[str] = []

        # General suggestions based on exception type
        if isinstance(exception, ImportError):
            suggestions.extend(
                [
                    "Check if required modules are installed",
                    "Verify Python path configuration",
                    "Check for circular imports",
                ]
            )
        elif isinstance(exception, FileNotFoundError):
            suggestions.extend(
                [
                    "Verify file path exists",
                    "Check file permissions",
                    "Ensure proper working directory",
                ]
            )
        elif isinstance(exception, ValueError):
            suggestions.extend(
                [
                    "Validate input parameters",
                    "Check data format and types",
                    "Review configuration values",
                ]
            )
        elif isinstance(exception, AttributeError):
            suggestions.extend(
                [
                    "Check object initialization",
                    "Verify method/attribute names",
                    "Ensure proper object state",
                ]
            )

        # Category-specific suggestions
        if category == ErrorCategory.TRANSLATION:
            suggestions.extend(
                ["Simplify input text", "Check model configuration", "Verify translation context"]
            )
        elif category == ErrorCategory.VALIDATION:
            suggestions.extend(
                [
                    "Check syntax rules",
                    "Review code structure",
                    "Validate against language standards",
                ]
            )
        elif category == ErrorCategory.PARSING:
            suggestions.extend(["Check input format", "Verify encoding", "Review parsing rules"])
        elif category == ErrorCategory.MODEL:
            suggestions.extend(
                ["Check model availability", "Verify API credentials", "Review model parameters"]
            )

        return suggestions

    def _log_error(self, error_info: ErrorInfo) -> None:
        """Log error with appropriate level based on severity."""
        formatted_message = self.format_error_message(error_info)

        if error_info.severity == ErrorSeverity.CRITICAL:
            self._logger.critical(formatted_message, exc_info=error_info.cause)
        elif error_info.severity == ErrorSeverity.HIGH:
            self._logger.error(formatted_message, exc_info=error_info.cause)
        elif error_info.severity == ErrorSeverity.MEDIUM:
            self._logger.warning(formatted_message)
        else:
            self._logger.info(formatted_message)
