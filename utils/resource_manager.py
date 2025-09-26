"""
Resource Manager for DinoAir 2.0
Handles proper resource lifecycle management and shutdown sequencing
"""

import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from .performance_monitor import performance_monitor

try:
    from .logger import Logger
except ImportError:
    from logger import Logger

logger = Logger()


# Enhanced logging for production environments
class ResourceManagerLogger:
    """Enhanced logger for resource management operations."""

    def __init__(self, base_logger: Any = None):
        self.base_logger = base_logger or logger
        self.context_stack: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def _get_context(self) -> dict[str, Any]:
        """Get current logging context."""
        context = {}
        for ctx in self.context_stack:
            context.update(ctx)
        return context

    def _format_message(self, message: str, extra_context: dict[str, Any] | None = None) -> str:
        """Format message with context information."""
        context = self._get_context()
        if extra_context:
            context.update(extra_context)

        if context:
            context_str = ", ".join(f"{k}={v}" for k, v in context.items())
            return f"[{context_str}] {message}"
        return message

    @contextmanager
    def context(self, **context_vars: Any) -> Generator[None, None, None]:
        """Add context for logging operations."""
        with self._lock:
            self.context_stack.append(context_vars)
        try:
            yield
        finally:
            with self._lock:
                if self.context_stack:
                    self.context_stack.pop()

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message with context."""
        formatted_msg = self._format_message(message, kwargs)
        self.base_logger.debug(formatted_msg)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message with context."""
        formatted_msg = self._format_message(message, kwargs)
        self.base_logger.info(formatted_msg)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message with context."""
        formatted_msg = self._format_message(message, kwargs)
        self.base_logger.warning(formatted_msg)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message with context."""
        formatted_msg = self._format_message(message, kwargs)
        self.base_logger.error(formatted_msg)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message with context."""
        formatted_msg = self._format_message(message, kwargs)
        self.base_logger.critical(formatted_msg)


@dataclass
class OperationMetrics:
    """Metrics for resource operations."""

    operation_name: str
    resource_id: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    duration: float | None = None
    success: bool = False
    error: Exception | None = None
    retry_count: int = 0

    def complete(self, success: bool = True, error: Exception | None = None) -> None:
        """Mark operation as complete."""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.success = success
        self.error = error


@contextmanager
def timed_operation(
    operation_name: str,
    resource_id: str | None = None,
    rm_logger: ResourceManagerLogger | None = None,
) -> Generator[OperationMetrics, None, None]:
    """Context manager for timing operations with logging."""
    metrics = OperationMetrics(operation_name=operation_name, resource_id=resource_id)
    rm_logger = rm_logger or ResourceManagerLogger()

    context = {"operation": operation_name}
    if resource_id:
        context["resource_id"] = resource_id

    with rm_logger.context(**context):
        rm_logger.debug(f"Starting {operation_name}")
        try:
            yield metrics
            metrics.complete(success=True)
            rm_logger.debug(f"Completed {operation_name} in {metrics.duration:.3f}s")
        except Exception as e:
            metrics.complete(success=False, error=e)
            rm_logger.error(f"Failed {operation_name} after {metrics.duration:.3f}s: {e}")
            raise


# Custom Exception Classes for Resource Management


class AtomicCounter:
    """Thread-safe atomic counter."""

    def __init__(self, initial_value: int = 0):
        self._value = initial_value
        self._lock = threading.Lock()

    def increment(self, amount: int = 1) -> int:
        """Atomically increment and return new value."""
        with self._lock:
            self._value += amount
            return self._value

    def decrement(self, amount: int = 1) -> int:
        """Atomically decrement and return new value."""
        with self._lock:
            self._value -= amount
            return self._value

    def get(self) -> int:
        """Get current value."""
        with self._lock:
            return self._value

    def set(self, value: int) -> int:
        """Set value and return old value."""
        with self._lock:
            old_value = self._value
            self._value = value
            return old_value


class ThreadSafeResourceRegistry:
    """Thread-safe registry for resources with optimized read access."""

    def __init__(self):
        self._resources: dict[str, ResourceInfo] = {}
        self._read_lock = threading.RLock()  # Allows multiple readers
        self._write_lock = threading.Lock()  # Exclusive for writers
        self._resource_count = AtomicCounter()

    def get(self, resource_id: str) -> ResourceInfo | None:
        """Get resource with optimized read access."""
        with self._read_lock:
            return self._resources.get(resource_id)

    def put(self, resource_id: str, resource_info: ResourceInfo) -> bool:
        """Add or update resource."""
        with self._write_lock:
            is_new = resource_id not in self._resources
            self._resources[resource_id] = resource_info
            if is_new:
                self._resource_count.increment()
            return is_new

    def remove(self, resource_id: str) -> ResourceInfo | None:
        """Remove resource if exists."""
        with self._write_lock:
            resource_info = self._resources.pop(resource_id, None)
            if resource_info:
                self._resource_count.decrement()
            return resource_info

    def list_all(self) -> list[ResourceInfo]:
        """Get snapshot of all resources."""
        with self._read_lock:
            return list(self._resources.values())

    def list_by_type(self, resource_type: "ResourceType") -> list["ResourceInfo"]:
        """Get resources of specific type."""
        with self._read_lock:
            return [r for r in self._resources.values() if r.resource_type == resource_type]

    def list_by_state(self, state: "ResourceState") -> list["ResourceInfo"]:
        """Get resources in specific state."""
        with self._read_lock:
            return [r for r in self._resources.values() if r.state == state]

    def count(self) -> int:
        """Get current resource count."""
        return self._resource_count.get()

    def contains(self, resource_id: str) -> bool:
        """Check if resource exists."""
        with self._read_lock:
            return resource_id in self._resources

    def get_ids(self) -> set[str]:
        """Get set of all resource IDs."""
        with self._read_lock:
            return set(self._resources.keys())


# Custom Exception Classes for Resource Management
class ResourceManagerError(Exception):
    """Base exception for resource manager errors."""

    def __init__(self, message: str, resource_id: str | None = None, error_code: str | None = None):
        super().__init__(message)
        self.resource_id = resource_id
        self.error_code = error_code
        self.timestamp = datetime.now()


class ResourceRegistrationError(ResourceManagerError):
    """Exception raised when resource registration fails."""


class ResourceShutdownError(ResourceManagerError):
    """Exception raised when resource shutdown fails."""

    def __init__(
        self,
        message: str,
        resource_id: str | None = None,
        timeout_exceeded: bool = False,
        nested_exception: Exception | None = None,
    ):
        super().__init__(message, resource_id, "SHUTDOWN_FAILED")
        self.timeout_exceeded = timeout_exceeded
        self.nested_exception = nested_exception


class CircularDependencyError(ResourceManagerError):
    """Exception raised when circular dependencies are detected."""

    def __init__(self, message: str, cycle_path: list[str] | None = None):
        super().__init__(message, error_code="CIRCULAR_DEPENDENCY")
        self.cycle_path = cycle_path or []


class ResourceNotFoundError(ResourceManagerError):
    """Exception raised when a requested resource is not found."""

    def __init__(self, resource_id: str):
        super().__init__(f"Resource not found: {resource_id}", resource_id, "RESOURCE_NOT_FOUND")


class DependencyValidationError(ResourceManagerError):
    """Exception raised when dependency validation fails."""

    def __init__(self, message: str, invalid_dependencies: list[str] | None = None):
        super().__init__(message, error_code="DEPENDENCY_VALIDATION_FAILED")
        self.invalid_dependencies = invalid_dependencies or []


@dataclass
class RetryConfig:
    """Configuration for retry mechanisms."""

    max_attempts: int = 3
    base_delay: float = 0.1
    max_delay: float = 5.0
    backoff_factor: float = 2.0
    retry_exceptions: tuple[type[Exception], ...] = (
        Exception,
    )  # Will be updated after class definition

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt using exponential backoff."""
        delay = self.base_delay * (self.backoff_factor**attempt)
        return min(delay, self.max_delay)


