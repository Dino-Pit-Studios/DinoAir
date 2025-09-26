from __future__ import annotations

from typing import Any


def resp(
    success: bool,
    data: object | None = None,
    error: str | None = None,
    code: int | None = None,
) -> dict[str, Any]:
    """
    Return a consistent response envelope.
    Must exactly match RagService._resp shape.
    """
    return {"success": success, "data": data, "error": error, "code": code}


def guard_imports(
    modules: tuple[str, ...],
    unavailable_message: str = "RAG components unavailable",
    code: int = 501,
) -> dict[str, Any] | None:
    """
    Try importing each module in 'modules'.
    - Return None if all imports succeed.
    - On ImportError, return a 501-style response envelope.
    Pure and side-effect free except for the import attempts.
    """
    for module in modules:
        try:
            __import__(module)
        except ImportError:
            return resp(False, None, unavailable_message, code)
    return None
