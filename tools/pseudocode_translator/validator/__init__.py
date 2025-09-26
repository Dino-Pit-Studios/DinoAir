"""
Validator package for Python code validation.

This package provides comprehensive validation capabilities for Python code,
including syntax validation, logic checks, and improvement suggestions.

The package has been refactored to improve code health by separating concerns
into focused modules while maintaining full backward compatibility.
"""

from .checkers import (
    PerformanceChecker,
    RuntimeRiskChecker,
    TypeConsistencyChecker,
    UndefinedVariableChecker,
)

# Import all classes to maintain backward compatibility
from .core import Validator
from .result import ValidationErrorParams, ValidationResult
from .scope import Scope

# Export all public classes
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
