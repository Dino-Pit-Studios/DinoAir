from __future__ import annotations

import contextlib
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING, Any, TypeVar, cast

from starlette.types import Message, Receive, Scope, Send

if TYPE_CHECKING:
    from .settings import Settings

try:
    # type: ignore[attr-defined]
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # pragma: no cover
    from pythonjsonlogger.jsonlogger import JsonFormatter  # type: ignore[misc]

# Local alias to avoid linter/editor false positives on starlette.types.ASGIApp
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

T = TypeVar("T")

# Type definitions for better type safety (aligned with core_router and routing schemas)
JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | dict[str, "JSONValue"] | list["JSONValue"]
LogStructure = dict[str, JSONValue] | list[JSONValue] | tuple[JSONValue, ...]
JSONLike = str | LogStructure


@dataclass(frozen=True)
class RedactionConfig:
    """Configuration constants for redaction operations."""

    redacted_placeholder: str = "***"
    auth_header_lower: str = "x-dinoair-auth"
    auth_header_mixed: str = "X-DinoAir-Auth"
    sensitive_field_names: frozenset[str] = field(
        default_factory=lambda: frozenset(["headers", "extra", "data"])
    )
    structured_log_fields: tuple[str, ...] = field(
        default_factory=lambda: (
            "status",
            "route",
            "path",
            "method",
            "trace_id",
            "duration_ms",
            "bytes_in",
            "bytes_out",
        )
    )


class RedactionService:
    """Service responsible for redacting sensitive information from log data."""

    def __init__(self, auth_token: str | None, config: RedactionConfig) -> None:
        """Initialize the redaction service.

        Args:
            auth_token: The authentication token to redact, if any
            config: Configuration for redaction behavior
        """
        self.config = config
        self.secrets = [s for s in [auth_token] if s]

    def redact_text(self, text: str) -> str:
        """Redact sensitive information from text strings.

        Args:
            text: The text to redact

        Returns:
            Text with sensitive information redacted
        """
        redacted = text

        # Redact explicit secrets
        for secret in self.secrets:
            if secret and secret in redacted:
                redacted = redacted.replace(secret, self.config.redacted_placeholder)

        # Apply pattern-based redaction
        redacted = self._redact_json_auth_header(redacted)
        return self._redact_plain_auth_header(redacted)

    def redact_value(self, value: T) -> T:
        """Recursively redact values in various data structures.

        Args:
            value: The value to redact

        Returns:
            The value with sensitive information redacted
        """
        if isinstance(value, str):
            return cast("T", self.redact_text(value))

        if isinstance(value, dict):
            return cast("T", self._redact_dict(cast("dict[str, JSONValue]", value)))

        if isinstance(value, list):
            return cast("T", self._redact_list(cast("list[JSONValue]", value)))

        if isinstance(value, tuple):
            return cast("T", self._redact_tuple(cast("tuple[JSONValue, ...]", value)))

        return value

    def redact_structure(self, obj: JSONLike) -> JSONLike:
        """Redact structured data (dict, list, tuple, or string).

        Args:
            obj: The structured object to redact

        Returns:
            The object with sensitive information redacted
        """
        with contextlib.suppress(Exception):
            return self._redact_by_type(obj)
        return obj

    def _redact_by_type(self, obj: JSONLike) -> JSONLike:
        """Redact object based on its type.

        Args:
            obj: The object to redact

        Returns:
            The redacted object
        """
        if isinstance(obj, dict):
            return self._redact_dict(cast("dict[str, JSONValue]", obj))
        if isinstance(obj, list):
            return self._redact_list(cast("list[JSONValue]", obj))
        if isinstance(obj, tuple):
            return self._redact_tuple(cast("tuple[JSONValue, ...]", obj))
        return self.redact_text(str(obj))

    def _redact_dict(self, obj: dict[str, JSONValue]) -> dict[str, JSONValue]:
        """Redact dictionary values, with special handling for auth headers."""
        redacted_dict: dict[str, JSONValue] = {
            k: (
                self.config.redacted_placeholder
                if isinstance(k, str) and k.lower() == self.config.auth_header_lower
                else self.redact_value(v)
            )
            for k, v in obj.items()
        }
        return redacted_dict

    def _redact_list(self, obj: list[JSONValue]) -> list[JSONValue]:
        """Redact list values."""
        return [self.redact_value(v) for v in obj]

    def _redact_tuple(self, obj: tuple[JSONValue, ...]) -> tuple[JSONValue, ...]:
        """Redact tuple values."""
        return tuple(self.redact_value(v) for v in obj)

    def _redact_json_auth_header(self, text: str) -> str:
        """Redact JSON-style auth headers like "x-dinoair-auth":"value"."""
        with contextlib.suppress(Exception):
            return self._replace_auth_pattern(
                text,
                f'"{self.config.auth_header_lower}"',
                ":",
                '"',
            )
        return text

    def _redact_plain_auth_header(self, text: str) -> str:
        """Redact plain auth headers like X-DinoAir-Auth: value."""
        with contextlib.suppress(Exception):
            return self._replace_auth_pattern(
                text,
                self.config.auth_header_mixed,
                ":",
            )
        return text

    def _replace_auth_pattern(
        self, text: str, key: str, sep: str, terminator: str | None = None
    ) -> str:
        """Replace authentication patterns in text.

        Args:
            text: The text to search in
            key: The key to search for
            sep: The separator after the key
            terminator: The terminating character (None for comma/EOL)

        Returns:
            Text with the authentication pattern replaced
        """
        key_idx = text.find(key)
        if key_idx == -1:
            return text

        sep_idx = text.find(sep, key_idx + len(key))
        if sep_idx == -1:
            return text

        start = sep_idx + len(sep)
        end = self._find_pattern_end(text, start, terminator)

        # Skip leading whitespace
        while start < len(text) and text[start] == " ":
            start += 1

        return text[:start] + self.config.redacted_placeholder + text[end:]

    @staticmethod
    def _find_pattern_end(text: str, start: int, terminator: str | None) -> int:
        """Find the end position of a pattern to redact.

        Args:
            text: The text to search in
            start: Starting position
            terminator: The terminating character

        Returns:
            End position of the pattern
        """
        if terminator:
            end = text.find(terminator, start)
            return end if end != -1 else len(text)

        comma = text.find(",", start)
        return comma if comma != -1 else len(text)


