"""
Streaming pipeline for memory-efficient pseudocode translation

This module provides a streaming pipeline that processes code chunks through
the translation stages while maintaining context and handling backpressure.
"""

import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

# Note on imports: to avoid circular imports with translator.py, we avoid
# importing TranslationManager at module import time. We import it lazily
# inside methods that need it.
from ..config import TranslatorConfig
from ..integration.events import EventType
from ..models import BlockType, CodeBlock
from ..models.base_model import TranslationResult as ModelTranslationResult
from ..telemetry import get_recorder
from .chunker import CodeChunk

logger = logging.getLogger(__name__)


@dataclass
class StreamConfig:
    """Configuration for streaming pipeline"""

    enable_streaming: bool = True
    min_file_size_for_streaming: int = 1024 * 100  # 100KB
    max_concurrent_chunks: int = 3
    chunk_timeout: float = 30.0
    progress_callback_interval: float = 0.5
    maintain_context_window: bool = True
    context_window_size: int = 1024  # Characters
    enable_backpressure: bool = True
    max_queue_size: int = 10
    thread_pool_size: int = 4


@dataclass
class StreamingProgress:
    """Progress information for streaming operations"""

    total_chunks: int = 0
    processed_chunks: int = 0
    current_chunk: int | None = None
    bytes_processed: int = 0
    total_bytes: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def progress_percentage(self) -> float:
        """Get progress as percentage"""
        if self.total_chunks == 0:
            return 0.0
        return (self.processed_chunks / self.total_chunks) * 100

    @property
    def is_complete(self) -> bool:
        """Check if streaming is complete"""
        return self.processed_chunks >= self.total_chunks


@dataclass
class ChunkResult:
    """Result of processing a single chunk"""

    chunk_index: int
    success: bool
    parsed_blocks: list[Any] | None = None
    translated_blocks: list[Any] | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    processing_time: float = 0.0


