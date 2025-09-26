# pylint: disable=too-many-instance-attributes,logging-fstring-interpolation,logging-format-interpolation
"""
Dependency Injection Container for DinoAir 2.0
Manages dependencies and prevents circular dependency issues
"""

import inspect
import logging
import threading
import uuid
from collections.abc import Callable
from typing import Any, TypeVar, cast

# Import from new modules
from .dependency_enums import LifecycleState, Scope
from .dependency_exceptions import CircularDependencyError, DependencyResolutionError
from .dependency_info import DependencyInfo
from .dependency_scope import ScopeContext

# Import logger with fallback
try:
    from logger import Logger

    logger = Logger()
except ImportError:
    # Fallback to creating a basic logger
    logger = logging.getLogger(__name__)

T = TypeVar("T")


class DependencyContainer:  # pylint: disable=too-many-instance-attributes
    """
    Dependency injection container that manages object lifecycles
    and resolves dependencies automatically.
    """

    def __init__(self):
        self._dependencies: dict[str, DependencyInfo] = {}
        self._instances: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._resolution_stack: list[str] = []
        self._scoped_instances: dict[str, dict[str, Any]] = {}
        self._current_scope: str | None = None

    # Public accessors to manage current scope (avoid private attribute use from external helpers)
    def get_current_scope(self) -> str | None:
        """Read the current scope name, if any."""
        return self._current_scope

    def set_current_scope(self, scope_name: str | None) -> None:
        """Set or clear the current scope name."""
        self._current_scope = scope_name

    def register_singleton(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        name: str,
        dependency_type: type[T],
        factory: Callable[[], T] | None = None,
        dependencies: list[str] | None = None,
        initialization_order: int = 100,
    ) -> "DependencyContainer":
        """
        Register a singleton dependency.

        Args:
            name: Unique name for the dependency
            dependency_type: Type of the dependency
            factory: Optional factory function to create the instance
            dependencies: List of dependency names this depends on
            initialization_order: Order of initialization (higher = later)
        """
        return self._register(
            name,
            dependency_type,
            threading.Event(),
            factory,
            dependencies,
            initialization_order,
        )

    def register_transient(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        name: str,
        dependency_type: type[T],
        factory: Callable[[], T] | None = None,
        dependencies: list[str] | None = None,
        initialization_order: int = 100,
    ) -> "DependencyContainer":
        """Register a transient dependency (new instance each time)."""
        return self._register(
            name,
            dependency_type,
            factory,
            Scope.TRANSIENT,
            dependencies,
            initialization_order,
        )

    def register_scoped(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        name: str,
        dependency_type: type[T],
        factory: Callable[[], T] | None = None,
        dependencies: list[str] | None = None,
        initialization_order: int = 100,
    ) -> "DependencyContainer":
        """Register a scoped dependency (one instance per scope)."""
        return self._register(
            name,
            dependency_type,
            factory,
            Scope.SCOPED,
            dependencies,
            initialization_order,
        )

    def register_instance(
        self,
        name: str,
        instance: object,
        dependencies: list[str] | None = None,
    ) -> "DependencyContainer":
        """Register an existing instance as a singleton."""
        with self._lock:
            dependency_info = DependencyInfo(
                name=name,
                dependency_type=type(instance),
                instance=instance,
                scope=Scope.SINGLETON,
                dependencies=dependencies or [],
                state=LifecycleState.CREATED,
            )

            self._dependencies[name] = dependency_info
            self._instances[name] = instance

            logger.debug(f"Registered instance: {name}")
            return self

    def _register(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        name: str,
        dependency_type: type[Any],
        factory: Callable[..., Any] | None,
        scope: Scope,
        dependencies: list[str] | None,
        initialization_order: int,
    ) -> "DependencyContainer":
        """Internal registration method."""
        with self._lock:
            if name in self._dependencies:
                raise DependencyResolutionError(f"Dependency '{name}' already registered")

            dependency_info = DependencyInfo(
                name=name,
                dependency_type=dependency_type,
                factory=factory,
                scope=scope,
                dependencies=dependencies or [],
                initialization_order=initialization_order,
            )

            self._dependencies[name] = dependency_info
            logger.debug(f"Registered {scope.value} dependency: {name}")

            return self

    def resolve(self, name: str) -> Any:
        """
        Resolve a dependency by name.

        Args:
            name: Name of the dependency to resolve

        Returns:
            The resolved dependency instance

        Raises:
            DependencyResolutionError: If dependency cannot be resolved
            CircularDependencyError: If circular dependency detected
        """
        with self._lock:
            return self._resolve_internal(name)

    def resolve_type(self, dependency_type: type[T]) -> T:
        """
        Resolve a dependency by type.

        Args:
            dependency_type: Type of the dependency to resolve

        Returns:
            The resolved dependency instance
        """
        with self._lock:
            # Find dependency by type
            for name, info in self._dependencies.items():
                if info.dependency_type == dependency_type:
                    return self._resolve_internal(name)

            raise DependencyResolutionError(f"No dependency registered for type: {dependency_type}")

    def _resolve_internal(self, name: str) -> Any:
        """Internal dependency resolution with circular dependency detection."""
        self._validate_dependency_resolution(name)
        dependency_info = self._dependencies[name]

        # Try to get existing instance
        existing_instance = self._get_existing_instance(name, dependency_info)
        if existing_instance is not None:
            return existing_instance

        # For scoped, if no current scope, return None
        if dependency_info.scope == Scope.SCOPED and not self._current_scope:
            return None

        # Create new instance
        return self._create_and_store_instance(name, dependency_info)

    def _validate_dependency_resolution(self, name: str) -> None:
        """Validate that dependency can be resolved.

        Args:
            name: Name of the dependency to validate

        Raises:
            CircularDependencyError: If circular dependency is detected
            DependencyResolutionError: If dependency is unknown
        """
        if name in self._resolution_stack:
            cycle = " -> ".join(self._resolution_stack + [name])
            raise CircularDependencyError(f"Circular dependency detected: {cycle}")

        if name not in self._dependencies:
            raise DependencyResolutionError(f"Unknown dependency: {name}")

    def _get_existing_instance(self, name: str, dependency_info: DependencyInfo) -> Any | None:
        """Get existing instance if available based on scope.

        Args:
            name: Name of the dependency
            dependency_info: Dependency information

        Returns:
            Existing instance or None if not found
        """
        if dependency_info.scope == Scope.SINGLETON:
            return self._instances.get(name)

        if dependency_info.scope == Scope.SCOPED:
            return self._get_scoped_instance(name)

        return None

    def _get_scoped_instance(self, name: str) -> Any | None:
        """Get scoped instance if available.

        Args:
            name: Name of the dependency

        Returns:
            Scoped instance or None if not found
        """
        if not self._current_scope or self._current_scope not in self._scoped_instances:
            return None

        scoped_instances = self._scoped_instances[self._current_scope]
        return scoped_instances.get(name)

    def _create_and_store_instance(self, name: str, dependency_info: DependencyInfo) -> Any:
        """Create and store a new instance.

        Args:
            name: Name of the dependency
            dependency_info: Dependency information

        Returns:
            Created instance
        """
        try:
            self._resolution_stack.append(name)
            dependency_info.state = LifecycleState.CREATING

            instance = self._create_instance(dependency_info)
            dependency_info.state = LifecycleState.CREATED

            self._store_instance(name, instance, dependency_info.scope)
            return instance

        finally:
            self._resolution_stack.remove(name)

    def _store_instance(self, name: str, instance: Any, scope: Scope) -> None:
        """Store instance based on scope.

        Args:
            name: Name of the dependency
            instance: Created instance
            scope: Dependency scope
        """
        if scope == Scope.SINGLETON:
            self._instances[name] = instance
        elif scope == Scope.SCOPED and self._current_scope:
            if self._current_scope not in self._scoped_instances:
                self._scoped_instances[self._current_scope] = {}
            self._scoped_instances[self._current_scope][name] = instance

    def _create_instance(self, dependency_info: DependencyInfo) -> Any:
        """Create an instance of a dependency."""
        resolved_dependencies = self._resolve_dependencies(dependency_info.dependencies)

        if dependency_info.factory:
            return self._create_instance_with_factory(dependency_info, resolved_dependencies)

        return self._create_instance_with_constructor(dependency_info, resolved_dependencies)

    def _resolve_dependencies(self, dependencies: list[str]) -> dict[str, Any]:
        """Resolve all dependencies for an instance.

        Args:
            dependencies: List of dependency names to resolve

        Returns:
            Dictionary mapping dependency names to resolved instances
        """
        resolved_dependencies: dict[str, Any] = {
            dep_name: self._resolve_internal(dep_name) for dep_name in dependencies
        }
        return resolved_dependencies

    def _create_instance_with_factory(
        self, dependency_info: DependencyInfo, resolved_dependencies: dict[str, Any]
    ) -> Any:
        """Create instance using a factory function.

        Args:
            dependency_info: Information about the dependency
            resolved_dependencies: Already resolved dependencies

        Returns:
            Created instance

        Raises:
            DependencyResolutionError: If factory creation fails
        """
        try:
            factory = cast("Callable[..., Any]", dependency_info.factory)
            factory_kwargs = DependencyContainer._get_factory_kwargs(factory, resolved_dependencies)
            return factory(**factory_kwargs)
        except RuntimeError as e:
            raise DependencyResolutionError(
                f"Factory failed for {dependency_info.name}: {e}"
            ) from e

    def _create_instance_with_constructor(
        self, dependency_info: DependencyInfo, resolved_dependencies: dict[str, Any]
    ) -> Any:
        """Create instance using constructor.

        Args:
            dependency_info: Information about the dependency
            resolved_dependencies: Already resolved dependencies

        Returns:
            Created instance

        Raises:
            DependencyResolutionError: If constructor creation fails
        """
        try:
            constructor = dependency_info.dependency_type
            constructor_kwargs = DependencyContainer._get_constructor_kwargs(
                constructor, resolved_dependencies
            )
            return constructor(**constructor_kwargs)
        except RuntimeError as e:
            raise DependencyResolutionError(
                f"Constructor failed for {dependency_info.name}: {e}"
            ) from e

    @staticmethod
    def _get_factory_kwargs(
        factory: Callable[..., Any], resolved_dependencies: dict[str, Any]
    ) -> dict[str, Any]:
        """Get keyword arguments for factory function.

        Args:
            factory: Factory function
            resolved_dependencies: Available resolved dependencies

        Returns:
            Keyword arguments for the factory
        """
        sig = inspect.signature(factory)
        if not sig.parameters:
            return {}

        kwargs: dict[str, Any] = {
            param_name: resolved_dependencies[param_name]
            for param_name in sig.parameters
            if param_name in resolved_dependencies
        }
        return kwargs

    @staticmethod
    def _get_constructor_kwargs(
        constructor: type[Any], resolved_dependencies: dict[str, Any]
    ) -> dict[str, Any]:
        """Get keyword arguments for constructor.

        Args:
            constructor: Constructor function/class
            resolved_dependencies: Available resolved dependencies

        Returns:
            Keyword arguments for the constructor
        """
        sig = inspect.signature(constructor)
        if not sig.parameters:
            return {}

        kwargs: dict[str, Any] = {}

        # First, try to match by parameter name
        for param_name, param in sig.parameters.items():
            if param_name in resolved_dependencies:
                kwargs[param_name] = resolved_dependencies[param_name]

        # Then, try to match by type for unmatched parameters
        for param_name, param in sig.parameters.items():
            if param_name not in kwargs and param.annotation != inspect.Parameter.empty:
                # Find a dependency with matching type
                for _dep_name, dep_instance in resolved_dependencies.items():
                    # Check if annotation is actually a type before using isinstance
                    try:
                        # Handle forward references (string annotations)
                        if isinstance(param.annotation, str):
                            # Try to match by class name
                            if param.annotation == type(dep_instance).__name__:
                                kwargs[param_name] = dep_instance
                                break
                        elif isinstance(param.annotation, type) and isinstance(
                            dep_instance, param.annotation
                        ):
                            kwargs[param_name] = dep_instance
                            break
                    except TypeError:
                        # param.annotation is not a valid type for isinstance
                        continue

        return kwargs

    def create_scope(self, scope_name: str | None = None) -> "ScopeContext":
        """Create a new dependency scope context."""
        if scope_name is None:
            scope_name = str(uuid.uuid4())
        return ScopeContext(self, scope_name)

    def dispose_scope(self, scope_name: str) -> None:
        """Dispose of a dependency scope and its instances."""
        with self._lock:
            if scope_name in self._scoped_instances:
                scoped_instances = self._scoped_instances[scope_name]

                # Dispose instances in reverse creation order
                for instance in reversed(list(scoped_instances.values())):
                    self._dispose_instance(instance)

                del self._scoped_instances[scope_name]
                logger.debug(f"Disposed scope: {scope_name}")

    @staticmethod
    def _dispose_instance(instance: Any) -> None:
        """Dispose of an instance if it has disposal methods."""
        try:
            if hasattr(instance, "dispose"):
                instance.dispose()
            elif hasattr(instance, "close"):
                instance.close()
            elif hasattr(instance, "cleanup"):
                instance.cleanup()
        except RuntimeError as e:
            logger.warning(f"Error disposing instance: {str(e)}")

    def get_dependency_info(self, name: str) -> DependencyInfo | None:
        """Get information about a registered dependency."""
        return self._dependencies.get(name)

    def list_dependencies(self) -> list[DependencyInfo]:
        """List all registered dependencies."""
        return list(self._dependencies.values())

    def validate_dependencies(self) -> list[str]:
        """
        Validate all dependencies can be resolved.

        Returns:
            List of validation errors (empty if all valid)
        """
        errors: list[str] = []

        with self._lock:
            for name, info in self._dependencies.items():
                try:
                    # Check if all dependencies exist
                    errors.extend(
                        f"Dependency '{name}' requires unknown dependency '{dep_name}'"
                        for dep_name in info.dependencies
                        if dep_name not in self._dependencies
                    )
                    # Try to detect circular dependencies
                    try:
                        self._check_circular_dependency(name, set())
                    except CircularDependencyError as e:
                        errors.append(str(e))

                except RuntimeError as e:
                    errors.append(f"Error validating {name}: {e}")

        return errors

    def _check_circular_dependency(self, name: str, visited: set[str]) -> None:
        """Check for circular dependencies recursively."""
        if name in visited:
            raise CircularDependencyError(f"Circular dependency detected involving: {name}")

        if name not in self._dependencies:
            return

        visited.add(name)

        for dep_name in self._dependencies[name].dependencies:
            self._check_circular_dependency(dep_name, visited.copy())

    def initialize_all(self) -> bool:
        """
        Initialize all singleton dependencies in proper order.

        Returns:
            True if all dependencies initialized successfully
        """
        logger.info("Initializing all dependencies...")

        try:
            # Get singletons sorted by initialization order
            singletons = [
                info for info in self._dependencies.values() if info.scope == Scope.SINGLETON
            ]
            singletons.sort(key=lambda x: x.initialization_order)

            # Initialize each singleton
            for info in singletons:
                try:
                    self.resolve(info.name)
                    logger.debug(f"Initialized: {info.name}")
                except RuntimeError as e:
                    logger.error(f"Failed to initialize {info.name}: {e}")
                    return False

            logger.info("All dependencies initialized successfully")
            return True

        except RuntimeError as e:
            logger.error(f"Error during dependency initialization: {e}")
            return False

    def dispose_all(self) -> None:
        """Dispose of all managed instances."""
        logger.info("Disposing all dependencies...")

        with self._lock:
            # Dispose scoped instances first
            for scope_name in list(self._scoped_instances.keys()):
                self.dispose_scope(scope_name)

            # Dispose singletons in reverse initialization order
            singletons = [
                (name, info)
                for name, info in self._dependencies.items()
                if info.scope == Scope.SINGLETON and name in self._instances
            ]
            singletons.sort(key=lambda x: x[1].initialization_order, reverse=True)

            for name, info in singletons:
                try:
                    instance = self._instances[name]
                    self._dispose_instance(instance)
                    info.state = LifecycleState.DISPOSED
                except RuntimeError as e:
                    logger.warning(f"Error disposing {name}: {e}")

            self._instances.clear()
            logger.info("All dependencies disposed")


# Re-export all public classes and functions
__all__ = [
    "Scope",
    "LifecycleState",
    "DependencyInfo",
    "DependencyResolutionError",
    "CircularDependencyError",
    "DependencyContainer",
    "ScopeContext",
]
