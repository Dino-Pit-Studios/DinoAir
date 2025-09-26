"""
Enhanced logging system with advanced features for DinoAir

This module provides:
- Custom log levels (TRACE, VERBOSE) beyond standard Python levels
- Contextual logging with correlation IDs
- Structured logging improvements
- Performance-aware logging
- Configuration-based log routing
- Async logging capabilities
- Log filtering and sampling
- Thread-safe operations
"""

import json
import logging
import logging.handlers
import queue
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

# Custom log levels
TRACE_LEVEL = 5
VERBOSE_LEVEL = 15

# Add custom levels to logging module
logging.addLevelName(TRACE_LEVEL, "TRACE")
logging.addLevelName(VERBOSE_LEVEL, "VERBOSE")


def trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Log 'message % args' with severity 'TRACE'."""
    if self.isEnabledFor(TRACE_LEVEL):
        self.log(TRACE_LEVEL, message, *args, **kwargs)


def verbose(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Log 'message % args' with severity 'VERBOSE'."""
    if self.isEnabledFor(VERBOSE_LEVEL):
        self.log(VERBOSE_LEVEL, message, *args, **kwargs)


# Monkey patch Logger class to add custom methods
logging.Logger.trace = trace
logging.Logger.verbose = verbose


@dataclass
class LogContext:
    """Context information for logging operations."""

    correlation_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    operation_id: str | None = None
    component: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for logging."""
        result: dict[str, Any] = {}
        if self.correlation_id:
            result["correlation_id"] = self.correlation_id
        if self.user_id:
            result["user_id"] = self.user_id
        if self.session_id:
            result["session_id"] = self.session_id
        if self.operation_id:
            result["operation_id"] = self.operation_id
        if self.component:
            result["component"] = self.component
        result.update(self.metadata)
        return result


class LogContextManager:
    """Thread-local storage for log context."""

    def __init__(self):
        self._local = threading.local()

    def get_context(self) -> LogContext:
        """Get current log context."""
        if not hasattr(self._local, "context"):
            self._local.context = LogContext()
        return self._local.context

    def set_context(self, context: LogContext):
        """Set current log context."""
        self._local.context = context

    def update_context(self, **kwargs: Any) -> None:
        """Update current log context."""
        context = self.get_context()
        for key, value in kwargs.items():
            if hasattr(context, key):
                setattr(context, key, value)
            else:
                context.metadata[key] = value

    def clear_context(self):
        """Clear current log context."""
        if hasattr(self._local, "context"):
            delattr(self._local, "context")


# Global context manager
_context_manager = LogContextManager()


@dataclass
class LogFilterConfig:
    """Configuration for log filtering."""

    enabled: bool = True
    level_filters: dict[str, int] = field(default_factory=dict)  # module -> level
    sampling_rate: float = 1.0  # 1.0 = 100% sampling
    exclude_patterns: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)


class EnhancedLogFilter(logging.Filter):
    """Advanced log filter with sampling and pattern matching."""

    def __init__(self, config: LogFilterConfig):
        super().__init__()
        self.config = config
        self._sample_counter = 0

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter.

        Args:
            record: TODO: Add description

        Returns:
            TODO: Add return description
        """
        if not self.config.enabled:
            return True

        # Check level filters
        module_level = self.config.level_filters.get(record.name)
        if module_level is not None and record.levelno < module_level:
            return False

        # Check exclude patterns
        for pattern in self.config.exclude_patterns:
            if pattern in record.getMessage():
                return False

        # Check include patterns (if specified, only include matching)
        if self.config.include_patterns:
            for pattern in self.config.include_patterns:
                if pattern in record.getMessage():
                    break
            else:
                return False

        # Apply sampling
        if self.config.sampling_rate < 1.0:
            self._sample_counter += 1
            if self._sample_counter % int(1.0 / self.config.sampling_rate) != 0:
                return False

        return True


@dataclass
class FormatterConfig:
    """Configuration for log formatters."""

    format_type: str = "json"  # json, text, custom
    include_timestamp: bool = True
    include_level: bool = True
    include_logger: bool = True
    include_module: bool = True
    include_function: bool = True
    include_context: bool = True
    custom_format: str | None = None
    date_format: str = "%Y-%m-%dT%H:%M:%S.%fZ"


