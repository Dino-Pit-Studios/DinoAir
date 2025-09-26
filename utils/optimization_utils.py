"""
Optimization utilities for DinoAir 2.5
Implements Phase 1 critical performance fixes
"""

from __future__ import annotations

import importlib
import logging
import re
import threading
import time
from collections import defaultdict
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

# Import new performance monitoring system
from .performance_monitor import PerformanceMonitor, get_performance_monitor

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# Qt timer import with fallback for headless environments
# pylint: disable=import-error
try:
    QtCore = importlib.import_module("PyQt5.QtCore")
    QTimer = QtCore.QTimer  # type: ignore[assignment]
except ImportError:
    try:
        QtCore = importlib.import_module("PySide2.QtCore")
        QTimer = QtCore.QTimer  # type: ignore[assignment]
    except ImportError:
        # Minimal dummy QTimer to satisfy runtime in non-Qt contexts
        # pylint: disable=missing-function-docstring,invalid-name
        class _DummyQTimer:
            """Dummy implementation of QTimer for non-Qt environments."""

            def __init__(self) -> None:
                self._timer: threading.Timer | None = None
                self._callback: Callable[[], Any] | None = None

            @staticmethod
            def setSingleShot(*_args: Any, **_kwargs: Any) -> None:
                """No-op stub for dummy QTimer; intentionally does nothing."""

            def set_callback(self, callback: Callable[[], Any]) -> None:
                """Set the callback function (public interface)."""
                self._callback = callback

            @property
            def timeout(self) -> Any:
                class _Signal:
                    """Signal interface to connect callbacks for DummyQTimer."""

                    def __init__(self, outer: _DummyQTimer) -> None:
                        self._outer = outer

                    def connect(self, cb: Callable[[], Any]) -> None:
                        # Use public interface method
                        self._outer.set_callback(cb)

                return _Signal(self)

            def start(self, ms: int) -> None:
                if self._timer:
                    self._timer.cancel()
                delay = ms / 1000.0
                self._timer = threading.Timer(delay, self._invoke)
                self._timer.start()

            def _invoke(self) -> None:
                cb = self._callback
                if callable(cb):
                    try:
                        cb()  # type: ignore  # pylint: disable=not-callable
                    except RuntimeError:  # pylint: disable=broad-exception-caught
                        pass  # Ignore callback errors
                    finally:
                        self._callback = None
                else:
                    # Ensure cleanup even if a non-callable was assigned
                    self._callback = None

            def stop(self) -> None:
                if self._timer:
                    self._timer.cancel()
                    self._timer = None

        QTimer = _DummyQTimer  # type: ignore[assignment, misc]
# pylint: enable=import-error

# Typing helpers for Qt-like interfaces (editor-only; no runtime impact)
if TYPE_CHECKING:
    # pylint: disable=missing-function-docstring,invalid-name
    class _SignalProto(Protocol):
        """Protocol for signal-like objects with connect method."""

        @staticmethod
        def connect(cb: Callable[..., Any]) -> Any: ...

    class _QTimerProto(Protocol):
        """Protocol defining the interface for QTimer-like objects."""

        @staticmethod
        def setSingleShot(singleShot: bool) -> None: ...

        @property
        def timeout(self) -> _SignalProto: ...

        @staticmethod
        def start(ms: int) -> None: ...

        @staticmethod
        def stop() -> None: ...

else:
    _QTimerProto = Any  # type: ignore[assignment, misc]
    _SignalProto = Any  # type: ignore[assignment, misc]


