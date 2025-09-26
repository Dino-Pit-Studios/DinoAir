"""
Streaming Translator for real-time pseudocode translation

This module provides a StreamingTranslator with reduced internal complexity
via consolidated parse+translate helpers.
"""

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from queue import Queue
from typing import Any

from ..config import TranslatorConfig
from ..exceptions import StreamingError
from ..models import CodeBlock
from ..parser import ParserModule
from ..translator import TranslationManager
from .buffer import BufferConfig, ContextBuffer, StreamBuffer
from .chunker import ChunkConfig, CodeChunker
from .event_runtime import EventRuntime
from .events import StreamingEvent, StreamingEventData, StreamingMode, TranslationUpdate
from .interactive_core import (
    interactive_translate,
    interactive_translate_async,
    process_interactive_input,
)
from .pipeline import StreamingProgress
from .translation_invoker import TranslationInvoker
from .translator_core import (
    is_complete_statement,
    parse_and_translate_blocks,
    parse_success,
    process_accumulated_blocks,
    process_statement,
    translate_block,
    translate_chunk_blocks,
)

logger = logging.getLogger(__name__)

__all__ = ["StreamingTranslator", "StreamingMode"]


class StreamingTranslator:
    """
    Real-time streaming translator with progressive results and cancellation support
    """

    def __init__(self, config: TranslatorConfig):
        """
        Initialize the streaming translator

        Args:
            config: Translator configuration
        """
        self.config = config
        self.parser = ParserModule()
        self.chunker = CodeChunker(
            ChunkConfig(
                max_chunk_size=config.max_context_length,
                respect_boundaries=True,
                chunk_by_blocks=True,
            )
        )

        # Translation components
        self.translation_manager = None
        self.context_buffer = ContextBuffer(window_size=2048)

        # Streaming state
        self.is_streaming = False
        self.is_cancelled = False
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused by default

        # Event system
        self.event_listeners = []
        self.event_queue = Queue()
        self._event_thread = None

        # Runtime for lifecycle/eventing
        self._rt = EventRuntime()

        # Progress tracking
        self.current_progress = StreamingProgress()

        # Results buffer
        self.result_buffer = StreamBuffer(BufferConfig(max_size_mb=100, enable_compression=True))

        # Translation invoker (used by translator_core helpers)
        self._invoker = TranslationInvoker(self._emit_event, self.context_buffer)

        # Interactive mode state
        self.interactive_session = None

        # Helper bindings (extracted to reduce LOC & complexity)
        self._parse_success = parse_success
        self._parse_and_translate_blocks = (
            lambda text, chunk_index, on_update=None: parse_and_translate_blocks(
                self, text, chunk_index, on_update
            )
        )
        self._translate_chunk_blocks = (
            lambda parse_result, chunk_index, on_update=None: translate_chunk_blocks(
                self, parse_result, chunk_index, on_update
            )
        )
        self._translate_block = lambda block, chunk_index, block_index: translate_block(
            self, block, chunk_index, block_index
        )
        self._is_complete_statement = is_complete_statement
        self._process_statement = lambda statement, chunk_index, on_update=None: process_statement(
            self, statement, chunk_index, on_update
        )
        self._process_accumulated_blocks = (
            lambda accumulated_input, on_update=None: process_accumulated_blocks(
                self, accumulated_input, on_update
            )
        )
        self._process_interactive_input = (
            lambda user_input,
            session_context,
            interaction_count,
            on_update=None: process_interactive_input(
                self, user_input, session_context, interaction_count, on_update
            )
        )

    def add_event_listener(self, listener: Callable[[StreamingEventData], None]):
        """
        Add an event listener for streaming events

        Args:
            listener: Callback function for events
        """
        self.event_listeners.append(listener)
        self._rt.add_listener(listener)

    def remove_event_listener(self, listener: Callable[[StreamingEventData], None]):
        """Remove an event listener"""
        if listener in self.event_listeners:
            self.event_listeners.remove(listener)
        self._rt.remove_listener(listener)

    async def translate_stream_async(
        self,
        input_stream: AsyncIterator[str],
        mode: StreamingMode = StreamingMode.BLOCK_BY_BLOCK,
        on_update: Callable[[TranslationUpdate], None] | None = None,
    ) -> AsyncIterator[str]:
        """
        Asynchronously translate a stream of input

        Args:
            input_stream: Async iterator of input text
            mode: Streaming mode to use
            on_update: Callback for translation updates

        Yields:
            Translated code chunks
        """
        self._start_streaming()

        try:
            # Initialize translation manager
            self.translation_manager = TranslationManager(self.config)

            # Collect input based on mode using strategy map
            async_strategies = {
                StreamingMode.LINE_BY_LINE: self._translate_line_by_line_async,
                StreamingMode.BLOCK_BY_BLOCK: self._translate_block_by_block_async,
                StreamingMode.FULL_DOCUMENT: self._translate_full_document_async,
                StreamingMode.INTERACTIVE: self._translate_interactive_async,
            }
            strategy = async_strategies.get(mode)
            if strategy:
                if mode == StreamingMode.FULL_DOCUMENT:
                    # Collect all input first
                    full_input = []
                    async for chunk in input_stream:
                        full_input.append(chunk)
                        if self._check_cancelled():
                            return

                    # Translate as complete document
                    full_text = "".join(full_input)
                    async for translated in strategy(full_text, on_update):
                        yield translated
                else:
                    async for translated in strategy(input_stream, on_update):
                        yield translated

        except Exception as e:
            self._emit_event(StreamingEventData(event=StreamingEvent.ERROR, error=str(e)))
            raise StreamingError(f"Streaming translation failed: {e}")

        finally:
            self._stop_streaming()
            if self.translation_manager:
                self.translation_manager.shutdown()

    def translate_stream(
        self,
        input_stream: Iterator[str],
        mode: StreamingMode = StreamingMode.BLOCK_BY_BLOCK,
        on_update: Callable[[TranslationUpdate], None] | None = None,
    ) -> Iterator[str]:
        """
        Synchronously translate a stream of input

        Args:
            input_stream: Iterator of input text
            mode: Streaming mode to use
            on_update: Callback for translation updates

        Yields:
            Translated code chunks
        """
        self._start_streaming()

        try:
            # Initialize translation manager
            self.translation_manager = TranslationManager(self.config)

            # Strategy map for sync dispatch
            sync_strategies = {
                StreamingMode.LINE_BY_LINE: self._translate_line_by_line,
                StreamingMode.BLOCK_BY_BLOCK: self._translate_block_by_block,
                StreamingMode.FULL_DOCUMENT: self._translate_full_document,
                StreamingMode.INTERACTIVE: self._translate_interactive,
            }
            strategy = sync_strategies.get(mode)
            if strategy:
                if mode == StreamingMode.FULL_DOCUMENT:
                    # Collect all input first
                    full_text = "".join(input_stream)
                    yield from strategy(full_text, on_update)
                else:
                    yield from strategy(input_stream, on_update)

        except Exception as e:
            self._emit_event(StreamingEventData(event=StreamingEvent.ERROR, error=str(e)))
            raise StreamingError(f"Streaming translation failed: {e}")

        finally:
            self._stop_streaming()
            if self.translation_manager:
                self.translation_manager.shutdown()

    def _translate_interactive(self, input_stream, on_update=None):
        # Thin wrapper delegating to extracted generator
        yield from interactive_translate(self, input_stream, on_update)

    async def _translate_interactive_async(self, input_stream, on_update=None):
        async for out in interactive_translate_async(self, input_stream, on_update):
            yield out

    def _translate_line_by_line(self, input_stream, on_update=None):
        """Translate incrementally when a complete statement is detected (sync)."""
        line_buffer: list[str] = []
        chunk_index = 0
        for line in input_stream:
            if self._check_cancelled():
                break
            self._wait_if_paused()
            line_buffer.append(line)
            if self._is_complete_statement("".join(line_buffer)):
                statement = "".join(line_buffer)
                line_buffer.clear()
                translated = self._process_statement(statement, chunk_index, on_update)
                if translated:
                    yield translated
                chunk_index += 1

    def _translate_block_by_block(self, input_stream, on_update=None):
        """Translate whenever parser identifies a complete block boundary (sync)."""
        accumulated_input: list[str] = []
        for chunk in input_stream:
            if self._check_cancelled():
                break
            self._wait_if_paused()
            accumulated_input.append(chunk)
            result = self._process_accumulated_blocks(accumulated_input, on_update)
            if result:
                translated_chunks, remaining = result
                if translated_chunks:
                    yield from translated_chunks
                accumulated_input = remaining

    def _translate_full_document(self, full_text: str, on_update=None):
        """Translate an entire document as a single unit (sync)."""
        # Emit chunk lifecycle for full-document path
        self._emit_event(StreamingEventData(event=StreamingEvent.CHUNK_STARTED, chunk_index=0))
        try:
            for t in self._parse_and_translate_blocks(full_text, 0, on_update):
                # Ensure full-document outputs are chunk-like and end with double newline
                yield f"{t}\n\n"
        finally:
            self._emit_event(
                StreamingEventData(event=StreamingEvent.CHUNK_COMPLETED, chunk_index=0)
            )

    def cancel(self):
        """Cancel the streaming translation"""
        # Preserve legacy flags for API/behavioral stability
        self.is_cancelled = True
        self._cancel_event.set()
        # Delegate to runtime
        self._rt.cancel()
        # Emit cancellation event via runtime
        self._emit_event(StreamingEventData(event=StreamingEvent.CANCELLED))

    def pause(self):
        """Pause the streaming translation"""
        # Delegate to runtime
        self._rt.pause()
        # Maintain legacy flag semantics
        self._pause_event.clear()

    def resume(self):
        """Resume the streaming translation"""
        # Delegate to runtime
        self._rt.resume()
        # Maintain legacy flag semantics
        self._pause_event.set()

    def _rt_check_cancelled(self) -> bool:
        """Check if translation is cancelled"""
        return self._rt.check_cancelled()

    def _rt_wait_if_paused(self):
        """Wait if translation is paused"""
        self._rt.wait_if_paused()

    def _rt_start_streaming(self):
        """Initialize streaming state"""
        # Maintain legacy flags
        self.is_streaming = True
        self.is_cancelled = False
        self._cancel_event.clear()
        self._pause_event.set()
        self.current_progress = StreamingProgress()

        # Delegate lifecycle to runtime (worker managed internally)
        self._rt.start(self.current_progress)

        # Emit started via runtime
        self._emit_event(StreamingEventData(event=StreamingEvent.STARTED))

    def _stop_streaming(self):
        """Clean up streaming state"""
        self.is_streaming = False

        cancelled = self._rt.check_cancelled() or self.is_cancelled
        if not cancelled:
            self._emit_event(
                StreamingEventData(event=StreamingEvent.COMPLETED, progress=self.current_progress)
            )

        # Delegate shutdown to runtime
        self._rt.stop(self.current_progress, cancelled)

    def _emit_event(self, event_data: StreamingEventData):
        """Emit an event to all listeners"""
        self._rt.emit(event_data)

    def _handle_events(self):
        """Process events (delegated to EventRuntime worker)."""
        # The runtime owns the worker loop; this method remains for backward references.
        return

    def _translate_single_block(
        self, block: CodeBlock, chunk_index: int, block_index: int
    ) -> str | None:
        """Translate a single block (delegated to core helper)."""
        return translate_block(self, block, chunk_index, block_index)

    def _build_translation_context(self) -> dict[str, Any]:
        """Build translation context from buffer"""
        return {
            "code": self.context_buffer.get_context(),
            "streaming": True,
            "mode": "real-time",
        }

    # Async versions of translation methods
    async def _translate_line_by_line_async(
        self,
        input_stream: AsyncIterator[str],
        on_update: Callable[[TranslationUpdate], None] | None = None,
    ) -> AsyncIterator[str]:
        """Async version of line-by-line translation"""
        line_buffer = []
        chunk_index = 0

        async for line in input_stream:
            if self._rt_check_cancelled():
                break

            self._rt_wait_if_paused()

            line_buffer.append(line)

            if self._is_complete_statement("".join(line_buffer)):
                statement = "".join(line_buffer)
                line_buffer.clear()

                # Process in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                translated = await loop.run_in_executor(
                    None, self._process_statement, statement, chunk_index, on_update
                )

                if translated:
                    yield translated

                chunk_index += 1

    async def _translate_block_by_block_async(
        self,
        input_stream: AsyncIterator[str],
        on_update: Callable[[TranslationUpdate], None] | None = None,
    ) -> AsyncIterator[str]:
        """Async version of block-by-block translation"""
        accumulated_input = []

        async for chunk in input_stream:
            if self._rt_check_cancelled():
                break

            self._rt_wait_if_paused()
            accumulated_input.append(chunk)

            # Process in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._process_accumulated_blocks, accumulated_input, on_update
            )

            if result:
                translated, remaining = result
                if translated:
                    for t in translated:
                        yield t
                accumulated_input = remaining

    async def _translate_full_document_async(
        self,
        full_text: str,
        on_update: Callable[[TranslationUpdate], None] | None = None,
    ) -> AsyncIterator[str]:
        """Async version of full document translation"""
        # Process in thread pool
        loop = asyncio.get_event_loop()

        # Use sync generator in thread
        def generate():
            return list(self._translate_full_document(full_text, on_update))

        results = await loop.run_in_executor(None, generate)

        for result in results:
            if self._rt_check_cancelled():
                break
            yield result

    def _process_statement(
        self,
        statement: str,
        chunk_index: int,
        on_update: Callable[[TranslationUpdate], None] | None,
    ) -> str | None:
        """Process a single statement (refactored)."""
        translations = self._parse_and_translate_blocks(statement, chunk_index, on_update)
        return ("\n".join(translations) + "\n") if translations else None

    def identify_blocks(self, current_input: str) -> list[str]:
        return self.parser.identify_blocks(current_input)

    def _process_accumulated_blocks(
        self,
        accumulated_input: list[str],
        on_update: Callable[[TranslationUpdate], None] | None,
    ) -> tuple | None:
        """Process accumulated blocks and return (translated_list, remaining_list) (refactored)."""
        current_input = "".join(accumulated_input)
        try:
            blocks = self.identify_blocks(current_input)
            if len(blocks) > 1:
                translated_chunks: list[str] = []
                for i, block_text in enumerate(blocks[:-1]):
                    if not block_text.strip():
                        continue
                    translations = self._parse_and_translate_blocks(block_text, i, on_update)
                    if translations:
                        translated_chunks.append("\n".join(translations) + "\n\n")
                return translated_chunks, [blocks[-1]]
        except Exception as e:
            logger.warning("Error processing blocks: %s", e)
        return None
