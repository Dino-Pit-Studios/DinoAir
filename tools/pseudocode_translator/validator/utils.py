"""
Utility functions for the validator module.

This module contains common utility functions used across
different validator components.
"""

import hashlib
import threading

from .result import ValidationResult


class ValidationCache:
    """Thread-safe cache for validation results."""

    def __init__(self, max_size: int = 100):
        self._cache: dict[str, ValidationResult] = {}
        self._lock = threading.Lock()
        self._max_size = max_size

    def get(self, key: str) -> ValidationResult | None:
        """Get cached result."""
        with self._lock:
            return self._cache.get(key)

    def put(self, key: str, result: ValidationResult):
        """Cache a validation result."""
        with self._lock:
            # Simple LRU: remove oldest if at capacity
            if len(self._cache) >= self._max_size and key not in self._cache:
                # Remove the first (oldest) item
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]

            self._cache[key] = result

    def clear(self):
        """Clear the cache."""
        with self._lock:
            self._cache.clear()


def get_cache_key(code: str, validation_type: str) -> str:
    """
    Generate a cache key for validation results.

    Args:
        code: The code being validated
        validation_type: Type of validation (syntax, logic, etc.)

    Returns:
        Cache key string
    """
    code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
    return f"{validation_type}_{code_hash}"


def get_surrounding_lines(lines: list[str], line_no: int, context_size: int = 2) -> list[str]:
    """
    Get surrounding lines for error context.

    Args:
        lines: All lines of code
        line_no: Line number (1-based)
        context_size: Number of lines before/after to include

    Returns:
        List of surrounding lines
    """
    if not line_no or line_no <= 0:
        return []

    start = max(0, line_no - context_size - 1)
    end = min(len(lines), line_no + context_size)
    return lines[start:end]


def format_line_context(lines: list[str], line_no: int, context_size: int = 2) -> str:
    """
    Format lines with context for error display.

    Args:
        lines: All lines of code
        line_no: Line number to highlight (1-based)
        context_size: Number of lines before/after to include

    Returns:
        Formatted string with line numbers and highlighting
    """
    if not lines or line_no <= 0:
        return ""

    start_line = max(1, line_no - context_size)
    end_line = min(len(lines), line_no + context_size)

    context_lines = []
    for i in range(start_line, end_line + 1):
        if i <= len(lines):
            line_content = lines[i - 1]
            marker = " -> " if i == line_no else "    "
            context_lines.append(f"{marker}{i:3d}: {line_content}")

    return "\n".join(context_lines)


def count_leading_whitespace(line: str) -> int:
    """
    Count leading whitespace characters in a line.

    Args:
        line: Line of code

    Returns:
        Number of leading whitespace characters
    """
    return len(line) - len(line.lstrip())


def normalize_code_for_comparison(code: str) -> str:
    """
    Normalize code for comparison by removing extra whitespace.

    Args:
        code: Python code string

    Returns:
        Normalized code string
    """
    lines = code.split("\n")
    normalized_lines = []

    for line in lines:
        # Remove trailing whitespace but preserve leading indentation
        normalized_line = line.rstrip()
        if normalized_line:  # Only add non-empty lines
            normalized_lines.append(normalized_line)

    return "\n".join(normalized_lines)


def extract_code_metrics(code: str) -> dict[str, int]:
    """
    Extract basic metrics from code.

    Args:
        code: Python code string

    Returns:
        Dictionary with code metrics
    """
    lines = code.split("\n")

    # Count different types of lines
    total_lines = len(lines)
    blank_lines = sum(1 for line in lines if not line.strip())
    comment_lines = sum(1 for line in lines if line.strip().startswith("#"))
    code_lines = total_lines - blank_lines - comment_lines

    # Calculate average line length (excluding blank lines)
    non_blank_lines = [line for line in lines if line.strip()]
    avg_line_length = sum(len(line) for line in non_blank_lines) // max(len(non_blank_lines), 1)

    # Find longest line
    max_line_length = max(len(line) for line in lines) if lines else 0

    return {
        "total_lines": total_lines,
        "blank_lines": blank_lines,
        "comment_lines": comment_lines,
        "code_lines": code_lines,
        "avg_line_length": avg_line_length,
        "max_line_length": max_line_length,
    }


def calculate_complexity_score(code: str) -> float:
    """
    Calculate a simple complexity score for code.

    Args:
        code: Python code string

    Returns:
        Complexity score (higher = more complex)
    """
    try:
        import ast

        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return 0.0

    complexity = 0

    # Count various complexity indicators
    for node in ast.walk(tree):
        if isinstance(node, ast.If | ast.While | ast.For | ast.Try):
            complexity += 1
        elif isinstance(node, ast.FunctionDef):
            complexity += 0.5  # Functions add some complexity
        elif isinstance(node, ast.ClassDef):
            complexity += 0.5  # Classes add some complexity
        elif isinstance(node, ast.Lambda):
            complexity += 0.5  # Lambdas add complexity

    # Normalize by number of lines
    metrics = extract_code_metrics(code)
    code_lines = max(metrics["code_lines"], 1)

    return complexity / code_lines


def split_long_message(message: str, max_length: int = 80) -> list[str]:
    """
    Split a long message into multiple lines for better readability.

    Args:
        message: Message to split
        max_length: Maximum length per line

    Returns:
        List of message lines
    """
    if len(message) <= max_length:
        return [message]

    words = message.split()
    lines = []
    current_line = []
    current_length = 0

    for word in words:
        if current_length + len(word) + 1 <= max_length:
            current_line.append(word)
            current_length += len(word) + 1
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word)

    if current_line:
        lines.append(" ".join(current_line))

    return lines


def deduplicate_suggestions(suggestions: list[str]) -> list[str]:
    """
    Remove duplicate suggestions while preserving order.

    Args:
        suggestions: List of suggestion strings

    Returns:
        List with duplicates removed
    """
    seen = set()
    result = []

    for suggestion in suggestions:
        normalized = suggestion.lower().strip()
        if normalized not in seen:
            seen.add(normalized)
            result.append(suggestion)

    return result