class StreamingPipeline:
    """Manages streaming translation pipeline with backpressure and context"""

    def __init__(self, config: TranslatorConfig, stream_config: StreamConfig | None = None):
        """Initialize streaming pipeline"""

    def _dispatch(self, event_type, **data):
        """Best-effort event dispatch via manager's dispatcher; never raises."""
        try:
            if self.translator:
                try:
                    pass
                except Exception:
                    pass
        except Exception:
            pass

    def _get_dispatcher(self):
        try:
            return self.translator.get_event_dispatcher()
        except Exception:
            return None

    def _dispatch_decision(self, previous_size: int, next_size: int):
        dispatcher = self._get_dispatcher()
        if dispatcher:
            reason = "increase" if next_size > previous_size else "decrease"
            dispatcher.dispatch_event(
                EventType.STREAM_DECISION,
                source=self.__class__.__name__,
                reason=reason,
                previous_size=previous_size,
                next_size=next_size,
            )

    def _dispatch_chunk_event(self, chunk_idx: int, chunk_length: int, duration: float):
        dispatcher = self._get_dispatcher()
        if dispatcher:
            dispatcher.dispatch_event(
                EventType.STREAM_CHUNK,
                source=self.__class__.__name__,
                chunk_idx=chunk_idx,
                chunk_length=chunk_length,
                duration=duration,
            )

    def _adaptive_sequential_stream(
        self,
        code: str,
        sizer,
        recorder,
    ) -> Iterator[ChunkResult]:
        sc = self.config.streaming
        text = code
        n = len(text)
        pos = 0
        chunk_idx = 0
        prev_size: int | None = None

        hard_cap_max = int(self.config.max_context_length * 2)

        while pos < n and not self._stop_event.is_set():
            desired = int(sizer.get_next_chunk_size(default_chunk_size=sc.chunk_size))
            desired = max(1, min(desired, hard_cap_max))

            if prev_size is not None and desired != prev_size:
                self._dispatch_decision(prev_size, desired)

            start = pos
            end = min(pos + desired, n)
            text_chunk = text[start:end]
            chunk_idx += 1

            start_time = time.perf_counter()
            try:
                result = self.translator.stream_translate(text_chunk)
            except Exception as e:
                result = self.translator.CodecErrorResult(e)
            duration = time.perf_counter() - start_time

            self._dispatch_chunk_event(chunk_idx, len(text_chunk), duration)

            chunk_result = self._process_chunk(result, recorder)
            prev_size = desired
            pos = end
            yield chunk_result

        total_start = time.perf_counter()
        try:
            if getattr(self.config.streaming, "adaptive_chunking_enabled", False):
                # Run adaptive sequential path (keep parallel path unchanged/off for adaptive in this version)
                yield from self._adaptive_sequential_stream(code, sizer, recorder)
            else:
                # Existing behavior (precompute chunks via chunker and process)
                chunks = list(self.chunker.stream_chunks(code, None))
                self.progress.total_chunks = len(chunks)

                if self.stream_config.max_concurrent_chunks > 1:
                    # Parallel processing
                    yield from self._process_chunks_parallel(chunks)
                else:
                    # Sequential processing
                    yield from self._process_chunks_sequential(chunks)

        finally:
            # Record total stream time
            try:
                recorder.record_event("stream.total", (time.perf_counter() - total_start) * 1000.0)
            except Exception:
                pass

            # Emit STREAM_COMPLETED with processed chunk count
            self._dispatch(EventType.STREAM_COMPLETED, chunks=self.progress.processed_chunks)

            # Cleanup
            self._stop_progress_reporting()
            if self.translator:
                self.translator.shutdown()

    def _process_chunks_sequential(self, chunks: list[CodeChunk]) -> Iterator[ChunkResult]:
        """
        Process chunks sequentially

        Args:
            chunks: List of code chunks

        Yields:
            ChunkResult objects
        """
        for chunk in chunks:
            if self._stop_event.is_set():
                break

            start_time = time.time()
            self.progress.current_chunk = chunk.chunk_index

            try:
                # Process chunk
                result = self._process_single_chunk(chunk)
                result.processing_time = time.time() - start_time
                try:
                    recorder = get_recorder()
                    recorder.record_event(
                        "stream.chunk",
                        result.processing_time * 1000.0,
                        extra={"chunk_index": chunk.chunk_index, "size": chunk.size},
                    )
                except Exception:
                    pass

                # Update progress
                self.progress.processed_chunks += 1
                self.progress.bytes_processed += chunk.size

                if result.error:
                    self.progress.errors.append(result.error)
                self.progress.warnings.extend(result.warnings)

                # Emit per-chunk event
                self._dispatch(
                    EventType.STREAM_CHUNK_PROCESSED,
                    index=chunk.chunk_index,
                    success=bool(result.success),
                    duration_ms=int(result.processing_time * 1000.0),
                )

                yield result

            except Exception as e:
                logger.error("Error processing chunk %s: %s", chunk.chunk_index, e)
                fail = ChunkResult(
                    chunk_index=chunk.chunk_index,
                    success=False,
                    error=str(e),
                    processing_time=time.time() - start_time,
                )
                # Emit per-chunk event for failure
                self._dispatch(
                    EventType.STREAM_CHUNK_PROCESSED,
                    index=chunk.chunk_index,
                    success=False,
                    duration_ms=int(fail.processing_time * 1000.0),
                )
                yield fail

    def _process_chunks_parallel(self, chunks: list[CodeChunk]) -> Iterator[ChunkResult]:
        """
        Process chunks in parallel with backpressure

        Args:
            chunks: List of code chunks

        Yields:
            ChunkResult objects
        """
        from concurrent.futures import FIRST_COMPLETED, wait

        # Track all outstanding work (running + queued in executor)
        futures: dict[Any, CodeChunk] = {}
        chunk_iter = iter(chunks)

        # Pre-fill up to max_concurrent_chunks to cap initial in-flight work.
        # Additional submissions are bounded by (max_concurrent_chunks + max_queue_size)
        # which limits queued-but-not-yet-executing work, providing backpressure upstream.
        initial = min(self.stream_config.max_concurrent_chunks, len(chunks))
        for _ in range(initial):
            try:
                chunk = next(chunk_iter)
            except StopIteration:
                break
            fut = self.executor.submit(self._process_single_chunk, chunk)
            futures[fut] = chunk

        # Combined window for outstanding work. When backpressure is disabled, we
        # fall back to strict concurrency only.
        combined_limit = (
            self.stream_config.max_concurrent_chunks + self.stream_config.max_queue_size
            if self.stream_config.enable_backpressure
            else self.stream_config.max_concurrent_chunks
        )

        # Submission/collection loop
        while True:
            # Submit as many as allowed by the combined window
            while len(futures) < combined_limit:
                try:
                    next_chunk = next(chunk_iter)
                except StopIteration:
                    break
                fut = self.executor.submit(self._process_single_chunk, next_chunk)
                futures[fut] = next_chunk

            if not futures:
                # No outstanding work and no more chunks to submit
                break

            # Backpressure: we've reached the window or have nothing more to submit.
            # Block until at least one future completes to free capacity.
            done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)

            for fut in list(done):
                chunk = futures.pop(fut)
                try:
                    result = fut.result(timeout=self.stream_config.chunk_timeout)

                    try:
                        recorder = get_recorder()
                        recorder.record_event(
                            "stream.chunk",
                            getattr(result, "processing_time", 0.0) * 1000.0,
                            extra={
                                "chunk_index": chunk.chunk_index,
                                "size": chunk.size,
                            },
                        )
                    except Exception:
                        pass

                    # Update progress
                    self.progress.processed_chunks += 1
                    self.progress.bytes_processed += chunk.size

                    if result.error:
                        self.progress.errors.append(result.error)
                    self.progress.warnings.extend(result.warnings)

                    # Emit per-chunk event
                    self._dispatch(
                        EventType.STREAM_CHUNK_PROCESSED,
                        index=chunk.chunk_index,
                        success=bool(result.success),
                        duration_ms=int(getattr(result, "processing_time", 0.0) * 1000.0),
                    )

                    yield result
                except Exception as e:
                    logger.error("Error processing chunk %s: %s", chunk.chunk_index, e)
                    # Emit per-chunk failure event
                    self._dispatch(
                        EventType.STREAM_CHUNK_PROCESSED,
                        index=chunk.chunk_index,
                        success=False,
                    )
                    yield ChunkResult(chunk_index=chunk.chunk_index, success=False, error=str(e))

    def _process_single_chunk(self, chunk: CodeChunk) -> ChunkResult:
        """
        Process a single chunk through the pipeline

        Args:
            chunk: Code chunk to process

        Returns:
            ChunkResult
        """
        start_time = time.time()
        result = ChunkResult(chunk_index=chunk.chunk_index, success=True)

        try:
            # Add context from previous chunks
            chunk_with_context = self._add_context_to_chunk(chunk)

            # Parse the chunk
            parse_result = self.parser.get_parse_result(chunk_with_context)

            # Be robust to different ParseResult shapes (property vs computed)
            success_attr = getattr(parse_result, "success", None)
            parse_success = (
                success_attr if isinstance(success_attr, bool) else (len(parse_result.errors) == 0)
            )
            if not parse_success:
                result.success = False
                result.error = f"Parse error: {parse_result.errors}"
                return result

            result.parsed_blocks = parse_result.blocks
            result.warnings.extend(parse_result.warnings)

            # Translate English blocks
            translated_blocks = []
            for block in parse_result.blocks:
                if block.type == BlockType.ENGLISH:
                    # Build translation context
                    context = self._build_translation_context(chunk.chunk_index)

                    try:
                        # Delegate via TranslationManager public wrapper
                        translator = self.translator
                        if translator is None:
                            raise RuntimeError("Translator not initialized")
                        res = translator.translate_text_block(text=block.content, context=context)
                        # Normalize translation result to expected type with .success attribute
                        if (
                            not isinstance(res, ModelTranslationResult)
                            or not getattr(res, "success", False)
                            or getattr(res, "code", None) is None
                        ):
                            raise RuntimeError(
                                "Translation failed: "
                                + (
                                    ", ".join(getattr(res, "errors", []))
                                    if getattr(res, "errors", [])
                                    else "No code returned"
                                )
                            )
                        translated_code = str(res.code)

                        # Create translated block
                        translated_block = CodeBlock(
                            type=BlockType.PYTHON,
                            content=translated_code,
                            line_numbers=block.line_numbers,
                            metadata={**block.metadata, "translated": True},
                            context=block.context,
                        )
                        translated_blocks.append(translated_block)

                    except Exception as e:
                        logger.error("Translation error in chunk %s: %s", chunk.chunk_index, e)
                        result.warnings.append(f"Translation error: {str(e)}")
                        translated_blocks.append(block)  # Keep original
                else:
                    translated_blocks.append(block)

            result.translated_blocks = translated_blocks

            # Update context window
            self._update_context_window(chunk, translated_blocks)

            # Buffer the result
            self.buffer.add_chunk(chunk.chunk_index, result)

        except Exception as e:
            logger.error("Error in chunk %s: %s", chunk.chunk_index, e)
            result.success = False
            result.error = str(e)

        result.processing_time = time.time() - start_time
        return result

    def _add_context_to_chunk(self, chunk: CodeChunk) -> str:
        """
        Add context from previous chunks to current chunk

        Args:
            chunk: Current chunk

        Returns:
            Chunk content with context
        """
        if not self.stream_config.maintain_context_window:
            return chunk.content

        # Get context from buffer
        context_lines = []

        # Add previous chunk's tail if available
        if chunk.chunk_index > 0:
            prev_result = self.buffer.get_chunk(chunk.chunk_index - 1)
            if prev_result and prev_result.translated_blocks:
                # Get last few lines from previous chunk
                last_block = prev_result.translated_blocks[-1]
                context_lines.extend(last_block.content.splitlines()[-10:])

        if context_lines:
            context = "\n".join(context_lines)
            return f"{context}\n\n# --- Chunk {chunk.chunk_index} ---\n\n{chunk.content}"

        return chunk.content

    def _build_translation_context(self, chunk_index: int) -> dict[str, Any]:
        """
        Build context for translation

        Args:
            chunk_index: Current chunk index

        Returns:
            Context dictionary
        """
        context = {"chunk_index": chunk_index, "code": "", "before": "", "after": ""}

        # Get previous chunk's code
        if chunk_index > 0:
            prev_result = self.buffer.get_chunk(chunk_index - 1)
            if prev_result and prev_result.translated_blocks:
                prev_code = "\n".join(
                    block.content
                    for block in prev_result.translated_blocks
                    if block.type == BlockType.PYTHON
                )
                context["before"] = prev_code[-self.stream_config.context_window_size :]
                context["code"] = context["before"]

        return context

    def _update_context_window(self, chunk: CodeChunk, blocks: list[Any]):
        """
        Update the context window with processed blocks

        Args:
            chunk: Processed chunk
            blocks: Translated blocks
        """
        # Keep a sliding window of recent code
        for block in blocks:
            if block.type == BlockType.PYTHON:
                self.context_window.append(
                    {
                        "chunk_index": chunk.chunk_index,
                        "content": block.content,
                        "metadata": block.metadata,
                    }
                )

        # Limit context window size
        max_items = 10
        if len(self.context_window) > max_items:
            self.context_window[:] = self.context_window[-max_items:]

    def assemble_streamed_code(self) -> str:
        """
        Assemble all streamed chunks into final code

        Returns:
            Complete assembled code
        """
        all_blocks = []

        # Get all chunks from buffer in order
        for i in range(self.progress.total_chunks):
            result = self.buffer.get_chunk(i)
            if result and result.translated_blocks:
                all_blocks.extend(result.translated_blocks)

        # Use assembler to create final code
        return self.assembler.assemble(all_blocks)

    def _start_progress_reporting(self):
        """Start the progress reporting thread"""
        self._stop_event.clear()
        self._progress_thread = threading.Thread(target=self._progress_reporter, daemon=True)
        self._progress_thread.start()

    def _stop_progress_reporting(self):
        """Stop the progress reporting thread"""
        self._stop_event.set()
        if self._progress_thread:
            self._progress_thread.join(timeout=1)

    def _progress_reporter(self):
        """Thread function for reporting progress"""
        while not self._stop_event.is_set():
            # Report progress to all callbacks
            for callback in self.progress_callbacks:
                try:
                    callback(self.progress)
                except Exception as e:
                    logger.error("Error in progress callback: %s", e)

            # Wait before next update
            self._stop_event.wait(self.stream_config.progress_callback_interval)

    def cancel_streaming(self):
        """Cancel ongoing streaming operation"""
        self._stop_event.set()
        self.executor.shutdown(wait=False)
        logger.info("Streaming operation cancelled")

    def get_memory_usage(self) -> dict[str, int]:
        """
        Get current memory usage statistics

        Returns:
            Memory usage in bytes
        """
        return {
            "buffer_size": self.buffer.get_size(),
            "context_window_size": sum(
                len(item["content"].encode("utf-8")) for item in self.context_window
            ),
            # No internal chunk_queue; queued work is bounded via submission window.
            # Expose 0 to preserve key without referencing removed attribute.
            "queue_size": 0,
        }