class ResourceType(Enum):
    """Types of resources managed by the resource manager."""

    DATABASE = "database"
    THREAD = "thread"
    TIMER = "timer"
    WATCHDOG = "watchdog"
    FILE_HANDLE = "file_handle"
    NETWORK = "network"
    GUI_COMPONENT = "gui_component"
    CUSTOM = "custom"


class ResourceState(Enum):
    """States a resource can be in."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    SHUTTING_DOWN = "shutting_down"
    SHUTDOWN = "shutdown"
    ERROR = "error"


@dataclass
class ResourceInfo:
    """Information about a managed resource."""

    resource_id: str
    resource_type: ResourceType
    resource: Any
    cleanup_func: Callable[[], None] | None = None
    shutdown_timeout: float = 10.0
    priority: int = 100  # Lower number = higher priority (shutdown first)
    state: ResourceState = ResourceState.INITIALIZING
    created_at: datetime = field(default_factory=datetime.now)
    shutdown_at: datetime | None = None
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Error tracking
    last_error: Exception | None = None
    error_count: int = 0
    retry_attempts: int = 0
    max_retries: int = 3


class ResourceManager:
    """
    Centralized resource management with proper shutdown sequencing.

    Manages lifecycle of all application resources and ensures proper
    cleanup order during application shutdown.
    """

    def __init__(self, retry_config: RetryConfig | None = None) -> None:
        self._resources: dict[str, ResourceInfo] = {}
        self._lock = threading.RLock()
        self._shutdown_initiated = False
        self._shutdown_event = threading.Event()
        self._retry_config = retry_config or RetryConfig()
        self._logger = ResourceManagerLogger()  # Enhanced logger

        # Update retry config with proper exception types
        self._retry_config.retry_exceptions = (
            ResourceShutdownError,
            ConnectionError,
            TimeoutError,
            OSError,
        )

        # Shutdown priorities (lower = shutdown first)
        self._shutdown_priorities = {
            ResourceType.GUI_COMPONENT: 10,
            ResourceType.TIMER: 20,
            ResourceType.WATCHDOG: 30,
            ResourceType.THREAD: 40,
            ResourceType.NETWORK: 50,
            ResourceType.FILE_HANDLE: 60,
            ResourceType.DATABASE: 70,
            ResourceType.CUSTOM: 80,
        }

    def _retry_operation(
        self, operation: Callable[[], Any], operation_name: str, resource_id: str | None = None
    ) -> Any:
        """
        Execute an operation with retry logic.

        Args:
            operation: Function to execute
            operation_name: Name of operation for logging
            resource_id: Optional resource ID for context

        Returns:
            Result of operation

        Raises:
            ResourceManagerError: If all retry attempts fail
        """
        last_exception = None
        retry_config = self._retry_config

        for attempt in range(retry_config.max_attempts):
            try:
                if attempt > 0:
                    delay = retry_config.calculate_delay(attempt - 1)
                    logger.debug(
                        f"Retrying {operation_name} for {resource_id} (attempt {attempt + 1}/{retry_config.max_attempts}) after {delay:.2f}s delay"
                    )
                    time.sleep(delay)

                result = operation()
                if attempt > 0:
                    logger.info(
                        f"{operation_name} succeeded for {resource_id} on attempt {attempt + 1}"
                    )
                return result

            except Exception as e:
                last_exception = e

                # Check if this exception should be retried
                if not any(isinstance(e, exc_type) for exc_type in retry_config.retry_exceptions):
                    logger.warning(
                        f"{operation_name} failed for {resource_id} with non-retryable error: {e}"
                    )
                    raise

                logger.warning(
                    f"{operation_name} failed for {resource_id} (attempt {attempt + 1}/{retry_config.max_attempts}): {e}"
                )

                # If this was the last attempt, don't wait

        logger.error(
            f"{operation_name} failed for {resource_id} after {retry_config.max_attempts} attempts"
        )
        if last_exception:
            raise ResourceManagerError(
                f"{operation_name} failed after {retry_config.max_attempts} attempts", resource_id
            ) from last_exception
        raise ResourceManagerError(
            f"{operation_name} failed after {retry_config.max_attempts} attempts", resource_id
        )

    def _handle_error(
        self, error: Exception, resource_id: str | None = None, operation: str = "unknown"
    ) -> None:
        """
        Handle and log errors with proper categorization.

        Args:
            error: The exception that occurred
            resource_id: Optional resource ID for context
            operation: Name of operation that failed
        """
        error_info = {
            "operation": operation,
            "resource_id": resource_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.now().isoformat(),
        }

        # Update resource error tracking if applicable
        if resource_id and resource_id in self._resources:
            resource_info = self._resources[resource_id]
            resource_info.last_error = error
            resource_info.error_count += 1

        # Log based on error severity
        if isinstance(error, (ResourceNotFoundError, DependencyValidationError)):
            logger.warning(f"Resource management warning: {error_info}")
        elif isinstance(error, CircularDependencyError):
            logger.error(f"Critical resource management error: {error_info}")
        else:
            logger.error(f"Resource management error: {error_info}")

    def _validate_resource_registration(
        self,
        resource_id: str,
        resource: Any,
        resource_type: ResourceType,
        dependencies: list[str] | None = None,
    ) -> None:
        """
        Validate resource registration parameters.

        Args:
            resource_id: ID of resource to register
            resource: The resource object
            resource_type: Type of resource
            dependencies: List of dependency IDs

        Raises:
            ResourceRegistrationError: If validation fails
        """
        if not resource_id or not isinstance(resource_id, str):
            raise ResourceRegistrationError("Resource ID must be a non-empty string", resource_id)

        if resource is None:
            raise ResourceRegistrationError("Resource cannot be None", resource_id)

        if not isinstance(resource_type, ResourceType):
            raise ResourceRegistrationError("Invalid resource type", resource_id)

        if resource_id in self._resources:
            raise ResourceRegistrationError(
                f"Resource {resource_id} is already registered", resource_id
            )

        # Validate dependencies exist
        if dependencies:
            missing_deps = [dep for dep in dependencies if dep not in self._resources]
            if missing_deps:
                raise DependencyValidationError(
                    f"Missing dependencies for {resource_id}", missing_deps
                )

    @performance_monitor(operation="register_resource")
    def register_resource(
        self,
        resource_id: str,
        resource: Any,
        resource_type: ResourceType,
        cleanup_func: Callable[[], None] | None = None,
        shutdown_timeout: float = 10.0,
        priority: int | None = None,
        dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Register a resource for management.

        Args:
            resource_id: Unique identifier for the resource
            resource: The actual resource object
            resource_type: Type of resource
            cleanup_func: Function to call for cleanup (optional)
            shutdown_timeout: Max time to wait for shutdown
            priority: Shutdown priority (lower = first)
            dependencies: List of resource IDs this depends on
            metadata: Additional metadata about the resource

        Raises:
            ResourceRegistrationError: If registration fails
            DependencyValidationError: If dependencies are invalid
        """
        try:
            with self._lock:
                if self._shutdown_initiated:
                    raise ResourceRegistrationError(
                        f"Cannot register resource {resource_id} - shutdown in progress",
                        resource_id,
                    )

                # Validate registration parameters
                self._validate_resource_registration(
                    resource_id, resource, resource_type, dependencies
                )

                if priority is None:
                    priority = self._shutdown_priorities.get(resource_type, 100)

                resource_info = ResourceInfo(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    resource=resource,
                    cleanup_func=cleanup_func,
                    shutdown_timeout=shutdown_timeout,
                    priority=priority,
                    dependencies=dependencies or [],
                    metadata=metadata or {},
                )

                self._resources[resource_id] = resource_info
                resource_info.state = ResourceState.ACTIVE

                logger.info(f"Registered resource: {resource_id} ({resource_type.value})")

        except Exception as e:
            self._handle_error(e, resource_id, "register_resource")
            raise

    def unregister_resource(self, resource_id: str) -> bool:
        """
        Unregister a resource from management.

        Args:
            resource_id: ID of resource to unregister

        Returns:
            True if resource was found and removed
        """
        with self._lock:
            if resource_id in self._resources:
                resource_info = self._resources[resource_id]

                # If resource is still active, try to shut it down
                if resource_info.state == ResourceState.ACTIVE:
                    self._shutdown_single_resource(resource_info)

                del self._resources[resource_id]
                logger.info(f"Unregistered resource: {resource_id}")
                return True
            return False

    def get_resource(self, resource_id: str) -> Any | None:
        """Get a managed resource by ID."""
        with self._lock:
            resource_info = self._resources.get(resource_id)
            return resource_info.resource if resource_info else None

    def get_resource_info(self, resource_id: str) -> ResourceInfo | None:
        """Get resource information by ID."""
        with self._lock:
            return self._resources.get(resource_id)

    def list_resources(self, resource_type: ResourceType | None = None) -> list[ResourceInfo]:
        """List all managed resources, optionally filtered by type."""
        with self._lock:
            resources = list(self._resources.values())
            if resource_type:
                resources = [r for r in resources if r.resource_type == resource_type]
            return resources

    def get_resource_status(self) -> dict[str, Any]:
        """Get overall resource manager status."""
        with self._lock:
            resources_by_type: dict[str, int] = {}
            resources_by_state: dict[str, int] = {}

            for resource_info in self._resources.values():
                # Count by type
                type_name = resource_info.resource_type.value
                resources_by_type[type_name] = resources_by_type.get(type_name, 0) + 1

                # Count by state
                state_name = resource_info.state.value
                resources_by_state[state_name] = resources_by_state.get(state_name, 0) + 1

            status: dict[str, Any] = {
                "total_resources": len(self._resources),
                "shutdown_initiated": self._shutdown_initiated,
                "resources_by_type": resources_by_type,
                "resources_by_state": resources_by_state,
            }

            return status

    @performance_monitor(operation="shutdown_all_resources")
    def shutdown_all_resources(self, timeout: float = 30.0) -> bool:
        """
        Shutdown all managed resources in proper order.

        Args:
            timeout: Maximum time to wait for all shutdowns

        Returns:
            True if all resources were shutdown successfully
        """
        logger.info("Initiating resource manager shutdown...")

        with self._lock:
            if self._shutdown_initiated:
                logger.warning("Shutdown already in progress")
                return True

            self._shutdown_initiated = True
            self._shutdown_event.clear()

        start_time = time.time()
        success = True

        try:
            # Get resources sorted by shutdown priority and dependencies
            shutdown_order = self._calculate_shutdown_order()

            logger.info(f"Shutting down {len(shutdown_order)} resources...")

            for resource_info in shutdown_order:
                elapsed = time.time() - start_time
                remaining_time = timeout - elapsed
                if remaining_time <= 0:
                    logger.error("Shutdown timeout exceeded")
                    success = False
                    break

                individual_timeout = min(resource_info.shutdown_timeout, remaining_time)

                if not self._shutdown_single_resource(resource_info, individual_timeout):
                    logger.error(f"Failed to shutdown resource: {resource_info.resource_id}")
                    success = False

            # Clean up any remaining resources
            with self._lock:
                failed_resources = [
                    r.resource_id
                    for r in self._resources.values()
                    if r.state not in (ResourceState.SHUTDOWN, ResourceState.ERROR)
                ]

                if failed_resources:
                    logger.warning(f"Resources failed to shutdown cleanly: {failed_resources}")
                    success = False

        except RuntimeError as e:
            logger.error(f"Error during resource shutdown: {e}")
            success = False

        finally:
            self._shutdown_event.set()
            total_time = time.time() - start_time
            logger.info(f"Resource shutdown completed in {total_time:.2f}s (success: {success})")

        return success

    def _calculate_shutdown_order(self) -> list[ResourceInfo]:
        """Calculate the proper shutdown order considering priorities and dependencies."""
        with self._lock:
            resources = list(self._resources.values())

            # Filter to only active resources
            active_resources = [r for r in resources if r.state == ResourceState.ACTIVE]

            if not active_resources:
                return []

            # Perform dependency resolution using topological sorting
            ordered_resources = self._resolve_shutdown_dependencies(active_resources)

            # Within each dependency level, sort by priority (lower = shutdown first)
            # This ensures dependencies are respected while maintaining priority ordering
            return self._apply_priority_within_dependency_order(ordered_resources)

    def _resolve_shutdown_dependencies(self, resources: list[ResourceInfo]) -> list[ResourceInfo]:
        """
        Resolve resource dependencies using topological sorting for shutdown order.

        Resources that depend on others must be shut down BEFORE their dependencies.
        This is the reverse of startup dependency order.

        Args:
            resources: List of resources to order

        Returns:
            Resources ordered for safe shutdown (dependents before dependencies)
        """
        # Create resource lookup map
        resource_map = {r.resource_id: r for r in resources}

        # Build dependency graph (for shutdown, we reverse the dependencies)
        # If A depends on B, then A must shut down before B
        shutdown_graph: dict[str, set[str]] = {r.resource_id: set() for r in resources}
        in_degree = {r.resource_id: 0 for r in resources}

        for resource in resources:
            for dependency_id in resource.dependencies:
                # If dependency exists in our active resources
                if dependency_id in resource_map:
                    # For shutdown: dependency must be shut down AFTER the resource that depends on it
                    shutdown_graph[dependency_id].add(resource.resource_id)
                    in_degree[resource.resource_id] += 1

        # Detect circular dependencies
        circular_deps = self._detect_circular_dependencies(
            shutdown_graph, list(resource_map.keys())
        )
        if circular_deps:
            logger.warning(f"Circular dependencies detected: {circular_deps}")
            # Fall back to priority-only ordering for circular dependencies
            return self._fallback_priority_ordering(resources)

        # Perform topological sort using Kahn's algorithm
        ordered_ids = []
        queue = [rid for rid in resource_map if in_degree[rid] == 0]

        while queue:
            # Sort queue by priority to maintain ordering within same dependency level
            queue.sort(key=lambda rid: resource_map[rid].priority)
            current_id = queue.pop(0)
            ordered_ids.append(current_id)

            # Update in-degrees for dependent resources
            for dependent_id in shutdown_graph[current_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        # Verify all resources were processed (no remaining cycles)
        if len(ordered_ids) != len(resources):
            logger.warning("Dependency resolution incomplete - possible circular dependencies")
            return self._fallback_priority_ordering(resources)

        # Convert IDs back to ResourceInfo objects
        return [resource_map[rid] for rid in ordered_ids]

    def _detect_circular_dependencies(
        self, graph: dict[str, set[str]], nodes: list[str]
    ) -> list[list[str]]:
        """
        Detect circular dependencies in the resource graph.

        Args:
            graph: Adjacency list representation of dependencies
            nodes: List of all node IDs

        Returns:
            List of circular dependency paths found
        """
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs_cycle_detection(node: str, path: list[str]) -> bool:
            """DFS to detect cycles."""
            if node in rec_stack:
                # Found a cycle - extract the cycle path
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return True

            if node in visited:
                return False

            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, set()):
                if dfs_cycle_detection(neighbor, path):
                    break  # Stop after finding first cycle in this path

            rec_stack.remove(node)
            path.pop()
            return False

        for node in nodes:
            if node not in visited:
                dfs_cycle_detection(node, [])

        return cycles

    def _fallback_priority_ordering(self, resources: list[ResourceInfo]) -> list[ResourceInfo]:
        """
        Fallback to simple priority-based ordering when dependency resolution fails.

        Args:
            resources: Resources to order

        Returns:
            Resources sorted by priority only
        """
        logger.info("Using fallback priority-based ordering")
        return sorted(resources, key=lambda r: r.priority)

    def _apply_priority_within_dependency_order(
        self, ordered_resources: list[ResourceInfo]
    ) -> list[ResourceInfo]:
        """
        Apply priority ordering within groups of resources that have no dependency constraints.

        This maintains the dependency order while optimizing shutdown within each "level".

        Args:
            ordered_resources: Resources already ordered by dependencies

        Returns:
            Resources with priority optimization applied
        """
        # For now, the topological sort already considers priority within each level
        # This method is a placeholder for more sophisticated priority optimization
        return ordered_resources

    def add_resource_dependency(self, resource_id: str, dependency_id: str) -> bool:
        """
        Add a dependency relationship between resources.

        Args:
            resource_id: Resource that depends on dependency_id
            dependency_id: Resource that resource_id depends on

        Returns:
            True if dependency was added successfully
        """
        with self._lock:
            if resource_id not in self._resources:
                logger.error(f"Resource {resource_id} not found")
                return False

            if dependency_id not in self._resources:
                logger.error(f"Dependency resource {dependency_id} not found")
                return False

            resource_info = self._resources[resource_id]
            if dependency_id not in resource_info.dependencies:
                resource_info.dependencies.append(dependency_id)
                logger.info(f"Added dependency: {resource_id} -> {dependency_id}")

                # Verify no circular dependencies were created
                all_resources = list(self._resources.values())
                test_order = self._resolve_shutdown_dependencies(all_resources)
                if len(test_order) != len(all_resources):
                    # Circular dependency detected, remove the added dependency
                    resource_info.dependencies.remove(dependency_id)
                    logger.error(
                        f"Circular dependency detected, removed: {resource_id} -> {dependency_id}"
                    )
                    return False

            return True

    def remove_resource_dependency(self, resource_id: str, dependency_id: str) -> bool:
        """
        Remove a dependency relationship between resources.

        Args:
            resource_id: Resource to remove dependency from
            dependency_id: Dependency to remove

        Returns:
            True if dependency was removed successfully
        """
        with self._lock:
            if resource_id not in self._resources:
                logger.error(f"Resource {resource_id} not found")
                return False

            resource_info = self._resources[resource_id]
            if dependency_id in resource_info.dependencies:
                resource_info.dependencies.remove(dependency_id)
                logger.info(f"Removed dependency: {resource_id} -> {dependency_id}")
                return True

            return False

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """
        Get the current dependency graph for all resources.

        Returns:
            Dictionary mapping resource IDs to their dependencies
        """
        with self._lock:
            return {
                resource_id: resource_info.dependencies.copy()
                for resource_id, resource_info in self._resources.items()
            }

    def validate_dependencies(self) -> dict[str, Any]:
        """
        Validate the current dependency configuration.

        Returns:
            Dictionary with validation results including any issues found
        """
        with self._lock:
            resources = list(self._resources.values())
            issues = []

            # Check for missing dependencies
            all_resource_ids = set(self._resources.keys())
            for resource in resources:
                for dep_id in resource.dependencies:
                    if dep_id not in all_resource_ids:
                        issues.append(
                            f"Resource {resource.resource_id} depends on non-existent resource {dep_id}"
                        )

            # Check for circular dependencies
            circular_deps = self._detect_circular_dependencies(
                {r.resource_id: set(r.dependencies) for r in resources}, list(all_resource_ids)
            )

            if circular_deps:
                issues.extend(
                    [f"Circular dependency: {' -> '.join(cycle)}" for cycle in circular_deps]
                )

            # Test dependency resolution
            try:
                ordered_resources = self._resolve_shutdown_dependencies(resources)
                resolution_success = len(ordered_resources) == len(resources)
            except Exception as e:
                resolution_success = False
                issues.append(f"Dependency resolution failed: {str(e)}")

            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "circular_dependencies": circular_deps,
                "resolution_success": resolution_success,
                "total_resources": len(resources),
                "total_dependencies": sum(len(r.dependencies) for r in resources),
            }

    @staticmethod
    def _shutdown_single_resource(
        resource_info: ResourceInfo, timeout: float | None = None
    ) -> bool:
        """
        Shutdown a single resource.

        Args:
            resource_info: Information about the resource to shutdown
            timeout: Maximum time to wait for shutdown

        Returns:
            True if shutdown was successful
        """
        if timeout is None:
            timeout = resource_info.shutdown_timeout

        resource_id = resource_info.resource_id
        logger.info(f"Shutting down resource: {resource_id}")

        try:
            resource_info.state = ResourceState.SHUTTING_DOWN
            start_time = time.time()

            # Call custom cleanup function if provided
            if resource_info.cleanup_func:
                logger.debug(f"Calling cleanup function for {resource_id}")

                # Run cleanup in separate thread to enforce timeout
                cleanup_result = {"completed": False, "exception": None}

                def cleanup_wrapper():
                    """Cleanup wrapper."""
                    try:
                        resource_info.cleanup_func()
                        cleanup_result["completed"] = True
                    except Exception as e:
                        cleanup_result["exception"] = e
                        cleanup_result["completed"] = True

                cleanup_thread = threading.Thread(target=cleanup_wrapper, daemon=True)
                cleanup_start = time.time()
                cleanup_thread.start()

                # Wait for cleanup to complete with timeout
                cleanup_thread.join(timeout=timeout)

                cleanup_elapsed = time.time() - cleanup_start

                if cleanup_thread.is_alive():
                    logger.warning(
                        f"Cleanup function for {resource_id} timed out after {cleanup_elapsed:.2f}s "
                        f"(timeout: {timeout}s). Resource may not be fully cleaned up."
                    )
                elif cleanup_result["exception"]:
                    logger.error(
                        f"Cleanup function for {resource_id} raised exception: {cleanup_result['exception']}"
                    )
                    resource_info.state = ResourceState.ERROR
                    return False
                else:
                    logger.debug(
                        f"Cleanup function for {resource_id} completed in {cleanup_elapsed:.2f}s"
                    )

            # Try standard cleanup methods if no custom function
            else:
                resource = resource_info.resource

                # Try common cleanup methods
                if hasattr(resource, "close"):
                    resource.close()
                elif hasattr(resource, "shutdown"):
                    resource.shutdown()
                elif hasattr(resource, "stop"):
                    resource.stop()
                elif hasattr(resource, "quit"):
                    resource.quit()
                else:
                    logger.debug(f"No cleanup method found for {resource_id}")

            # Mark as shutdown
            resource_info.state = ResourceState.SHUTDOWN
            resource_info.shutdown_at = datetime.now()

            elapsed = time.time() - start_time
            logger.info(f"Resource {resource_id} shutdown in {elapsed:.2f}s")
            return True

        except RuntimeError as e:
            logger.error(f"Error shutting down resource {resource_id}: {e}")
            resource_info.state = ResourceState.ERROR
            return False

    def wait_for_shutdown(self, timeout: float = 30.0) -> bool:
        """
        Wait for shutdown to complete.

        Args:
            timeout: Maximum time to wait

        Returns:
            True if shutdown completed within timeout
        """
        return self._shutdown_event.wait(timeout)

    def force_shutdown_resource(self, resource_id: str) -> bool:
        """
        Force shutdown of a specific resource.

        Args:
            resource_id: ID of resource to force shutdown

        Returns:
            True if resource was found and shutdown attempted
        """
        with self._lock:
            resource_info = self._resources.get(resource_id)
            if not resource_info:
                return False

            logger.warning(f"Force shutting down resource: {resource_id}")
            return self._shutdown_single_resource(resource_info, timeout=5.0)


