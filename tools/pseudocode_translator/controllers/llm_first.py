from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

# Avoid importing translator.py to prevent cycles.
# Use injected collaborators and callbacks exclusively.


class LlmFirstController:
    """
    Controller for the LLM-first translation flow.

    Behavior preservation:
    - Telemetry section names identical ("translate.model").
    - Logging messages and metadata keys/values identical to original implementation.
    - Validation and fix semantics delegated via provided validate_and_optionally_fix_fn with
      llm_first=True at the call site (TranslationManager wiring).
    """

    def __init__(
        self,
        model: Any,
        assembler: Any,
        validator: Any,
        recorder: Any,
        events: Any,
        logger: logging.Logger,
        *,
        validate_and_optionally_fix_fn: Callable[[str], tuple[str, Any]],
        build_config_for_document_fn: Callable[[], Any],
        result_cls: type,
    ) -> None:
        self._model = model
        self._assembler = assembler
        self._validator = validator
        self._recorder = recorder
        self._events = events
        self._logger = logger

        # Callbacks
        self._validate_and_optionally_fix = validate_and_optionally_fix_fn
        self._build_config_for_document = build_config_for_document_fn
        self._result_cls = result_cls

    def run(
        self,
        input_text: str,
        start_time: float,
        translation_id: int,
        target_language: Any,  # OutputLanguage
    ) -> Any:
        """
        Execute LLM-first flow and return TranslationResult (manager's dataclass instance).
        """
        logger = self._logger
        logger.debug("Translation #%s: Using LLM-first approach", translation_id)

        # Build translation config for document-level LLM translation
        translation_config = self._build_config_for_document()

        # Validate input with LLM
        model = self._model
        if model is None:
            raise RuntimeError("Translation model is not initialized")
        is_valid, error_msg = model.validate_input(input_text)
        if not is_valid:
            raise ValueError(f"LLM input validation failed: {error_msg}")

        # Translate using the LLM model directly
        logger.debug("Translation #%s: Translating with LLM", translation_id)
        with self._recorder.timed_section("translate.model"):
            result = model.translate(
                instruction=input_text,
                config=translation_config,
                context={
                    "approach": "llm_first",
                    "translation_id": translation_id,
                    "fallback_available": True,
                },
            )

        if not getattr(result, "success", False):
            raise RuntimeError(
                f"LLM translation failed: {', '.join(getattr(result, 'errors', []) or [])}"
            )

        generated_code = getattr(result, "code", None)
        if not generated_code:
            raise RuntimeError("LLM produced no code output")

        # Validate and optionally fix (preserving telemetry labels and re-validation behavior)
        logger.debug("Translation #%s: Validating generated code", translation_id)
        final_code, validation_result = self._validate_and_optionally_fix(generated_code)

        # Logic validation and improvements (unchanged wording and list order)
        logic_result = self._validator.validate_logic(final_code)
        warnings = list(getattr(logic_result, "warnings", []) or [])

        suggestions = self._validator.suggest_improvements(final_code)
        if suggestions:
            warnings.append(f"Improvement suggestions: {'; '.join(suggestions)}")

        # Calculate metadata (unchanged keys/values)
        import time as _time

        duration_ms = int((_time.time() - start_time) * 1000)
        model_name = "unknown"
        try:
            if getattr(result, "metadata", None):
                model_name = result.metadata.get("model", "unknown")
        except Exception:
            pass

        metadata: dict[str, Any] = {
            "duration_ms": duration_ms,
            "blocks_processed": 1,  # Treated as single block
            "blocks_translated": 1,
            "cache_hits": 0,
            "model_tokens_used": 0,  # Would need to be tracked in model
            "validation_passed": getattr(validation_result, "is_valid", False),
            "translation_id": translation_id,
            "approach": "llm_first",
            "model": model_name,
        }

        return self._result_cls(
            success=getattr(validation_result, "is_valid", False),
            code=final_code,
            errors=getattr(validation_result, "errors", []) or [],
            warnings=warnings,
            metadata=metadata,
        )
