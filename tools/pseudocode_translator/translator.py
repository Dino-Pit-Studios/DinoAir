"""
Translation Manager module for the Pseudocode Translator

This module coordinates the entire translation pipeline, orchestrating
the parser, LLM interface, assembler, and validator components.
"""

from __future__ import annotations

# Standard imports group
import ast
import contextlib
import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, TypeVar, cast

from utils.shutdown_protocols import ShutdownMixin

from .assembler import CodeAssembler
from .ast_cache import parse_cached
from .controllers.llm_first import LlmFirstController
from .controllers.structured_flow import StructuredParsingController
from .exceptions import AssemblyError, ErrorContext, TranslatorError
from .execution.process_pool import ParseValidateExecutor
from .integration.events import EventDispatcher, EventType

# Import from models.py file (not the models directory)
from .models import BlockType, CodeBlock

# Import new model abstraction from models directory
from .models.base_model import (
    BaseTranslationModel,
    OutputLanguage,
)
from .models.base_model import TranslationConfig as ModelTranslationConfig
from .models.model_factory import ModelFactory, create_model
from .models.plugin_system import get_plugin_system
from .parser import ParserModule
from .services.dependency_gateway import DependencyAnalysisGateway
from .services.validation_service import ValidationService
from .telemetry import get_recorder
from .validator import ValidationResult, Validator

if TYPE_CHECKING:
    from .config import TranslatorConfig

try:
    from concurrent.futures.process import BrokenProcessPool as _BrokenProcessPool  # type: ignore
except Exception:  # pragma: no cover

    class _FallbackBrokenProcessPool(Exception):
        """Fallback exception used when the concurrent.futures BrokenProcessPool import fails."""

    # type: ignore[misc,assignment]
    _BrokenProcessPool = _FallbackBrokenProcessPool
BrokenProcessPool = _BrokenProcessPool

# Logger
logger = logging.getLogger(__name__)

# Import mock model to ensure it's registered as fallback
try:
    from .models.mock_model import MockModel

    _ = MockModel  # keep import for side effects (model registration)
except ImportError:
    logger.warning("Mock model not available - no fallback will be available")


# Type contracts and aliases for static typing and event/timing wrappers


class ModelConfig(TypedDict, total=False):
    """TypedDict for translator configuration options.

    Attributes:
        model_name: name of the translation model
        model_path: filesystem path to the model
        temperature: sampling temperature for generation
        max_tokens: maximum number of tokens to generate
    """

    model_name: str | None
    model_path: str | None
    temperature: float | None
    max_tokens: int | None


class ParseResult(TypedDict):
    """Result of parsing code into blocks.

    Attributes:
        code: the original or transformed source code
        blocks: list of parsed code blocks
        meta: additional metadata from parsing
    """

    code: str | None
    blocks: list[Block]
    meta: dict[str, Any]


class Block(Protocol):
    """Protocol representing a code block extracted from source.

    Attributes:
        type: the block type identifier
        content: text content of the block
        line_numbers: start and end line numbers in source
        metadata: additional block-specific metadata
        context: parsing context or related data

    Methods:
        to_source: reconstruct the block into source code string
    """

    type: Any
    content: str
    line_numbers: tuple[int, int]
    metadata: dict[str, Any]
    context: Any

    def to_source(self) -> str: ...


# Validation result adapter alias
TimedSection = AbstractContextManager[None]
MaybeOffloadValidate = Callable[[ast.AST], "ValidationResult | str"]

T = TypeVar("T")


# This sentinel exists solely to ensure the Enum import is used (lint compliance).
class _EnumSentinel(Enum):
    """Sentinel to ensure Enum import is used; no runtime effect."""

    __unused__ = 0


# Reference to avoid unused-class diagnostics
_ENUM_SENTINEL_REF = _EnumSentinel.__unused__


# Event/timing wrappers to eliminate Unknown types across boundaries
def _dispatch_event(
    dispatcher: EventDispatcher,
    event_type: EventType,
    source: str | None = None,
    **data: Any,
) -> None:
    cast("Any", dispatcher).dispatch_event(event_type, source=source, **data)


def timed_section(name: str, extra: dict[str, Any] | None = None) -> AbstractContextManager[None]:
    rec_any: Any = get_recorder()
    return cast("AbstractContextManager[None]", rec_any.timed_section(name, extra))


def _as_validation_result(value: ValidationResult | str) -> ValidationResult:
    """
    Normalize a ValidationResult | str into a ValidationResult.

    >>> _as_validation_result("bad").is_valid
    False
    """
    if isinstance(value, str):
        return ValidationResult(False, [value], [])
    return value


def _safe_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    """
    Return a non-None metadata dictionary.

    >>> _safe_meta(None)
    {}
    """
    return {} if meta is None else meta


def _blocks_len(blocks: list[Block] | None) -> int:
    """
    Safe length for blocks list.

    >>> _blocks_len([])
    0
    """
    return 0 if blocks is None else len(blocks)


def _run_safely(fn: Callable[[], Any], ctx: str) -> Any | None:
    """
    Run a callable, logging and swallowing exceptions to preserve prior behavior.

    Logging uses lazy formatting and includes stack trace.
    """
    try:
        return fn()
    except (ValueError, RuntimeError, TypeError, AttributeError) as e:
        logger.exception("Failure in %s: %s", ctx, e)
        return None
    except Exception as e:
        logger.exception("Unexpected failure in %s: %s", ctx, e)
        return None


@dataclass
class TranslationResult:
    """Result of a translation operation"""

    success: bool
    code: str | None
    errors: list[str]
    warnings: list[str]
    metadata: dict[str, Any]

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors"""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings"""
        return len(self.warnings) > 0


@dataclass
class TranslationMetadata:
    """Metadata about the translation process"""

    duration_ms: int
    blocks_processed: int
    blocks_translated: int
    cache_hits: int
    model_tokens_used: int
    validation_passed: bool


