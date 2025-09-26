"""
Worker thread implementation for asynchronous translation operations

This module provides the TranslationWorker class that runs translations
in a separate thread to keep the GUI responsive.
"""

import logging
import traceback
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from .assembler import CodeAssembler
from .config import TranslatorConfig
from .models import BlockType, CodeBlock, ParseResult
from .parser import ParserModule
from .translator import TranslationManager

logger = logging.getLogger(__name__)


@dataclass
class TranslationStatus:
    """Status information for translation operations"""

    phase: str  # "parsing", "translating", "assembling", "validating"
    progress: int  # 0-100
    message: str
    details: dict[str, Any] | None = None


@dataclass
class TranslationResult:
    """Result of a translation operation"""

    success: bool
    code: str | None
    errors: list[str]
    warnings: list[str]
    metadata: dict[str, Any]
    parse_result: ParseResult | None = None


class TranslationWorker(QObject):
    """
    Worker class for performing translations in a separate thread

    This class handles the actual translation work and emits signals
    to communicate progress and results back to the main thread.
    """

    # Signals
    started = Signal()
    progress = Signal(int)  # Progress percentage
    status = Signal(TranslationStatus)  # Detailed status
    completed = Signal(TranslationResult)  # Final result
    error = Signal(str)  # Error message
    finished = Signal()  # Worker done

    def __init__(
        self,
        pseudocode: str,
        config: TranslatorConfig,
        parser: ParserModule,
        manager: TranslationManager | None,
        parent: QObject | None = None,
    ):
        """
        Initialize the translation worker

        Args:
            pseudocode: The pseudocode text to translate
            config: Translator configuration
            parser: Parser module instance
            manager: TranslationManager instance
            parent: Optional parent QObject
        """
        super().__init__(parent)

        self.pseudocode = pseudocode
        self.config = config
        self.parser = parser
        self.manager = manager

        # State tracking
        self._cancelled = False
        self._running = False

    @Slot()
    def run(self):
        """
        Main worker method that performs the translation

        This method is called when the worker thread starts.
        It emits signals to communicate progress and results.
        """
        if self._running:
            logger.warning("Translation already running")
            return

        self._running = True
        self._cancelled = False

        try:
            self.started.emit()

            # Emit initial status
            self._emit_status("translating", 10, "Starting translation...")

            # Ensure manager is available
            if self.manager is None:
                self.manager = TranslationManager(self.config)

            # Delegate to TranslationManager for unified behavior
            mgr_result = self.manager.translate_pseudocode(self.pseudocode)

            # Build parse_result for GUI consumers
            parse_result = self.parser.get_parse_result(self.pseudocode)

            # Create final result
            result = TranslationResult(
                success=mgr_result.success and (mgr_result.code is not None),
                code=mgr_result.code,
                errors=mgr_result.errors,
                warnings=mgr_result.warnings,
                metadata=mgr_result.metadata,
                parse_result=parse_result,
            )

            self.progress.emit(100)
            self.completed.emit(result)

        except Exception as e:
            logger.error("Translation worker error: %s", e)
            logger.error(traceback.format_exc())
            self.error.emit(str(e))

        finally:
            self._running = False
            self.finished.emit()

    @Slot()
    def cancel(self):
        """Cancel the translation operation"""
        self._cancelled = True
        logger.info("Translation cancelled by user")

    def _emit_status(
        self,
        phase: str,
        progress: int,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        """Helper to emit status updates"""
        status = TranslationStatus(phase, progress, message, details)
        self.status.emit(status)

    def _handle_cancellation(self):
        """Handle cancellation of the translation"""
        self._emit_status("cancelled", 0, "Translation cancelled")
        result = TranslationResult(
            success=False,
            code=None,
            errors=["Translation cancelled by user"],
            warnings=[],
            metadata={"cancelled": True},
        )
        self.completed.emit(result)

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

    def _validate_code(self, code: str) -> list[str]:
        """
        Validate Python code and return list of errors

        Args:
            code: Python code to validate

        Returns:
            List of validation error messages
        """
        errors = []

        if not code or not code.strip():
            errors.append("Generated code is empty")
            return errors

        # Syntax validation
        try:
            compile(code, "<generated>", "exec")
        except SyntaxError as e:
            line_info = f" at line {e.lineno}" if e.lineno else ""
            errors.append(f"Syntax error{line_info}: {e.msg}")
        except Exception as e:
            errors.append(f"Compilation error: {str(e)}")

        # Additional validation based on configuration
        if self.config.llm.validation_level == "strict":
            # Check for undefined variables (simplified check)
            if self.config.check_undefined_vars:
                undefined_check_errors = self._check_undefined_variables(code)
                errors.extend(undefined_check_errors)

            # Check imports
            if self.config.validate_imports:
                import_errors = self._check_imports(code)
                errors.extend(import_errors)

        return errors

    def _check_undefined_variables(self, code: str) -> list[str]:
        """
        Check for potentially undefined variables using the validator module

        This delegates to the robust implementation in the validator module
        that properly handles scopes, imports, and special cases.
        """
        # Import the undefined variable checker directly
        from .validator.constants import get_builtin_names
        from .validator.variable_trackers import UndefinedVariableChecker

        try:
            # Parse the code
            import ast

            tree = ast.parse(code)

            # Use the undefined variable checker directly
            checker = UndefinedVariableChecker()
            checker.visit(tree)

            # Process results similar to LogicValidator._check_undefined_names
            builtin_names = get_builtin_names()
            issues = []

            # Normalize tuples to (name, line, col)
            normalized = []
            for tup in checker.undefined_names:
                if len(tup) == 2:
                    name, line = tup
                    col = None
                else:
                    name, line, col = tup
                normalized.append((name, line, col))

            # Deduplicate and filter builtins
            seen = set()
            for name, line, col in normalized:
                if name in builtin_names:
                    continue
                key = (name, line, col)
                if key not in seen:
                    seen.add(key)

            # Sort by (line, name) and create issue messages
            sorted_items = sorted(seen, key=lambda x: (x[1], x[0]))
            for name, line, col in sorted_items:
                loc = f"line {line}" + (f", col {col}" if col is not None else "")
                issues.append(f"Undefined variable '{name}' at {loc}")

            return issues

        except SyntaxError:
            # If code has syntax errors, we can't check undefined vars
            return ["Cannot check undefined variables due to syntax errors"]
        except Exception as e:
            return [f"Error checking undefined variables: {str(e)}"]

    def _check_imports(self, code: str) -> list[str]:
        """
        Check if imports are valid

        This is a basic implementation that checks for common issues.
        """
        errors = []
        lines = code.split("\n")

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Check for malformed imports
            if stripped.startswith(("import ", "from ")):
                try:
                    compile(stripped, "<import>", "single")
                except SyntaxError:
                    errors.append(f"Invalid import statement at line {i}: {stripped}")

        return errors

    def _create_result_from_parse(
        self, parse_result: ParseResult, translated_blocks: list[str]
    ) -> TranslationResult:
        """
        Create a translation result when no translation is needed

        Args:
            parse_result: The parse result
            translated_blocks: Empty list of translations

        Returns:
            TranslationResult object
        """
        # Use CodeAssembler even when no translation is needed
        # This ensures consistent formatting and import organization
        assembler = CodeAssembler(self.config)

        # Filter for Python and comment blocks only
        blocks_to_assemble = [
            block
            for block in parse_result.blocks
            if block.type in [BlockType.PYTHON, BlockType.COMMENT]
        ]

        final_code = assembler.assemble(blocks_to_assemble)
        validation_errors = self._validate_code(final_code)

        return TranslationResult(
            success=len(validation_errors) == 0,
            code=final_code,
            errors=validation_errors,
            warnings=parse_result.warnings + ["No English instructions found to translate"],
            metadata={
                "blocks_processed": getattr(
                    parse_result,
                    "block_count",
                    len(getattr(parse_result, "blocks", [])),
                ),
                "english_blocks": 0,
                "translated_blocks": 0,
            },
            parse_result=parse_result,
        )
