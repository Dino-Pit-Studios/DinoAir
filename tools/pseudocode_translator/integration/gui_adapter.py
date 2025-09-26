"""
GUI Adapter for the Pseudocode Translator

This module provides adapters and helpers for integrating the pseudocode
translator with GUI frameworks, particularly Qt-based applications.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .api import TranslatorAPI
from .callbacks import CallbackData, CallbackManager, CallbackType
from .events import EventDispatcher, EventType

try:
    from PySide6.QtCore import QObject as QtObject
    from PySide6.QtCore import QThread as QtThread
    from PySide6.QtCore import Signal as QtSignal
    from PySide6.QtCore import Slot

    HAS_QT = True
except ImportError:
    HAS_QT = False

    # Create dummy classes for type hints

    class QtObject:
        """Dummy QtObject used when PySide6 is unavailable. Acts as a stand-in for QObject."""

        def __init__(self, parent=None):
            """No-op constructor for dummy QtObject."""

    class QtSignal:
        """Dummy QtSignal used when PySide6 is unavailable. Provides emit() method placeholder."""

        def __init__(self, *args):
            """No-op dummy initializer."""
            # intentionally empty

        def emit(self, *args):
            """No-op dummy emit. Does nothing when PySide6 is unavailable."""
            # intentionally empty

    class QtThread:
        """Dummy QtThread used when PySide6 is unavailable. Serves as placeholder for QThread."""

    def Slot(*_args):
        """Dummy Slot decorator"""

        def decorator(func):
            """Dummy decorator that returns the original function unchanged."""
            return func

        return decorator


logger = logging.getLogger(__name__)


class GUIUpdateProtocol(Protocol):
    """Protocol for GUI update methods"""

    def update_progress(self, percentage: int, message: str) -> None:
        """Update progress display"""
        ...

    def update_status(self, status: str, details: dict[str, Any]) -> None:
        """Update status display"""
        ...

    def show_result(self, code: str, language: str) -> None:
        """Display translation result"""
        ...

    def show_error(self, error: str, details: dict[str, Any]) -> None:
        """Display error message"""
        ...


@dataclass
class TranslationTask:
    """Represents a translation task"""

    id: int
    pseudocode: str
    language: str
    options: dict[str, Any]
    status: str = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None


class GUITranslatorAdapter:
    """
    Adapter for integrating the translator with GUI applications.

    This class provides a high-level interface that handles threading,
    progress updates, and error handling for GUI applications.
    """

    def __init__(
        self,
        config_path: str | None = None,
        gui_updater: GUIUpdateProtocol | None = None,
    ):
        """
        Initialize GUI adapter

        Args:
            config_path: Optional path to configuration file
            gui_updater: Object implementing GUI update methods
        """
        self.api = TranslatorAPI(config_path)
        self.gui_updater = gui_updater
        self.callback_manager = CallbackManager()
        self.event_dispatcher = EventDispatcher()

        self._current_task: TranslationTask | None = None
        self._task_counter = 0
        self._lock = threading.Lock()

        # Setup callbacks
        self._setup_callbacks()

    def _setup_callbacks(self):
        """Setup internal callbacks"""

        # Progress callback
        def on_progress(data: CallbackData):
            """Called when a progress update is received. Updates the GUI progress bar."""
            if data.type == CallbackType.PROGRESS and self.gui_updater:
                percentage = data.data.get("percentage", 0)
                message = data.message or "Processing..."
                self.gui_updater.update_progress(percentage, message)

        self.callback_manager.register(on_progress, CallbackType.PROGRESS)

        # Status callback
        def on_status(data: CallbackData):
            """Called when a status update is received. Updates the GUI status display."""
            if data.type == CallbackType.STATUS and self.gui_updater:
                self.gui_updater.update_status(data.message or "Unknown", data.data)

        self.callback_manager.register(on_status, CallbackType.STATUS)

        # Error callback
        def on_error(data: CallbackData):
            """Called when an error occurs. Displays the error message in the GUI."""
            if data.type == CallbackType.ERROR and self.gui_updater:
                self.gui_updater.show_error(data.message or "Unknown error", data.data)

        self.callback_manager.register(on_error, CallbackType.ERROR)

    def translate(
        self,
        pseudocode: str,
        language: str = "python",
        async_mode: bool = True,
        **options,
    ) -> int | None:
        """
        Start a translation task

        Args:
            pseudocode: The pseudocode to translate
            language: Target programming language
            async_mode: Whether to run asynchronously
            **options: Additional translation options

        Returns:
            Task ID if async, None if sync
        """
        with self._lock:
            self._task_counter += 1
            task = TranslationTask(
                id=self._task_counter,
                pseudocode=pseudocode,
                language=language,
                options=options,
            )
            self._current_task = task

        if async_mode:
            # Run in thread
            thread = threading.Thread(target=self._run_translation, args=(task,))
            thread.start()
            return task.id
        # Run synchronously
        self._run_translation(task)
        return None

    def _run_translation(self, task: TranslationTask):
        """Run the translation task"""
        try:
            # Emit start event
            self.event_dispatcher.dispatch_event(
                EventType.TRANSLATION_STARTED, task_id=task.id, language=task.language
            )

            # Update status
            task.status = "running"
            self.callback_manager.trigger_status("Starting translation...", task_id=task.id)

            # Perform translation
            result = self.api.translate(task.pseudocode, task.language, **task.options)

            # Update task
            task.result = result
            task.status = "completed" if result["success"] else "failed"

            if result["success"]:
                # Show result
                if self.gui_updater:
                    self.gui_updater.show_result(result["code"], result["language"])

                # Emit completion event
                self.event_dispatcher.dispatch_event(
                    EventType.TRANSLATION_COMPLETED,
                    task_id=task.id,
                    code=result["code"],
                    language=result["language"],
                )
            else:
                # Handle error
                task.error = "; ".join(result["errors"])

                # Emit error event
                self.event_dispatcher.dispatch_event(
                    EventType.TRANSLATION_FAILED,
                    task_id=task.id,
                    errors=result["errors"],
                )

        except Exception as e:
            logger.error("Translation error: %s", e)
            task.status = "error"
            task.error = str(e)

            # Show error
            if self.gui_updater:
                self.gui_updater.show_error(str(e), {"task_id": task.id})

    def cancel_current(self):
        """Cancel the current translation task"""
        if self._current_task and self._current_task.status == "running":
            self._current_task.status = "cancelled"
            self.event_dispatcher.dispatch_event(
                EventType.TRANSLATION_CANCELLED, task_id=self._current_task.id
            )

    def get_current_task(self) -> TranslationTask | None:
        """Get the current translation task"""
        return self._current_task

    def set_language(self, language: str):
        """Set the default output language"""
        self.api.set_default_language(language)
        self.event_dispatcher.dispatch_event(EventType.LANGUAGE_CHANGED, language=language)

    def switch_model(self, model_name: str):
        """Switch to a different model"""
        self.api.switch_model(model_name)
        self.event_dispatcher.dispatch_event(EventType.MODEL_CHANGED, model=model_name)

    def update_config(self, updates: dict[str, Any]):
        """Update configuration"""
        self.api.update_config(updates)
        self.event_dispatcher.dispatch_event(EventType.CONFIG_CHANGED, updates=updates)


if HAS_QT:

    class QtTranslatorWidget(QtObject):
        """
        Qt widget adapter for the pseudocode translator

        This class provides Qt signals for GUI integration.
        """

        # Qt signals
        progressUpdated = QtSignal(int, str)  # percentage, message
        statusUpdated = QtSignal(str, dict)  # status, details
        translationCompleted = QtSignal(str, str)  # code, language
        errorOccurred = QtSignal(str, dict)  # error, details

        def __init__(self, config_path: str | None = None, parent: QtObject | None = None):
            """
            Initialize Qt translator widget

            Args:
                config_path: Optional configuration file path
                parent: Parent QObject
            """
            super().__init__(parent)

            # Create adapter with self as GUI updater
            self.adapter = GUITranslatorAdapter(config_path, self)

            # Translation thread
            self._worker_thread: QtThread | None = None

        def update_progress(self, percentage: int, message: str):
            """Update progress (implements GUIUpdateProtocol)"""
            self.progressUpdated.emit(percentage, message)

        def update_status(self, status: str, details: dict[str, Any]):
            """Update status (implements GUIUpdateProtocol)"""
            self.statusUpdated.emit(status, details)

        def show_result(self, code: str, language: str):
            """Show result (implements GUIUpdateProtocol)"""
            self.translationCompleted.emit(code, language)

        def show_error(self, error: str, details: dict[str, Any]):
            """Show error (implements GUIUpdateProtocol)"""
            self.errorOccurred.emit(error, details)

        @Slot(str, str)
        def translate(self, pseudocode: str, language: str = "python"):
            """
            Translate pseudocode (Qt slot)

            Args:
                pseudocode: The pseudocode to translate
                language: Target language
            """
            self.adapter.translate(pseudocode, language, async_mode=True)

        @Slot()
        def cancel(self):
            """Cancel current translation (Qt slot)"""
            self.adapter.cancel_current()

        @Slot(str)
        def setLanguage(self, language: str):
            """Set output language (Qt slot)"""
            self.adapter.set_language(language)

        @Slot(str)
        def switchModel(self, model_name: str):
            """Switch model (Qt slot)"""
            self.adapter.switch_model(model_name)

        def get_available_languages(self) -> list:
            """Get list of available languages"""
            info = self.adapter.api.get_info()
            return info["supported_languages"]

        def get_available_models(self) -> list:
            """Get list of available models"""
            info = self.adapter.api.get_info()
            return info["available_models"]


def create_progress_reporter(
    progress_bar=None, status_label=None, console_output=None
) -> Callable[[int, str], None]:
    """
    Create a progress reporter function for GUI elements

    Args:
        progress_bar: Progress bar widget (should have setValue method)
        status_label: Status label widget (should have setText method)
        console_output: Console/text widget (should have append method)

    Returns:
        Progress reporter function
    """

    def report_progress(percentage: int, message: str):
        """Report progress to GUI elements"""
        if progress_bar:
            progress_bar.setValue(percentage)
        if status_label:
            status_label.setText(message)
        if console_output:
            console_output.append(f"[{percentage}%] {message}")

    return report_progress


def create_result_handler(
    code_editor=None, language_label=None, _save_dialog_func: Callable | None = None
) -> Callable[[str, str], None]:
    """
    Create a result handler function for GUI elements

    Args:
        code_editor: Code editor widget (should have setText method)
        language_label: Language label widget (should have setText method)
        save_dialog_func: Function to show save dialog

    Returns:
        Result handler function
    """

    def handle_result(code: str, language: str):
        """Handle translation result"""
        if code_editor:
            code_editor.setText(code)
        if language_label:
            language_label.setText(f"Language: {language}")

    return handle_result
