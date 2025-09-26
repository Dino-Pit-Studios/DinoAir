from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..exceptions import ParsingError, TranslatorError  # type: ignore

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

    from ..models import CodeBlock


class StructuredParsingController:
    """
    Controller for the structured parsing flow.

    Behavior preservation:
    - Telemetry section names identical ("translate.parse", "translate.validate").
    - Error/warning wording, metadata keys/values, and ordering preserved.
    - Parse offload via provided maybe_offload_parse; validate offload via provided maybe_offload_validate
      (through ValidationService callback for the structured path).
    """

    def __init__(
        self,
        parser: Any,
        assembler: Any,
        validator: Any,
        recorder: Any,
        events: Any,
        logger: logging.Logger,
        maybe_offload_parse: Callable[[str], Any],
        # kept for parity; used by ValidationService
        maybe_offload_validate: Callable[[Any], Any],
        *,
        # Callbacks to preserve behavior without importing translator.py
        process_blocks_fn: Callable[[list[CodeBlock]], list[CodeBlock]],
        assemble_or_error_fn: Callable[[list[Any]], tuple[bool, str | None, str | None]],
        suggest_improvements_fn: Callable[[str], list[str]],
        create_metadata_fn: Callable[[float, int, int, int, int, bool], dict[str, Any]],
        dependency_gateway: Any,
        validation_service: Any,
        result_cls: type,
    ) -> None:
        self._parser = parser
        self._assembler = assembler
        self._validator = validator
        self._recorder = recorder
        self._events = events
        self._logger = logger
        self._maybe_offload_parse = maybe_offload_parse
        self._maybe_offload_validate = maybe_offload_validate

        # Delegated helpers
        self._process_blocks = process_blocks_fn
        self._assemble_or_error = assemble_or_error_fn
        self._suggest_improvements = suggest_improvements_fn
        self._create_metadata = create_metadata_fn
        self._dep = dependency_gateway
        self._validation = validation_service
        self._result_cls = result_cls

    def run(
        self,
        input_text: str,
        start_time: float,
        translation_id: int,
        warnings: list[str],
    ) -> Any:
        """
        Execute structured parsing flow and return TranslationResult (manager's dataclass instance).
        """
        logger = self._logger
        logger.debug(f"Translation #{translation_id}: Using structured parsing approach")
        errors: list[str] = []
        local_warnings = warnings.copy()

        try:
            # Step 1: Parse the input
            logger.debug("Parsing input text")
            try:
                with self._recorder.timed_section("translate.parse"):
                    parse_result = self._maybe_offload_parse(input_text)

                # Compatible success check
                success_attr = getattr(parse_result, "success", None)
                parse_success = (
                    success_attr
                    if isinstance(success_attr, bool)
                    else (len(parse_result.errors) == 0)
                )

                if not parse_success:
                    # Convert parse errors to detailed error messages
                    for parse_error in parse_result.errors:
                        error = ParsingError(
                            f"Parse error: {parse_error}",
                            block_content=input_text[:200],
                        )
                        errors.append(error.format_error())

                    return self._result_cls(
                        success=False,
                        code=None,
                        errors=errors,
                        warnings=local_warnings,
                        metadata=self._create_metadata(start_time, 0, 0, 0, 0, False),
                    )
            except Exception as e:
                error = ParsingError(
                    "Failed to parse input", block_content=input_text[:200], cause=e
                )
                error.add_suggestion("Check input format")
                error.add_suggestion("Ensure pseudocode syntax is valid")

                return self._result_cls(
                    success=False,
                    code=None,
                    errors=[error.format_error()],
                    warnings=local_warnings,
                    metadata=self._create_metadata(start_time, 0, 0, 0, 0, False),
                )

            local_warnings.extend(parse_result.warnings)

            # Step 2: Process blocks
            logger.debug("Processing %d blocks", len(parse_result.blocks))
            processed_blocks = self._process_blocks(parse_result.blocks)

            # Step 3: Handle dependencies between blocks
            try:
                self._dep.analyze_and_annotate(processed_blocks)
            except Exception as e:
                logger.warning("Error handling dependencies: %s", e)
                local_warnings.append(f"Could not analyze dependencies: {str(e)}")

            # Continue with completion logic (assembly + validation)
            return self._complete_structured_translation(
                processed_blocks,
                parse_result,
                start_time,
                local_warnings,
                translation_id,
            )

        except Exception as e:
            logger.error("Structured parsing translation failed: %s", str(e))

            terr = TranslatorError("Structured parsing translation failed", cause=e)
            terr.add_suggestion("Check the input format")
            terr.add_suggestion("Review any error messages above")
            terr.add_suggestion("Try using simpler pseudocode")

            return self._result_cls(
                success=False,
                code=None,
                errors=[terr.format_error()],
                warnings=local_warnings,
                metadata=self._create_metadata(start_time, 0, 0, 0, 0, False),
            )

    # Mirrors TranslationManager._complete_structured_translation behavior
    def _complete_structured_translation(
        self,
        processed_blocks: list[CodeBlock],
        parse_result: Any,
        start_time: float,
        warnings: list[str],
        translation_id: int,
    ) -> Any:
        logger = self._logger
        errors: list[str] = []

        # Assemble or return early with identically formatted error
        ok, assembled_code, assembly_error = self._assemble_or_error(processed_blocks)
        if not ok:
            return self._result_cls(
                success=False,
                code=None,
                errors=[assembly_error] if assembly_error else [],
                warnings=warnings,
                metadata=self._create_metadata(
                    start_time,
                    len(parse_result.blocks),
                    len(processed_blocks),
                    0,
                    0,
                    False,
                ),
            )

        # Validate the code (structured path semantics)
        logger.debug("Validating generated code")
        original_code = assembled_code
        fixed_code, validation_result = self._validation.validate_and_optionally_fix(
            assembled_code, llm_first=False
        )

        assembled_final = original_code
        if not getattr(validation_result, "is_valid", False):
            # Could not fully fix
            errors.extend(getattr(validation_result, "errors", []) or [])
            warnings.extend(getattr(validation_result, "warnings", []) or [])
        # If code changed due to auto-fix, append the warning exactly as before
        elif fixed_code != original_code:
            assembled_final = fixed_code
            warnings.append("Code was automatically fixed to resolve syntax errors")
        else:
            assembled_final = original_code

        # Logic validation unchanged
        logic_result = self._validator.validate_logic(assembled_final)
        warnings.extend(getattr(logic_result, "warnings", []) or [])

        # Suggestions unchanged
        suggestions = self._suggest_improvements(assembled_final)  # type: ignore[arg-type]
        if suggestions:
            warnings.append(f"Improvement suggestions: {'; '.join(suggestions)}")

        # Metadata unchanged
        blocks_translated = sum(1 for b in processed_blocks if b.metadata.get("translated", False))
        cache_hits = 0
        metadata = self._create_metadata(
            start_time,
            len(parse_result.blocks),
            blocks_translated,
            cache_hits,
            0,
            getattr(validation_result, "is_valid", False),
        )
        metadata["approach"] = "structured_parsing"
        metadata["translation_id"] = translation_id

        return self._result_cls(
            success=getattr(validation_result, "is_valid", False),
            code=assembled_final,
            errors=errors,
            warnings=warnings,
            metadata=metadata,
        )
