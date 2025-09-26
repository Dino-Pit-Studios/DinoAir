"""
Dependency Injection Exceptions

This module defines custom exceptions used in the dependency injection system
for handling resolution errors and circular dependencies.
"""


class DependencyResolutionError(Exception):
    """Raised when dependency resolution fails."""


class CircularDependencyError(DependencyResolutionError):
    """Raised when a circular dependency is detected."""
