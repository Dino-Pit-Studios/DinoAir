"""
NotesSecurity - Security validation for notes operations.
Handles input validation, sanitization, and security checks.
"""

import os
from abc import ABC, abstractmethod
from typing import Any

from utils.logger import Logger


class SecurityPolicy(ABC):
    """Abstract base class for security policies"""

    @abstractmethod
    def validate_note_data(self, title: str, content: str, tags: list[str]) -> dict[str, Any]:
        """Validate note data and return validation result"""

    @abstractmethod
    def escape_sql_wildcards(self, text: str) -> str:
        """Escape SQL wildcard characters for safe queries"""


class NotesSecurity:
    """
    Security manager for notes operations.
    Handles validation, sanitization, and security policy enforcement.
    """

    def __init__(self):
        self.logger = Logger()
        self._policy: SecurityPolicy = self._load_security_policy()

    def _load_security_policy(self) -> SecurityPolicy:
        """Load the appropriate security policy"""
        try:
            from gui.components.notes_security import get_notes_security

            self.logger.debug("Successfully loaded notes_security module")
            return get_notes_security()
        except ImportError as e:
            # Fallback to conservative security
            self.logger.error(
                f"notes_security module import failed: {e}. Using conservative fallback."
            )

            # Check if strict mode is enabled
            strict = os.environ.get("STRICT_NOTES_SECURITY", "").strip().lower() in (
                "1",
                "true",
                "yes",
            )

            if strict:
                self.logger.critical(
                    "STRICT_NOTES_SECURITY enabled and notes_security is unavailable. Aborting."
                )
                raise RuntimeError(
                    "Notes security module not available and STRICT_NOTES_SECURITY is enabled."
                ) from e

            # Use fallback security
            self.logger.warning("Using FallbackSecurity for notes validation.")
            return FallbackSecurity()

    def validate_note_data(self, title: str, content: str, tags: list[str]) -> dict[str, Any]:
        """Validate note data using the current security policy"""
        return self._policy.validate_note_data(title, content, tags)

    def escape_sql_wildcards(self, text: str) -> str:
        """Escape SQL wildcards using the current security policy"""
        return self._policy.escape_sql_wildcards(text)

    def can_perform_write_operation(self, operation: str) -> tuple[bool, str | None]:
        """
        Check if write operations are allowed.
        Returns (allowed, error_message)
        """
        # If using fallback security, check environment variable
        if isinstance(self._policy, FallbackSecurity):
            allow = os.environ.get("ALLOW_NOTES_FALLBACK_WRITES", "").strip().lower() in (
                "1",
                "true",
                "yes",
            )

            if not allow:
                error_msg = (
                    f"Write operation '{operation}' blocked: notes_security unavailable. "
                    "Set ALLOW_NOTES_FALLBACK_WRITES=1 to override in non-production."
                )
                self.logger.critical(error_msg)
                return False, "Security module unavailable; write operation blocked"
            self.logger.warning(
                f"Proceeding with '{operation}' under FallbackSecurity. "
                "Not recommended for production."
            )

        return True, None


class FallbackSecurity(SecurityPolicy):
    """
    Conservative fallback security policy.
    Provides basic validation when the main security module is unavailable.
    """

    def validate_note_data(self, title: str, content: str, tags: list[str]) -> dict[str, Any]:
        """Perform basic validation with conservative rules"""
        errors: list[str] = []

        # Title validation
        if not isinstance(title, str) or not title.strip():
            errors.append("Title is required.")
        elif len(title) > 300:
            errors.append("Title exceeds 300 characters.")

        # Content validation (allow empty but cap size)
        if content is None:
            content_len = 0
        elif isinstance(content, str):
            content_len = len(content)
        else:
            errors.append("Content must be a string.")
            content_len = 0

        if content_len > 20000:
            errors.append("Content exceeds 20000 characters.")

        # Tags validation
        if tags is None:
            tags = []
        if not isinstance(tags, list):
            errors.append("Tags must be a list of strings.")
        else:
            if len(tags) > 100:
                errors.append("Too many tags (max 100).")
            for tag in tags:
                if not isinstance(tag, str):
                    errors.append("All tags must be strings.")
                elif len(tag) > 50:
                    errors.append("Tag length exceeds 50 characters.")

        return {"valid": len(errors) == 0, "errors": errors}

    def escape_sql_wildcards(self, text: str) -> str:
        """Escape SQL wildcard characters for LIKE queries"""
        if not text:
            return ""

        # Escape backslashes first, then other wildcards
        return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
