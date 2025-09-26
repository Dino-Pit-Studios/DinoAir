"""
Validation result data structures.

This module contains classes that represent the results of code validation,
including errors, warnings, and suggestions.
"""

from dataclasses import dataclass, field


# Typed default factories to satisfy static type checkers (e.g., Pylance)
def _new_str_list() -> list[str]:
    return []


def _new_int_list() -> list[int]:
    return []


@dataclass
class ValidationErrorParams:
    """Parameters for creating validation errors to reduce argument count"""

    message: str
    line_text: str
    line_no: int
    all_lines: list[str]
    suggestions: list[str] | None = None
    validation_type: str = "syntax"


@dataclass
class ValidationResult:
    """Result of code validation"""

    is_valid: bool
    errors: list[str] = field(default_factory=_new_str_list)
    warnings: list[str] = field(default_factory=_new_str_list)
    line_numbers: list[int] = field(default_factory=_new_int_list)
    suggestions: list[str] = field(default_factory=_new_str_list)

    def add_error(self, error: str, line_number: int | None = None):
        """Add an error to the validation result"""
        self.errors.append(error)
        if line_number is not None:
            self.line_numbers.append(line_number)
        self.is_valid = False

    def add_warning(self, warning: str):
        """Add a warning to the validation result"""
        self.warnings.append(warning)

    def add_suggestion(self, suggestion: str):
        """Add an improvement suggestion"""
        self.suggestions.append(suggestion)
