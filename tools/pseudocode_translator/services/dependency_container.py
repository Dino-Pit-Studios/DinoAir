"""
Dependency Injection Container for the Pseudocode Translator

This module provides a lightweight dependency injection system to manage
service dependencies and enable better testability and modularity.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DependencyError(Exception):
    """Exception raised when dependency resolution fails."""


class DependencyContainer:
    """
    Lightweight dependency injection container.

    Supports singleton and transient lifetimes, factory functions,
    and automatic dependency resolution.
    """

    def __init__(self):
        self._services: dict[str, Any] = {}
        self._factories: dict[str, Callable[[], Any]] = {}
        self._singletons: dict[str, Any] = {}
        self._types: dict[str, type[Any]] = {}

    def register_singleton(self, service_type: type[T], instance: T) -> None:
        """Register a singleton instance."""
        key = self._get_key(service_type)
        self._singletons[key] = instance
        self._types[key] = service_type
        logger.debug("Registered singleton: %s", key)

    def register_factory(self, service_type: type[T], factory: Callable[[], T]) -> None:
        """Register a factory function for transient instances."""
        key = self._get_key(service_type)
        self._factories[key] = factory
        self._types[key] = service_type
        logger.debug("Registered factory: %s", key)

    def register_instance(self, service_type: type[T], instance: T) -> None:
        """Register a specific instance."""
        key = self._get_key(service_type)
        self._services[key] = instance
        self._types[key] = service_type
        logger.debug("Registered instance: %s", key)

    def resolve(self, service_type: type[T]) -> T:
        """Resolve a service instance."""
        key = self._get_key(service_type)

        # Check singletons first
        if key in self._singletons:
            return self._singletons[key]

        # Check registered instances
        if key in self._services:
            return self._services[key]

        # Check factories
        if key in self._factories:
            try:
                instance = self._factories[key]()
                logger.debug("Created instance via factory: %s", key)
                return instance
            except Exception as e:
                raise DependencyError(f"Failed to create instance of {key}") from e

        raise DependencyError(f"Service not registered: {key}")

    def try_resolve(self, service_type: type[T]) -> T | None:
        """Try to resolve a service, return None if not found."""
        try:
            return self.resolve(service_type)
        except DependencyError:
            return None

    def is_registered(self, service_type: type[T]) -> bool:
        """Check if a service type is registered."""
        key = self._get_key(service_type)
        return key in self._services or key in self._factories or key in self._singletons

    def clear(self) -> None:
        """Clear all registered services."""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()
        self._types.clear()
        logger.debug("Container cleared")

    def get_registered_types(self) -> list[type[Any]]:
        """Get list of all registered service types."""
        return list(self._types.values())

    @staticmethod
    def _get_key(service_type: type[Any]) -> str:
        """Generate a key for the service type."""
        return f"{service_type.__module__}.{service_type.__qualname__}"


# Global container instance
_container = DependencyContainer()


def get_container() -> DependencyContainer:
    """Get the global dependency container instance."""
    return _container


def register_singleton(service_type: type[T], instance: T) -> None:
    """Register a singleton instance in the global container."""
    _container.register_singleton(service_type, instance)


def register_factory(service_type: type[T], factory: Callable[[], T]) -> None:
    """Register a factory function in the global container."""
    _container.register_factory(service_type, factory)


def register_instance(service_type: type[T], instance: T) -> None:
    """Register an instance in the global container."""
    _container.register_instance(service_type, instance)


def resolve(service_type: type[Any]) -> Any:
    """Resolve a service from the global container."""
    return _container.resolve(service_type)


def try_resolve(service_type: type[Any]) -> Any | None:
    """Try to resolve a service from the global container."""
    return _container.try_resolve(service_type)
