"""
Input processing stages package for DinoAir InputSanitizer.

This package contains modular components for processing user input
through various security and enhancement stages.
"""

# Validation module
# Enhanced security modules
from .enhanced_sanitizer import EnhancedInputSanitizer, SecurityMonitor

# Escaping module
from .escaping import (
    ClaudeEscaper,
    DefaultEscaper,
    EscapeStrategy,
    GPTEscaper,
    TextEscaper,
    escape_for_model,
)

# Intent classification module
from .intent import IntentClassification, IntentClassifier, IntentType, classify_intent

# Pattern normalization module
from .pattern import FuzzyMatcher, PatternNormalizer, fuzzy_match, normalize_input

# Profanity filtering module
from .profanity import FilterResult, ProfanityFilter, ProfanityMatch, Severity, filter_profanity

# Rate limiting module
from .rate_limiter import (
    RateLimitConfig,
    RateLimiter,
    RateLimitStatus,
    RateLimitStrategy,
    check_rate_limit,
    get_rate_limiter,
    reset_rate_limit,
)
from .validation import InputValidator, ThreatLevel, ValidationError, ValidationResult

__all__ = [
    # Validation
    "ValidationError",
    "ThreatLevel",
    "ValidationResult",
    "InputValidator",
    # Escaping
    "EscapeStrategy",
    "ClaudeEscaper",
    "GPTEscaper",
    "DefaultEscaper",
    "TextEscaper",
    "escape_for_model",
    # Pattern normalization
    "PatternNormalizer",
    "FuzzyMatcher",
    "normalize_input",
    "fuzzy_match",
    # Profanity filtering
    "Severity",
    "ProfanityMatch",
    "FilterResult",
    "ProfanityFilter",
    "filter_profanity",
    # Intent classification
    "IntentType",
    "IntentClassification",
    "IntentClassifier",
    "classify_intent",
    # Rate limiting
    "RateLimitStrategy",
    "RateLimitConfig",
    "RateLimitStatus",
    "RateLimiter",
    "get_rate_limiter",
    "check_rate_limit",
    "reset_rate_limit",
    # Enhanced security
    "EnhancedInputSanitizer",
    "SecurityMonitor",
]
