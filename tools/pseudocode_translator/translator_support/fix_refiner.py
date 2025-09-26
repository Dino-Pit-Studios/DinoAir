"""
Fix refinement support module.

Provides a behavior-parity helper for code refinement that mirrors the logic from
TranslationManager._attempt_fixes without importing translator.py.

Parity guarantees:
- Use only the top-3 validation errors joined by newline as error_context.
- Do not raise on any exception; return (original_code, []) on failures.
- Return (refined_code, warnings_delta) on success; warnings_delta is [] here to avoid
  altering caller semantics. Callers that previously appended warnings should continue
  to do so outside this helper.

Note: Keep imports minimal to avoid cycles; do not import translator internals.
"""

from typing import Any


def attempt_fixes(model: Any, code: str, validation_result: Any) -> tuple[str, list[str]]:
    """
    Attempt to refine code using the provided model and validation errors.

    Args:
        model: Active translation model (may be None). Must provide refine_code(code, error_context, config=None).
        code: The code string to refine.
        validation_result: An object with an 'errors' attribute (list[str]).

    Returns:
        Tuple of (refined_code: str, warnings_delta: list[str]).
        On exception or if no improvement is produced, returns (original code, []).
    """
    try:
        errors = getattr(validation_result, "errors", None) or []
        if not errors:
            return code, []

        # Compact top-3 error summary (parity with translator)
        error_context = "\n".join(errors[:3])

        if model is None:
            return code, []

        # Call model refine; keep config minimal/None to avoid importing model types
        result = model.refine_code(code=code, error_context=error_context, config=None)

        if getattr(result, "success", False) and getattr(result, "code", None):
            # Return refined code; warnings are left to callers to append for parity
            return result.code, []

        return code, []
    except Exception:
        # Strict parity: never raise from refinement helper
        return code, []
