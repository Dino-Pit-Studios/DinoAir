"""
Structured Parsing Translation Service

This service provides structured parsing approach for pseudocode translation
using the parser module and rule-based translation techniques.
"""

from __future__ import annotations

import ast
import logging
import time
from typing import TYPE_CHECKING, Any

from utils.shutdown_protocols import ShutdownMixin

from ..models.base_model import OutputLanguage
from .error_handler import ErrorCategory, ErrorHandler

if TYPE_CHECKING:
    from ..parser import ParserModule
    from .translation_pipeline import TranslationContext, TranslationResult

logger = logging.getLogger(__name__)


class StructuredParsingService(ShutdownMixin):
    """
    Service for structured parsing translation approach.

    Uses parsing and rule-based translation to convert pseudocode to
    target programming languages with high accuracy and consistency.
    """

    def __init__(
        self, parser: ParserModule | None = None, error_handler: ErrorHandler | None = None
    ):
        super().__init__()
        self.parser = parser
        self.error_handler = error_handler or ErrorHandler(logger_name=__name__)

        # Statistics
        self._successful_translations = 0
        self._failed_translations = 0
        self._total_processing_time = 0.0
        self._blocks_processed = 0
        self._blocks_translated = 0

        logger.debug("StructuredParsingService initialized")

    def classify_block(self, block):
        return self.parser.classify_block(block)

    def translate(self, context: TranslationContext) -> TranslationResult:
        """
        Translate pseudocode using structured parsing approach.

        Args:
            context: Translation context with input text and metadata

        Returns:
            TranslationResult with translated code or errors
        """
        from .translation_pipeline import TranslationResult

        start_time = time.time()

        try:
            logger.debug(
                "Starting structured parsing translation for ID: %s", context.translation_id
            )

            # Initialize parser if needed
            if not self.parser:
                from ..parser import ParserModule

                self.parser = ParserModule()

            # Parse input into blocks
            blocks = self.parser.identify_blocks(context.input_text)
            self._blocks_processed += len(blocks)

            if not blocks:
                self._failed_translations += 1
                return TranslationResult(
                    success=False,
                    code=None,
                    errors=["No code blocks found in input"],
                    warnings=[],
                    metadata=self._create_metadata(context, start_time, 0, 0, False),
                )

            # Translate each block
            translated_blocks = []
            errors = []
            warnings = []
            blocks_translated = 0

            for i, block in enumerate(blocks):
                try:
                    # Classify block type
                    block_type = self.classify_block(block)

                    # Translate based on block type and target language
                    translated_block = self._translate_block(
                        block, block_type, context.target_language, i
                    )

                    if translated_block:
                        translated_blocks.append(translated_block)
                        blocks_translated += 1
                    else:
                        warnings.append(f"Block {i + 1} could not be translated")
                        translated_blocks.append(f"# Block {i + 1}: Translation failed")

                except Exception as e:
                    error_msg = f"Error translating block {i + 1}: {str(e)}"
                    errors.append(error_msg)
                    translated_blocks.append(f"# Block {i + 1}: Translation error")
                    logger.warning(error_msg)

            # Combine translated blocks
            final_code = self._combine_blocks(translated_blocks, context.target_language)

            # Validate final code
            validation_warnings = self._validate_generated_code(final_code, context.target_language)
            warnings.extend(validation_warnings)

            # Determine success
            success = len(errors) == 0 and blocks_translated > 0

            if success:
                self._successful_translations += 1
                self._blocks_translated += blocks_translated
            else:
                self._failed_translations += 1

            end_time = time.time()
            self._total_processing_time += end_time - start_time

            return TranslationResult(
                success=success,
                code=final_code if success else None,
                errors=errors,
                warnings=warnings,
                metadata=self._create_metadata(
                    context, start_time, len(blocks), blocks_translated, success
                ),
            )

        except Exception as e:
            self._failed_translations += 1
            error_info = self.error_handler.handle_exception(
                e, ErrorCategory.TRANSLATION, additional_context="Structured parsing translation"
            )

            return TranslationResult(
                success=False,
                code=None,
                errors=[self.error_handler.format_error_message(error_info)],
                warnings=[],
                metadata=self._create_metadata(context, start_time, 0, 0, False),
            )

    def _translate_block(
        self, block: str, block_type: Any, target_language: OutputLanguage, block_index: int
    ) -> str | None:
        """
        Translate a single block based on its type and target language.

        Args:
            block: Text content of the block
            block_type: Classified type of the block
            target_language: Target programming language
            block_index: Index of the block for debugging

        Returns:
            Translated block or None if translation failed
        """
        try:
            # Handle different block types
            block_type_name = getattr(block_type, "name", str(block_type)).upper()

            if block_type_name == "PYTHON":
                # Already Python code, may need minor adjustments
                return self._translate_python_block(block, target_language)
            if block_type_name == "ENGLISH":
                # Natural language pseudocode
                return self._translate_pseudocode_block(block, target_language)
            if block_type_name == "COMMENT":
                # Comment block
                return self._translate_comment_block(block, target_language)
            # Mixed or unknown block
            return self._translate_mixed_block(block, target_language)

        except Exception as e:
            logger.warning("Failed to translate block %d: %s", block_index, e)
            return None

    def _translate_python_block(self, block: str, target_language: OutputLanguage) -> str:
        """Translate Python code block to target language."""
        if target_language == OutputLanguage.PYTHON:
            # Already Python, just clean up
            return block.strip()
        if target_language == OutputLanguage.JAVASCRIPT:
            return self._python_to_javascript(block)
        # For other languages, add a comment noting the conversion
        return f"# Python code block (conversion to {target_language.value} needed):\n# {block}"

    def _translate_pseudocode_block(self, block: str, target_language: OutputLanguage) -> str:
        """Translate natural language pseudocode to target language."""
        # Basic rule-based translation for common patterns
        lines = block.split("\n")
        translated_lines = []

        for line in lines:
            translated_line = self._translate_pseudocode_line(line.strip(), target_language)
            if translated_line:
                translated_lines.append(translated_line)

        return "\n".join(translated_lines)

    def _translate_comment_block(self, block: str, target_language: OutputLanguage) -> str:
        """Translate comment block to target language comment syntax."""
        if target_language == OutputLanguage.PYTHON:
            # Python uses # for comments
            lines = block.split("\n")
            return "\n".join(f"# {line.strip()}" if line.strip() else "#" for line in lines)
        if target_language == OutputLanguage.JAVASCRIPT:
            # JavaScript uses // for single line comments
            lines = block.split("\n")
            return "\n".join(f"// {line.strip()}" if line.strip() else "//" for line in lines)
        # Default to # style comments
        lines = block.split("\n")
        return "\n".join(f"# {line.strip()}" if line.strip() else "#" for line in lines)

    def _translate_mixed_block(self, block: str, target_language: OutputLanguage) -> str:
        """Translate mixed content block."""
        # For mixed blocks, try to identify and translate components
        lines = block.split("\n")
        translated_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                translated_lines.append("")
                continue

            # Try different translation approaches
            if self._looks_like_code(line):
                translated_line = self._translate_code_line(line, target_language)
            else:
                translated_line = self._translate_pseudocode_line(line, target_language)

            translated_lines.append(translated_line)

        return "\n".join(translated_lines)

    def _translate_pseudocode_line(self, line: str, target_language: OutputLanguage) -> str:
        """Translate a single pseudocode line to target language."""
        line_lower = line.lower()
        translator = self._find_pseudocode_translator(line_lower)
        if translator:
            return translator(line, line_lower, target_language)
        return self._default_pseudocode_line(line, target_language)

    def _find_pseudocode_translator(self, line_lower: str):
        if line_lower.startswith("if ") and line_lower.endswith(":"):
            return self._handle_if
        if line_lower.startswith("for ") and line_lower.endswith(":"):
            return self._handle_for
        if line_lower.startswith("while ") and line_lower.endswith(":"):
            return self._handle_while
        if line_lower.startswith("function ") or line_lower.startswith("def "):
            return self._handle_function
        if line_lower in ["end", "end if", "end for", "end while"]:
            return self._handle_end
        return None

    def _handle_if(self, line: str, line_lower: str, target_language: OutputLanguage) -> str:
        condition = line[3:-1].strip()
        if target_language == OutputLanguage.PYTHON:
            return f"if {condition}:"
        if target_language == OutputLanguage.JAVASCRIPT:
            return f"if ({condition}) {{"
        return self._default_pseudocode_line(line, target_language)

    def _handle_for(self, line: str, line_lower: str, target_language: OutputLanguage) -> str:
        loop_spec = line[4:-1].strip()
        if target_language == OutputLanguage.PYTHON:
            return f"for {loop_spec}:"
        if target_language == OutputLanguage.JAVASCRIPT:
            return f"for ({loop_spec}) {{"
        return self._default_pseudocode_line(line, target_language)

    def _handle_while(self, line: str, line_lower: str, target_language: OutputLanguage) -> str:
        condition = line[6:-1].strip()
        if target_language == OutputLanguage.PYTHON:
            return f"while {condition}:"
        if target_language == OutputLanguage.JAVASCRIPT:
            return f"while ({condition}) {{"
        return self._default_pseudocode_line(line, target_language)

    def _handle_function(self, line: str, line_lower: str, target_language: OutputLanguage) -> str:
        if target_language == OutputLanguage.PYTHON:
            return line.replace("function ", "def ")
        if target_language == OutputLanguage.JAVASCRIPT:
            return line.replace("def ", "function ")
        return self._default_pseudocode_line(line, target_language)

    def _handle_end(self, line: str, line_lower: str, target_language: OutputLanguage) -> str:
        if target_language == OutputLanguage.PYTHON:
            return "pass"
        if target_language == OutputLanguage.JAVASCRIPT:
            return "}"
        return self._default_pseudocode_line(line, target_language)

    def _default_pseudocode_line(self, line: str, target_language: OutputLanguage) -> str:
        if target_language == OutputLanguage.PYTHON:
            return f"# {line}"
        if target_language == OutputLanguage.JAVASCRIPT:
            return f"// {line}"
        return f"# {line}"

    def _translate_code_line(self, line: str, target_language: OutputLanguage) -> str:
        """Translate a code-like line to target language."""
        # Basic code translation patterns
        if (
            target_language == OutputLanguage.JAVASCRIPT
            and target_language != OutputLanguage.PYTHON
        ):
            # Python to JavaScript conversions
            line = line.replace("print(", "console.log(")
            line = line.replace("True", "true")
            line = line.replace("False", "false")
            line = line.replace("None", "null")
            line = line.replace(" and ", " && ")
            line = line.replace(" or ", " || ")
            line = line.replace(" not ", " !")

        return line

    def _looks_like_code(self, line: str) -> bool:
        """Determine if a line looks like code rather than natural language."""
        code_indicators = [
            "=",
            "(",
            ")",
            "[",
            "]",
            "{",
            "}",
            ";",
            "def ",
            "function ",
            "var ",
            "let ",
            "const ",
            "if ",
            "for ",
            "while ",
            "return ",
            "print(",
        ]

        return any(indicator in line for indicator in code_indicators)

    def _python_to_javascript(self, python_code: str) -> str:
        """Convert Python code to JavaScript."""
        lines = python_code.split("\n")
        js_lines = []

        for line in lines:
            js_line = self._translate_code_line(line, OutputLanguage.JAVASCRIPT)
            # Handle indentation (convert Python indentation to braces)
            if line.strip() and not line.strip().startswith("#"):
                js_lines.append(js_line)

        return "\n".join(js_lines)

    def _combine_blocks(self, translated_blocks: list[str], target_language: OutputLanguage) -> str:
        """Combine translated blocks into final code."""
        return "\n\n".join(block for block in translated_blocks if block.strip())

    def _validate_generated_code(self, code: str, target_language: OutputLanguage) -> list[str]:
        """Validate generated code and return warnings."""
        warnings = []

        if not code.strip():
            warnings.append("Generated code is empty")
            return warnings

        # Basic syntax validation for Python
        if target_language == OutputLanguage.PYTHON:
            try:
                ast.parse(code)
            except SyntaxError as e:
                warnings.append(f"Python syntax error: {str(e)}")
            except Exception as e:
                warnings.append(f"Code validation error: {str(e)}")

        # Check for common issues
        lines = code.splitlines()
        if len(lines) < 2:
            warnings.append("Generated code seems too short")

        # Check for untranslated pseudocode patterns
        untranslated_patterns = ["# TODO", "# FIXME", "Translation failed", "Translation error"]
        for pattern in untranslated_patterns:
            if pattern in code:
                warnings.append(f"Found untranslated content: {pattern}")

        return warnings

    def _create_metadata(
        self,
        context: TranslationContext,
        start_time: float,
        blocks_processed: int,
        blocks_translated: int,
        success: bool,
    ) -> dict[str, Any]:
        """Create metadata for translation result."""
        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "translation_id": context.translation_id,
            "approach": "structured_parsing",
            "duration_ms": duration_ms,
            "target_language": context.target_language.value,
            "input_length": len(context.input_text),
            "blocks_processed": blocks_processed,
            "blocks_translated": blocks_translated,
            "success": success,
            "service": "StructuredParsingService",
        }

    def get_statistics(self) -> dict[str, Any]:
        """Get service statistics."""
        total_translations = self._successful_translations + self._failed_translations
        success_rate = (
            self._successful_translations / total_translations * 100
            if total_translations > 0
            else 0.0
        )
        avg_processing_time = (
            self._total_processing_time
            / (self._successful_translations + self._failed_translations)
            if total_translations > 0
            else 0.0
        )

        return {
            "successful_translations": self._successful_translations,
            "failed_translations": self._failed_translations,
            "total_translations": total_translations,
            "success_rate_percent": round(success_rate, 2),
            "average_processing_time_seconds": round(avg_processing_time, 3),
            "total_processing_time_seconds": round(self._total_processing_time, 3),
            "blocks_processed": self._blocks_processed,
            "blocks_translated": self._blocks_translated,
        }

    def reset_statistics(self) -> None:
        """Reset service statistics."""
        self._successful_translations = 0
        self._failed_translations = 0
        self._total_processing_time = 0.0
        self._blocks_processed = 0
        self._blocks_translated = 0
        logger.debug("Structured parsing statistics reset")

    def _cleanup_resources(self) -> None:
        """Clean up service resources during shutdown."""
        logger.debug("StructuredParsingService shutdown complete")
