"""
Comprehensive error handling utilities for robust application behavior.

This module provides standardized patterns for error handling including retries,
circuit breakers, timeouts, and graceful degradation. All utilities are configurable,
thread-safe where necessary, and integrate with the existing logging system.
"""

import asyncio
import functools
import logging
import random
import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar, cast

T = TypeVar("T")

# Try to import enhanced logging, fallback to standard logging
try:
    from enhanced_logger import get_logger

    logger = get_logger(__name__)
    enhanced_logging_available = True
except ImportError:
    logger = logging.getLogger(__name__)
    enhanced_logging_available = False


class ErrorSeverity(Enum):
    """Error severity levels for classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification and handling."""

    NETWORK = "network"
    FILESYSTEM = "filesystem"
    DATABASE = "database"
    EXTERNAL_SERVICE = "external_service"
    RESOURCE = "resource"
    CONFIGURATION = "configuration"
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information for error classification."""

    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    operation: str
    retryable: bool = True
    details: dict[str, Any] = field(default_factory=dict)


class ErrorClassifier:
    """Classifies errors into categories and severity levels."""

    # Exception types mapped to categories
    EXCEPTION_CATEGORIES = {
        ErrorCategory.FILESYSTEM: (
            FileNotFoundError,
            PermissionError,
            IsADirectoryError,  # File operations
        ),
        ErrorCategory.TIMEOUT: (
            TimeoutError,
            asyncio.TimeoutError,
        ),
        ErrorCategory.NETWORK: (
            ConnectionError,
            OSError,  # Network-related (after more specific categories)
        ),
        ErrorCategory.DATABASE: (
            # Add database-specific exceptions as needed
        ),
        ErrorCategory.EXTERNAL_SERVICE: (
            # Add external service exceptions as needed
        ),
        ErrorCategory.RESOURCE: (MemoryError,),  # Resource exhaustion
        ErrorCategory.CONFIGURATION: (
            ValueError,
            KeyError,  # Configuration issues
        ),
        ErrorCategory.VALIDATION: (
            ValueError,
            TypeError,  # Validation errors
        ),
    }

    @staticmethod
    def classify_error(error: Exception, operation: str = "") -> ErrorContext:
        """Classify an exception into category and severity.

        Args:
            error: The exception to classify
            operation: Description of the operation that failed

        Returns:
            ErrorContext with classification details
        """
        error_type = type(error)

        # Determine category
        category = ErrorCategory.UNKNOWN
        for cat, exceptions in ErrorClassifier.EXCEPTION_CATEGORIES.items():
            if any(issubclass(error_type, exc) for exc in exceptions):
                category = cat
                break

        # Determine severity based on category and error type
        if category in (ErrorCategory.NETWORK, ErrorCategory.FILESYSTEM):
            severity = ErrorSeverity.MEDIUM
        elif category in (ErrorCategory.DATABASE, ErrorCategory.EXTERNAL_SERVICE):
            severity = ErrorSeverity.HIGH
        elif category == ErrorCategory.RESOURCE:
            severity = ErrorSeverity.CRITICAL
        elif category == ErrorCategory.TIMEOUT:
            severity = ErrorSeverity.MEDIUM
        else:
            severity = ErrorSeverity.LOW

        # Check if error is retryable
        retryable = category in (
            ErrorCategory.NETWORK,
            ErrorCategory.TIMEOUT,
            ErrorCategory.EXTERNAL_SERVICE,
            ErrorCategory.UNKNOWN,
            ErrorCategory.FILESYSTEM,
        )

        return ErrorContext(
            category=category,
            severity=severity,
            message=str(error),
            operation=operation,
            retryable=retryable,
            details={"exception_type": error_type.__name__},
        )


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 3
    timeout: float = 5.0


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker monitoring."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None


class CircuitBreaker:
    """Circuit breaker pattern implementation for fault tolerance."""

    def __init__(self, config: CircuitBreakerConfig):
        """Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
        """
        self.config = config
        self._state = CircuitBreakerState.CLOSED
        self._stats = CircuitBreakerStats()
        self._lock = threading.Lock()

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result of the function call

        Raises:
            CircuitBreakerOpenError: If circuit breaker is open
            Exception: If function raises an exception
        """
        with self._lock:
            self._stats.total_calls += 1

            if self._state == CircuitBreakerState.OPEN:
                if not self._should_attempt_recovery():
                    raise CircuitBreakerOpenError("Circuit breaker is open")
                self._state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker entering half-open state")

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise

    def _record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self._stats.successful_calls += 1
            self._stats.consecutive_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = time.time()

            if (
                self._state == CircuitBreakerState.HALF_OPEN
                and self._stats.consecutive_successes >= self.config.success_threshold
            ):
                self._state = CircuitBreakerState.CLOSED
                logger.info("Circuit breaker closed after recovery")

    def _record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._stats.failed_calls += 1
            self._stats.consecutive_failures += 1
            self._stats.consecutive_successes = 0
            self._stats.last_failure_time = time.time()

            if self._stats.consecutive_failures >= self.config.failure_threshold:
                self._state = CircuitBreakerState.OPEN
                logger.warning(
                    "Circuit breaker opened after %d failures",
                    self._stats.consecutive_failures,
                )

    def _should_attempt_recovery(self) -> bool:
        """Check if recovery should be attempted."""
        if self._stats.last_failure_time is None:
            return True

        elapsed = time.time() - self._stats.last_failure_time
        return elapsed >= self.config.recovery_timeout

    def get_state(self) -> str:
        """Get current state as string."""
        with self._lock:
            return self._state.value

    def get_stats(self) -> CircuitBreakerStats:
        """Get current statistics."""
        with self._lock:
            return CircuitBreakerStats(**self._stats.__dict__)

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        with self._lock:
            self._state = CircuitBreakerState.CLOSED
            self._stats = CircuitBreakerStats()


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""