class RedactionFilter(logging.Filter):
    """Logging filter that redacts sensitive values from log records."""

    def __init__(self, auth_token: str | None) -> None:
        """Initialize the redaction filter.

        Args:
            auth_token: The authentication token to redact
        """
        super().__init__()
        self.config = RedactionConfig()
        self.redaction_service = RedactionService(auth_token, self.config)

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter and redact sensitive information from log records.

        Args:
            record: The log record to filter

        Returns:
            Always True (record is processed but not filtered out)
        """
        self._redact_message(record)
        self._redact_args(record)
        self._redact_extra_fields(record)
        return True

    def _redact_message(self, record: logging.LogRecord) -> None:
        """Redact the main log message."""
        with contextlib.suppress(Exception):
            if isinstance(record.msg, str):
                record.msg = self.redaction_service.redact_text(record.msg)

    def _redact_args(self, record: logging.LogRecord) -> None:
        """Redact log record arguments."""
        with contextlib.suppress(Exception):
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: self.redaction_service.redact_value(v) for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(self.redaction_service.redact_value(a) for a in record.args)

    def _redact_extra_fields(self, record: logging.LogRecord) -> None:
        """Redact sensitive extra fields in log records."""
        with contextlib.suppress(Exception):
            for key in record.__dict__:
                if key in self.config.sensitive_field_names:
                    record.__dict__[key] = self.redaction_service.redact_structure(
                        record.__dict__[key]
                    )
                elif isinstance(record.__dict__[key], str):
                    record.__dict__[key] = self.redaction_service.redact_text(record.__dict__[key])


class ISOFormatter(JsonFormatter):
    """JSON formatter that outputs ISO8601 timestamp and selected fields."""

    def __init__(self, config: RedactionConfig) -> None:
        """Initialize the ISO formatter.

        Args:
            config: Configuration for field handling
        """
        super().__init__(fmt="%(message)s")  # type: ignore[call-arg]
        self.config = config

    def add_fields(
        self,
        log_record: dict[str, JSONValue],
        record: logging.LogRecord,
        message_dict: dict[str, JSONValue],
    ) -> None:
        """Add fields to the log record.

        Args:
            log_record: The log record dictionary to modify
            record: The original logging record
            message_dict: Additional message data
        """
        super().add_fields(log_record, record, message_dict)

        self._add_timestamp(log_record)
        self._normalize_level(log_record, record)
        self._add_logger_name(log_record, record)
        self._copy_structured_fields(log_record, record, message_dict)

    @staticmethod
    def _add_timestamp(log_record: dict[str, JSONValue]) -> None:
        """Add ISO8601 timestamp if not present."""
        if "ts" not in log_record:
            log_record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    @staticmethod
    def _normalize_level(log_record: dict[str, JSONValue], record: logging.LogRecord) -> None:
        """Normalize the log level to lowercase."""
        lvl = (
            log_record.get("level")
            or getattr(record, "levelname", None)
            or logging.getLevelName(getattr(record, "levelno", 0))
            or "INFO"
        )

        with contextlib.suppress(Exception):
            log_record["level"] = str(lvl).lower()

        if "level" not in log_record:
            log_record["level"] = "info"

    @staticmethod
    def _add_logger_name(log_record: dict[str, JSONValue], record: logging.LogRecord) -> None:
        """Add logger name to the record."""
        log_record["logger"] = record.name

    def _copy_structured_fields(
        self,
        log_record: dict[str, JSONValue],
        record: logging.LogRecord,
        message_dict: dict[str, JSONValue],
    ) -> None:
        """Copy structured fields from various sources."""
        with contextlib.suppress(Exception):
            self._copy_configured_fields(log_record, record, message_dict)
            self._mirror_path_to_route(log_record)

    def _copy_configured_fields(
        self,
        log_record: dict[str, JSONValue],
        record: logging.LogRecord,
        message_dict: dict[str, JSONValue],
    ) -> None:
        """Copy configured structured fields."""
        for field_name in self.config.structured_log_fields:
            value = self._get_field_value(field_name, message_dict, log_record, record)
            if value is not None:
                log_record[field_name] = value

    @staticmethod
    def _mirror_path_to_route(log_record: dict[str, JSONValue]) -> None:
        """Mirror path to route for stability."""
        if "route" not in log_record and "path" in log_record:
            log_record["route"] = log_record.get("path")

    @staticmethod
    def _get_field_value(
        field_name: str,
        message_dict: dict[str, JSONValue],
        log_record: dict[str, JSONValue],
        record: logging.LogRecord,
    ) -> JSONValue:
        """Get field value from various sources in priority order."""
        return (
            message_dict.get(field_name)
            or log_record.get(field_name)
            or getattr(record, field_name, None)
        )


def ensure_log_dir(path: str) -> None:
    """Ensure the log directory exists.

    Args:
        path: Path to the log directory
    """
    with contextlib.suppress(Exception):
        os.makedirs(path, exist_ok=True)


@dataclass(frozen=True)
class HandlerConfig:
    """Configuration for logging handlers."""

    level: int
    formatter: logging.Formatter
    redactor: logging.Filter


class LoggingFactory:
    """Factory for creating logging components."""

    @staticmethod
    def create_redaction_filter(settings: Settings) -> RedactionFilter:
        """Create a redaction filter from settings.

        Args:
            settings: Application settings

        Returns:
            Configured redaction filter
        """
        return RedactionFilter(settings.auth_token)

    @staticmethod
    def create_formatter() -> ISOFormatter:
        """Create an ISO formatter.

        Returns:
            Configured ISO formatter
        """
        return ISOFormatter(RedactionConfig())

    @staticmethod
    def create_stream_handler(config: HandlerConfig) -> logging.StreamHandler[Any]:
        """Create a stream handler.

        Args:
            config: Handler configuration

        Returns:
            Configured stream handler
        """
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setLevel(config.level)
        handler.setFormatter(config.formatter)
        handler.addFilter(config.redactor)
        return handler

    @staticmethod
    def create_file_handler(logfile: str, config: HandlerConfig) -> RotatingFileHandler:
        """Create a rotating file handler.

        Args:
            logfile: Path to log file
            config: Handler configuration

        Returns:
            Configured file handler
        """
        handler = RotatingFileHandler(
            logfile,
            maxBytes=1_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setLevel(config.level)
        handler.setFormatter(config.formatter)
        handler.addFilter(config.redactor)
        return handler


def setup_logging(settings: Settings) -> None:
    """Configure structured JSON logging with redaction.

    Sets up:
    - StreamHandler (stderr)
    - RotatingFileHandler (logs/api.log)
    - Redaction of secrets

    Args:
        settings: Application settings
    """
    _prepare_logging_environment(settings)
    _configure_root_logger(settings)


def _prepare_logging_environment(settings: Settings) -> None:
    """Prepare the logging environment by creating necessary directories.

    Args:
        settings: Application settings
    """
    ensure_log_dir(settings.log_dir)


def _configure_root_logger(settings: Settings) -> None:
    """Configure the root logger with handlers and formatting.

    Args:
        settings: Application settings
    """
    logfile = os.path.join(settings.log_dir, "api.log")
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers to avoid duplication
    _clear_existing_handlers(root_logger)

    # Create and add handlers
    _add_logging_handlers(root_logger, logfile, level, settings)


def _add_logging_handlers(
    logger: logging.Logger, logfile: str, level: int, settings: Settings
) -> None:
    """Add stream and file handlers to the logger.

    Args:
        logger: The logger to configure
        logfile: Path to the log file
        level: Logging level
        settings: Application settings
    """
    factory = LoggingFactory()
    formatter = factory.create_formatter()
    redactor = factory.create_redaction_filter(settings)

    config = HandlerConfig(level=level, formatter=formatter, redactor=redactor)

    stream_handler = factory.create_stream_handler(config)
    file_handler = factory.create_file_handler(logfile, config)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)


def _clear_existing_handlers(logger: logging.Logger) -> None:
    """Clear existing handlers from a logger.

    Args:
        logger: The logger to clear handlers from
    """
    for handler in logger.handlers[:]:  # Create a copy to avoid modification during iteration
        logger.removeHandler(handler)
        with contextlib.suppress(Exception):
            handler.close()


class RequestResponseLoggerMiddleware:
    """ASGI middleware that logs request/response information."""

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application to wrap
        """
        self.app = app
        self.log = logging.getLogger("api.requests")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process HTTP requests and log information.

        Args:
            scope: ASGI scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        await self._process_http_request(scope, receive, send)

    async def _process_http_request(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process an HTTP request and handle logging.

        Args:
            scope: ASGI scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        start_ns = time.perf_counter_ns()
        status_holder: dict[str, int | None] = {"status": None}
        send_wrapper = RequestResponseLoggerMiddleware._create_send_wrapper(send, status_holder)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            self._log_request_info(scope, start_ns, status_holder["status"])

    @staticmethod
    def _create_send_wrapper(send: Send, status_holder: dict[str, int | None]) -> Send:
        """Create a send wrapper that captures status codes.

        Args:
            send: Original send callable
            status_holder: Dictionary to store status code

        Returns:
            Wrapped send callable
        """

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                status_holder["status"] = int(message.get("status", 0))
            await send(message)

        return send_wrapper

    def _log_request_info(self, scope: Scope, start_ns: int, status: int | None) -> None:
        """Log request information.

        Args:
            scope: ASGI scope
            start_ns: Request start time in nanoseconds
            status: HTTP status code
        """
        end_ns = time.perf_counter_ns()
        duration_ms = (end_ns - start_ns) / 1_000_000.0

        trace_obj = scope.get("trace_id", "")
        trace_id: str = trace_obj if isinstance(trace_obj, str) else ""

        self.log.info(
            "request",
            extra={
                "trace_id": trace_id,
                "path": scope.get("path", ""),
                "method": scope.get("method", ""),
                "status": status or 0,
                "duration_ms": round(duration_ms, 3),
            },
        )