class OptimizedPatterns:
    """Pre-compiled regex patterns for performance optimization"""

    # Function patterns
    FUNCTION_PATTERN = re.compile(r"def\s+\w+\([^)]*\)")
    ASYNC_FUNCTION_PATTERN = re.compile(r"async\s+def\s+\w+\([^)]*\)")
    CLASS_PATTERN = re.compile(r"class\s+\w+")

    # Validation patterns
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    URL_PATTERN = re.compile(r"^https?://[^\s/$.?#].[^\s]*$")
    PHONE_PATTERN = re.compile(r"^\+?[\d\s\-\(\)]{10,}$")

    # Code patterns
    IMPORT_PATTERN = re.compile(
        r"^(?:from\s+\w+(?:\.\w+)*\s+import\s+[\w\s,]+|import\s+\w+(?:\.\w+)*)"
    )
    COMMENT_PATTERN = re.compile(r"#.*$", re.MULTILINE)
    STRING_PATTERN = re.compile(r'["\'](?:[^"\\]|\\.)*["\']')

    # File patterns
    FILE_EXTENSION_PATTERN = re.compile(r"\.([a-zA-Z0-9]+)$")
    PATH_PATTERN = re.compile(r"^[a-zA-Z]:\\|^/|^[a-zA-Z0-9._-]+/")

    # JSON patterns
    JSON_KEY_PATTERN = re.compile(r'"([^\"]+)":\s*')
    JSON_STRING_PATTERN = re.compile(r'"([^"\\]|\\.)*"')

    @classmethod
    def match_function(cls, code: str) -> re.Match[str] | None:
        """Match function definition in code"""
        return cls.FUNCTION_PATTERN.search(code)

    @classmethod
    def match_email(cls, email: str) -> bool:
        """Validate email format"""
        return bool(cls.EMAIL_PATTERN.match(email))

    @classmethod
    def match_url(cls, url: str) -> bool:
        """Validate URL format"""
        return bool(cls.URL_PATTERN.match(url))

    @classmethod
    def extract_file_extension(cls, filename: str) -> str | None:
        """Extract file extension from filename"""
        match = cls.FILE_EXTENSION_PATTERN.search(filename)
        return match.group(1) if match else None


class StringBuilder:
    """Optimized string building utility"""

    def __init__(self, initial_capacity: int = 1000) -> None:
        self._parts: list[str] = []
        self._length = 0
        self._initial_capacity = initial_capacity

    def append(self, text: str) -> StringBuilder:
        """Append text to the builder"""
        self._parts.append(text)
        self._length += len(text)
        return self

    def append_line(self, text: str = "") -> StringBuilder:
        """Append text with newline"""
        return self.append(text + "\n")

    def append_format(self, format_str: str, *args: Any, **kwargs: Any) -> StringBuilder:
        """Append formatted text"""
        return self.append(format_str.format(*args, **kwargs))

    def clear(self) -> StringBuilder:
        """Clear all content"""
        self._parts.clear()
        self._length = 0
        return self

    def build(self) -> str:
        """Build the final string"""
        if not self._parts:
            return ""
        if len(self._parts) == 1:
            return self._parts[0]
        return "".join(self._parts)

    def __len__(self) -> int:
        return self._length

    def __str__(self) -> str:
        return self.build()


class ObjectPool:
    """Object pooling for frequently created objects"""

    def __init__(
        self,
        factory_func: Callable[[], Any],
        max_size: int = 100,
        cleanup_func: Callable[[Any], Any] | None = None,
    ) -> None:
        self._pool: list[Any] = []
        self._factory: Callable[[], Any] = factory_func
        self._cleanup: Callable[[Any], Any] | None = cleanup_func
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self) -> Any:
        """Get an object from the pool or create a new one"""
        with self._lock:
            return self._pool.pop() if self._pool else self._factory()

    def put(self, obj: Any) -> None:
        """Return an object to the pool"""
        if obj is None:
            return

        with self._lock:
            if len(self._pool) < self._max_size:
                if self._cleanup:
                    self._cleanup(obj)
                self._pool.append(obj)

    def clear(self) -> None:
        """Clear the pool"""
        with self._lock:
            self._pool.clear()

    def size(self) -> int:
        """Get current pool size"""
        with self._lock:
            return len(self._pool)


class LazyImporter:
    """Lazy import utility for performance optimization"""

    def __init__(self) -> None:
        self._imports: dict[str, Any] = {}
        self._lock = threading.Lock()

    def get_module(self, module_name: str) -> Any:
        """Get a module, importing it lazily if needed"""
        if module_name not in self._imports:
            with self._lock:
                if module_name not in self._imports:
                    self._imports[module_name] = __import__(module_name)
        return self._imports[module_name]

    def get_class(self, module_name: str, class_name: str) -> type:
        """Get a class from a module, importing it lazily if needed"""
        module = self.get_module(module_name)
        return getattr(module, class_name)

    def clear_cache(self) -> None:
        """Clear the import cache"""
        with self._lock:
            self._imports.clear()