# Global instance
_resource_manager: Optional["ResourceManager"] = None
_manager_lock = threading.Lock()


_resource_manager: ResourceManager | None = None


def get_resource_manager(_resource_manager_container=None) -> ResourceManager:
    """Get the global resource manager instance."""
    if _resource_manager_container is None:
        _resource_manager_container = [None]
    if _resource_manager_container[0] is None:
        with _manager_lock:
            if _resource_manager_container[0] is None:
                _resource_manager_container[0] = ResourceManager()

    return _resource_manager_container[0]


def register_resource(
    resource_id: str,
    resource: Any,
    resource_type: ResourceType,
    cleanup_func: Callable[[], None] | None = None,
    shutdown_timeout: float = 10.0,
    priority: int | None = None,
    dependencies: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Convenience function to register a resource with the global manager."""
    get_resource_manager().register_resource(
        resource_id=resource_id,
        resource=resource,
        resource_type=resource_type,
        cleanup_func=cleanup_func,
        shutdown_timeout=shutdown_timeout,
        priority=priority,
        dependencies=dependencies,
        metadata=metadata,
    )


def shutdown_all_resources(timeout: float = 30.0) -> bool:
    """Convenience function to shutdown all resources via the global manager."""
    return get_resource_manager().shutdown_all_resources(timeout=timeout)
