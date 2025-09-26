"""
Event system for the Pseudocode Translator

This module provides an event-driven architecture for the translator,
enabling decoupled communication between components and supporting
reactive GUI updates.
"""

import logging
import queue
import threading
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

from utils.shutdown_protocols import ShutdownMixin

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events in the translation system"""

    # Translation lifecycle events
    TRANSLATION_STARTED = auto()
    TRANSLATION_PROGRESS = auto()
    TRANSLATION_COMPLETED = auto()
    TRANSLATION_FAILED = auto()
    TRANSLATION_CANCELLED = auto()

    # Model events
    MODEL_INITIALIZING = auto()
    MODEL_READY = auto()
    MODEL_CHANGED = auto()
    MODEL_ERROR = auto()

    # Configuration events
    CONFIG_CHANGED = auto()
    CONFIG_ERROR = auto()

    # Language events
    LANGUAGE_CHANGED = auto()

    # Streaming events
    STREAM_STARTED = auto()
    STREAM_CHUNK_PROCESSED = auto()
    STREAM_COMPLETED = auto()
    # Adaptive streaming decisions (payload: old_size, new_size, reason,
    # smoothed_latency_ms, target_latency_ms, backpressure_util, cooldown_remaining)
    STREAM_ADAPTATION_DECISION = auto()

    # System events
    SYSTEM_WARNING = auto()
    SYSTEM_ERROR = auto()
    SYSTEM_INFO = auto()

    # Execution/process pool events
    # STARTED: {"max_workers": int, "start_method": str | None}
    EXEC_POOL_STARTED = auto()
    # SUBMITTED: {"kind": "parse" | "validate", "size_chars": int}
    EXEC_POOL_TASK_SUBMITTED = auto()
    # COMPLETED: {"kind": "...", "duration_ms": float}
    EXEC_POOL_TASK_COMPLETED = auto()
    # TIMEOUT: {"kind": "...", "timeout_ms": int, "attempt": int}
    EXEC_POOL_TIMEOUT = auto()
    # FALLBACK: {"kind": "...", "reason": "timeout" | "broken_pool" | "job_too_large"}
    EXEC_POOL_FALLBACK = auto()


@dataclass
class TranslationEvent:
    """Event data structure"""

    type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    target: str | None = None

    @property
    def name(self) -> str:
        """Get event name"""
        return self.type.name

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "type": self.type.name,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "target": self.target,
            "data": self.data,
        }

    def __str__(self) -> str:
        """String representation"""
        return f"Event({self.name}, source={self.source}, data={self.data})"


class EventHandler:
    """Handler for events"""

    def __init__(
        self,
        callback: Callable[[TranslationEvent], None],
        event_types: set[EventType] | None = None,
        filter_func: Callable[[TranslationEvent], bool] | None = None,
    ):
        """
        Initialize event handler

        Args:
            callback: Function to call when event is received
            event_types: Set of event types to handle (None for all)
            filter_func: Optional filter function
        """
        self.callback = callback
        self.event_types = event_types
        self.filter_func = filter_func
        self._enabled = True

    def can_handle(self, event: TranslationEvent) -> bool:
        """
        Check if this handler can handle the event

        Args:
            event: Event to check

        Returns:
            True if handler can handle the event
        """
        if not self._enabled:
            return False

        # Check event type
        if self.event_types and event.type not in self.event_types:
            return False

        # Apply filter
        return not (self.filter_func and not self.filter_func(event))

    def handle(self, event: TranslationEvent) -> None:
        """
        Handle an event

        Args:
            event: Event to handle
        """
        if self.can_handle(event):
            try:
                self.callback(event)
            except Exception as e:
                logger.error("Error in event handler: %s", e)

    def enable(self):
        """Enable the handler"""
        self._enabled = True

    def disable(self):
        """Disable the handler"""
        self._enabled = False


class EventDispatcher(ShutdownMixin):
    """
    Central event dispatcher for the translation system

    This class manages event distribution to registered handlers,
    supporting both synchronous and asynchronous event delivery.
    """

    def __init__(self, async_mode: bool = True):
        """
        Initialize event dispatcher

        Args:
            async_mode: Whether to use async event delivery
        """
        super().__init__()
        self._handlers: list[weakref.ref] = []
        self._lock = threading.RLock()
        self._async_mode = async_mode
        self._event_queue: queue.Queue[TranslationEvent] | None = None
        self._worker_thread: threading.Thread | None = None
        self._running = False

        if async_mode:
            self._start_async_worker()

    def _start_async_worker(self):
        """Start the async event worker thread"""
        self._event_queue = queue.Queue()
        self._running = True
        self._worker_thread = threading.Thread(target=self._async_worker, daemon=True)
        self._worker_thread.start()

    def _async_worker(self):
        """Worker thread for async event delivery"""
        while self._running:
            try:
                # Get event with timeout to allow checking _running
                if self._event_queue is not None:
                    event = self._event_queue.get(timeout=0.1)
                    self._deliver_event(event)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error("Error in async event worker: %s", e)

    def _deliver_event(self, event: TranslationEvent):
        """Deliver event to all handlers"""
        with self._lock:
            # Clean up dead references
            self._handlers = [h for h in self._handlers if h() is not None]
            handlers = [h() for h in self._handlers if h() is not None]

        # Deliver to handlers
        for handler in handlers:
            if handler is not None:
                try:
                    handler.handle(event)
                except Exception as e:
                    logger.error("Error delivering event %s to handler: %s", event.name, e)

    def register(self, handler: EventHandler) -> None:
        """
        Register an event handler

        Args:
            handler: Handler to register
        """
        with self._lock:
            # Use weak reference to avoid circular references
            self._handlers.append(weakref.ref(handler))

    def unregister(self, handler: EventHandler) -> None:
        """
        Unregister an event handler

        Args:
            handler: Handler to unregister
        """
        with self._lock:
            self._handlers = [h for h in self._handlers if h() is not None and h() != handler]

    def dispatch(self, event: TranslationEvent) -> None:
        """
        Dispatch an event

        Args:
            event: Event to dispatch
        """
        logger.debug("Dispatching event: %s", event)

        if self._async_mode and self._event_queue:
            # Async delivery
            self._event_queue.put(event)
        else:
            # Sync delivery
            self._deliver_event(event)

    def dispatch_event(self, event_type: EventType, source: str | None = None, **data) -> None:
        """
        Convenience method to create and dispatch an event

        Args:
            event_type: Type of event
            source: Event source
            **data: Event data
        """
        event = TranslationEvent(type=event_type, source=source, data=data)
        self.dispatch(event)

    def clear_handlers(self) -> None:
        """Clear all registered handlers"""
        with self._lock:
            self._handlers.clear()

    def _cleanup_resources(self):
        """Cleanup dispatcher resources during shutdown"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=1.0)

    def __del__(self):
        """Cleanup on deletion"""
        self.shutdown()


