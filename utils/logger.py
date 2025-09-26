"""
Logger utility for DinoAir
Provides centralized logging functionality

Security Note (PY-A6006):
This module configures logging which can be security-sensitive. It includes:
- Secure file permissions for log files
- Warning about potential information disclosure
- Recommendation to use structured_logging with redaction for production
"""

import importlib.util
import logging
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class Logger:
    """Centralized logging utility"""

    _instance: Optional["Logger"] = None
    _initialized: bool = False

    def __new__(cls) -> "Logger":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._validate_security_requirements()
            self.setup_logging()
            Logger._initialized = True

    def _validate_security_requirements(self) -> None:
        """Validate security requirements for logging configuration.

        Security Audit (PY-A6006): This validates that logging is configured securely.
        """
        # Check if structured logging with redaction is available
        try:
            spec = importlib.util.find_spec("utils.structured_logging")
            if spec is not None:
                # Issue security warning if using basic logging instead of secure structured logging
                warnings.warn(
                    "Using basic Logger without redaction filters. "
                    "Consider using utils.structured_logging.setup_logging() for production use "
                    "to ensure sensitive data is properly redacted from logs.",
                    UserWarning,
                    stacklevel=3,
                )
        except ImportError:
            # structured_logging not available, basic logging is acceptable
            pass

    def setup_logging(self) -> None:
        """Setup logging configuration.

        Note:
            If structured logging is already configured via
            utils.structured_logging.setup_logging(), this method will not
            reconfigure handlers. It will simply obtain the namespaced logger.

        Security Audit (PY-A6006):
            This method configures logging which can be security-sensitive.
            - Log files are created with restricted permissions (0o600)
            - Log format is designed to avoid exposing sensitive information
            - For production use, consider using utils.structured_logging.setup_logging()
              which includes proper redaction filters for sensitive data
        """
        root = logging.getLogger()
        if getattr(root, "_dinoair_structured_logging_configured", False):
            # Structured logging already set up; just obtain a namespaced logger
            self.logger = logging.getLogger("DinoAir")
            return

        # Fallback basic configuration (legacy)
        # SECURITY NOTE: This is a basic configuration without redaction filters
        # For production use, prefer utils.structured_logging.setup_logging()
        log_dir = Path(__file__).parent.parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d")
        log_file = log_dir / f"dinoair_{timestamp}.log"

        # SECURITY: Create log file with restricted permissions (read/write owner only)
        log_file.touch(mode=0o600, exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
        )

        self.logger = logging.getLogger("DinoAir")

    def _sanitize_message(self, message: str) -> str:
        """Basic sanitization of log messages to avoid exposing common secrets.

        Security Audit (PY-A6006): This provides basic protection against
        accidental logging of sensitive information.

        Note: This is basic protection. For comprehensive redaction,
        use utils.structured_logging which has proper redaction filters.
        """
        # Basic pattern matching for common secret patterns

        # Redact potential API keys, tokens, passwords
        patterns = [
            (r"\b[A-Za-z0-9]{32,}\b", "***REDACTED_TOKEN***"),  # Long alphanumeric strings
            (r"password[=:]\s*[^\s]+", "password=***REDACTED***"),  # password fields
            (r"token[=:]\s*[^\s]+", "token=***REDACTED***"),  # token fields
            (r"key[=:]\s*[^\s]+", "key=***REDACTED***"),  # key fields
            (r"secret[=:]\s*[^\s]+", "secret=***REDACTED***"),  # secret fields
        ]

        sanitized = message
        for pattern, replacement in patterns:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        return sanitized

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log info message with basic sanitization"""
        sanitized_message = self._sanitize_message(message)
        self.logger.info(sanitized_message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log warning message with basic sanitization"""
        sanitized_message = self._sanitize_message(message)
        self.logger.warning(sanitized_message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log error message with basic sanitization"""
        sanitized_message = self._sanitize_message(message)
        self.logger.error(sanitized_message, *args, **kwargs)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log debug message with basic sanitization"""
        sanitized_message = self._sanitize_message(message)
        self.logger.debug(sanitized_message, *args, **kwargs)

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log critical message with basic sanitization"""
        sanitized_message = self._sanitize_message(message)
        self.logger.critical(sanitized_message, *args, **kwargs)


# Convenience functions for direct import
def log_info(message: str) -> None:
    """Convenience wrapper for info logging."""
    Logger().info(message)


def log_warning(message: str) -> None:
    """Convenience wrapper for warning logging."""
    Logger().warning(message)


def log_error(message: str) -> None:
    """Convenience wrapper for error logging."""
    Logger().error(message)


def log_debug(message: str) -> None:
    """Convenience wrapper for debug logging."""
    Logger().debug(message)


def log_critical(message: str) -> None:
    """Convenience wrapper for critical logging."""
    Logger().critical(message)