@contextmanager
def operation_timer(operation: str, monitor: PerformanceMonitor | None = None):
    """Context manager for timing operations"""
    if monitor is None:
        monitor = get_performance_monitor()

    operation_id = monitor.start_operation(operation)
    try:
        yield
    finally:
        monitor.end_operation(operation_id)


def build_string(*parts: str) -> str:
    """Optimized string building from multiple parts"""
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "".join(parts)


def safe_string_join(parts: Iterable[Any | None], separator: str = "") -> str:
    """Safely join strings, filtering out None values"""
    filtered_parts = [str(part) for part in parts if part is not None]
    return separator.join(filtered_parts)


# Global performance monitor instance (now imported from performance_monitor module)

# Global lazy importer instance
lazy_importer = LazyImporter()


# Global object pools
def _return_none() -> None:
    return None


widget_pool = ObjectPool(_return_none, max_size=50)
string_builder_pool = ObjectPool(StringBuilder, max_size=20)

# Phase 2 Optimization Utilities


class ComponentState(Enum):
    """Component initialization states."""

    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    ERROR = "error"


@dataclass
class ComponentInfo:
    """Information about a lazy-loaded component."""

    name: str
    factory_func: Callable[[], Any]
    dependencies: list[str] = field(default_factory=list)
    state: ComponentState = ComponentState.UNINITIALIZED
    instance: Any = None
    error: str | None = None
    init_time: float | None = None


class LazyComponentManager:
    """Manages lazy initialization of components with dependency resolution."""

    def __init__(self) -> None:
        self._components: dict[str, ComponentInfo] = {}
        self._initialization_order: list[str] = []
        self._performance_monitor = get_performance_monitor()

    def register_component(
        self,
        name: str,
        factory_func: Callable[[], Any],
        dependencies: list[str] | None = None,
    ) -> None:
        """Register a component for lazy initialization."""
        self._components[name] = ComponentInfo(
            name=name, factory_func=factory_func, dependencies=dependencies or []
        )

    def get_component(self, name: str) -> Any:
        """Get a component, initializing it if necessary."""
        if name not in self._components:
            raise KeyError(f"Component '{name}' not registered")

        component_info = self._components[name]

        if component_info.state == ComponentState.INITIALIZED:
            return component_info.instance

        if component_info.state == ComponentState.INITIALIZING:
            # Handle circular dependencies
            raise RuntimeError(f"Circular dependency detected for component '{name}'")

        # Initialize dependencies first
        for dep_name in component_info.dependencies:
            self.get_component(dep_name)

        # Initialize this component
        return self._initialize_component(component_info)

    def _initialize_component(self, component_info: ComponentInfo) -> Any:
        """Initialize a single component."""
        operation_id = self._performance_monitor.start_operation(
            f"component_init_{component_info.name}"
        )
        component_info.state = ComponentState.INITIALIZING

        try:
            LazyComponentManager._create_and_register_component(component_info)
            component_info.init_time = time.perf_counter()
            self._initialization_order.append(component_info.name)

            self._performance_monitor.end_operation(operation_id)
            return component_info.instance

        except RuntimeError as e:
            # Use value-based lookup to satisfy static analyzers that may not resolve enum members
            component_info.state = ComponentState("error")
            component_info.error = str(e)
            self._performance_monitor.end_operation(operation_id)
            raise RuntimeError(
                f"Failed to initialize component '{component_info.name}': {e}"
            ) from e

    @staticmethod
    def _create_and_register_component(component_info: ComponentInfo) -> None:
        """Create component instance and mark as initialized."""
        component_info.instance = component_info.factory_func()
        component_info.state = ComponentState.INITIALIZED

    def preload_components(self, component_names: list[str]) -> None:
        """Preload specific components."""
        for name in component_names:
            if name in self._components:
                self.get_component(name)

    def get_initialization_metrics(self) -> dict[str, Any]:
        """Get metrics about component initialization."""
        metrics: dict[str, Any] = {
            "total_components": len(self._components),
            "initialized_components": len(
                [c for c in self._components.values() if c.state == ComponentState.INITIALIZED]
            ),
            "initialization_order": self._initialization_order.copy(),
            "component_times": {},
        }

        for name, info in self._components.items():
            if info.init_time:
                metrics["component_times"][name] = info.init_time

        return metrics


