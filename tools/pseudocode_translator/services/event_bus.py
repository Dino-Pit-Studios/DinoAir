"""
Event Bus Service for Decoupled Communication

This module provides a lightweight event bus system for decoupled
communication between translation components.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """Event priority levels for handling order."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Event:
    """Event data container."""

    type: str
    data: dict[str, Any]
    source: str | None = None
    priority: EventPriority = EventPriority.NORMAL
    timestamp: float | None = None

    def __post_init__(self):
        if self.timestamp is None:
            import time

            self.timestamp = time.time()


class EventHandler:
    """Event handler wrapper."""

    def __init__(
        self,
        callback: Callable[[Event], None],
        priority: EventPriority = EventPriority.NORMAL,
        once: bool = False,
    ):
        self.callback = callback
        self.priority = priority
        self.once = once
        self.call_count = 0

    def handle(self, event: Event) -> bool:
        """
        Handle event and return True if handler should be kept.

        Args:
            event: The event to handle

        Returns:
            True if handler should remain active, False if it should be removed
        """
        try:
            self.callback(event)
            self.call_count += 1
            return not self.once
        except Exception as e:
            logger.error("Event handler failed for %s: %s", event.type, e)
            return True  # Keep handler active even if it fails


class EventBus:
    """
    Lightweight event bus for decoupled component communication.

    Provides event publishing, subscription, and filtering capabilities
    without tight coupling between components.
    """

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []
        self._event_count = 0
        self._handler_count = 0

        logger.debug("EventBus initialized")

    def subscribe(
        self,
        event_type: str,
        callback: Callable[[Event], None],
        priority: EventPriority = EventPriority.NORMAL,
        once: bool = False,
    ) -> str:
        """
        Subscribe to events of a specific type.

        Args:
            event_type: Type of event to subscribe to
            callback: Function to call when event occurs
            priority: Priority level for handler ordering
            once: If True, handler is removed after first execution

        Returns:
            Handler ID for unsubscribing
        """
        handler = EventHandler(callback, priority, once)

        if event_type not in self._handlers:
            self._handlers[event_type] = []

        self._handlers[event_type].append(handler)

        # Sort handlers by priority
        self._handlers[event_type].sort(key=lambda h: h.priority.value, reverse=True)

        self._handler_count += 1
        handler_id = f"{event_type}_{id(handler)}"

        logger.debug("Subscribed to %s events (priority: %s)", event_type, priority.name)
        return handler_id

    def subscribe_all(
        self,
        callback: Callable[[Event], None],
        priority: EventPriority = EventPriority.NORMAL,
        once: bool = False,
    ) -> str:
        """
        Subscribe to all events (global handler).

        Args:
            callback: Function to call for any event
            priority: Priority level for handler ordering
            once: If True, handler is removed after first execution

        Returns:
            Handler ID for unsubscribing
        """
        handler = EventHandler(callback, priority, once)
        self._global_handlers.append(handler)

        # Sort global handlers by priority
        self._global_handlers.sort(key=lambda h: h.priority.value, reverse=True)

        self._handler_count += 1
        handler_id = f"global_{id(handler)}"

        logger.debug("Subscribed to all events (priority: %s)", priority.name)
        return handler_id

    def unsubscribe(self, event_type: str, handler_id: str) -> bool:
        """
        Unsubscribe from events.

        Args:
            event_type: Type of event to unsubscribe from
            handler_id: Handler ID returned from subscribe

        Returns:
            True if handler was found and removed
        """
        if event_type in self._handlers:
            original_count = len(self._handlers[event_type])
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if f"{event_type}_{id(h)}" != handler_id
            ]
            removed = len(self._handlers[event_type]) < original_count
            if removed:
                self._handler_count -= 1
                logger.debug("Unsubscribed from %s events", event_type)
                return True

        # Check global handlers
        original_count = len(self._global_handlers)
        self._global_handlers = [
            h for h in self._global_handlers if f"global_{id(h)}" != handler_id
        ]
        removed = len(self._global_handlers) < original_count
        if removed:
            self._handler_count -= 1
            logger.debug("Unsubscribed from global events")

        return removed

    def emit(
        self,
        event_type: str,
        data: dict[str, Any],
        source: str | None = None,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> int:
        """
        Emit an event to all subscribers.

        Args:
            event_type: Type of event to emit
            data: Event data dictionary
            source: Source component name (optional)
            priority: Event priority level

        Returns:
            Number of handlers that processed the event
        """
        event = Event(type=event_type, data=data, source=source, priority=priority)

        self._event_count += 1
        handlers_called = 0

        logger.debug("Emitting event: %s from %s", event_type, source or "unknown")

        # Call specific event handlers
        if event_type in self._handlers:
            active_handlers = []
            for handler in self._handlers[event_type]:
                if handler.handle(event):
                    active_handlers.append(handler)
                handlers_called += 1

            # Update handler list (removes 'once' handlers)
            self._handlers[event_type] = active_handlers
            if not active_handlers:
                del self._handlers[event_type]

        # Call global handlers
        active_global = []
        for handler in self._global_handlers:
            if handler.handle(event):
                active_global.append(handler)
            handlers_called += 1

        self._global_handlers = active_global

        logger.debug("Event %s processed by %d handlers", event_type, handlers_called)
        return handlers_called

    def clear_handlers(self, event_type: str | None = None) -> None:
        """
        Clear event handlers.

        Args:
            event_type: Specific event type to clear, or None for all handlers
        """
        if event_type:
            if event_type in self._handlers:
                count = len(self._handlers[event_type])
                del self._handlers[event_type]
                self._handler_count -= count
                logger.debug("Cleared %d handlers for %s", count, event_type)
        else:
            total_handlers = sum(len(handlers) for handlers in self._handlers.values())
            total_handlers += len(self._global_handlers)

            self._handlers.clear()
            self._global_handlers.clear()
            self._handler_count = 0

            logger.debug("Cleared all %d handlers", total_handlers)

    def get_statistics(self) -> dict[str, Any]:
        """Get event bus statistics."""
        specific_handlers = sum(len(handlers) for handlers in self._handlers.values())

        return {
            "total_events": self._event_count,
            "active_handlers": self._handler_count,
            "specific_handlers": specific_handlers,
            "global_handlers": len(self._global_handlers),
            "event_types": list(self._handlers.keys()),
        }

    def reset_statistics(self) -> None:
        """Reset event statistics."""
        self._event_count = 0
        logger.debug("Event statistics reset")


# Global event bus instance
_global_bus: EventBus | None = None


_bus = None


_global_bus = None


_global_bus = None


def get_global_bus() -> EventBus:
    """Get or create the global event bus instance."""
    if not hasattr(get_global_bus, "bus"):
        get_global_bus.bus = EventBus()
    return get_global_bus.bus


def emit_global(
    event_type: str,
    data: dict[str, Any],
    source: str | None = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> int:
    """Emit event on the global bus."""
    return get_global_bus().emit(event_type, data, source, priority)


def subscribe_global(
    event_type: str,
    callback: Callable[[Event], None],
    priority: EventPriority = EventPriority.NORMAL,
    once: bool = False,
) -> str:
    """Subscribe to events on the global bus."""
    return get_global_bus().subscribe(event_type, callback, priority, once)
