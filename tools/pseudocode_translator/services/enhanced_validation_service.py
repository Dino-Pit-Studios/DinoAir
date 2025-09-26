"""
Enhanced Validation Service

This module provides comprehensive validation capabilities extracted from the
monolithic TranslationManager, with improved error handling and extensibility.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from ..validator import ValidationResult, Validator
from .error_handler import ErrorCategory, ErrorHandler

if TYPE_CHECKING:
    from ..config import TranslatorConfig

logger = logging.getLogger(__name__)


class ValidationService:
    """
    Standalone validation service that handles code validation,
    error fixing, and improvement suggestions.
    """

    def __init__(
        self,
        config: TranslatorConfig,
        validator: Validator | None = None,
        error_handler: ErrorHandler | None = None,
    ):
        self.config = config
        self.validator = validator or Validator(config)
        self.error_handler = error_handler or ErrorHandler(logger_name=__name__)

        # Validation statistics
        self._validation_count = 0
        self._fix_attempts = 0
        self._successful_fixes = 0

        logger.debug("ValidationService initialized")

    def validate_syntax(self, code: str) -> ValidationResult:
        """
        Validate code syntax.

        Args:
            code: The code to validate

        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        try:
            self._validation_count += 1
            logger.debug("Validating syntax for code (length: %d)", len(code))

            result = self.validator.validate_syntax(code)

            if not result.is_valid:
                logger.warning("Syntax validation failed with %d errors", len(result.errors))

            return result

        except Exception as e:
            error_info = self.error_handler.handle_exception(
                e, ErrorCategory.VALIDATION, additional_context="Syntax validation"
            )

            return ValidationResult(
                is_valid=False,
                errors=[self.error_handler.format_error_message(error_info)],
                warnings=[],
            )

    def validate_logic(self, code: str) -> ValidationResult:
        """
        Validate code logic and patterns.

        Args:
            code: The code to validate

        Returns:
            ValidationResult with logic validation status
        """
        try:
            logger.debug("Validating logic for code")
            return self.validator.validate_logic(code)

        except Exception as e:
            error_info = self.error_handler.handle_exception(
                e, ErrorCategory.VALIDATION, additional_context="Logic validation"
            )

            return ValidationResult(
                is_valid=False,
                errors=[self.error_handler.format_error_message(error_info)],
                warnings=[],
            )

    def validate_comprehensive(self, code: str) -> ValidationResult:
        """
        Perform comprehensive validation including syntax, logic, and patterns.

        Args:
            code: The code to validate

        Returns:
            Combined ValidationResult
        """
        try:
            # Syntax validation first
            syntax_result = self.validate_syntax(code)

            # If syntax fails, don't continue with logic validation
            if not syntax_result.is_valid:
                return syntax_result

            # Logic validation
            logic_result = self.validate_logic(code)

            # Combine results
            return ValidationResult(
                is_valid=syntax_result.is_valid and logic_result.is_valid,
                errors=syntax_result.errors + logic_result.errors,
                warnings=syntax_result.warnings + logic_result.warnings,
            )

        except Exception as e:
            error_info = self.error_handler.handle_exception(
                e, ErrorCategory.VALIDATION, additional_context="Comprehensive validation"
            )

            return ValidationResult(
                is_valid=False,
                errors=[self.error_handler.format_error_message(error_info)],
                warnings=[],
            )

    def validate_and_fix(
        self, code: str, max_attempts: int = 3, use_llm_fixes: bool = True
    ) -> tuple[str, ValidationResult]:
        """
        Validate code and attempt to fix any errors found.

        Args:
            code: The code to validate and fix
            max_attempts: Maximum number of fix attempts
            use_llm_fixes: Whether to use LLM-based error fixing

        Returns:
            Tuple of (fixed_code, final_validation_result)
        """
        current_code = code
        attempt = 0

        while attempt < max_attempts:
            # Validate current code
            validation_result = self.validate_comprehensive(current_code)

            if validation_result.is_valid:
                logger.debug("Code validation successful after %d attempts", attempt)
                return current_code, validation_result

            # Attempt to fix errors
            if not validation_result.errors:
                break

            self._fix_attempts += 1
            attempt += 1

            logger.debug("Attempting fix #%d for validation errors", attempt)

            try:
                fixed_code = self._attempt_fix(current_code, validation_result, use_llm_fixes)

                if fixed_code and fixed_code != current_code:
                    current_code = fixed_code
                    logger.debug("Applied fix attempt #%d", attempt)
                else:
                    logger.warning("Fix attempt #%d produced no changes", attempt)
                    break

            except Exception as e:
                logger.error("Error during fix attempt #%d: %s", attempt, e)
                break

        # Final validation
        final_result = self.validate_comprehensive(current_code)

        if final_result.is_valid and attempt > 0:
            self._successful_fixes += 1
            logger.info("Successfully fixed code after %d attempts", attempt)

        return current_code, final_result

    def suggest_improvements(self, code: str) -> list[str]:
        """
        Generate improvement suggestions for the code.

        Args:
            code: The code to analyze

        Returns:
            List of improvement suggestions
        """
        try:
            return self.validator.suggest_improvements(code)
        except Exception as e:
            self.error_handler.handle_exception(
                e, ErrorCategory.VALIDATION, additional_context="Improvement suggestions"
            )
            return []

    def _attempt_fix(
        self, code: str, validation_result: ValidationResult, use_llm_fixes: bool
    ) -> str | None:
        """
        Attempt to fix validation errors in the code.

        Args:
            code: The code to fix
            validation_result: The validation result containing errors
            use_llm_fixes: Whether to use LLM-based fixing

        Returns:
            Fixed code or None if no fixes could be applied
        """
        if not validation_result.errors:
            return code

        try:
            # Try built-in validator fixes first
            fixed_code = self._apply_builtin_fixes(code, validation_result)

            if fixed_code != code:
                return fixed_code

            # Try LLM-based fixes if enabled and available
            if use_llm_fixes:
                llm_fixed = self._apply_llm_fixes(code, validation_result)
                if llm_fixed is not None:
                    return llm_fixed

            return None

        except Exception as e:
            logger.error("Error during fix attempt: %s", e)
            return None

    def _apply_builtin_fixes(self, code: str, validation_result: ValidationResult) -> str:
        """Apply built-in validation fixes."""
        # Simple built-in fixes for common issues
        fixed_code = code

        for error in validation_result.errors:
            # Fix common indentation issues
            if "indentation" in error.lower():
                lines = fixed_code.split("\n")
                fixed_lines: list[str] = []
                for line in lines:
                    # Simple indentation fix - ensure proper 4-space indentation
                    stripped = line.lstrip()
                    if stripped and not line.startswith("    ") and line.startswith(" "):
                        # Re-indent to 4 spaces
                        indent_level = (len(line) - len(stripped)) // 2
                        fixed_lines.append("    " * indent_level + stripped)
                    else:
                        fixed_lines.append(line)
                fixed_code = "\n".join(fixed_lines)

            # Fix missing colons
            elif "expected ':'" in error:
                # Add colons to control structures
                patterns = [
                    (r"^(\s*)(if\s+.*)(?<!:)$", r"\1\2:"),
                    (r"^(\s*)(for\s+.*)(?<!:)$", r"\1\2:"),
                    (r"^(\s*)(while\s+.*)(?<!:)$", r"\1\2:"),
                    (r"^(\s*)(def\s+.*)(?<!:)$", r"\1\2:"),
                    (r"^(\s*)(class\s+.*)(?<!:)$", r"\1\2:"),
                ]

                lines = fixed_code.split("\n")
                fixed_lines_list: list[str] = []
                for line in lines:
                    modified_line = line
                    for pattern, replacement in patterns:
                        if re.match(pattern, line, re.MULTILINE):
                            modified_line = re.sub(pattern, replacement, line, flags=re.MULTILINE)
                            break
                    fixed_lines_list.append(modified_line)
                fixed_code = "\n".join(fixed_lines_list)

        return fixed_code

    def _apply_llm_fixes(self, code: str, validation_result: ValidationResult) -> str | None:
        """Apply LLM-based fixes if available."""
        try:
            # Try to get LLM-based fix support from the container
            # This would be implemented when we have the model service ready
            logger.debug("LLM-based fixing not yet implemented")
            return None

        except Exception as e:
            logger.debug("LLM-based fixing failed: %s", e)
            return None

    def get_statistics(self) -> dict[str, Any]:
        """Get validation service statistics."""
        return {
            "validation_count": self._validation_count,
            "fix_attempts": self._fix_attempts,
            "successful_fixes": self._successful_fixes,
            "fix_success_rate": (self._successful_fixes / max(self._fix_attempts, 1)) * 100,
        }

    def reset_statistics(self) -> None:
        """Reset validation statistics."""
        self._validation_count = 0
        self._fix_attempts = 0
        self._successful_fixes = 0
        logger.debug("Validation statistics reset")
