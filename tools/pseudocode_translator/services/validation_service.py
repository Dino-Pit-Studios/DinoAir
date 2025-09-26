from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

# Intentionally avoid importing ValidationResult to prevent type resolution issues in editors.
# Use 'Any' for callback typing to keep this module decoupled from translator/validator internals.


class ValidationService:
    """
    Orchestrates validation and the optional fix loop with strict behavior parity.

    Behavior requirements (preserved):
    - Initial validation wrapped in recorder.timed_section("translate.validate").
    - Re-validate semantics differ:
        * LLM-first (llm_first=True): re-validation is NOT wrapped in a timed section.
        * Structured parsing (llm_first=False): re-validation IS wrapped in a timed section.
    - Logging messages must match wording used by previous implementation paths.
    - Offload gates are respected via provided maybe_offload_validate callback.
    - Fix loop is delegated to provided attempt_fixes_fn to avoid cycles and preserve semantics.
    """

    def __init__(
        self,
        validator: Any,
        recorder: Any,
        logger: logging.Logger,
        maybe_offload_validate: Callable[[Any], Any],
        attempt_fixes_fn: Callable[[str, Any], str],
    ) -> None:
        self._validator = validator
        self._recorder = recorder
        self._logger = logger
        self._maybe_offload_validate = maybe_offload_validate
        self._attempt_fixes = attempt_fixes_fn

    def validate_and_optionally_fix(self, code: str, llm_first: bool) -> tuple[str, Any]:
        """
        Validate code and optionally attempt automatic fixes.

        Returns:
            (final_code, validation_result)
        """
        # Initial validate is always timed
        with self._recorder.timed_section("translate.validate"):
            validation_result = self._maybe_offload_validate(code)

        if getattr(validation_result, "is_valid", False):
            return code, validation_result

        # Attempt to fix, preserving identical logging semantics
        self._logger.debug("Attempting to fix validation errors")
        try:
            fixed = self._attempt_fixes(code, validation_result)

            # Re-validate with flow-specific telemetry semantics
            if llm_first:
                # LLM-first path: do NOT wrap re-validation in a timed section
                new_validation = self._maybe_offload_validate(fixed)
            else:
                # Structured path: wrap re-validation in the same timed section name
                with self._recorder.timed_section("translate.validate"):
                    new_validation = self._maybe_offload_validate(fixed)

            if getattr(new_validation, "is_valid", False):
                self._logger.info("Code fixed successfully")
                return fixed, new_validation

            # Could not fully fix
            self._logger.warning("Could not fix all validation errors")
            return code, validation_result

        except Exception as fix_error:
            # Preserve warning text from existing behavior
            self._logger.warning("Code fixing failed: %s", fix_error)
            return code, validation_result