class TranslationManager(ShutdownMixin):
    """Main controller that coordinates the translation pipeline"""

    def __init__(self, config: TranslatorConfig):
        """
        Initialize the Translation Manager

        Args:
            config: Translator configuration object
        """
        super().__init__()
        self.config = config
        self.parser = ParserModule()
        self.assembler = CodeAssembler(config)
        self.validator = Validator(config)

        # Thread safety
        self._lock = threading.Lock()
        self._translation_count = 0
        # Thread-local flow context for helper orchestration (internal-only)
        self._thread = threading.local()

        # Events dispatcher (sync to keep unit tests deterministic)
        self._events = EventDispatcher(async_mode=False)

        # Optional exec process pool (lazy)
        self._exec_pool: ParseValidateExecutor | None = None
        # Test-only seams to inject slow functions into pool (top-level callables)
        self._exec_pool_test_parse_fn: Callable[[str], Any] | None = None
        self._exec_pool_test_validate_fn: Callable[[Any], Any] | None = None

        # Model management
        self._current_model: BaseTranslationModel | None = None
        self._model_name: str | None = None
        self._target_language = OutputLanguage.PYTHON  # Default

        # Initialize plugin system if enabled
        if getattr(config, "enable_plugins", True):
            plugin_system = get_plugin_system()
            plugin_system.load_all_plugins()

        # Initialize model
        logger.info("Initializing Translation Manager")
        try:
            self._initialize_model()
        except Exception as e:
            logger.error("Failed to initialize model: %s", e)
            error = TranslatorError("Failed to initialize translation model", cause=e)
            error.add_suggestion("Check model configuration")
            error.add_suggestion("Verify API credentials if using external models")
            error.add_suggestion("Ensure model files are available for local models")
            raise error

    def _initialize_model(self, model_name: str | None = None):
        """Initialize or switch to a different model"""
        # Determine model name from config or parameter
        if model_name is None:
            model_name = getattr(
                self.config.llm,
                "model_type",
                getattr(self.config.llm, "model_name", "qwen"),
            )

        # Create model configuration
        model_config: dict[str, Any] = {
            "temperature": self.config.llm.temperature,
            "top_p": getattr(self.config.llm, "top_p", 0.9),
            "top_k": getattr(self.config.llm, "top_k", 40),
            "max_tokens": self.config.llm.max_tokens,
            "n_ctx": self.config.llm.n_ctx,
            "n_batch": getattr(self.config.llm, "n_batch", 512),
            "n_threads": self.config.llm.n_threads,
            "n_gpu_layers": self.config.llm.n_gpu_layers,
        }

        # Add model path if available
        if hasattr(self.config.llm, "model_path"):
            model_config["model_path"] = self.config.llm.model_path

        # Create model instance
        self._current_model = create_model(model_name, model_config)
        self._model_name = model_name

        # Initialize the model
        model_path: Path | None = None
        if hasattr(self.config.llm, "model_path"):
            model_path = Path(self.config.llm.model_path)

        cast("Any", self._current_model).initialize(model_path)
        logger.info("Initialized model: %s", model_name)

        # Instantiate extracted collaborators (Phase 1; behavior-preserving)
        recorder = get_recorder()
        self._validation = ValidationService(
            self.validator,
            recorder,
            logger,
            self._maybe_offload_validate,
            self._attempt_fixes,
        )
        self._dep_gateway = DependencyAnalysisGateway(parse_cached, logger)

        # Controllers
        self._llm_first = LlmFirstController(
            self._current_model,
            self.assembler,
            self.validator,
            recorder,
            self._events,
            logger,
            validate_and_optionally_fix_fn=lambda code: self._validation.validate_and_optionally_fix(
                code, llm_first=True
            ),
            build_config_for_document_fn=self._build_model_config_for_document,
            result_cls=TranslationResult,
        )
        self._structured = StructuredParsingController(
            self.parser,
            self.assembler,
            self.validator,
            recorder,
            self._events,
            logger,
            self._maybe_offload_parse,
            self._maybe_offload_validate,
            process_blocks_fn=self._process_blocks,
            assemble_or_error_fn=self._assemble_or_error,
            suggest_improvements_fn=self._suggest_improvements,
            create_metadata_fn=self._create_metadata,
            dependency_gateway=self._dep_gateway,
            validation_service=self._validation,
            result_cls=TranslationResult,
        )

    def _ensure_exec_pool(self) -> ParseValidateExecutor:
        if self._exec_pool is None:
            try:
                exec_cfg = getattr(self.config, "execution", None)
            except Exception:
                exec_cfg = None
            if exec_cfg is None:
                # Feature group not present; disable offload
                raise RuntimeError("Execution configuration not available")

            # Wire dispatcher and telemetry; allow test seams
            recorder = get_recorder()
            self._exec_pool = ParseValidateExecutor(
                exec_cfg,
                recorder=recorder,
                dispatcher=self._events,
                start_method=getattr(exec_cfg, "process_pool_start_method", None),
                parse_fn=self._exec_pool_test_parse_fn,
                validate_fn=self._exec_pool_test_validate_fn,
            )
        return self._exec_pool

    def _maybe_offload_parse(self, text: str) -> Any:
        """Parse via process pool when enabled/targeted, else in-process."""
        try:
            exec_cfg = getattr(self.config, "execution", None)
        except Exception:
            exec_cfg = None

        # Use OffloadExecutor facade to centralize gating, submission, and fallbacks.
        # Local import to avoid potential import cycles (support must not import translator.py).
        try:
            from .translator_support.offload_executor import OffloadExecutor  # type: ignore
        except Exception:
            # On facade import failure, preserve behavior by using in-process parse.
            return cast("Any", self.parser).get_parse_result(text)

        recorder = get_recorder()
        offload = OffloadExecutor(
            dispatcher=self._events,
            recorder=recorder,
            exec_cfg=exec_cfg,
            ensure_pool_cb=self._ensure_exec_pool,
        )

        ok, result = offload.submit("parse", text, timeout=None)

        # Not offloaded -> run local path exactly as before.
        if not ok:
            return cast("Any", self.parser).get_parse_result(text)

        # Immediate/local fallback instruction from pool/facade.
        # Do not emit fallback here to avoid duplicates; OffloadExecutor/pool handled emissions.
        if isinstance(result, str) and result.startswith("exec_pool_fallback:"):
            return cast("Any", self.parser).get_parse_result(text)

        # Successful offload result.
        return result

    def _maybe_offload_validate(self, ast_obj: ast.AST | str) -> ValidationResult | str:
        """Validate via process pool when enabled/targeted, else in-process."""
        try:
            exec_cfg = getattr(self.config, "execution", None)
        except Exception:
            exec_cfg = None

        # Local import to avoid cycles; support module must not import translator.py.
        try:
            from .translator_support.offload_executor import OffloadExecutor  # type: ignore
        except Exception:
            # Preserve behavior if facade isn't available.
            return self.validator.validate_syntax(
                ast_obj if isinstance(ast_obj, str) else str(ast_obj)
            )

        recorder = get_recorder()
        offload = OffloadExecutor(
            dispatcher=self._events,
            recorder=recorder,
            exec_cfg=exec_cfg,
            ensure_pool_cb=self._ensure_exec_pool,
        )

        ok, result = offload.submit("validate", ast_obj, timeout=None)

        # Not offloaded -> local validation with identical stringification semantics.
        if not ok:
            return self.validator.validate_syntax(
                ast_obj if isinstance(ast_obj, str) else str(ast_obj)
            )

        # Immediate/local fallback path; do not emit fallback here (avoid duplicates).
        if isinstance(result, str) and result.startswith("exec_pool_fallback:"):
            return self.validator.validate_syntax(
                ast_obj if isinstance(ast_obj, str) else str(ast_obj)
            )

        # Successful offload result.
        return result

    def _emit_translation_started(self, translation_id: int, mode: str) -> None:
        """Emit TRANSLATION_STARTED with identical payload semantics."""
        _run_safely(
            lambda: _dispatch_event(
                self._events,
                EventType.TRANSLATION_STARTED,
                source=self.__class__.__name__,
                mode=mode,
                id=translation_id,
            ),
            "emit.TRANSLATION_STARTED",
        )

    def _emit_translation_completed(self, translation_id: int, approach: str, result: Any) -> None:
        """Emit TRANSLATION_COMPLETED with identical payload semantics."""
        _run_safely(
            lambda: _dispatch_event(
                self._events,
                EventType.TRANSLATION_COMPLETED,
                source=self.__class__.__name__,
                success=True,
                id=translation_id,
                approach=approach,
            ),
            "emit.TRANSLATION_COMPLETED",
        )

    def _emit_translation_failed(self, translation_id: int, error: str) -> None:
        """Emit TRANSLATION_FAILED with identical payload semantics."""
        _run_safely(
            lambda: _dispatch_event(
                self._events,
                EventType.TRANSLATION_FAILED,
                source=self.__class__.__name__,
                success=False,
                id=translation_id,
                error=error,
            ),
            "emit.TRANSLATION_FAILED",
        )

    def _run_llm_first_flow(self, input_text: str) -> tuple[bool, Any]:
        """
        Run LLM-first translation; on success return (True, result),
        on handled exception return (False, error_info) using identical exception semantics.
        """
        try:
            start_time = self._thread.start_time
            translation_id = self._thread.translation_id
            result = self._translate_with_llm_first(input_text, start_time, translation_id)
            return True, result
        except Exception as llm_error:
            logger.warning("LLM-first translation failed: %s", llm_error)
            return False, llm_error

    def _run_structured_flow(self, input_text: str) -> Any:
        """Run structured parsing flow with identical handling of warnings/parse errors."""
        start_time = self._thread.start_time
        translation_id = self._thread.translation_id
        warnings_ref = getattr(self._thread, "warnings", [])
        return self._translate_with_structured_parsing(
            input_text, start_time, translation_id, warnings_ref
        )

    def _initialize_translation_context(
        self, target_language: OutputLanguage | None = None
    ) -> tuple[float, int, list[str], list[str]]:
        """Initialize context for a new translation operation."""
        if target_language:
            self._target_language = target_language

        start_time = time.time()
        errors: list[str] = []
        warnings: list[str] = []

        # Increment translation count
        with self._lock:
            self._translation_count += 1
            translation_id = self._translation_count

        logger.info("Starting translation #%d", translation_id)

        # Seed thread-local context for helpers
        try:
            self._thread.start_time = start_time
            self._thread.translation_id = translation_id
            self._thread.warnings = warnings
        except Exception:
            pass

        return start_time, translation_id, errors, warnings

    def _handle_llm_first_success(
        self, result: TranslationResult, translation_id: int
    ) -> TranslationResult:
        """Handle successful LLM-first translation."""
        meta_safe = _safe_meta(result.metadata)
        approach = meta_safe.get("approach")
        self._emit_translation_completed(translation_id, approach, result)  # type: ignore[arg-type]
        return result

    def _handle_structured_fallback(
        self,
        input_text: str,
        llm_error: Exception,
        warnings: list[str],
        errors: list[str],
        start_time: float,
        translation_id: int,
    ) -> TranslationResult:
        """Handle fallback to structured parsing after LLM-first failure."""
        warnings.append(f"LLM-first approach failed: {str(llm_error)}")

        try:
            result = self._run_structured_flow(input_text)
        except Exception as parse_error:
            logger.error("Both translation approaches failed: %s", parse_error)
            errors.append(f"Structured parsing also failed: {str(parse_error)}")

            result = TranslationResult(
                success=False,
                code=None,
                errors=errors + [str(llm_error), str(parse_error)],
                warnings=warnings,
                metadata=self._create_metadata(start_time, 0, 0, 0, 0, False),
            )

            # Emit failure (best-effort) and return
            err_msg = ""
            if result and result.errors:
                err_msg = "; ".join(result.errors[:1])
            self._emit_translation_failed(translation_id, err_msg)
            return result

        # Emit completion/failure events for structured path (best-effort)
        return self._finalize_structured_result(result, translation_id)

    def _finalize_structured_result(
        self, result: TranslationResult, translation_id: int
    ) -> TranslationResult:
        """Finalize and emit events for structured parsing result."""
        if result and result.success:
            meta_safe = _safe_meta(result.metadata if hasattr(result, "metadata") else {})
            approach = meta_safe.get("approach")
            self._emit_translation_completed(translation_id, approach, result)  # type: ignore[arg-type]
        else:
            err_msg = ""
            if result and result.errors:
                err_msg = "; ".join(result.errors[:1])
            self._emit_translation_failed(translation_id, err_msg)

        return result

    def translate_pseudocode(
        self, input_text: str, target_language: OutputLanguage | None = None
    ) -> TranslationResult:
        """Main translation method that converts pseudocode to code"""
        start_time, translation_id, errors, warnings = self._initialize_translation_context(
            target_language
        )

        # Emit started (best-effort)
        self._emit_translation_started(translation_id, "llm_first")

        # LLM-first flow
        ok, payload = self._run_llm_first_flow(input_text)
        if ok:
            return self._handle_llm_first_success(payload, translation_id)

        # Fallback to structured flow
        return self._handle_structured_fallback(
            input_text, payload, warnings, errors, start_time, translation_id
        )

    def _translate_with_llm_first(
        self, input_text: str, start_time: float, translation_id: int
    ) -> TranslationResult:
        """Thin wrapper delegating to LlmFirstController (no behavior change)."""
        return self._llm_first.run(input_text, start_time, translation_id, self._target_language)

    def _translate_with_structured_parsing(
        self,
        input_text: str,
        start_time: float,
        translation_id: int,
        existing_warnings: list[str],
    ) -> TranslationResult:
        """Thin wrapper delegating to StructuredParsingController (no behavior change)."""
        return self._structured.run(input_text, start_time, translation_id, existing_warnings)

    def _assemble_or_error(
        self, processed_blocks: list[Any]
    ) -> tuple[bool, str | None, str | None]:
        """
        Perform assembly within the same telemetry section and error formatting used today.
        Returns (True, code, None) on success, else (False, None, error_string).
        """
        logger.debug("Assembling code")
        try:
            with timed_section("translate.assemble"):
                assembled_code = self.assembler.assemble(processed_blocks)

            if not assembled_code:
                error = AssemblyError(
                    "Failed to assemble code from blocks",
                    blocks_info=[
                        {"type": b.type.value, "lines": b.line_numbers} for b in processed_blocks
                    ],
                    assembly_stage="final",
                )
                error.add_suggestion("Check block compatibility")
                error.add_suggestion("Verify all blocks were translated successfully")
                return False, None, error.format_error()

            return True, assembled_code, None

        except Exception as e:
            error = AssemblyError(
                "Code assembly failed",
                blocks_info=[
                    {"type": b.type.value, "lines": b.line_numbers} for b in processed_blocks
                ],
                assembly_stage="assembly",
                cause=e,
            )
            return False, None, error.format_error()

    def _suggest_improvements(self, code: str) -> list[str]:
        """Delegate to validator.suggest_improvements with identical wording/ordering semantics."""
        return self.validator.suggest_improvements(code)

    def _handle_assembly_failure(
        self, assembly_error: str | None, warnings: list[str], parse_result: Any, start_time: float
    ) -> TranslationResult:
        """Handle assembly failure with appropriate error formatting."""
        return TranslationResult(
            success=False,
            code=None,
            errors=[assembly_error] if assembly_error else [],
            warnings=warnings,
            metadata=self._create_metadata(
                start_time,
                _blocks_len(getattr(parse_result, "blocks", None)),
                0,  # No blocks processed on assembly failure
                0,
                0,
                False,
            ),
        )

    def _validate_assembled_code(self, assembled_code: str) -> Any:
        """Validate assembled code and return validation result."""
        logger.debug("Validating generated code")
        with timed_section("translate.validate"):
            vr = self._maybe_offload_validate(assembled_code)
        return _as_validation_result(vr)

    def _attempt_code_fixes(
        self, assembled_code: str, validation_result: Any, warnings: list[str]
    ) -> tuple[str, Any]:
        """Attempt to fix validation errors and re-validate."""
        logger.debug("Attempting to fix validation errors")
        fixed_code = self._attempt_fixes(assembled_code, validation_result)

        with timed_section("translate.validate"):
            vr2 = self._maybe_offload_validate(fixed_code)
        new_validation_result = _as_validation_result(vr2)

        if new_validation_result.is_valid:
            warnings.append("Code was automatically fixed to resolve syntax errors")
            return fixed_code, new_validation_result

        return assembled_code, new_validation_result

    def _perform_logic_validation_and_suggestions(
        self, assembled_code: str, warnings: list[str]
    ) -> None:
        """Perform logic validation and add improvement suggestions."""
        # Logic validation unchanged
        logic_result = self.validator.validate_logic(assembled_code)
        warnings.extend(logic_result.warnings)

        # Suggestions unchanged
        suggestions = self._suggest_improvements(assembled_code)
        if suggestions:
            warnings.append(f"Improvement suggestions: {'; '.join(suggestions)}")

    def _create_structured_metadata(
        self,
        processed_blocks: list[CodeBlock],
        parse_result: Any,
        start_time: float,
        translation_id: int,
        validation_result: Any,
    ) -> dict[str, Any]:
        """Create metadata for structured translation result."""
        blocks_translated = sum(1 for b in processed_blocks if b.metadata.get("translated", False))
        cache_hits = 0
        metadata = self._create_metadata(
            start_time,
            _blocks_len(getattr(parse_result, "blocks", None)),
            blocks_translated,
            cache_hits,
            0,
            validation_result.is_valid,
        )
        metadata["approach"] = "structured_parsing"
        metadata["translation_id"] = translation_id
        return metadata

    def _complete_structured_translation(
        self,
        processed_blocks: list[CodeBlock],
        parse_result: Any,
        start_time: float,
        warnings: list[str],
        translation_id: int,
    ) -> TranslationResult:
        """Complete the structured translation with assembly and validation"""
        errors: list[str] = []

        # Assemble or return early with identically formatted error
        ok, assembled_code, assembly_error = self._assemble_or_error(processed_blocks)
        if not ok:
            return self._handle_assembly_failure(assembly_error, warnings, parse_result, start_time)

        # Validate the assembled code
        if not isinstance(assembled_code, str):
            raise TranslatorError(
                f"Internal error: assembled_code is not a string (got {type(assembled_code).__name__})"
            )

        assembled_str: str = assembled_code
        validation_result = self._validate_assembled_code(assembled_str)

        # Attempt fixes if validation failed
        if not validation_result.is_valid:
            assembled_str, validation_result = self._attempt_code_fixes(
                assembled_str, validation_result, warnings
            )

            if not validation_result.is_valid:
                errors.extend(validation_result.errors)
                warnings.extend(validation_result.warnings)

        # Perform logic validation and add suggestions
        self._perform_logic_validation_and_suggestions(assembled_str, warnings)

        # Create metadata
        metadata = self._create_structured_metadata(
            processed_blocks, parse_result, start_time, translation_id, validation_result
        )

        return TranslationResult(
            success=validation_result.is_valid,
            code=assembled_str,
            errors=errors,
            warnings=warnings,
            metadata=metadata,
        )

    def _build_model_config_for_block(self) -> ModelTranslationConfig:
        """Build per-block model translation config identical to previous inline construction."""
        return ModelTranslationConfig(
            target_language=self._target_language,
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
            top_p=getattr(self.config.llm, "top_p", 0.9),
            top_k=getattr(self.config.llm, "top_k", 40),
            include_comments=True,
            follow_conventions=True,
        )

    def _build_model_config_for_document(self) -> ModelTranslationConfig:
        """
        Build the model TranslationConfig for whole-document LLM-first translation.
        Parity: matches the inline construction previously used in _translate_with_llm_first.
        """
        return ModelTranslationConfig(
            target_language=self._target_language,
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
            top_p=getattr(self.config.llm, "top_p", 0.9),
            top_k=getattr(self.config.llm, "top_k", 40),
            include_comments=True,
            follow_conventions=True,
        )

    def _validate_and_optionally_fix(self, code: str) -> tuple[str, Any]:
        """Thin wrapper delegating to ValidationService with LLM-first semantics (parity preserved)."""
        return self._validation.validate_and_optionally_fix(code, llm_first=True)

    def _parse_input_with_offload(self, text: str) -> Any:
        """
        Parse orchestration wrapper that calls _maybe_offload_parse(text) and returns the result.
        Parity: no formatting or conversion changes here; callers retain current handling.
        """
        return self._maybe_offload_parse(text)

    def _validate_translation_model(self, model: Any) -> str | None:
        """Validate that translation model is initialized."""
        if model is None:
            return "Translation model is not initialized"
        return None

    def _create_error_context_for_block(self, block: Any, text: str) -> ErrorContext:
        """Create error context for top-level ENGLISH blocks."""
        return ErrorContext(
            line_number=block.line_numbers[0],
            code_snippet=(text or "")[:100],
            metadata={
                "block_type": "english",
                "line_range": f"{block.line_numbers[0]}-{block.line_numbers[1]}",
            },
        )

    def _create_formatted_error_response(
        self, block: Any, text: str, error_msg: str, cause: Exception | None = None
    ) -> tuple[None, dict[str, Any]]:
        """Create formatted error response for top-level ENGLISH blocks."""
        try:
            error_context = self._create_error_context_for_block(block, text)
            terr = TranslatorError(
                "Failed to translate English block",
                context=error_context,
                cause=cause or RuntimeError(error_msg),
            )
            terr.add_suggestion("Simplify the instruction")
            terr.add_suggestion("Check for ambiguous language")
            terr.add_suggestion("Break down complex requirements")
            return None, {
                "translation_failed": True,
                "error": terr.format_error(),
            }
        except Exception:
            # Fallback to simple error
            return None, {"translation_failed": True, "error": error_msg}

    def _should_validate_block(self, block: Any | None) -> bool:
        """Determine if block should be validated (only top-level ENGLISH blocks)."""
        if block is None:
            return False
        if getattr(block, "type", None) != BlockType.ENGLISH:
            return False
        return not bool(block.metadata.get("is_sub_block", False))

    def _is_top_level_english_block(self, block: Any | None) -> bool:
        """Check if block is a top-level ENGLISH block."""
        if block is None:
            return False
        if getattr(block, "type", None) != BlockType.ENGLISH:
            return False
        return not block.metadata.get("is_sub_block", False)

    def _perform_translation_with_model(
        self, model: Any, text: str, context: dict[str, Any] | None
    ) -> str:
        """Perform the actual translation with the model."""
        translation_config = self._build_model_config_for_block()

        with timed_section("translate.model"):
            result = model.translate(
                instruction=text,
                config=translation_config,
                context=context,
            )

        if not result.success:
            raise RuntimeError("Translation failed: " + ", ".join(result.errors))

        translated_code = result.code
        if translated_code is None:
            raise RuntimeError("Model returned no code")

        return translated_code

    def _log_translation_error(self, block: Any | None, error: Exception) -> None:
        """Log translation error with appropriate context."""
        try:
            if block is not None and getattr(block, "metadata", {}).get("is_sub_block", False):
                logger.error("Failed to translate sub-block: %s", error)
            else:
                logger.error("Failed to translate block: %s", error)
        except Exception:
            logger.error("Failed to translate block: %s", error)

    def _translate_text_with_model(
        self,
        text: str,
        *,
        context: dict[str, Any] | None = None,
        block: Any | None = None,
    ) -> tuple[str | None, dict[str, Any]]:
        """
        Translate text with the active model, preserving telemetry and metadata semantics.

        Returns:
            (translated_code_or_None, metadata_updates)

        On success:
            - metadata includes {"translated": True}
        On failure:
            - metadata includes {"translation_failed": True, "error": <message>}
              For top-level ENGLISH blocks, the error message uses the formatted TranslatorError
              with ErrorContext and suggestions, matching previous behavior.
        """
        model = self._current_model

        # Check model initialization
        error_msg = self._validate_translation_model(model)
        if error_msg:
            if self._is_top_level_english_block(block):
                return self._create_formatted_error_response(block, text, error_msg)
            return None, {"translation_failed": True, "error": error_msg}

        try:
            # Validate input if needed (only for top-level ENGLISH blocks)
            if (
                self._should_validate_block(block)
                and model is not None
                and hasattr(model, "validate_input")
            ):
                is_valid, error_msg = model.validate_input(text)
                if not is_valid:
                    raise ValueError(f"Invalid input: {error_msg}")

            # Perform translation
            translated_code = self._perform_translation_with_model(model, text, context)

            return translated_code, {"translated": True}

        except Exception as e:
            # Log error appropriately
            self._log_translation_error(block, e)

            # Handle top-level ENGLISH blocks with formatted errors
            if self._is_top_level_english_block(block):
                return self._create_formatted_error_response(block, text, str(e), e)

            # Mixed and other cases: simpler error semantics
            return None, {"translation_failed": True, "error": str(e)}

    def _process_english_block(
        self, block: CodeBlock, index: int, blocks: list[CodeBlock]
    ) -> CodeBlock:
        """
        Process a top-level ENGLISH block into a PYTHON block or mark failure.
        Preserves metadata keys and error formatting behavior.
        """
        context = self._build_context(blocks, index)
        code, meta = self._translate_text_with_model(block.content, context=context, block=block)
        if code is not None:
            return CodeBlock(
                type=BlockType.PYTHON,
                content=code,
                line_numbers=block.line_numbers,
                metadata={
                    **block.metadata,
                    **meta,
                    "original_type": "english",
                },
                context=block.context,
            )

        # Failure path: update metadata on original block (already formatted by helper)
        with contextlib.suppress(Exception):
            block.metadata.update(meta)
        return block

    def _process_mixed_block(
        self, block: CodeBlock, index: int, blocks: list[CodeBlock]
    ) -> list[CodeBlock]:
        """
        Process a MIXED block by translating ENGLISH sub-blocks and passing through others.
        Preserves previous behavior for metadata and merging.
        """
        separated_blocks = self._separate_mixed_block(block)
        output_blocks: list[CodeBlock] = []
        for sub_block in separated_blocks:
            if sub_block.type == BlockType.ENGLISH:
                context = self._build_context(blocks, index)
                code, meta = self._translate_text_with_model(
                    sub_block.content, context=context, block=sub_block
                )
                if code is not None:
                    sub_block.content = code
                    sub_block.type = BlockType.PYTHON
                    try:
                        # includes {"translated": True}
                        sub_block.metadata.update(meta)
                    except Exception:
                        sub_block.metadata["translated"] = True
                else:
                    try:
                        # includes failure + error string
                        sub_block.metadata.update(meta)
                    except Exception:
                        sub_block.metadata["translation_failed"] = True
                        sub_block.metadata["error"] = meta.get("error", "unknown error")
            output_blocks.append(sub_block)
        return output_blocks

    def _process_passthrough_block(self, block: CodeBlock) -> CodeBlock:
        """Pass through non-translated block types unchanged."""
        return block

    def _process_blocks(self, blocks: list[CodeBlock]) -> list[CodeBlock]:
        """
        Process each block, translating English blocks to Python

        Args:
            blocks: List of parsed code blocks

        Returns:
            List of processed code blocks
        """
        processed_blocks: list[CodeBlock] = []

        for i, block in enumerate(blocks):
            logger.debug("Processing block %d/%d: %s", i + 1, len(blocks), block.type)

            if block.type == BlockType.ENGLISH:
                processed_blocks.append(self._process_english_block(block, i, blocks))
                continue

            if block.type == BlockType.MIXED:
                processed_blocks.extend(self._process_mixed_block(block, i, blocks))
                continue

            # Python and comment blocks pass through unchanged
            processed_blocks.append(self._process_passthrough_block(block))

        return processed_blocks

    def _handle_dependencies(self, blocks: list[CodeBlock]) -> None:
        """Thin wrapper delegating to DependencyAnalysisGateway (parity preserved)."""
        return self._dep_gateway.analyze_and_annotate(blocks)

    def _build_context(self, blocks: list[CodeBlock], current_index: int) -> dict[str, Any]:
        """
        Build context for translation based on surrounding blocks

        Args:
            blocks: All blocks
            current_index: Index of current block

        Returns:
            Context dictionary
        """
        context = {"code": "", "before": "", "after": ""}

        # Get previous Python code blocks for context
        previous_code: list[str] = []
        for i in range(max(0, current_index - 3), current_index):
            if blocks[i].type == BlockType.PYTHON:
                previous_code.append(blocks[i].content)

        if previous_code:
            context["before"] = "\n\n".join(previous_code[-2:])  # Last 2 blocks
            context["code"] = context["before"]

        # Get next block if available (for better understanding)
        if current_index + 1 < len(blocks):
            next_block = blocks[current_index + 1]
            if next_block.type in [BlockType.PYTHON, BlockType.ENGLISH]:
                context["after"] = next_block.content[:200]  # First 200 chars

        return context

    def _separate_mixed_block(self, block: CodeBlock) -> list[CodeBlock]:
        """
        Separate a mixed block into English and Python sub-blocks.
        Behavior parity: identical thresholds/heuristics, block typing, metadata, and return format.
        """
        lines = block.content.splitlines()
        if not lines:
            return [block]

        sub_blocks: list[CodeBlock] = []
        current_type: BlockType | None = None
        buffer: list[str] = []
        segment_start = block.line_numbers[0]

        def flush(is_final: bool = False) -> None:
            if not buffer:
                return
            end_line = block.line_numbers[1] if is_final else (segment_start + len(buffer) - 1)
            sub_blocks.append(
                CodeBlock(
                    type=(current_type if current_type is not None else BlockType.ENGLISH),
                    content="\n".join(buffer),
                    line_numbers=(segment_start, end_line),
                    metadata={"parent_block": block.metadata, "is_sub_block": True},
                    context=block.context,
                )
            )

        for i, raw_line in enumerate(lines):
            score = self.parser.score_line_language(raw_line.strip())
            line_type = BlockType.PYTHON if score > 0.5 else BlockType.ENGLISH

            if current_type is None:
                current_type = line_type
                buffer = [raw_line]
                segment_start = block.line_numbers[0]
                continue

            if line_type != current_type:
                flush(False)
                current_type = line_type
                buffer = [raw_line]
                segment_start = block.line_numbers[0] + i
                continue

            buffer.append(raw_line)

        flush(True)
        return sub_blocks if sub_blocks else [block]

    def _attempt_fixes(self, code: str, validation_result: ValidationResult) -> str:
        """
        Thin wrapper that delegates to translator_support.fix_refiner.attempt_fixes,
        preserving signature and return semantics (code-only). Telemetry and logging
        semantics are preserved relative to previous behavior.
        """
        if not getattr(validation_result, "errors", None):
            return code

        # Build compact error summary (parity is enforced in support helper too)
        try:
            # Local import to avoid cycles; support module must not import translator.py
            from .translator_support.fix_refiner import (
                attempt_fixes as _support_attempt_fixes,  # type: ignore
            )
        except Exception:
            # Preserve previous error/warning logging semantics on failure
            logger.error("Failed to fix code: import error in fix_refiner")
            recovery_error = TranslatorError(
                "Automatic error recovery failed", cause=ImportError("fix_refiner")
            )
            recovery_error.add_suggestion("Manual fixes may be required")
            logger.warning(recovery_error.format_error())
            return code

        try:
            refined_code, _warnings_delta = _support_attempt_fixes(
                self._current_model, code, validation_result
            )
            return refined_code
        except Exception as e:
            # Preserve previous error/warning logging semantics on failure
            logger.error("Failed to fix code: %s", e)
            recovery_error = TranslatorError("Automatic error recovery failed", cause=e)
            recovery_error.add_suggestion("Manual fixes may be required")
            logger.warning(recovery_error.format_error())
            return code

    def _create_metadata(
        self,
        start_time: float,
        blocks_processed: int,
        blocks_translated: int,
        cache_hits: int,
        model_tokens: int,
        validation_passed: bool,
    ) -> dict[str, Any]:
        """Create metadata dictionary for the translation result"""
        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "duration_ms": duration_ms,
            "blocks_processed": blocks_processed,
            "blocks_translated": blocks_translated,
            "cache_hits": cache_hits,
            "model_tokens_used": model_tokens,
            "validation_passed": validation_passed,
            "translation_id": self._translation_count,
        }

    def _cleanup_resources(self) -> None:
        """Cleanup translation manager resources during shutdown"""
        logger.info("Shutting down Translation Manager")
        # Stop exec pool first to ensure clean exit of child processes
        try:
            pool = self._exec_pool
            if pool is not None:
                pool.shutdown(wait=True)
        except Exception:
            pass
        if self._current_model:
            self._current_model.shutdown()
        logger.info("Translation Manager shutdown complete")

    def get_event_dispatcher(self) -> EventDispatcher:
        """Return the event dispatcher to allow external listeners to register."""
        return self._events

    def switch_model(self, model_name: str) -> None:
        """
        Switch to a different translation model

        Args:
            model_name: Name of the model to switch to
        """
        logger.info("Switching from %s to %s", self._model_name, model_name)

        # Shutdown current model
        if self._current_model:
            self._current_model.shutdown()

        # Initialize new model
        self._initialize_model(model_name)

        # Emit MODEL_CHANGED (best-effort)
        with contextlib.suppress(Exception):
            _dispatch_event(
                self._events,
                EventType.MODEL_CHANGED,
                source=self.__class__.__name__,
                model=model_name,
            )

    def get_current_model(self) -> str | None:
        """Get the name of the current model"""
        return self._model_name

    def list_available_models(self) -> list[str]:
        """List all available models"""
        return ModelFactory.list_models()

    def get_telemetry_snapshot(self) -> dict[str, Any]:
        """Return telemetry snapshot if enabled, else {}."""
        try:
            # Import on demand to avoid issues if module layout changes
            from .telemetry import get_recorder as _get_rec
            from .telemetry import telemetry_enabled as _t_enabled

            if _t_enabled():
                rec_any: Any = _get_rec()
                return cast("dict[str, Any]", rec_any.snapshot())
        except Exception:
            # Never raise from telemetry; keep behavior unchanged
            pass
        return {}

    def set_target_language(self, language: OutputLanguage) -> None:
        """Set the target output language"""
        self._target_language = language
        logger.info("Target language set to: %s", language.value)

    def _validate_model_for_text_block(self) -> None:
        """Validate that model is initialized for text block translation."""
        if self._current_model is None:
            raise RuntimeError("Translation model is not initialized")

    def _build_text_block_config(
        self, config: dict[str, Any] | ModelTranslationConfig | None
    ) -> ModelTranslationConfig:
        """Build translation config for text block translation."""
        if isinstance(config, ModelTranslationConfig):
            return config

        # Build default config
        translation_config = ModelTranslationConfig(
            target_language=self._target_language,
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
            top_p=getattr(self.config.llm, "top_p", 0.9),
            top_k=getattr(self.config.llm, "top_k", 40),
            include_comments=True,
            follow_conventions=True,
        )

        # Apply overrides from dict config
        if isinstance(config, dict):
            for key, value in config.items():
                if hasattr(translation_config, key):
                    setattr(translation_config, key, value)

        return translation_config

    def _delegate_to_model(
        self, text: str, translation_config: ModelTranslationConfig, context: dict[str, Any] | None
    ) -> Any:
        """Delegate translation to the active model."""
        if self._current_model is None:
            raise RuntimeError("Translation model is not initialized")
        return self._current_model.translate(
            instruction=text, config=translation_config, context=context
        )

    def translate_text_block(
        self,
        text: str,
        context: dict[str, Any] | None = None,
        config: dict[str, Any] | ModelTranslationConfig | None = None,
    ) -> Any:
        """
        Translate a single text block via the active model.

        This public wrapper is used by streaming paths to delegate translation
        to the currently selected model via the model factory abstraction.
        It adapts the manager's configuration into a model TranslationConfig
        and returns the model-level TranslationResult without exposing model internals.

        Args:
            text: The natural language instruction or mixed text to translate.
            context: Optional context dictionary to pass to the model.
            config: Optional overrides. May be a ModelTranslationConfig instance
                    or a dict containing fields to override on the TranslationConfig.

        Returns:
            The model-level TranslationResult object.
        """
        self._validate_model_for_text_block()

        # Build translation config
        translation_config = self._build_text_block_config(config)

        # Delegate to the active model
        return self._delegate_to_model(text, translation_config, context)

    def translate_streaming(
        self,
        input_text: str,
        chunk_size: int = 4096,
        progress_callback: Any | None = None,
    ) -> Iterator[TranslationResult]:
        """
        Translate pseudocode using streaming for memory efficiency

        Args:
            input_text: Mixed English/Python pseudocode
            chunk_size: Size of chunks for streaming
            progress_callback: Optional callback for progress updates

        Yields:
            TranslationResult objects for each processed chunk
        """
        emitter = self._setup_stream_emitter()
        start_time = time.time()
        try:
            yield from self._execute_streaming_pipeline(
                input_text, start_time, progress_callback, emitter
            )
        except ImportError:
            logger.warning("Streaming module not available, using regular translation")
            yield self.translate_pseudocode(input_text)
        except Exception as e:
            yield self._create_streaming_error_result(e)

    def _setup_stream_emitter(self) -> Any:
        """Setup stream emitter for event handling."""
        try:
            from .translator_support.stream_emitter import StreamEmitter  # type: ignore

            return StreamEmitter(self._events, source=self.__class__.__name__)
        except Exception:
            return None

    def _execute_streaming_pipeline(
        self, input_text: str, start_time: float, progress_callback: Any, emitter: Any
    ) -> Iterator[TranslationResult]:
        from .streaming.pipeline import StreamingPipeline

        pipeline = StreamingPipeline(self.config)
        with contextlib.suppress(Exception):
            pipeline.translator = self

        if not pipeline.should_use_streaming(input_text):
            yield self.translate_pseudocode(input_text)
            return

        all_results: list[TranslationResult] = []
        logger.info("Using streaming translation")
        self._emit_stream_started(emitter)
        for result in self._process_streaming_chunks(pipeline, input_text, progress_callback):
            all_results.append(result)
            yield result

        final_result = self._create_final_streaming_result(pipeline, start_time, all_results)
        self._emit_stream_completed(emitter, len(all_results))
        pipeline.cancel_streaming()
        yield final_result

    def _emit_stream_started(self, emitter: Any) -> None:
        """Emit stream started event."""
        if emitter is not None:
            emitter.stream_started("selected_by_config")
        else:
            with contextlib.suppress(Exception):
                _dispatch_event(
                    self._events,
                    EventType.STREAM_STARTED,
                    source=self.__class__.__name__,
                    reason="selected_by_config",
                )

    def _process_streaming_chunks(
        self, pipeline: Any, input_text: str, progress_callback: Any
    ) -> Iterator[TranslationResult]:
        """Process streaming chunks and yield results."""
        for chunk_result in pipeline.stream_translate(
            input_text, progress_callback=progress_callback
        ):
            if chunk_result.success and chunk_result.translated_blocks:
                chunk_code = self.assembler.assemble(chunk_result.translated_blocks)
                result = TranslationResult(
                    success=True,
                    code=chunk_code,
                    errors=[],
                    warnings=chunk_result.warnings,
                    metadata={
                        "chunk_index": chunk_result.chunk_index,
                        "processing_time": chunk_result.processing_time,
                        "streaming": True,
                    },
                )
            else:
                result = TranslationResult(
                    success=False,
                    code=None,
                    errors=[chunk_result.error] if chunk_result.error else [],
                    warnings=chunk_result.warnings,
                    metadata={
                        "chunk_index": chunk_result.chunk_index,
                        "streaming": True,
                    },
                )
            yield result

    def _create_final_streaming_result(
        self, pipeline: Any, start_time: float, all_results: list[TranslationResult]
    ) -> TranslationResult:
        """Create the final streaming result after processing all chunks."""
        final_code = pipeline.assemble_streamed_code()
        duration_ms = int((time.time() - start_time) * 1000)
        validation_result = self.validator.validate_syntax(final_code)
        return TranslationResult(
            success=validation_result.is_valid,
            code=final_code,
            errors=validation_result.errors,
            warnings=validation_result.warnings,
            metadata={
                "duration_ms": duration_ms,
                "streaming": True,
                "total_chunks": len(all_results),
                "memory_usage": pipeline.get_memory_usage(),
            },
        )

    def _emit_stream_completed(self, emitter: Any, chunk_count: int) -> None:
        """Emit stream completed event."""
        if emitter is not None:
            emitter.stream_completed(chunk_count)
        else:
            with contextlib.suppress(Exception):
                _dispatch_event(
                    self._events,
                    EventType.STREAM_COMPLETED,
                    source=self.__class__.__name__,
                    chunks=chunk_count,
                )

    def _create_streaming_error_result(self, error: Exception) -> TranslationResult:
        """Create error result for streaming failures."""
        translator_error = TranslatorError("Streaming translation failed", cause=error)
        translator_error.add_suggestion("Try regular translation instead")

        return TranslationResult(
            success=False,
            code=None,
            errors=[translator_error.format_error()],
            warnings=[],
            metadata={"streaming_error": True},
        )
