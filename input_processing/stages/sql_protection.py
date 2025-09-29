"""
SQL Injection Protection Module.

Provides comprehensive protection against SQL injection attacks.
"""

import re
import sqlite3
from typing import Any, cast


class SQLInjectionProtection:
    """Enhanced SQL injection protection."""

    # SQL keywords that indicate injection attempts
    SQL_KEYWORDS: set[str] = {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "EXEC",
        "EXECUTE",
        "UNION",
        "WHERE",
        "FROM",
        "JOIN",
        "TABLE",
        "DATABASE",
        "SCRIPT",
        "DECLARE",
        "CAST",
        "CONVERT",
        "CHAR",
        "TRUNCATE",
        "REPLACE",
        "MERGE",
        "CALL",
        "EXPLAIN",
        "GRANT",
        "REVOKE",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "PROCEDURE",
        "FUNCTION",
        "TRIGGER",
        "VIEW",
        "INDEX",
    }

    # SQL operators and special characters
    SQL_OPERATORS: set[str] = {
        "--",
        "/*",
        "*/",
        "@",
        "CHAR(",
        "NCHAR(",
        "VARCHAR(",
        "NVARCHAR(",
        "EXEC(",
        "EXECUTE(",
        "CAST(",
        "CONVERT(",
        "0x",
        "\\x",
        "PASSWORD(",
        "ENCRYPT(",
        "CONCAT(",
        "SUBSTRING(",
        "LENGTH(",
        "ASCII(",
        "MD5(",
        "SHA1(",
        "SHA2(",
        "ENCODE(",
        "DECODE(",
        "BENCHMARK(",
        "SLEEP(",
        "WAITFOR",
    }

    # Common SQL injection patterns
    SQL_PATTERNS: list[str] = [
        r"('\s*OR\s*'?\d*'?\s*=\s*'?\d*'?')",  # ' OR '1'='1' variations
        r"('\s*OR\s+\d+\s*=\s*\d+)",  # ' OR 1=1
        r"(;\s*DROP\s+TABLE\s+\w+)",  # ; DROP TABLE
        r"(;\s*DELETE\s+FROM\s+\w+)",  # ; DELETE FROM
        r"('\s*;\s*--)\"",  # '; --
        r"(UNION\s+ALL\s+SELECT)",  # UNION ALL SELECT
        r"(UNION\s+SELECT)",  # UNION SELECT
        r"(INTO\s+OUTFILE)",  # INTO OUTFILE
        r"(LOAD_FILE\s*\()",  # LOAD_FILE(
        r"(INTO\s+DUMPFILE)",  # INTO DUMPFILE
        r"('\s*AND\s*SLEEP\s*\(),",  # Time-based injection
        r"('\s*AND\s*BENCHMARK\s*\(),",  # Benchmark injection
        r"(INFORMATION_SCHEMA)",  # Information schema access
        r"(sys\.databases)",  # System tables
        r"(xp_cmdshell)",  # Command execution
        r"('\s*HAVING\s+\d+\s*=\s*\d+)",  # HAVING clause injection
        r"('\s*GROUP\s+BY\s+\w+\s*--)\"",  # GROUP BY injection
        r"('\s*ORDER\s+BY\s+\d+\s*--)\"",  # ORDER BY injection
    ]

    @staticmethod
    def _has_sql_comments(text: str) -> bool:
        """Return True if the text contains SQL comment markers ('--', '/*', or '*/')."""
        return "--" in text or "/*" in text or "*/" in text

    @staticmethod
    def _excessive_sql_keywords(text: str) -> bool:
        """Return True if the text contains two or more SQL keywords indicating potential injection."""
        text_upper = text.upper()
        count = sum(
            1 for kw in SQLInjectionProtection.SQL_KEYWORDS if f" {kw} " in f" {text_upper} "
        )
        return count >= 2

    @staticmethod
    def _contains_sql_operator(text: str) -> bool:
        """Return True if the text contains any SQL operator
        from the predefined list.
        """
        text_upper = text.upper()
        return any(op.upper() in text_upper for op in SQLInjectionProtection.SQL_OPERATORS)

    @staticmethod
    def _matches_sql_patterns(text: str) -> bool:
        """Return True if the text matches any common SQL injection regex pattern
        or contains hex-encoded SQL patterns (e.g., starting with 0x).
        """
        if any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in SQLInjectionProtection.SQL_PATTERNS
        ):
            return True
        return bool(re.search(r"0x[0-9a-fA-F]+", text))

    @staticmethod
    def _has_string_concat_in_sql_context(text: str) -> bool:
        """Return True if the text uses string concatenation operators in a SQL context (e.g., SELECT, WHERE)."""
        if any(op in text for op in ["||", "CONCAT", "+", "CHR("]):
            text_upper = text.upper()
            return any(kw in text_upper for kw in ["SELECT", "WHERE", "AND", "OR"])
        return False

    @staticmethod
    def detect_sql_injection(text: str) -> bool:
        """Detect potential SQL injection attempts in the provided text."""
        if not text:
            return False
        if SQLInjectionProtection._has_sql_comments(text):
            return True
        if SQLInjectionProtection._excessive_sql_keywords(text):
            return True
        if SQLInjectionProtection._contains_sql_operator(text):
            return True
        if SQLInjectionProtection._matches_sql_patterns(text):
            return True
        if SQLInjectionProtection._contains_hex_encoded_sql(text):
            return True
        if SQLInjectionProtection._has_string_concat_in_sql_context(text):
            return True
        return False

    @staticmethod
    def sanitize_sql_input(text: str) -> str:
        """Sanitize input text to mitigate SQL injection by removing comments, escaping quotes, and filtering dangerous characters."""
        if not text:
            return text

        # Remove SQL comments
        text = re.sub(r"--.*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

        # Escape single quotes (double them for SQL)
        text = text.replace("'", "''")

        # Remove/escape other dangerous characters
        dangerous_chars = {
            ";": "",  # Remove semicolons
            "\\": "\\\\",  # Escape backslashes
            "\x00": "",  # Remove null bytes
            "\n": " ",  # Replace newlines with spaces
            "\r": " ",  # Replace carriage returns
            "\x1a": "",  # Remove SUB character
            '"': '""',  # Escape double quotes
        }

        for char, replacement in dangerous_chars.items():
            text = text.replace(char, replacement)

        # Remove any remaining control characters
        text = re.sub(r"[\x00-\x1f\x7f]", "", text)

        return text.strip()

    @staticmethod
    def validate_identifier(identifier: str) -> bool:
        """Validate database identifiers (table/column names)."""
        if not identifier:
            return False

        # Only allow alphanumeric and underscore
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier):
            return False

        # Check length (most DBs have limits)
        if len(identifier) > 64:
            return False

        # Check against SQL keywords
        return identifier.upper() not in SQLInjectionProtection.SQL_KEYWORDS

    @staticmethod
    def escape_like_wildcards(text: str) -> str:
        """Escape wildcards for LIKE queries."""
        if not text:
            return text

        # Escape LIKE wildcards
        text = text.replace("\\", "\\\\")  # Escape backslash first
        text = text.replace("%", "\\%")
        text = text.replace("_", "\\_")
        return text.replace("[", "\\[")

    @staticmethod
    def generate_parameterized_query(
        query_template: str, params: dict[str, Any]
    ) -> tuple[str, tuple[Any, ...]]:
        """Generate a parameterized query with placeholders."""
        # Example: Convert "SELECT * FROM users WHERE name = {name}"
        # to ("SELECT * FROM users WHERE name = ?", ['value'])

        param_values: list[Any] = []
        param_index = 1

        def replace_param(match: re.Match[str]) -> str:
            nonlocal param_index
            param_name = match.group(1)
            if param_name in params:
                param_values.append(params[param_name])
                placeholder = f"${param_index}"  # PostgreSQL style
                param_index += 1
                return placeholder
            return match.group(0)

        # Replace {param} with placeholders
        query = re.sub(r"\{(\w+)\}", replace_param, query_template)

        return query, tuple(param_values)