def retry_on_failure(
    config: RetryConfig | None = None,
    exceptions: tuple[type[Exception], ...] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for retrying operations on failure.

    Args:
        config: Retry configuration (uses defaults if None)
        exceptions: Tuple of exceptions to retry on (uses config if None)

    Returns:
        Decorated function
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            retry_exceptions = exceptions or config.retryable_exceptions

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except retry_exceptions as e:
                    last_exception = e

                    if attempt < config.max_attempts - 1:
                        delay = _calculate_retry_delay(config, attempt)
                        if enhanced_logging_available:
                            logger.warning(
                                "Attempt %d failed for %s, retrying in %.2fs: %s",
                                attempt + 1,
                                func.__name__,
                                delay,
                                e,
                                extra={
                                    "operation": func.__name__,
                                    "attempt": attempt + 1,
                                    "max_attempts": config.max_attempts,
                                    "retry_delay": delay,
                                    "error_type": type(e).__name__,
                                    "component": "error_handling",
                                },
                            )
                        else:
                            logger.warning(
                                "Attempt %d failed for %s, retrying in %.2fs: %s",
                                attempt + 1,
                                func.__name__,
                                delay,
                                e,
                            )
                        time.sleep(delay)
                    elif enhanced_logging_available:
                        logger.error(
                            "All %d attempts failed for %s: %s",
                            config.max_attempts,
                            func.__name__,
                            e,
                            extra={
                                "operation": func.__name__,
                                "max_attempts": config.max_attempts,
                                "total_attempts": attempt + 1,
                                "error_type": type(e).__name__,
                                "component": "error_handling",
                                "severity": "high",
                            },
                        )
                    else:
                        logger.error(
                            "All %d attempts failed for %s: %s",
                            config.max_attempts,
                            func.__name__,
                            e,
                        )

            # This should never be None, but type checker needs assurance
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Unexpected error in retry logic")

        return wrapper

    return decorator


def circuit_breaker(
    config: CircuitBreakerConfig | None = None, name: str = ""
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for circuit breaker protection.

    Args:
        config: Circuit breaker configuration (uses defaults if None)
        name: Name for the circuit breaker (uses function name if empty)

    Returns:
        Decorated function
    """
    if config is None:
        config = CircuitBreakerConfig()

    # Thread-local storage for circuit breakers to avoid sharing
    local = threading.local()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        breaker_name = name or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Get or create circuit breaker for this function
            if not hasattr(local, "breakers"):
                local.breakers = {}

            breakers = local.breakers
            if breaker_name not in breakers:
                breakers[breaker_name] = CircuitBreaker(config)

            breaker = breakers[breaker_name]
            return cast("T", breaker.call(func, *args, **kwargs))

        return wrapper

    return decorator


@contextmanager
def timeout_context(seconds: float) -> Generator[None, None, None]:
    """Context manager for operation timeouts.

    Args:
        seconds: Timeout in seconds

    Raises:
        TimeoutError: If operation exceeds timeout
    """
    timeout_exception = TimeoutError(f"Operation timed out after {seconds} seconds")

    timeout_reached = threading.Event()

    def signal_timeout() -> None:
        """Signal that timeout has been reached."""
        timeout_reached.set()

    timer = threading.Timer(seconds, signal_timeout)
    timer.daemon = True
    timer.start()

    try:
        yield
    except Exception as e:
        if timeout_reached.is_set():
            raise timeout_exception from e
        else:
            raise
    finally:
        timer.cancel()
        # Clean up timer thread
        if timer.is_alive():
            timer.join(timeout=0.1)


def with_timeout(timeout_seconds: float) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for adding timeout to functions.

    Args:
        timeout_seconds: Timeout in seconds

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            with timeout_context(timeout_seconds):
                return func(*args, **kwargs)

        return wrapper

    return decorator


@dataclass
class FallbackResult:
    """Result of a fallback operation."""

    success: bool
    result: Any = None
    error: Exception | None = None
    fallback_used: bool = False


def try_multiple(
    *strategies: Callable[[], Any],
    catch_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> FallbackResult:
    """Try multiple strategies in order, returning first successful result.

    Args:
        *strategies: Functions to try in order
        catch_exceptions: Exceptions to catch and continue to next strategy

    Returns:
        FallbackResult with the result or first error
    """
    first_error = None

    for i, strategy in enumerate(strategies):
        try:
            result = strategy()
            return FallbackResult(success=True, result=result, fallback_used=(i > 0))
        except catch_exceptions as e:
            if first_error is None:
                first_error = e
            if i < len(strategies) - 1:
                logger.warning("Strategy %d failed, trying next: %s", i + 1, e)
            continue

    return FallbackResult(success=False, error=first_error, fallback_used=True)


@dataclass
class ErrorStats:
    """Statistics for error monitoring."""

    total_errors: int = 0
    errors_by_category: dict[ErrorCategory, int] = field(default_factory=lambda: defaultdict(int))
    errors_by_severity: dict[ErrorSeverity, int] = field(default_factory=lambda: defaultdict(int))
    recent_errors: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=100))


class ErrorAggregator:
    """Aggregates and reports error statistics."""

    def __init__(self, max_recent_errors: int = 100):
        """Initialize error aggregator.

        Args:
            max_recent_errors: Maximum number of recent errors to keep
        """
        self._stats = ErrorStats()
        self._stats.recent_errors = deque(maxlen=max_recent_errors)
        self._lock = threading.Lock()

    def record_error(self, error: Exception, operation: str = "") -> None:
        """Record an error for aggregation.

        Args:
            error: The exception that occurred
            operation: Description of the operation
        """
        context = ErrorClassifier.classify_error(error, operation)

        with self._lock:
            self._stats.total_errors += 1
            self._stats.errors_by_category[context.category] += 1
            self._stats.errors_by_severity[context.severity] += 1
            self._stats.recent_errors.append(
                {"timestamp": time.time(), "context": context, "error": str(error)}
            )

    def get_stats(self) -> ErrorStats:
        """Get current error statistics."""
        with self._lock:
            # Return a copy to avoid external modification
            return ErrorStats(
                total_errors=self._stats.total_errors,
                errors_by_category=dict(self._stats.errors_by_category),
                errors_by_severity=dict(self._stats.errors_by_severity),
                recent_errors=deque(self._stats.recent_errors),
            )

    def reset(self) -> None:
        """Reset error statistics."""
        with self._lock:
            self._stats = ErrorStats()
            # Keep the same maxlen for recent_errors
            maxlen = self._stats.recent_errors.maxlen
            self._stats.recent_errors = deque(maxlen=maxlen)


def _calculate_retry_delay(config: RetryConfig, attempt: int) -> float:
    """Calculate retry delay with exponential backoff and jitter.

    Args:
        config: Retry configuration
        attempt: Current attempt number (0-based)

    Returns:
        Delay in seconds
    """
    base_delay = config.initial_delay * (config.backoff_factor**attempt)
    delay = min(base_delay, config.max_delay)

    if config.jitter:
        # Add random jitter up to 10% of the delay
        jitter = random.uniform(0, delay * 0.1)
        delay += jitter

    return delay


# Global error aggregator instance
error_aggregator = ErrorAggregator()


def _log_safe_failure(message: str, op_name: str, e: Exception, *, async_operation: bool) -> None:
    """Internal helper to log consistent safe-operation failures with optional structured extras."""
    if enhanced_logging_available:
        extra = {
            "operation": op_name,
            "error_type": type(e).__name__,
            "component": "error_handling",
            "safe_operation": True,
        }
        if async_operation:
            extra["async_operation"] = True
        logger.error(message, e, extra=extra)
    else:
        logger.error(message, e)


# Convenience functions for common patterns
def safe_operation(
    func: Callable[..., T],
    *args: Any,
    fallback: T | None = None,
    log_errors: bool = True,
    **kwargs: Any,
) -> T | None:
    """Execute operation safely with fallback.

    Args:
        func: Function to execute
        fallback: Value to return on failure
        log_errors: Whether to log errors
        *args: Arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result of func or fallback value
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            _log_safe_failure("Safe operation failed: %s", func.__name__, e, async_operation=False)
        error_aggregator.record_error(e, func.__name__)
        return fallback


async def safe_async_operation(
    coro: Callable[..., Awaitable[T]],
    *args: Any,
    fallback: T | None = None,
    log_errors: bool = True,
    **kwargs: Any,
) -> T | None:
    """Execute async operation safely with fallback.

    Args:
        coro: Coroutine to execute
        fallback: Value to return on failure
        log_errors: Whether to log errors
        *args: Arguments for coro
        **kwargs: Keyword arguments for coro

    Returns:
        Result of coro or fallback value
    """
    try:
        return await coro(*args, **kwargs)
    except Exception as e:
        if log_errors:
            _log_safe_failure(
                "Safe async operation failed: %s", coro.__name__, e, async_operation=True
            )
        error_aggregator.record_error(e, coro.__name__)
        return fallback