class EventMixin:
    """
    Mixin class to add event support to other classes

    Classes that inherit from this mixin can easily emit events.
    """

    def __init__(self, *args, **kwargs):
        """Initialize event mixin"""
        super().__init__(*args, **kwargs)
        self._event_dispatcher: EventDispatcher | None = None
        self._event_source = self.__class__.__name__

    def set_event_dispatcher(self, dispatcher: EventDispatcher):
        """
        Set the event dispatcher

        Args:
            dispatcher: Event dispatcher to use
        """
        self._event_dispatcher = dispatcher

    def emit_event(self, event_type: EventType, **data):
        """
        Emit an event

        Args:
            event_type: Type of event to emit
            **data: Event data
        """
        if self._event_dispatcher:
            self._event_dispatcher.dispatch_event(event_type, source=self._event_source, **data)


def create_event_dispatcher() -> EventDispatcher:
    """
    Create and configure an event dispatcher

    Returns:
        Configured EventDispatcher
    """
    dispatcher = EventDispatcher(async_mode=True)

    # Add default logging handler
    def log_event(event: TranslationEvent):
        """Log all events"""
        level = logging.INFO
        if event.type in [EventType.SYSTEM_ERROR, EventType.MODEL_ERROR]:
            level = logging.ERROR
        elif event.type == EventType.SYSTEM_WARNING:
            level = logging.WARNING

        logger.log(level, "Event: %s from %s", event.name, event.source, extra=event.data)

    log_handler = EventHandler(
        log_event, filter_func=lambda e: e.type != EventType.TRANSLATION_PROGRESS
    )
    dispatcher.register(log_handler)

    return dispatcher


def create_gui_event_handler(gui_window) -> EventHandler:
    """
    Create an EventHandler for GUI updates based on translation events.

    Args:
        gui_window: GUI window instance with update_progress and show_result methods.

    Returns:
        EventHandler to handle translation events for GUI.
    """

    def handle_event(event: TranslationEvent):
        if event.type == EventType.TRANSLATION_PROGRESS:
            gui_window.update_progress(event.data["percentage"])
        elif event.type == EventType.TRANSLATION_COMPLETED:
            gui_window.show_result(event.data["code"])

    return EventHandler(handle_event)
