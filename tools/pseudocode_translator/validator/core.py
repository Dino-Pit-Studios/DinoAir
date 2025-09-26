"""
Core validator module containing the main Validator class.

This module contains the main Validator class that orchestrates all the
different validation checks and provides the primary public interface.
"""

import logging

from ..config import TranslatorConfig
from .improvements import ImprovementAnalyzer
from .logic import LogicValidator
from .result import ValidationResult
from .syntax import SyntaxValidator
from .utils import ValidationCache, get_cache_key

logger = logging.getLogger(__name__)


class Validator:
    """
    Validates Python code syntax and basic semantics.

    This class orchestrates different validation components while maintaining
    a clean and focused interface.
    """

    def __init__(self, config: TranslatorConfig):
        """
        Initialize the Validator.

        Args:
            config: Translator configuration object
        """
        self.config = config

        # Initialize validation components
        self.syntax_validator = SyntaxValidator(config)
        self.logic_validator = LogicValidator(config)
        self.improvement_analyzer = ImprovementAnalyzer(config)

        # Initialize cache
        self._cache = ValidationCache(max_size=100)

    def validate_syntax(self, code: str) -> ValidationResult:
        """
        Validate Python code syntax.

        Args:
            code: Python code to validate

        Returns:
            ValidationResult with syntax validation details
        """
        # Check cache first
        cache_key = get_cache_key(code, "syntax")
        cached_result = self._cache.get(cache_key)
        if cached_result:
            return cached_result

        # Delegate to syntax validator
        result = self.syntax_validator.validate_syntax(code)

        # Cache the result
        self._cache.put(cache_key, result)
        return result

    def validate_logic(self, code: str) -> ValidationResult:
        """
        Validate code logic and potential runtime issues.

        Args:
            code: Python code to validate

        Returns:
            ValidationResult with logic validation details
        """
        # Check cache first
        cache_key = get_cache_key(code, "logic")
        cached_result = self._cache.get(cache_key)
        if cached_result:
            return cached_result

        # Delegate to logic validator
        result = self.logic_validator.validate_logic(code)

        # Cache the result
        self._cache.put(cache_key, result)
        return result

    def suggest_improvements(self, code: str) -> list[str]:
        """
        Suggest improvements for the code.

        Args:
            code: Python code to analyze

        Returns:
            List of improvement suggestions
        """
        return self.improvement_analyzer.suggest_improvements(code)
