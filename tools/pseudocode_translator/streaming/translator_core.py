"""
Core translation helper functions extracted from StreamingTranslator
 to reduce file size and cognitive complexity.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..models import BlockType, CodeBlock
from .events import StreamingEvent, StreamingEventData, TranslationUpdate
from .translator import StreamingTranslator

logger = logging.getLogger(__name__)


def parse_success(parse_result) -> bool:
    success_attr = getattr(parse_result, "success", None)
    if isinstance(success_attr, bool):
        return success_attr
    return len(getattr(parse_result, "errors", [])) == 0


def parse_and_translate_blocks(
    translator: StreamingTranslator,
    text: str,
    chunk_index: int,
    on_update: Callable[[TranslationUpdate], None] | None = None,
) -> list[str]:
    try:
        parse_result = translator.parser.get_parse_result(text)
        if not parse_success(parse_result):
            return []
        translations: list[str] = []
        for block_index, block in enumerate(parse_result.blocks):
            translated = translate_block(translator, block, chunk_index, block_index)
            if not translated:
                continue
            translations.append(translated)
            if on_update:
                on_update(
                    TranslationUpdate(
                        chunk_index=chunk_index,
                        block_index=block_index,
                        original_content=block.content,
                        translated_content=translated,
                    )
                )
        return translations
    except Exception as e:
        logger.error("Parse/translate error: %s", e)
        translator.emit_event(
            StreamingEventData(
                event=StreamingEvent.WARNING,
                warning=f"Failed to translate segment: {e}",
                chunk_index=chunk_index,
            )
        )
        return []


def translate_chunk_blocks(
    translator: StreamingTranslator,
    parse_result,
    chunk_index: int,
    on_update: Callable[[TranslationUpdate], None] | None,
) -> list[str]:
    results: list[str] = []
    for block_index, block in enumerate(parse_result.blocks):
        translated = translate_block(translator, block, chunk_index, block_index)
        if not translated:
            continue
        results.append(translated)
        if on_update:
            on_update(
                TranslationUpdate(
                    chunk_index=chunk_index,
                    block_index=block_index,
                    original_content=block.content,
                    translated_content=translated,
                )
            )
    return results


def translate_block(
    translator: StreamingTranslator,
    block: CodeBlock,
    chunk_index: int,
    _block_index: int,
) -> str | None:
    try:
        translator.emit_event(
            StreamingEventData(
                event=StreamingEvent.TRANSLATION_STARTED,
                chunk_index=chunk_index,
                data={"block_type": block.type.value},
            )
        )
        if block.type == BlockType.ENGLISH:
            context = translator.build_context()
            manager = translator.translation_manager
            return translator.invoker.translate_english(
                text=block.content,
                context=context,
                manager=manager,
                chunk_index=chunk_index,
                block_type=block.type.value,
            )
        if block.type == BlockType.PYTHON:
            translator.context_buffer.add_context(block.content)
            return block.content
        if block.type == BlockType.COMMENT:
            return block.content
    except Exception as e:
        logger.error("Error translating block: %s", e)
        translator.emit_event(
            StreamingEventData(
                event=StreamingEvent.WARNING,
                warning=f"Failed to translate block: {str(e)}",
                chunk_index=chunk_index,
            )
        )
        return None


def is_complete_statement(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if t.endswith(":"):
        return False
    if (t.count("(") - t.count(")")) > 0:
        return False
    if (t.count("[") - t.count("]")) > 0:
        return False
    if (t.count("{") - t.count("}")) > 0:
        return False
    return not t.endswith("\\")


def process_statement(
    translator: StreamingTranslator,
    statement: str,
    chunk_index: int,
    on_update: Callable[[TranslationUpdate], None] | None,
) -> str | None:
    translations = parse_and_translate_blocks(translator, statement, chunk_index, on_update)
    return ("\n".join(translations) + "\n") if translations else None


def process_accumulated_blocks(
    translator,
    accumulated_input: list[str],
    on_update: Callable[[TranslationUpdate], None] | None,
):
    current_input = "".join(accumulated_input)
    try:
        blocks = translator.identify_blocks(current_input)
        if len(blocks) > 1:
            translated_chunks: list[str] = []
            for i, block_text in enumerate(blocks[:-1]):
                if not block_text.strip():
                    continue
                translations = parse_and_translate_blocks(translator, block_text, i, on_update)
                if translations:
                    translated_chunks.append("\n".join(translations) + "\n\n")
            return translated_chunks, [blocks[-1]]
    except Exception as e:
        logger.warning("Error processing blocks: %s", e)
    return None