class EnhancedJsonFormatter(logging.Formatter):
    """Enhanced JSON formatter with context support."""

    def __init__(self, config: FormatterConfig):
        """Initialize the EnhancedJsonFormatter with the given configuration.

        Args:
            config (FormatterConfig): Configuration for formatting options.
        """
        super().__init__()
        self.config = config

    def format(self, record: logging.LogRecord) -> str:
        """Format a LogRecord into a JSON string including standard, context, exception, and extra fields.

        Args:
            record (logging.LogRecord): The log record to format.

        Returns:
            str: A JSON string representation of the log record.
        """
        # Get current context
        context = _context_manager.get_context()

        # Build log entry
        log_entry = {}
        self._add_standard_fields(record, log_entry)
        log_entry["message"] = record.getMessage()

        # Add context information
        self._add_context(context, log_entry)

        # Add exception info if present
        self._add_exception_info(record, log_entry)

        # Add any extra fields from record
        self._add_extra_fields(record, log_entry)

        return json.dumps(log_entry, ensure_ascii=False, default=str)

    def _add_standard_fields(self, record: logging.LogRecord, log_entry: dict) -> None:
        """Add standard log fields to the log entry based on formatter configuration.

        Args:
            record (logging.LogRecord): The log record to extract fields from.
            log_entry (dict): The dictionary to populate with standard fields.
        """
        fields = [
            (
                "include_timestamp",
                "timestamp",
                lambda rec: self.formatTime(rec, self.config.date_format),
            ),
            ("include_level", "level", lambda rec: rec.levelname),
            ("include_logger", "logger", lambda rec: rec.name),
            ("include_module", "module", lambda rec: rec.module),
            ("include_function", "function", lambda rec: rec.funcName),
        ]
        for config_attr, key, func in fields:
            if getattr(self.config, config_attr):
                log_entry[key] = func(record)

    def _add_context(self, context: Any, log_entry: dict) -> None:
        """Add context information to the log entry if enabled and present.

        Args:
            context (Any): The context object containing contextual data.
            log_entry (dict): The dictionary to populate with context data.
        """
        if self.config.include_context:
            context_dict = context.to_dict()
            if context_dict:
                log_entry["context"] = context_dict

    def _add_exception_info(self, record: logging.LogRecord, log_entry: dict) -> None:
        """Add exception information to the log entry if present in the record.

        Args:
            record (logging.LogRecord): The log record that may contain exception info.
            log_entry (dict): The dictionary to populate with exception details.
        """
        if not record.exc_info:
            return
        if record.exc_info is True:
            import sys

            exc_info = sys.exc_info()
            if exc_info and exc_info[0] is not None:
                log_entry["exception"] = self.formatException(exc_info)
        elif isinstance(record.exc_info, tuple) and len(record.exc_info) == 3:
            log_entry["exception"] = self.formatException(record.exc_info)

    @staticmethod
    def _add_extra_fields(record: logging.LogRecord, log_entry: dict) -> None:
        """Add any additional fields from the log record to the log entry,
        excluding standard attributes.

        Args:
            record (logging.LogRecord): The log record to extract extra fields from.
            log_entry (dict): The dictionary to populate with extra fields.
        """
        excluded = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "getMessage",
        }
        for key, value in record.__dict__.items():
            if key not in excluded:
                log_entry[key] = value


class AsyncLogHandler(logging.Handler):
    """Asynchronous log handler for improved performance."""

    def __init__(self, handler: logging.Handler, queue_size: int = 1000):
        super().__init__()
        self.handler = handler
        self.queue: queue.Queue[logging.LogRecord] = queue.Queue(maxsize=queue_size)
        self._shutdown_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()

    def emit(self, record: logging.LogRecord):
        """Emit log record asynchronously."""
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            # If queue is full, log synchronously as fallback
            self.handler.emit(record)

    def _process_queue(self) -> None:
        """Process log records from queue."""
        while not self._shutdown_event.is_set():
            try:
                record = self.queue.get(timeout=1.0)
                self.handler.emit(record)
                self.queue.task_done()
            except queue.Empty:
                continue
            except (OSError, RuntimeError, ValueError):
                # Log the error to stderr and continue
                pass
            except Exception:
                # Catch any other exceptions to prevent thread from dying silently
                pass

    def close(self):
        """Close handler and cleanup."""
        self._shutdown_event.set()
        self._worker_thread.join(timeout=5.0)
        self.handler.close()
        super().close()


