"""
Callback system for GUI integration

This module provides callback interfaces and managers for integrating
the pseudocode translator with GUI applications, enabling real-time
progress updates, status monitoring, and error handling.
"""

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class CallbackType(Enum):
    """Types of callbacks"""

    PROGRESS = "progress"
    STATUS = "status"
    COMPLETION = "completion"
    ERROR = "error"
    WARNING = "warning"
    LOG = "log"


@dataclass
class CallbackData:
    """Data passed to callbacks"""

    type: CallbackType
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "data": self.data,
        }


class TranslationCallback(Protocol):
    """Protocol for translation callbacks"""

    def __call__(self, data: CallbackData) -> None:
        """
        Handle callback data

        Args:
            data: Callback data containing type, message, and additional info
        """
        ...


class ProgressCallback(Protocol):
    """Protocol for progress callbacks"""

    def __call__(self, percentage: int, message: str) -> None:
        """
        Handle progress update

        Args:
            percentage: Progress percentage (0-100)
            message: Progress message
        """
        ...


class StatusCallback(Protocol):
    """Protocol for status callbacks"""

    def __call__(self, status: str, details: dict[str, Any] | None = None) -> None:
        """
        Handle status update

        Args:
            status: Status message
            details: Optional additional details
        """
        ...


class BaseCallback(ABC):
    """Base class for callback handlers"""

    def __init__(self, name: str | None = None):
        """
        Initialize callback handler

        Args:
            name: Optional name for the callback
        """
        self.name = name or self.__class__.__name__
        self._enabled = True
        self._lock = threading.Lock()

    @abstractmethod
    def handle(self, data: CallbackData) -> None:
        """
        Handle callback data

        Args:
            data: Callback data to process
        """

    def __call__(self, data: CallbackData) -> None:
        """Make the callback callable"""
        if self._enabled:
            with self._lock:
                try:
                    self.handle(data)
                except Exception as e:
                    logger.error("Error in callback %s: %s", self.name, e)

    def enable(self):
        """Enable the callback"""
        self._enabled = True

    def disable(self):
        """Disable the callback"""
        self._enabled = False

    @property
    def enabled(self) -> bool:
        """Check if callback is enabled"""
        return self._enabled


class GUIProgressCallback(BaseCallback):
    """Progress callback for GUI applications"""

    def __init__(self, progress_handler: Callable[[int, str], None], name: str = "GUIProgress"):
        """
        Initialize GUI progress callback

        Args:
            progress_handler: Function to handle progress updates
            name: Callback name
        """
        super().__init__(name)
        self.progress_handler = progress_handler

    def handle(self, data: CallbackData) -> None:
        """Handle progress callback data"""
        if data.type == CallbackType.PROGRESS:
            percentage = data.data.get("percentage", 0)
            message = data.message or "Processing..."
            self.progress_handler(percentage, message)


class GUIStatusCallback(BaseCallback):
    """Status callback for GUI applications"""

    def __init__(
        self,
        status_handler: Callable[[str, dict[str, Any]], None],
        name: str = "GUIStatus",
    ):
        """
        Initialize GUI status callback

        Args:
            status_handler: Function to handle status updates
            name: Callback name
        """
        super().__init__(name)
        self.status_handler = status_handler

    def handle(self, data: CallbackData) -> None:
        """Handle status callback data"""
        if data.type == CallbackType.STATUS:
            status = data.message or "Unknown status"
            details = data.data
            self.status_handler(status, details)


class LoggingCallback(BaseCallback):
    """Callback that logs all events"""

    def __init__(
        self,
        logger_name: str | None = None,
        level: int = logging.INFO,
        name: str = "LoggingCallback",
    ):
        """
        Initialize logging callback

        Args:
            logger_name: Name of logger to use
            level: Logging level
            name: Callback name
        """
        super().__init__(name)
        self.logger = logging.getLogger(logger_name or __name__)
        self.level = level

    def handle(self, data: CallbackData) -> None:
        """Log callback data"""
        message = f"[{data.type.value}] {data.message or 'No message'}"

        if data.type == CallbackType.ERROR:
            self.logger.error(message, extra=data.data)
        elif data.type == CallbackType.WARNING:
            self.logger.warning(message, extra=data.data)
        else:
            self.logger.log(self.level, message, extra=data.data)


