"""Common result builders for tool responses.

These utilities help construct success and error result dictionaries while preserving
original keys and values. Pure functions with no side effects.
"""

from __future__ import annotations

from typing import Any


def build_success(payload: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a success result by merging payload and optional extra.

    Behavior:
    - Merge payload + extra (if provided).
    - If "success" is not in the merged dict, set success=True.
    - If the caller explicitly provided success, respect it.
    - Never remove or rename keys in payload/extra.
    """
    result: dict[str, Any] = {}
    result.update(payload if payload is not None else {})
    if extra:
        result.update(extra)
    if "success" not in result:
        result["success"] = True
    return result


def build_error(
    message: str, error: str | None = None, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a standardized error result.

    Returns:
      {
        "success": False,
        "message": message,
        "error": error or message,
        ...extra
      }
    """
    base: dict[str, Any] = {
        "success": False,
        "message": message,
        "error": error if error is not None else message,
    }
    if extra:
        # Return a merged copy without mutating the provided dict
        return {**base, **extra}
    return base
