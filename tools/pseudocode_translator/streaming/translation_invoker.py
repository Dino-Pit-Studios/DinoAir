"""
TranslationInvoker: centralizes block translation invocation and event emission.

This helper emits TRANSLATION_STARTED/TRANSLATION_COMPLETED events and performs
result normalization for ModelTranslationResult while updating the context buffer.

Behavior is intentionally identical to the existing StreamingTranslator._translate_block
English path to avoid any external behavior changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models.base_model import TranslationResult as ModelTranslationResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from .buffer import ContextBuffer


class TranslationInvoker:
    """
    Helper that encapsulates TranslationManager invocation for English blocks,
    event emission, and context buffer updates.
    """

    def __init__(
        self,
        emit_event: Callable[[Any], None],
        context_buffer: ContextBuffer,
    ):
        """
        Args:
            emit_event: Callback to emit StreamingEventData (e.g., StreamingTranslator._emit_event)
            context_buffer: Shared ContextBuffer to update with translated code
        """
        self._emit_event = emit_event
        self._context_buffer = context_buffer

    def translate_english(
        self,
        *,
        text: str,
        context: dict[str, Any],
        manager: Any,
        chunk_index: int,
        block_type: str = "english",
    ) -> str:
        """
        Invoke the TranslationManager for an English text block, emit events,
        verify result type/success, update context buffer, and return code.

        Args:
            text: English block content to translate
            context: Translation context dictionary (constructed by caller)
            manager: TranslationManager instance (must expose translate_text_block)
            chunk_index: Current chunk index for event correlation
            block_type: The block type string for event metadata; default 'english'

        Returns:
            Translated code string

        Raises:
            RuntimeError: When translation result indicates failure or missing code
        """
        # Resolve event types at call-time to avoid circular import at module import
        mod = __import__(
            "pseudocode_translator.streaming.stream_translator",
            fromlist=["StreamingEvent", "StreamingEventData"],
        )
        StreamingEvent = mod.StreamingEvent
        StreamingEventData = mod.StreamingEventData

        # Emit TRANSLATION_STARTED prior to translation
        self._emit_event(
            StreamingEventData(
                event=StreamingEvent.TRANSLATION_STARTED,
                chunk_index=chunk_index,
                data={"block_type": block_type},
            )
        )

        # Perform translation via manager
        if manager is None:
            raise RuntimeError("Translation manager is not initialized")

        res = manager.translate_text_block(text=text, context=context)

        # Normalize to expected TranslationResult type and success
        if (
            not isinstance(res, ModelTranslationResult)
            or not getattr(res, "success", False)
            or getattr(res, "code", None) is None
        ):
            # Match existing error message formatting from StreamingTranslator._translate_block
            raise RuntimeError(
                "Translation failed: "
                + (
                    ", ".join(getattr(res, "errors", []))
                    if getattr(res, "errors", [])
                    else "No code returned"
                )
            )

        translated = str(res.code)

        # Update context buffer to maintain continuity
        self._context_buffer.add_context(translated)

        # Emit TRANSLATION_COMPLETED after success
        self._emit_event(
            StreamingEventData(
                event=StreamingEvent.TRANSLATION_COMPLETED,
                chunk_index=chunk_index,
            )
        )

        return translated
