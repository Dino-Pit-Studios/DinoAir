r"""
SQL safety helpers for DinoAir core (non-API).

This module provides small utilities to help sanitize/normalize common SQL patterns
and encourage the use of parameterized queries throughout the codebase.

Rules of thumb:
- ALWAYS bind dynamic values using placeholders (?, ?, ...) and a tuple of params.
- NEVER interpolate user input directly into SQL strings.
- Table and column names generally cannot be parameterized: validate/allowlist them.

Functions:
- enforce_limit(limit: int, max_limit: int) -> int
- normalize_like_pattern(s: str) -> tuple[str, tuple[str, ...]]
- parameterize_delete_older_than(table: str, ts_field: str) -> tuple[str, tuple[str, ...]]

Examples:

    from utils.sql import enforce_limit, normalize_like_pattern, parameterize_delete_older_than

    # Enforce an upper bound on LIMIT values
    limit = enforce_limit(requested_limit, max_limit=100)

    # Safe LIKE usage
    pattern_sql, pattern_params = normalize_like_pattern("alice%")
    cursor.execute("SELECT * FROM users WHERE name LIKE ? ESCAPE '\\\\' LIMIT ?", pattern_params + (limit,))

    # Maintenance delete (with validated identifiers)
    sql, params = parameterize_delete_older_than("watchdog_metrics", "timestamp")
    cursor.execute(sql, params)

Notes:
- normalize_like_pattern escapes %, _ and \\ by prefixing with a backslash, and returns
  the pattern with surrounding wildcards (e.g., %s%) for a contains-style search.
- parameterize_delete_older_than returns "DELETE ... WHERE ts_field < ?" and a single param (ISO timestamp).
  The caller should validate table/column names if they are dynamic (e.g., with a small allowlist).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def enforce_limit(limit: int, max_limit: int) -> int:
    """Clamp a requested LIMIT value to a safe maximum.

    Args:
        limit: Requested limit (may be negative or excessively large).
        max_limit: Maximum allowed limit (must be positive).

    Returns:
        A safe positive integer in range [1, max_limit].
    """
    if max_limit <= 0:
        raise ValueError("max_limit must be > 0")
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return max_limit
    if n <= 0:
        return 1
    if n > max_limit:
        return max_limit
    return n


def _escape_like(s: str) -> str:
    r"""Escape %, _ and \\ in a LIKE pattern by prefixing with backslash."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def normalize_like_pattern(s: str) -> tuple[str, tuple[str, ...]]:
    r"""Return a parameterized pattern for a case-insensitive LIKE search.

    Escapes special characters and wraps the value with %...% for a contains search.

    Args:
        s: Raw search string.

    Returns:
        (sql_like_placeholder, params) where sql_like_placeholder is "?" and params is a single-element tuple.
        Use with "... LIKE ? ESCAPE '\\\\'".
    """
    safe = _escape_like(s or "")
    return "?", (f"%{safe}%",)


def _validate_identifier(name: str, kind: str) -> None:
    """Validate a SQL identifier (table/column) using a conservative regex.

    Args:
        name: Identifier to validate
        kind: 'table' or 'column' (for error messages)

    Raises:
        ValueError if the identifier is invalid.
    """
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid {kind} identifier: {name!r}")


def parameterize_delete_older_than(
    table: str, ts_field: str, days: int = 7
) -> tuple[str, tuple[str, ...]]:
    """Build a parameterized DELETE statement for retention jobs.

    Args:
        table: Table name (must be a validated/allowlisted identifier)
        ts_field: Timestamp column name (validated identifier)
        days: Retention window in days (rows older than now - days are deleted)

    Returns:
        (sql, params) suitable for cursor.execute(sql, params)

    Example:
        sql, params = parameterize_delete_older_than("watchdog_metrics", "timestamp", days=14)
        cursor.execute(sql, params)
    """
    _validate_identifier(table, "table")
    _validate_identifier(ts_field, "column")

    # Calculate cutoff timestamp
    cutoff = (datetime.now() - timedelta(days=int(days))).isoformat()

    # Construct SQL using validated identifiers and parameter placeholder
    sql = f"DELETE FROM {table} WHERE {ts_field} < %s"
    return sql, (cutoff,)
