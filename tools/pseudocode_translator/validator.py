"""
Validator module for the Pseudocode Translator

This module exposes the public validation API by re-exporting selected
classes from the refactored validator subpackage. Keeping these explicit
imports here preserves backward compatibility for code that imports from
tools.pseudocode_translator.validator.
"""

# Explicit imports from the validator subpackage to back the public API
from .validator.core import Validator
from .validator.performance_checkers import PerformanceChecker
from .validator.result import ValidationErrorParams, ValidationResult
from .validator.runtime_checkers import RuntimeRiskChecker
from .validator.scope import Scope
from .validator.type_checkers import TypeConsistencyChecker
from .validator.variable_trackers import UndefinedVariableChecker

# Explicit export list for star-imports
__all__ = [
    "Validator",
    "ValidationResult",
    "ValidationErrorParams",
    "Scope",
    "TypeConsistencyChecker",
    "RuntimeRiskChecker",
    "PerformanceChecker",
    "UndefinedVariableChecker",
]