class SignalConnectionManager:
    """Optimizes signal connections with connection pooling and validation."""

    def __init__(self) -> None:
        self._connections: dict[str, list[tuple[Any, Any, Any]]] = defaultdict(list)
        self._connection_groups: dict[str, list[str]] = defaultdict(list)
        self._performance_monitor = get_performance_monitor()

    @staticmethod
    def _validate_signal(signal: Any) -> None:
        """Validate that the signal has required methods."""
        if not hasattr(signal, "connect"):
            raise ValueError("Signal must have a 'connect' method")

    def connect_signal(
        self,
        signal: Any,
        slot: Any,
        connection_id: str | None = None,
        group: str | None = None,
    ) -> bool:
        """Connect a signal with tracking and validation."""
        try:
            # Validate signal and slot
            SignalConnectionManager._validate_signal(signal)

            # Connect the signal
            connection = signal.connect(slot)

            # Track the connection
            conn_id = connection_id or f"{id(signal)}_{id(slot)}"
            self._connections[conn_id].append((signal, slot, connection))

            if group:
                self._connection_groups[group].append(conn_id)

            return True

        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            # Log error using standard logging since new PerformanceMonitor doesn't have log_error
            logging.getLogger(__name__).warning("Signal connection failed: %s", e)
            return False

    def disconnect_group(self, group: str) -> int:
        """Disconnect all connections in a group."""
        if group not in self._connection_groups:
            return 0

        disconnected_count = 0
        for conn_id in self._connection_groups[group]:
            if conn_id in self._connections:
                for signal, slot, _connection in self._connections[conn_id]:
                    with suppress(AttributeError, TypeError, RuntimeError):
                        signal.disconnect(slot)
                        disconnected_count += 1
                del self._connections[conn_id]

        del self._connection_groups[group]
        return disconnected_count

    def disconnect_all(self) -> int:
        """Disconnect all tracked connections."""
        total_disconnected = 0
        for connections in self._connections.values():
            for signal, slot, _connection in connections:
                with suppress(AttributeError, TypeError, RuntimeError):
                    signal.disconnect(slot)
                    total_disconnected += 1
        self._connections.clear()
        self._connection_groups.clear()
        return total_disconnected

    def get_connection_stats(self) -> dict[str, Any]:
        """Get statistics about signal connections."""
        total_connections = sum(len(conns) for conns in self._connections.values())
        total_groups = len(self._connection_groups)

        return {
            "total_connections": total_connections,
            "connection_groups": total_groups,
            "group_details": {
                group: len(conn_ids) for group, conn_ids in self._connection_groups.items()
            },
        }


class DebouncedEventHandler:
    """Handles event debouncing to prevent excessive event processing."""

    def __init__(self, delay_ms: int = 300) -> None:
        self._delay = delay_ms
        self._timers: dict[str, _QTimerProto] = {}
        self._callbacks: dict[str, Callable[..., Any]] = {}
        self._performance_monitor = get_performance_monitor()

    def debounce(
        self, event_id: str, callback: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> None:
        """Debounce an event with the specified callback."""
        # Cancel existing timer for this event
        if event_id in self._timers:
            self._timers[event_id].stop()

        # Create new timer
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._execute_callback(event_id, *args, **kwargs))

        self._timers[event_id] = timer
        self._callbacks[event_id] = callback

        # Start the timer
        timer.start(self._delay)

    def _execute_callback(self, event_id: str, *args: Any, **kwargs: Any) -> None:
        """Execute the debounced callback."""
        if event_id in self._callbacks:
            operation_id = self._performance_monitor.start_operation(f"debounced_event_{event_id}")
            try:
                self._callbacks[event_id](*args, **kwargs)
            except RuntimeError as e:
                # Log error using standard logging
                logging.getLogger(__name__).warning("Debounced event error: %s", e)
            finally:
                self._performance_monitor.end_operation(operation_id)

                # Clean up
                if event_id in self._timers:
                    del self._timers[event_id]
                if event_id in self._callbacks:
                    del self._callbacks[event_id]

    def cancel_event(self, event_id: str) -> bool:
        """Cancel a pending debounced event."""
        if event_id in self._timers:
            self._timers[event_id].stop()
            del self._timers[event_id]
            if event_id in self._callbacks:
                del self._callbacks[event_id]
            return True
        return False

    def cancel_all_events(self) -> int:
        """Cancel all pending debounced events."""
        cancelled_count = 0
        for timer in self._timers.values():
            timer.stop()
            cancelled_count += 1

        self._timers.clear()
        self._callbacks.clear()
        return cancelled_count


