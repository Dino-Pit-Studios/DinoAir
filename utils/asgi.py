"""ASGI utility helpers.

Currently provides a safe header extraction helper for Starlette/ASGI scopes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

try:
    # starlette is already a dependency in this project
    from starlette.types import Scope
except (
    ImportError
):  # pragma: no cover - fallback typing if starlette not available at type-check time
    from typing import Any as Scope  # type: ignore


def get_header(scope: Scope, name: str) -> str | None:
    """
    Retrieve a header value from an ASGI scope in a case-insensitive way.

    - Returns the first matching value decoded using latin-1, or None if missing/undecodable.
    - Defensive against absent or ill-typed scope["headers"].
    """
    # noinspection PyCompatibility
    headers: Iterable[tuple[bytes, bytes]] = scope.get("headers") or []  # type: ignore[assignment]
    name_b = name.lower().encode("latin-1")
    for k, v in headers:
        if k.lower() == name_b:
            try:
                return v.decode("latin-1")
            except (UnicodeDecodeError, LookupError):
                return None
    return None
