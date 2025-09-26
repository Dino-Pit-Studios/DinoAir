"""
StreamEmitter centralizes event emissions for streaming-related translator events.

This helper preserves existing event types and payload shapes by delegating to the
translator's EventDispatcher with identical keys as currently used in translator.py
and streaming.pipeline. Emissions are best-effort and never raise.
"""

import contextlib

from ..integration.events import EventDispatcher, EventType


class StreamEmitter:
    """
    Lightweight wrapper around EventDispatcher for streaming emissions.

    Note:
    - Payload keys and event types are preserved exactly as used today.
    - Emissions are best-effort (exceptions are swallowed).
    """

    def __init__(self, dispatcher: EventDispatcher, source: str | None = None):
        self._d = dispatcher
        self._source = source

    def translation_started(self, translation_id: int, mode: str):
        # TRANSLATION_STARTED payload keys: mode, id
        with contextlib.suppress(AttributeError, TypeError, ValueError):
            self._d.dispatch_event(
                EventType.TRANSLATION_STARTED,
                source=self._source,
                mode=mode,
                id=translation_id,
            )

    def translation_completed(self, translation_id: int, approach: str):
        # TRANSLATION_COMPLETED payload keys: success=True, id, approach
        with contextlib.suppress(AttributeError, TypeError, ValueError):
            self._d.dispatch_event(
                EventType.TRANSLATION_COMPLETED,
                source=self._source,
                success=True,
                id=translation_id,
                approach=approach,
            )

    def translation_failed(self, translation_id: int, error_summary: str):
        # TRANSLATION_FAILED payload keys: success=False, id, error
        with contextlib.suppress(Exception):
            self._d.dispatch_event(
                EventType.TRANSLATION_FAILED,
                source=self._source,
                success=False,
                id=translation_id,
                error=error_summary,
            )

    def stream_started(self, reason: str | None = None):
        # STREAM_STARTED payload keys: reason
        try:
            if reason is not None:
                self._d.dispatch_event(
                    EventType.STREAM_STARTED,
                    source=self._source,
                    reason=reason,
                )
            else:
                self._d.dispatch_event(
                    EventType.STREAM_STARTED,
                    source=self._source,
                )
        except Exception:
            pass

    def stream_chunk_processed(self, chunk_index: int, processing_time: float, success: bool):
        # STREAM_CHUNK_PROCESSED payload keys: index, success, duration_ms
        try:
            duration_ms = int(processing_time * 1000.0)
            self._d.dispatch_event(
                EventType.STREAM_CHUNK_PROCESSED,
                source=self._source,
                index=chunk_index,
                success=bool(success),
                duration_ms=duration_ms,
            )
        except Exception:
            pass

    def stream_completed(self, total_chunks: int):
        # STREAM_COMPLETED payload keys: chunks
        with contextlib.suppress(Exception):
            self._d.dispatch_event(
                EventType.STREAM_COMPLETED,
                source=self._source,
                chunks=int(total_chunks),
            )

    def exec_pool_fallback(self, kind: str, reason: str):
        # EXEC_POOL_FALLBACK payload keys: kind, reason
        with contextlib.suppress(Exception):
            self._d.dispatch_event(
                EventType.EXEC_POOL_FALLBACK,
                source=self._source,
                kind=kind,
                reason=reason,
            )
