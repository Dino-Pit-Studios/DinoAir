from __future__ import annotations

import contextlib
import logging
import threading
import time
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from .events import StreamingEventData

logger = logging.getLogger(__name__)


class EventRuntime:
    """
    Event/lifecycle runtime that manages:
    - Cancellation state
    - Pause/resume gating
    - Event queue and worker thread
    - Listener registration and FIFO dispatch

    Notes on semantics:
    - _running is set() while the worker should be active.
    - _paused is set() when paused (i.e., True means paused).
    - _cancelled is set() when cancelled.
    - Event dispatch preserves FIFO both in queueing and listener invocation order.
    """

    def __init__(self):
        self._listeners: list[Callable[[StreamingEventData], None]] = []
        self._event_queue: Queue[StreamingEventData | None] = Queue()
        self._worker: threading.Thread | None = None

        self._running = threading.Event()
        self._paused = threading.Event()  # set() means paused
        self._cancelled = threading.Event()

        # Keep a weak reference to a progress object if provided by caller
        self._progress_ref = None

    def start(self, progress) -> None:
        """
        Start the runtime worker thread and initialize lifecycle flags.
        The provided progress object is stored for potential future use by events.
        """
        self._progress_ref = progress
        self._cancelled.clear()
        self._paused.clear()  # not paused by default
        self._running.set()

        # Start worker if not already running
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker.start()

    def stop(self, final_progress, cancelled: bool) -> None:
        """
        Stop the runtime and shut down the worker thread gracefully.
        The caller is responsible for emitting any terminal events (e.g., COMPLETED).
        """
        # Ensure any final state is visible
        self._progress_ref = final_progress
        if cancelled:
            self._cancelled.set()

        # Signal worker to stop
        self._running.clear()
        # Unblock queue.get and pause waits
        with contextlib.suppress(Exception):
            self._event_queue.put_nowait(None)

        # Join worker
        if self._worker:
            try:
                self._worker.join(timeout=1.0)
            except Exception as e:
                logger.debug("EventRuntime worker join timeout or error: %s", e)
            finally:
                self._worker = None

    def emit(self, event: StreamingEventData) -> None:
        """Enqueue an event for FIFO processing by the worker."""
        try:
            self._event_queue.put_nowait(event)
        except Exception as e:
            logger.error("Failed to enqueue event: %s", e)

    def pause(self) -> None:
        """Enter paused state. Dispatch will block until resumed."""
        self._paused.set()

    def resume(self) -> None:
        """Exit paused state. Dispatch continues."""
        self._paused.clear()

    def cancel(self) -> None:
        """Mark the runtime as cancelled. Does not emit events by itself."""
        self._cancelled.set()

    def check_cancelled(self) -> bool:
        """Returns True if cancellation has been requested."""
        return self._cancelled.is_set()

    def wait_if_paused(self) -> None:
        """Block while paused; returns immediately if not paused."""
        # Spin-wait with short sleep to avoid busy looping.
        while self._paused.is_set() and self._running.is_set() and not self._cancelled.is_set():
            time.sleep(0.01)

    def add_listener(self, listener: Callable[[StreamingEventData], None]) -> None:
        """Register a listener for events. Listener order is preserved (FIFO)."""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[StreamingEventData], None]) -> None:
        """Remove a previously registered listener."""
        try:
            self._listeners.remove(listener)
        except ValueError:
            # Already removed or never added
            pass

    # Internal helpers
    def _should_continue_running(self) -> bool:
        """Pure check for whether the worker should continue running."""
        return self._running.is_set()

    def _wait_if_paused(self) -> None:
        """Delegate to the existing pause wait to preserve semantics."""
        self.wait_if_paused()

    def _get_next_event(self, timeout: float) -> tuple[bool, Any]:
        """
        Attempt to get the next event from the queue with timeout.
        Returns (has_event, event).
        """
        try:
            item = self._event_queue.get(timeout=timeout)
            return True, item
        except Empty:
            return False, None
        except Exception as e:
            self._handle_loop_exception(e)
            return False, None

    def _dispatch_event(self, event: StreamingEventData) -> None:
        """Dispatch the event to registered listeners (FIFO)."""
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception as e:
                logger.error("Error in event listener: %s", e)

    def _handle_loop_exception(self, exc: Exception) -> None:
        """Centralized exception logging for loop internals."""
        logger.error("EventRuntime queue error: %s", exc)

    # Internal worker
    def _worker_loop(self) -> None:
        """
        Worker thread that drains the event queue and dispatches events to listeners.
        """
        while self._should_continue_running():
            has_event, item = self._get_next_event(timeout=0.1)
            if not has_event:
                continue

            if item is None:
                # Sentinel to break quickly
                break

            # Pause gating
            if self._paused.is_set():
                self._wait_if_paused()
                # If stopped/cancelled while paused, we may exit early
                if not self._running.is_set():
                    break

            # Dispatch to listeners in registration order
            self._dispatch_event(item)