class BatchUpdateManager:
    """Manages batch updates for widgets to improve rendering performance."""

    def __init__(self, parent_widget: Any | None = None) -> None:
        self._parent: Any | None = parent_widget
        self._update_queue: list[Callable[[], Any]] = []
        self._is_batching = False
        self._performance_monitor = get_performance_monitor()

    def set_parent_widget(self, parent_widget: Any | None) -> None:
        """Set the parent widget for batch updates."""
        self._parent = parent_widget

    def batch_update(self, update_func: Callable[[], Any]) -> None:
        """Queue an update function for batch execution."""
        self._update_queue.append(update_func)

    def execute_batch(self) -> None:
        """Execute all queued updates in a single batch."""
        if not self._update_queue or self._is_batching:
            return

        self._is_batching = True
        operation_id = self._performance_monitor.start_operation("batch_update")

        try:
            # Disable updates during batch operation
            if self._parent and hasattr(self._parent, "setUpdatesEnabled"):
                self._parent.setUpdatesEnabled(False)

            # Execute all queued updates
            for update_func in self._update_queue:
                try:
                    update_func()
                except RuntimeError as e:
                    # Log error using standard logging
                    logging.getLogger(__name__).warning("Batch update error: %s", e)

            # Clear the queue
            self._update_queue.clear()

        finally:
            # Re-enable updates
            if self._parent and hasattr(self._parent, "setUpdatesEnabled"):
                self._parent.setUpdatesEnabled(True)
                if hasattr(self._parent, "update"):
                    self._parent.update()

            self._is_batching = False
            self._performance_monitor.end_operation(operation_id)

    def clear_queue(self) -> int:
        """Clear the update queue and return the number of cleared items."""
        count = len(self._update_queue)
        self._update_queue.clear()
        return count

    def get_queue_size(self) -> int:
        """Get the current size of the update queue."""
        return len(self._update_queue)


# Global instances for Phase 2 optimizations
lazy_component_manager = LazyComponentManager()
signal_connection_manager = SignalConnectionManager()
debounced_event_handler = DebouncedEventHandler()
batch_update_manager = BatchUpdateManager()


# Utility functions for Phase 2 optimizations
def get_lazy_component_manager() -> LazyComponentManager:
    """Get the global lazy component manager instance."""
    return lazy_component_manager


def get_signal_connection_manager() -> SignalConnectionManager:
    """Get the global signal connection manager instance."""
    return signal_connection_manager


def get_debounced_event_handler() -> DebouncedEventHandler:
    """Get the global debounced event handler instance."""
    return debounced_event_handler


def get_batch_update_manager() -> BatchUpdateManager:
    """Get the global batch update manager instance."""
    return batch_update_manager


def debounce_event(event_id: str, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Debounce an event using the global event handler."""
    debounced_event_handler.debounce(event_id, callback, *args, **kwargs)


def batch_widget_update(parent_widget: Any, update_func: Callable[[], Any]) -> None:
    """Queue a widget update for batch execution."""
    batch_update_manager.set_parent_widget(parent_widget)
    batch_update_manager.batch_update(update_func)


def execute_batch_updates() -> None:
    """Execute all queued batch updates."""
    batch_update_manager.execute_batch()
