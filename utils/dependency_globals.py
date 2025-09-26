"""
Global Dependency Container and Convenience Functions

This module provides the global dependency container instance and convenience functions
for easy access to the dependency injection system.
"""

import threading
from typing import Any, Optional, TypeVar

from .dependency_container import DependencyContainer


def get_container(
    container: DependencyContainer | None, container_lock: threading.Lock
) -> DependencyContainer:
    """Get the dependency container."""
    if container is None:
        with container_lock:
            if container is None:
                container = DependencyContainer()

    return container


def resolve(name: str) -> Any:
    """Convenience function to resolve from global container."""
    return get_container().resolve(name)


def resolve_type(dependency_type: type[Any]) -> Any:
    """Convenience function to resolve by type from global container."""
    return get_container(_container, _container_lock).resolve_type(dependency_type)
