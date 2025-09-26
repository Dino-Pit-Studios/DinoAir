"""
PySide6 Integration API for Pseudocode Translator

This module provides a clean, signal-based API for integrating the
pseudocode translator with PySide6 GUI applications.
"""

import contextlib
import logging
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

from .assembler import CodeAssembler
from .config import ConfigManager, TranslatorConfig
from .gui_worker import TranslationResult, TranslationStatus, TranslationWorker
from .models import BlockType, CodeBlock, ParseResult
from .parser import ParserModule
from .translator import TranslationManager
from .validator import Validator

logger = logging.getLogger(__name__)


class PseudocodeTranslatorAPI(QObject):
    """
    Main API class for PySide6 integration

    Provides both synchronous and asynchronous translation methods with
    Qt signals for progress updates and status notifications.

    Example usage:
        translator = PseudocodeTranslatorAPI()
        translator.translation_completed.connect(on_translation_done)
        translator.translate_async("create a function that adds two numbers")
    """

    # Qt Signals for GUI communication
    translation_started = Signal()
    translation_progress = Signal(int)  # Progress percentage (0-100)
    translation_status = Signal(TranslationStatus)  # Detailed status
    translation_completed = Signal(TranslationResult)  # Final result
    translation_error = Signal(str)  # Error message
    model_status_changed = Signal(str)  # Model status message
    model_initialized = Signal()  # Model ready

    # Streaming signals
    streaming_started = Signal()
    streaming_chunk_processed = Signal(int, str)  # chunk_index, chunk_code
    streaming_progress = Signal(dict)  # Progress info with memory usage
    streaming_completed = Signal(str)  # Final assembled code
    memory_usage_updated = Signal(dict)  # Memory usage stats

    def __init__(self, config_path: str | None = None, parent: QObject | None = None):
        """
        Initialize the translator API

        Args:
            config_path: Optional path to configuration file
            parent: Optional parent QObject
        """
        super().__init__(parent)

        # Load configuration
        self.config = ConfigManager.load(config_path)

        # Initialize components
        self.parser = ParserModule()
        self.manager: TranslationManager | None = None
        self._wrapped_config = TranslatorConfig(self.config)
        self.assembler = CodeAssembler(self._wrapped_config)
        self.validator = Validator(self._wrapped_config)

        # Worker thread management
        self._worker_thread: QThread | None = None
        self._worker: TranslationWorker | None = None

        # State tracking
        self._is_translating = False
        self._model_initialized = False
        self._is_streaming = False
        self._streaming_pipeline = None

        # Auto-initialize model in background
        self._init_model_async()

    @property
    def is_ready(self) -> bool:
        """Check if the translator is ready to process requests"""
        return self._model_initialized and not self._is_translating and not self._is_streaming

    @property
    def is_translating(self) -> bool:
        """Check if a translation is currently in progress"""
        return self._is_translating

    def translate(self, pseudocode: str) -> TranslationResult:
        """
        Synchronous translation method

        Args:
            pseudocode: Mixed English/Python pseudocode input

        Returns:
            TranslationResult object with code and metadata

        Note:
            This method blocks until translation is complete.
            For GUI applications, use translate_async() instead.
        """
        try:
            # Ensure manager is initialized
            if not self._model_initialized or self.manager is None:
                self.model_status_changed.emit("Initializing model...")
                self.manager = TranslationManager(self._wrapped_config)
                self._model_initialized = True
                self.model_initialized.emit()

            # Emit status for GUI parity
            self.translation_status.emit(
                TranslationStatus(phase="parsing", progress=10, message="Parsing pseudocode...")
            )
            parse_result = self.parser.get_parse_result(pseudocode)

            # Delegate full translation to TranslationManager
            self.translation_status.emit(
                TranslationStatus(
                    phase="translating", progress=30, message="Translating to Python..."
                )
            )
            mgr_result = self.manager.translate_pseudocode(pseudocode)

            # Validate using existing validator for consistent GUI behavior
            self.translation_status.emit(
                TranslationStatus(
                    phase="validating",
                    progress=90,
                    message="Validating generated code...",
                )
            )
            final_code = mgr_result.code or ""
            validation = self.validator.validate_syntax(final_code)

            errors = list(mgr_result.errors)
            if not validation.is_valid:
                errors.extend(validation.errors)

            warnings = list(set(mgr_result.warnings + getattr(parse_result, "warnings", [])))

            result = TranslationResult(
                success=(validation.is_valid and mgr_result.success and bool(final_code.strip())),
                code=final_code if final_code.strip() else None,
                errors=errors,
                warnings=warnings,
                metadata={
                    **mgr_result.metadata,
                    "blocks_processed": getattr(parse_result, "block_count", 0),
                },
                parse_result=parse_result,
            )

            self.translation_progress.emit(100)
            return result

        except Exception as e:
            logger.error("Translation failed: %s", e)
            return TranslationResult(
                success=False,
                code=None,
                errors=[str(e)],
                warnings=[],
                metadata={"error": str(e)},
            )

    @Slot(str)
    def translate_async(self, pseudocode: str):
        """
        Asynchronous translation method using worker thread

        Args:
            pseudocode: Mixed English/Python pseudocode input

        Emits:
            translation_started: When translation begins
            translation_progress: Progress updates (0-100)
            translation_status: Detailed status updates
            translation_completed: When done with TranslationResult
            translation_error: If an error occurs
        """
        if self._is_translating:
            self.translation_error.emit("Translation already in progress")
            return

        # Clean up previous worker if exists
        self._cleanup_worker()

        # Create new worker thread
        self._worker_thread = QThread()
        # Ensure manager initialized
        if self.manager is None or not self._model_initialized:
            try:
                self.manager = TranslationManager(self._wrapped_config)
                self._model_initialized = True
                self.model_initialized.emit()
            except Exception as e:
                self.translation_error.emit(str(e))
                return
        self._worker = TranslationWorker(
            pseudocode, self._wrapped_config, self.parser, self.manager
        )

        # Move worker to thread
        self._worker.moveToThread(self._worker_thread)

        # Connect signals
        self._worker_thread.started.connect(self._worker.run)
        self._worker.started.connect(self._on_translation_started)
        self._worker.progress.connect(self.translation_progress)
        self._worker.status.connect(self.translation_status)
        self._worker.completed.connect(self._on_translation_completed)
        self._worker.error.connect(self._on_translation_error)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        # Start translation
        self._is_translating = True
        self._worker_thread.start()

    @Slot()
    def cancel_translation(self):
        """Cancel the current translation operation"""
        if self._worker and self._is_translating:
            self._worker.cancel()
            self.translation_status.emit(
                TranslationStatus(
                    phase="cancelled",
                    progress=0,
                    message="Translation cancelled by user",
                )
            )

    def get_model_status(self) -> dict[str, Any]:
        """
        Get current model status and health information

        Returns:
            Dictionary with model status information
        """
        if self.manager is None:
            return {
                "status": "not_initialized",
                "model_name": None,
                "available_models": [],
            }
        return {
            "status": "ready" if self._model_initialized else "initializing",
            "model_name": self.manager.get_current_model(),
            "available_models": self.manager.list_available_models(),
        }

    def update_config(self, config_updates: dict[str, Any]):
        """
        Update configuration without restart

        Args:
            config_updates: Dictionary of configuration updates
        """
        # Update config fields
        for key, value in config_updates.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
            elif hasattr(self.config.llm, key):
                setattr(self.config.llm, key, value)

        # Re-initialize if model config changed
        if any(key in config_updates for key in ["model_path", "model_file"]):
            self._model_initialized = False
            self._init_model_async()

    def warmup_model(self):
        """Warm up the model for better initial performance"""
        if self._model_initialized:

            def _warmup():
                try:
                    if self.manager is None:
                        self.manager = TranslationManager(self._wrapped_config)
                    self.manager.translate_text_block(
                        text="pass",
                        context={"warmup": True},
                        config={"max_tokens": 16, "temperature": 0.0},
                    )
                except Exception:
                    pass

            thread = QThread()
            thread.run = _warmup
            thread.start()

    @Slot(str)
    def translate_streaming(self, pseudocode: str):
        """
        Translate using streaming for memory-efficient processing

        Args:
            pseudocode: Mixed English/Python pseudocode input

        Emits:
            streaming_started: When streaming begins
            streaming_chunk_processed: For each processed chunk
            streaming_progress: Progress info
            streaming_completed: When done with final code
            translation_error: If an error occurs
        """
        if self._is_streaming or self._is_translating:
            self.translation_error.emit("Translation already in progress")
            return

        self._is_streaming = True

        def run_streaming():
            try:
                # Ensure manager initialized
                if self.manager is None or not self._model_initialized:
                    self.manager = TranslationManager(self._wrapped_config)
                    self._model_initialized = True
                    self.model_initialized.emit()

                self.streaming_started.emit()

                # Progress callback wrapper to convert to dict
                def on_progress(progress_obj):
                    try:
                        progress_info = {
                            "progress": getattr(progress_obj, "progress_percentage", None),
                            "chunks_processed": getattr(progress_obj, "processed_chunks", None),
                            "total_chunks": getattr(progress_obj, "total_chunks", None),
                            "bytes_processed": getattr(progress_obj, "bytes_processed", None),
                            "total_bytes": getattr(progress_obj, "total_bytes", None),
                            "errors": getattr(progress_obj, "errors", []),
                            "warnings": getattr(progress_obj, "warnings", []),
                        }
                    except Exception:
                        # If manager provides dict already
                        progress_info = progress_obj if isinstance(progress_obj, dict) else {}
                    self.streaming_progress.emit(progress_info)

                final_code: str | None = None

                for res in self.manager.translate_streaming(
                    pseudocode, progress_callback=on_progress
                ):
                    # Emit chunk updates if available
                    if isinstance(res.metadata, dict) and res.metadata.get("streaming", False):
                        chunk_index = res.metadata.get("chunk_index")
                        if res.code and chunk_index is not None:
                            with contextlib.suppress(Exception):
                                self.streaming_chunk_processed.emit(int(chunk_index), res.code)
                    if res.code:
                        final_code = res.code

                if final_code is None:
                    final_code = ""

                # Validate final code for GUI parity
                validation_result = self.validator.validate_syntax(final_code)
                result = TranslationResult(
                    success=validation_result.is_valid,
                    code=final_code,
                    errors=validation_result.errors,
                    warnings=validation_result.warnings,
                    metadata={"streaming": True},
                )

                self.streaming_completed.emit(final_code)
                self.translation_completed.emit(result)

            except Exception as e:
                logger.error("Streaming translation failed: %s", e)
                self.translation_error.emit(str(e))
            finally:
                self._is_streaming = False

        # Run in thread
        thread = QThread()
        thread.run = run_streaming
        thread.start()

    @Slot()
    def cancel_streaming(self):
        """Cancel ongoing streaming operation"""
        if self._streaming_pipeline:
            self._streaming_pipeline.cancel_streaming()
            self.translation_status.emit(
                TranslationStatus(
                    phase="cancelled",
                    progress=0,
                    message="Streaming translation cancelled",
                )
            )

    def get_memory_usage(self) -> dict[str, Any]:
        """
        Get current memory usage statistics

        Returns:
            Dictionary with memory usage information
        """
        if self._streaming_pipeline:
            return self._streaming_pipeline.get_memory_usage()
        return {"buffer_size": 0, "context_window_size": 0, "queue_size": 0}

    # Private methods

    def _init_model_async(self):
        """Initialize model in background thread"""

        def init_model():
            try:
                self.model_status_changed.emit("Loading language model...")
                self.manager = TranslationManager(self._wrapped_config)
                self._model_initialized = True
                self.model_status_changed.emit("Model ready")
                self.model_initialized.emit()
            except Exception as e:
                self.model_status_changed.emit(f"Model initialization failed: {e}")
                self.translation_error.emit(f"Failed to initialize model: {e}")

        thread = QThread()
        thread.run = init_model
        thread.start()

    def _create_code_blocks_for_assembly(
        self, parse_result: ParseResult, translated_blocks: list[str]
    ) -> list[CodeBlock]:
        """
        Create CodeBlock objects for assembly by combining original blocks with translations

        Args:
            parse_result: The parse result containing all blocks
            translated_blocks: List of translated Python code for English blocks

        Returns:
            List of CodeBlock objects ready for assembly
        """
        assembled_blocks = []
        translation_index = 0

        for block in parse_result.blocks:
            if block.type == BlockType.ENGLISH:
                # Replace English block with translated Python code
                if translation_index < len(translated_blocks):
                    translated_code = translated_blocks[translation_index]
                    # Create a new CodeBlock with the translated content
                    python_block = CodeBlock(
                        type=BlockType.PYTHON,
                        content=translated_code,
                        line_numbers=block.line_numbers,
                        context=block.context,
                        metadata=block.metadata,
                    )
                    assembled_blocks.append(python_block)
                    translation_index += 1
            else:
                # Keep other blocks as-is (Python, Comment, Mixed)
                assembled_blocks.append(block)

        return assembled_blocks

    def _cleanup_worker(self):
        """Clean up worker thread resources"""
        if self._worker_thread and self._worker_thread.isRunning():
            self._worker_thread.quit()
            self._worker_thread.wait()

        self._worker = None
        self._worker_thread = None

    # Slot handlers

    @Slot()
    def _on_translation_started(self):
        """Handle translation start"""
        self.translation_started.emit()

    @Slot(TranslationResult)
    def _on_translation_completed(self, result: TranslationResult):
        """Handle translation completion"""
        self._is_translating = False
        self.translation_completed.emit(result)

    @Slot(str)
    def _on_translation_error(self, error: str):
        """Handle translation error"""
        self._is_translating = False
        self.translation_error.emit(error)

    # Cleanup

    def __del__(self):
        """Cleanup on deletion"""
        self._cleanup_worker()
        if hasattr(self, "manager") and self.manager is not None:
            self.manager.shutdown()


# Convenience factory function
def create_translator_api(config_path: str | None = None) -> PseudocodeTranslatorAPI:
    """
    Create a translator API instance

    Args:
        config_path: Optional configuration file path

    Returns:
        Configured PseudocodeTranslatorAPI instance
    """
    return PseudocodeTranslatorAPI(config_path)