@dataclass
class LogConfig:
    """Configuration for enhanced logging system."""

    level: str = "WARNING"
    format_type: str = "json"
    log_dir: str = "logs"
    max_file_size: int = 10_000_000  # 10MB
    backup_count: int = 5
    async_logging: bool = True
    async_queue_size: int = 1000
    filter_config: LogFilterConfig = field(default_factory=LogFilterConfig)
    formatter_config: FormatterConfig = field(default_factory=FormatterConfig)


class EnhancedLogger:
    """Enhanced logging system with advanced features."""

    _instance: Optional["EnhancedLogger"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "EnhancedLogger":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self.config = LogConfig()
        self._loggers: dict[str, logging.Logger] = {}
        self._handlers: list[logging.Handler] = []
        self._lock = threading.RLock()

    def configure(self, config: LogConfig):
        """Configure the enhanced logging system."""
        with self._lock:
            self.config = config
            self._setup_logging()

    def _setup_logging(self):
        """Setup logging with current configuration."""
        # Clear existing handlers
        root = logging.getLogger()
        for handler in self._handlers:
            root.removeHandler(handler)
        self._handlers.clear()

        # Set root level
        level = getattr(logging, self.config.level.upper(), logging.INFO)
        root.setLevel(level)

        # Create log directory
        log_dir = Path(self.config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create formatter
        if self.config.formatter_config.format_type == "json":
            formatter = EnhancedJsonFormatter(self.config.formatter_config)
        else:
            formatter = logging.Formatter(
                self.config.formatter_config.custom_format
                or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        # Create file handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_dir / "enhanced.log",
            maxBytes=self.config.max_file_size,
            backupCount=self.config.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        # Add filter
        filter_obj = EnhancedLogFilter(self.config.filter_config)
        file_handler.addFilter(filter_obj)
        console_handler.addFilter(filter_obj)

        # Wrap in async handler if enabled
        if self.config.async_logging:
            file_handler = AsyncLogHandler(file_handler, self.config.async_queue_size)
            console_handler = AsyncLogHandler(console_handler, self.config.async_queue_size)

        # Add handlers
        root.addHandler(file_handler)
        root.addHandler(console_handler)
        self._handlers.extend([file_handler, console_handler])

    def get_logger(self, name: str) -> logging.Logger:
        """Get or create a logger with the given name."""
        with self._lock:
            if name not in self._loggers:
                logger = logging.getLogger(name)
                self._loggers[name] = logger
            return self._loggers[name]

    def set_level(self, level: str, logger_name: str | None = None):
        """Set log level dynamically."""
        with self._lock:
            level_value = getattr(logging, level.upper(), logging.INFO)
            if logger_name:
                logger = self.get_logger(logger_name)
                logger.setLevel(level_value)
            else:
                logging.getLogger().setLevel(level_value)

    def update_filter_config(self, **kwargs: Any) -> None:
        """Update filter configuration dynamically."""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.config.filter_config, key):
                    setattr(self.config.filter_config, key, value)
            self._setup_logging()  # Reconfigure with new filter

    def update_config(self, **kwargs: Any) -> None:
        """Update logging configuration dynamically."""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
            self._setup_logging()  # Reconfigure with new settings

    def set_module_level(self, module_name: str, level: str):
        """Set log level for a specific module."""
        with self._lock:
            level_value = getattr(logging, level.upper(), logging.INFO)
            self.config.filter_config.level_filters[module_name] = level_value
            self._setup_logging()  # Reconfigure with new module level

    def remove_module_level(self, module_name: str):
        """Remove custom log level for a specific module."""
        with self._lock:
            self.config.filter_config.level_filters.pop(module_name, None)
            self._setup_logging()  # Reconfigure without module level

    def get_module_levels(self) -> dict[str, str]:
        """Get current module-specific log levels."""
        # Use logging's built-in level names mapping
        return {
            module: logging.getLevelName(level)
            for module, level in self.config.filter_config.level_filters.items()
        }

    def shutdown(self):
        """Shutdown the logging system."""
        with self._lock:
            for handler in self._handlers:
                handler.close()
            self._handlers.clear()


# Global enhanced logger instance
_enhanced_logger = EnhancedLogger()


# Context management functions
def get_log_context() -> LogContext:
    """Get current log context."""
    return _context_manager.get_context()


def set_log_context(context: LogContext):
    """Set current log context."""
    _context_manager.set_context(context)


def update_log_context(**kwargs: Any) -> None:
    """Update current log context."""
    _context_manager.update_context(**kwargs)


def clear_log_context():
    """Clear current log context."""
    _context_manager.clear_context()


@contextmanager
def log_context(**kwargs: Any):
    """Context manager for temporary log context."""
    old_context = get_log_context()
    # Create new context with only valid fields
    valid_fields = {
        "correlation_id",
        "user_id",
        "session_id",
        "operation_id",
        "component",
    }
    context_args = {k: v for k, v in kwargs.items() if k in valid_fields}
    metadata = {k: v for k, v in kwargs.items() if k not in valid_fields}
    new_context = LogContext(**context_args, metadata=metadata)
    set_log_context(new_context)
    try:
        yield
    finally:
        set_log_context(old_context)


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return str(uuid4())


# Convenience functions
def get_logger(name: str) -> logging.Logger:
    """Get enhanced logger instance."""
    return _enhanced_logger.get_logger(name)


def configure_logging(config: LogConfig):
    """Configure the enhanced logging system."""
    _enhanced_logger.configure(config)


def set_log_level(level: str, logger_name: str | None = None):
    """Set log level dynamically."""
    _enhanced_logger.set_level(level, logger_name)


# Integration with existing systems
def integrate_with_performance_monitor() -> None:
    """Integrate logging with performance monitoring."""
    # This will be called during setup to connect the systems
    # Implementation will be added when performance monitor is available
    return


def integrate_with_error_handling() -> None:
    """Integrate logging with error handling."""
    # This will be called during setup to connect the systems
    # Implementation will be added when error handler is available
    return


@dataclass
class LogAggregationConfig:
    """Configuration for log aggregation."""

    time_window_seconds: int = 300  # 5 minutes
    max_entries: int = 10000
    aggregation_fields: list[str] = field(default_factory=lambda: ["level", "logger", "component"])
    enable_pattern_analysis: bool = True
    enable_error_rate_tracking: bool = True


class LogAggregator:
    """Aggregates and analyzes log entries for insights."""

    def __init__(self, config: LogAggregationConfig | None = None):
        self.config = config or LogAggregationConfig()
        self._entries: deque[dict[str, Any]] = deque(maxlen=self.config.max_entries)
        self._lock = threading.RLock()
        self._start_time = time.time()

    @staticmethod
    def _count_by_field(entries: list[dict[str, Any]], field_name: str) -> dict[str, int]:
        """Count entries by a specific field value."""
        counts: dict[str, int] = {}
        for entry in entries:
            value = entry.get(field_name, "unknown")
            counts[value] = counts.get(value, 0) + 1
        return counts

    def add_entry(self, entry: dict[str, Any]):
        """Add a log entry to the aggregator."""
        with self._lock:
            self._entries.append(
                {
                    "timestamp": entry.get("timestamp", time.time()),
                    "level": entry.get("level", "UNKNOWN"),
                    "logger": entry.get("logger", "unknown"),
                    "message": entry.get("message", ""),
                    "component": entry.get("context", {}).get("component", "unknown"),
                    "correlation_id": entry.get("context", {}).get("correlation_id"),
                    "operation": entry.get("context", {}).get("operation"),
                    "error_type": entry.get("context", {}).get("error_type"),
                    **entry,
                }
            )

    def get_summary(self, time_window_seconds: int | None = None) -> dict[str, Any]:
        """Get aggregated summary of log entries."""
        window = time_window_seconds or self.config.time_window_seconds
        cutoff_time = time.time() - window

        with self._lock:
            recent_entries = [e for e in self._entries if e["timestamp"] > cutoff_time]

            summary: dict[str, Any] = {
                "total_entries": len(recent_entries),
                "time_window_seconds": window,
                "start_time": self._start_time,
                "current_time": time.time(),
            }

            if recent_entries:
                # Level distribution
                summary["level_distribution"] = self._count_by_field(recent_entries, "level")

                # Component distribution
                summary["component_distribution"] = self._count_by_field(
                    recent_entries, "component"
                )

                # Error rate tracking
                if self.config.enable_error_rate_tracking:
                    error_entries = [
                        e for e in recent_entries if e["level"] in ["ERROR", "CRITICAL"]
                    ]
                    summary["error_rate"] = len(error_entries) / len(recent_entries)
                    summary["error_count"] = len(error_entries)

                    # Error types
                    summary["error_types"] = self._count_by_field(error_entries, "error_type")

                # Operations with most logs
                operations = self._count_by_field(recent_entries, "operation")
                summary["top_operations"] = dict(
                    sorted(operations.items(), key=lambda x: x[1], reverse=True)[:10]
                )

            return summary

    def get_error_patterns(self) -> dict[str, Any]:
        """Analyze error patterns in logs."""
        with self._lock:
            error_entries = [e for e in self._entries if e["level"] in ["ERROR", "CRITICAL"]]

            patterns: dict[str, Any] = {
                "total_errors": len(error_entries),
                "error_patterns": {},
                "frequent_messages": {},
            }

            if error_entries:
                # Group by error type
                for entry in error_entries:
                    error_type = entry.get("error_type", "unknown")
                    if error_type not in patterns["error_patterns"]:
                        patterns["error_patterns"][error_type] = []
                    patterns["error_patterns"][error_type].append(
                        {
                            "timestamp": entry["timestamp"],
                            "message": entry["message"],
                            "component": entry["component"],
                            "operation": entry.get("operation"),
                        }
                    )

                # Frequent error messages
                messages = self._count_by_field(error_entries, "message")
                patterns["frequent_messages"] = dict(
                    sorted(messages.items(), key=lambda x: x[1], reverse=True)[:10]
                )

            return patterns

    def get_performance_insights(self) -> dict[str, Any]:
        """Extract performance-related insights from logs."""
        with self._lock:
            perf_entries = [
                e for e in self._entries if "performance" in str(e).lower() or "duration" in e
            ]

            insights: dict[str, Any] = {
                "performance_alerts": len(perf_entries),
                "slow_operations": [],
                "resource_alerts": [],
            }

            for entry in perf_entries:
                if "duration" in entry.get("message", "").lower():
                    insights["slow_operations"].append(
                        {
                            "timestamp": entry["timestamp"],
                            "message": entry["message"],
                            "component": entry["component"],
                        }
                    )
                elif any(
                    word in entry.get("message", "").lower()
                    for word in ["memory", "cpu", "resource"]
                ):
                    insights["resource_alerts"].append(
                        {
                            "timestamp": entry["timestamp"],
                            "message": entry["message"],
                            "component": entry["component"],
                        }
                    )

            return insights

    def clear_entries(self, older_than_seconds: int | None = None):
        """Clear old entries from the aggregator."""
        with self._lock:
            if older_than_seconds:
                cutoff_time = time.time() - older_than_seconds
                self._entries = deque(
                    [e for e in self._entries if e["timestamp"] > cutoff_time],
                    maxlen=self.config.max_entries,
                )
            else:
                self._entries.clear()


class LogAnalyzer:
    """Advanced log analysis utilities."""

    @staticmethod
    def detect_anomalies(
        entries: list[dict[str, Any]], baseline_window: int = 3600
    ) -> dict[str, Any]:
        """Detect anomalous patterns in log entries."""
        if len(entries) < 10:
            return {"anomalies_detected": False, "reason": "Insufficient data"}

        # Simple anomaly detection based on error rate spikes
        recent_entries = [e for e in entries if e["timestamp"] > time.time() - baseline_window]
        baseline_entries = [e for e in entries if e["timestamp"] <= time.time() - baseline_window]

        if not baseline_entries:
            return {"anomalies_detected": False, "reason": "No baseline data"}

        recent_error_rate = len(
            [e for e in recent_entries if e["level"] in ["ERROR", "CRITICAL"]]
        ) / len(recent_entries)
        baseline_error_rate = len(
            [e for e in baseline_entries if e["level"] in ["ERROR", "CRITICAL"]]
        ) / len(baseline_entries)

        threshold = baseline_error_rate * 2.0  # 2x baseline is anomalous

        return {
            "anomalies_detected": recent_error_rate > threshold,
            "recent_error_rate": recent_error_rate,
            "baseline_error_rate": baseline_error_rate,
            "threshold": threshold,
            "severity": (
                "high"
                if recent_error_rate > threshold * 2
                else "medium"
                if recent_error_rate > threshold
                else "low"
            ),
        }

    @staticmethod
    def generate_report(aggregator: LogAggregator) -> str:
        """Generate a human-readable report from log aggregator."""
        summary = aggregator.get_summary()
        error_patterns = aggregator.get_error_patterns()
        perf_insights = aggregator.get_performance_insights()

        report = f"""
LOG ANALYSIS REPORT
===================

Time Window: {summary["time_window_seconds"]} seconds
Total Entries: {summary["total_entries"]}

LEVEL DISTRIBUTION:
{chr(10).join(f"  {level}: {count}" for level, count in summary.get("level_distribution", {}).items())}

COMPONENT DISTRIBUTION:
{chr(10).join(f"  {comp}: {count}" for comp, count in summary.get("component_distribution", {}).items())}

ERROR ANALYSIS:
  Total Errors: {error_patterns["total_errors"]}
  Error Rate: {summary.get("error_rate", 0):.2%}
  Top Error Types: {", ".join(error_patterns.get("error_types", {}).keys())}

PERFORMANCE INSIGHTS:
  Performance Alerts: {perf_insights["performance_alerts"]}
  Slow Operations: {len(perf_insights["slow_operations"])}
  Resource Alerts: {len(perf_insights["resource_alerts"])}

TOP OPERATIONS:
{chr(10).join(f"  {op}: {count}" for op, count in summary.get("top_operations", {}).items())}
"""
        return report.strip()


# Global log aggregator instance
_log_aggregator = LogAggregator()


def get_log_aggregator() -> LogAggregator:
    """Get the global log aggregator instance."""
    return _log_aggregator


def get_log_analysis_report() -> str:
    """Get a comprehensive log analysis report."""
    return LogAnalyzer.generate_report(_log_aggregator)


def detect_log_anomalies(baseline_window: int = 3600) -> dict[str, Any]:
    """Detect anomalies in recent log entries."""
    aggregator = get_log_aggregator()
    # Get entries safely through the aggregator's public interface
    # Get larger window for baseline
    summary = aggregator.get_summary(baseline_window * 2)
    if summary.get("total_entries", 0) < 10:
        return {"anomalies_detected": False, "reason": "Insufficient data"}

    # Simple implementation - real implementation would need access to raw entries
    error_rate = summary.get("error_rate", 0.0)
    return {
        "anomalies_detected": error_rate > 0.1,  # 10% error rate threshold
        "recent_error_rate": error_rate,
        "baseline_error_rate": 0.05,  # Assumed baseline
        "threshold": 0.1,
        "severity": "high" if error_rate > 0.2 else "medium" if error_rate > 0.1 else "low",
    }


# Configuration convenience functions
def update_logging_config(**kwargs: Any) -> None:
    """Update logging configuration dynamically."""
    _enhanced_logger.update_config(**kwargs)


def set_module_log_level(module_name: str, level: str):
    """Set log level for a specific module."""
    _enhanced_logger.set_module_level(module_name, level)


def remove_module_log_level(module_name: str):
    """Remove custom log level for a specific module."""
    _enhanced_logger.remove_module_level(module_name)


def get_module_log_levels() -> dict[str, str]:
    """Get current module-specific log levels."""
    return _enhanced_logger.get_module_levels()


def update_log_filter_config(**kwargs: Any) -> None:
    """Update log filter configuration dynamically."""
    _enhanced_logger.update_filter_config(**kwargs)