class CallbackManager:
    """
    Manager for handling multiple callbacks

    This class manages a collection of callbacks and provides methods
    for registering, unregistering, and triggering callbacks.
    """

    def __init__(self):
        """Initialize callback manager"""
        self._callbacks: dict[str, list[TranslationCallback]] = {
            callback_type.value: [] for callback_type in CallbackType
        }
        self._global_callbacks: list[TranslationCallback] = []
        self._lock = threading.Lock()

    def register(
        self,
        callback: TranslationCallback,
        callback_type: CallbackType | None = None,
    ) -> None:
        """
        Register a callback

        Args:
            callback: The callback to register
            callback_type: Optional type to register for (None for all types)
        """
        with self._lock:
            if callback_type:
                if callback not in self._callbacks[callback_type.value]:
                    self._callbacks[callback_type.value].append(callback)
            elif callback not in self._global_callbacks:
                self._global_callbacks.append(callback)

    def unregister(
        self,
        callback: TranslationCallback,
        callback_type: CallbackType | None = None,
    ) -> None:
        """
        Unregister a callback

        Args:
            callback: The callback to unregister
            callback_type: Optional type to unregister from
        """
        with self._lock:
            if callback_type:
                if callback in self._callbacks[callback_type.value]:
                    self._callbacks[callback_type.value].remove(callback)
            else:
                # Remove from all lists
                if callback in self._global_callbacks:
                    self._global_callbacks.remove(callback)
                for callbacks in self._callbacks.values():
                    if callback in callbacks:
                        callbacks.remove(callback)

    def trigger(self, data: CallbackData) -> None:
        """
        Trigger callbacks for the given data

        Args:
            data: Callback data to send
        """
        with self._lock:
            # Get callbacks to trigger
            specific_callbacks = self._callbacks[data.type.value].copy()
            global_callbacks = self._global_callbacks.copy()

        # Trigger specific callbacks
        for callback in specific_callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error("Error in callback: %s", e)

        # Trigger global callbacks
        for callback in global_callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error("Error in global callback: %s", e)

    def trigger_progress(self, percentage: int, message: str) -> None:
        """
        Convenience method to trigger progress callback

        Args:
            percentage: Progress percentage (0-100)
            message: Progress message
        """
        data = CallbackData(
            type=CallbackType.PROGRESS, message=message, data={"percentage": percentage}
        )
        self.trigger(data)

    def trigger_status(self, status: str, **kwargs) -> None:
        """
        Convenience method to trigger status callback

        Args:
            status: Status message
            **kwargs: Additional status data
        """


def create_gui_callbacks(
    progress_bar=None, status_label=None, error_handler=None, completion_handler=None
) -> CallbackManager:
    """
        Create a callback manager configured for GUI integration

        Args:
            progress_bar: GUI progress bar widget (should have setValue method)
            status_label: GUI label widget (should have setText method)
            error_handler: Function to handle errors
            completion_handler: Function to handle completion

    Returns:
        Configured CallbackManager
    """

    manager = CallbackManager()

    # Progress callback
    if progress_bar:

        def on_progress(data: CallbackData):
            if data.type == CallbackType.PROGRESS:
                percentage = data.data.get("percentage", 0)
                progress_bar.setValue(percentage)

        manager.register(on_progress, CallbackType.PROGRESS)

    # Status callback
    if status_label:

        def on_status(data: CallbackData):
            if data.type == CallbackType.STATUS:
                status_label.setText(data.message or "Processing...")

        manager.register(on_status, CallbackType.STATUS)

    # Error callback
    if error_handler:

        def on_error(data: CallbackData):
            if data.type == CallbackType.ERROR:
                error_handler(data.message, data.data)

        manager.register(on_error, CallbackType.ERROR)

    # Completion callback
    if completion_handler:

        def on_completion(data: CallbackData):
            if data.type == CallbackType.COMPLETION:
                completion_handler(data.data)

        manager.register(on_completion, CallbackType.COMPLETION)

    # Add logging callback
    logging_callback = LoggingCallback()
    manager.register(logging_callback)

    return manager


# Example usage
# Example Usage:
#
#     # Create callback manager
#     from pseudocode_translator.integration.callbacks import (
#         CallbackManager, CallbackType, CallbackData
#     )
#
#     manager = CallbackManager()
#
#     # Register a simple callback
#     def on_progress(data):
#         print(f"Progress: {data.data['percentage']}% - {data.message}")
#
#     manager.register(on_progress, CallbackType.PROGRESS)
#
#     # Trigger progress
#     manager.trigger_progress(50, "Half way there!")
#
#     # Using with GUI (Qt example)
#     from pseudocode_translator.integration.callbacks import (
#         create_gui_callbacks
#     )
#
#     callbacks = create_gui_callbacks(
#         progress_bar=self.ui.progressBar,
#         status_label=self.ui.statusLabel,
#         error_handler=lambda msg, data: QMessageBox.critical(
#             self, "Error", msg
#         ),
#         completion_handler=lambda data: self.on_translation_complete(data)
#     )
#
#     # Custom callback class
#     from pseudocode_translator.integration.callbacks import BaseCallback
#
#     class FileOutputCallback(BaseCallback):
#         def __init__(self, output_file):
#             super().__init__("FileOutput")
#             self.output_file = output_file
#
#         def handle(self, data):
#             with open(self.output_file, 'a') as f:
#                 f.write(
#                     f"{data.timestamp}: {data.type.value} - "
#                     f"{data.message}\n"
#                 )
