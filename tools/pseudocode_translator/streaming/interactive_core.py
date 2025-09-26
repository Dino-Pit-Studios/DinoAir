"""Interactive translation helpers extracted from StreamingTranslator."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from typing import TYPE_CHECKING

from ..models import BlockType
from ..models.base_model import TranslationResult as ModelTranslationResult
from .events import TranslationUpdate
from .streaming_translator import StreamingTranslator


def process_interactive_input(
    translator: StreamingTranslator,
    user_input: str,
    session_context: list[str],
    interaction_count: int,
    on_update: Callable[[TranslationUpdate], None] | None,
) -> str | None:
    context = {
        "mode": "interactive",
        "session_history": "\n".join(session_context[-5:]),
        "interaction_count": interaction_count,
    }
    try:
        parse_result = translator.parser.get_parse_result(user_input)
        success_attr = getattr(parse_result, "success", None)
        parse_success = (
            success_attr if isinstance(success_attr, bool) else (len(parse_result.errors) == 0)
        )
        if not parse_success:
            return None
        translations: list[str] = []
        for block in parse_result.blocks:
            if block.type == BlockType.ENGLISH:
                manager = translator.translation_manager
                if manager is None:
                    raise RuntimeError("Translation manager is not initialized")
                res = manager.translate_text_block(text=block.content, context=context)
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
                translated = str(res.code)
            else:
                translated = block.content
            translations.append(translated)
            if on_update:
                on_update(
                    TranslationUpdate(
                        chunk_index=interaction_count,
                        block_index=0,
                        original_content=user_input,
                        translated_content=translated,
                        metadata={"interactive": True},
                    )
                )
        return "\n".join(translations)
    except Exception as e:
        logging.error("Error in interactive translation: %s", e)
        return f"Error: {str(e)}"


def interactive_translate(
    translator: StreamingTranslator,
    input_stream: Iterator[str],
    on_update=None,
):
    session_context: list[str] = []
    interaction_count = 0
    for user_input in input_stream:
        if translator.check_cancelled():
            break
        translator.wait_if_paused()
        session_context.append(f"# User input {interaction_count}:\n{user_input}")
        response = process_interactive_input(
            translator, user_input, session_context, interaction_count, on_update
        )
        if response:
            yield f"# Translation {interaction_count}:\n{response}\n\n"
            session_context.append(f"# Translation {interaction_count}:\n{response}")
        interaction_count += 1


async def interactive_translate_async(
    translator: StreamingTranslator,
    input_stream: AsyncIterator[str],
    on_update=None,
):
    session_context: list[str] = []
    interaction_count = 0
    async for user_input in input_stream:
        if translator.check_cancelled():
            break
        translator.wait_if_paused()
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            process_interactive_input,
            translator,
            user_input,
            session_context,
            interaction_count,
            on_update,
        )
        if response:
            yield f"# Translation {interaction_count}:\n{response}\n\n"
            session_context.append(f"# User {interaction_count}: {user_input}")
            session_context.append(f"# Assistant {interaction_count}: {response}")
        interaction_count += 1
