"""
Dependency Injection Enums

This module defines enums used in the dependency injection system,
including lifecycle scopes and dependency states.
"""

from enum import Enum


class Scope(Enum):
    """Dependency lifecycle scopes."""

    SINGLETON = "singleton"  # One instance for entire app
    TRANSIENT = "transient"  # New instance every time
    SCOPED = "scoped"  # One instance per scope/request


class LifecycleState(Enum):
    """States a dependency can be in."""

    REGISTERED = "registered"
    CREATING = "creating"
    CREATED = "created"
    DISPOSING = "disposing"
    DISPOSED = "disposed"
