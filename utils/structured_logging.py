"""
Structured logging setup for DinoAir core (non-API modules).

This module configures:
- RotatingFileHandler logs/core.log (1 MB max, 5 backups)
- StreamHandler to stderr
- JSON log formatter (stdlib json)
- Redaction filter for sensitive keys/headers and DINOAIR_* env secrets

Usage:
    from utils.structured_logging import setup_logging
    setup_logging(app_name="dinoair-core", log_dir="logs", level="INFO")
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Iterable

REDACT_KEYS = {
    "authorization",
    "x-dinoair-auth",
    "auth",
    "password",
    "token",
    "access_token",
    "secret",
    "api_key",
    "apikey",
}

# Collect env-based secrets to redact (values)
_ENV_SECRET_VALUES = {v for k, v in os.environ.items() if k.upper().startswith("DINOAIR_") and v}


class RedactionFilter(logging.Filter):
    """Filter that redacts sensitive fields from log records."""

    def __init__(self, keys_to_mask: Iterable[str]) -> None:
        super().__init__()
        self.keys = {k.lower() for k in keys_to_mask}

    @staticmethod
    def _mask_value(value: Any) -> Any:
        try:
            if not value:
                return value
            # If value equals any secret env value, mask it
            if isinstance(value, str) and value in _ENV_SECRET_VALUES:
                return "***REDACTED***"
            # Mask long strings that look like secrets (heuristic)
            if isinstance(value, str) and len(value) >= 40:
                return "***REDACTED***"
            return value
        except RuntimeError:
            return "***REDACTED***"

    def _redact_mapping(self, obj: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in self.keys:
                sanitized[k] = "***REDACTED***"
            elif isinstance(v, dict):
                sanitized[k] = self._redact_mapping(cast("dict[str, Any]", v))
            elif isinstance(v, list | tuple):
                sanitized[k] = [RedactionFilter._mask_value(x) for x in cast("Iterable[Any]", v)]
            else:
                sanitized[k] = RedactionFilter._mask_value(v)
        return sanitized

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter.

        Args:
            record: TODO: Add description

        Returns:
            TODO: Add return description
        """
        try:
            # Scan known attributes often used to carry dictionaries
            for attr in ("msg",):
                val = getattr(record, attr, None)
                if isinstance(val, dict):
                    setattr(record, attr, self._redact_mapping(cast("dict[str, Any]", val)))

            # Also scan record.__dict__ extras for common names
            for k in list(record.__dict__.keys()):
                lk = str(k).lower()
                if lk in self.keys:
                    record.__dict__[k] = "***REDACTED***"
                else:
                    v = record.__dict__[k]
                    if isinstance(v, dict):
                        record.__dict__[k] = self._redact_mapping(cast("dict[str, Any]", v))
                    elif isinstance(v, list | tuple):
                        record.__dict__[k] = [
                            RedactionFilter._mask_value(x) for x in cast("Iterable[Any]", v)
                        ]
                    elif isinstance(v, str) and v in _ENV_SECRET_VALUES:
                        record.__dict__[k] = "***REDACTED***"
        except RuntimeError:
            # Never drop logs because of filter failures
            pass
        except Exception:
            # Ensure filter does not block logging on error
            return True
        return True


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter with core fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Format.

        Args:
            record: TODO: Add description

        Returns:
            TODO: Add return description
        """
        try:
            payload = {
                "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S.%fZ"),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
                "module": record.module,
                "funcName": record.funcName,
            }
            # Include optional trace id if present in extra
            trace_id = getattr(record, "trace_id", None)
            if trace_id:
                payload["trace_id"] = trace_id
            return json.dumps(payload, ensure_ascii=False)
        except RuntimeError:
            # Fallback to basic formatting on error
            return super().format(record)


def is_structured_logging_configured(logger: logging.Logger) -> bool:
    """Check if structured logging configured.

    Args:
        logger: TODO: Add description

    Returns:
        TODO: Add return description
    """
    return getattr(logger, "_dinoair_structured_logging_configured", False)


def set_structured_logging_configured(logger: logging.Logger) -> None:
    """Set structured logging configured.

    Args:
        logger: TODO: Add description

    Returns:
        TODO: Add return description
    """
    logger.configure_structured_logging()


def setup_logging(
    app_name: str = "dinoair-core", log_dir: str = "logs", level: str = "INFO"
) -> None:
    """Configure structured logging with rotation and redaction.

    Args:
        app_name: Name used for top-level logger.
        log_dir: Directory where logs will be stored.
        level: Logging level string ("DEBUG", "INFO", "WARNING", "ERROR").
    """
    # Ensure idempotency: configure root only once
    root = logging.getLogger()
    if is_structured_logging_configured(root):
        return

    # Create log directory
    base_dir = Path(__file__).resolve().parents[2]  # project root
    logs_path = base_dir / log_dir
    logs_path.mkdir(parents=True, exist_ok=True)

    # Handlers
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(logs_path / "core.log"),
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    stream_handler = logging.StreamHandler(stream=sys.stderr)

    # Formatter
    formatter = JsonFormatter()
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    # Redaction filter
    redactor = RedactionFilter(REDACT_KEYS)
    file_handler.addFilter(redactor)
    stream_handler.addFilter(redactor)

    # Root logger setup
    lvl = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(lvl)
    root.handlers = [file_handler, stream_handler]

    # Mark configured
    set_structured_logging_configured(root)

    # Create a namespaced logger for the app (optional convenience)
    app_logger = logging.getLogger(app_name)
    app_logger.propagate = True
    app_logger.debug("Structured logging configured")