class SafeSQLExecutionError(Exception):
    """Raised when SafeSQL encounters execution problems."""


class SafeSQL:
    """Safe SQL query execution with parameterization."""

    @staticmethod
    def execute_query(
        connection: Any,
        query: str,
        params: tuple[Any, ...] | None = None,
        fetch_one: bool = False,
    ) -> Any:
        """Execute SQL query with parameters safely."""
        cursor = connection.cursor()

        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            if query.strip().upper().startswith(("SELECT", "SHOW", "DESC")):
                return cursor.fetchone() if fetch_one else cursor.fetchall()
            connection.commit()
            return cursor.rowcount

        except (sqlite3.Error, ValueError, TypeError) as e:
            connection.rollback()
            raise SafeSQLExecutionError(str(e)) from e
        finally:
            cursor.close()

    @staticmethod
    def build_where_clause(
        conditions: dict[str, Any], operator: str = "AND"
    ) -> tuple[str, tuple[Any, ...]]:
        """Build a safe WHERE clause from conditions."""
        if not conditions:
            return "", ()

        normalized_operator = operator.strip().upper() if operator else "AND"
        if normalized_operator not in {"AND", "OR"}:
            raise ValueError(f"Invalid logical operator: {operator}")

        clauses: list[str] = []
        params: list[Any] = []

        for field, value in conditions.items():
            # Validate field name
            if not SQLInjectionProtection.validate_identifier(field):
                raise ValueError(f"Invalid field name: {field}")

            if isinstance(value, list | tuple):
                # IN clause
                placeholders = ", ".join(["?" for _ in value])
                clauses.append(f"{field} IN ({placeholders})")
                params.extend(cast("list[Any] | tuple[Any, ...]", value))
            elif value is None:
                clauses.append(f"{field} IS NULL")
            else:
                clauses.append(f"{field} = ?")
                params.append(value)

        where_clause = f" {normalized_operator} ".join(clauses)
        return where_clause, tuple(params)
