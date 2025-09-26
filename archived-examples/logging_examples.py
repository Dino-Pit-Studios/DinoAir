"""
Comprehensive examples demonstrating enhanced logging features for DinoAir

This module provides practical examples of:
- Custom log levels (TRACE, VERBOSE)
- Contextual logging with correlation IDs
- Structured logging with metadata
- Log filtering and sampling
- Async logging for performance
- Integration with performance monitoring
- Error handling with enhanced logging
- Log aggregation and analysis
"""

import contextlib
import logging
import time
from typing import Any

# Import enhanced logging components
try:
    from enhanced_logger import (
        TRACE_LEVEL,
        VERBOSE_LEVEL,
        FormatterConfig,
        LogConfig,
        LogFilterConfig,
        configure_logging,
        detect_log_anomalies,
        generate_correlation_id,
        get_log_aggregator,
        get_log_analysis_report,
        get_logger,
        log_context,
        update_log_context,
    )

    enhanced_available = True

    # Configure enhanced logging
    config = LogConfig(
        level="DEBUG",
        format_type="json",
        async_logging=True,
        filter_config=LogFilterConfig(
            sampling_rate=0.8,  # Sample 80% of logs
            # Higher level for noisy module
            level_filters={"noisy_module": logging.WARNING},
        ),
        formatter_config=FormatterConfig(
            include_context=True, include_timestamp=True, include_function=True
        ),
    )
    configure_logging(config)
    logger = get_logger(__name__)

except ImportError:
    # Fallback to standard logging
    enhanced_available = False
    logger = logging.getLogger(__name__)

    # Define dummy variables for when enhanced logging is not available
    def get_logger(name: str):
        """Get logger.

        Args:
            name: TODO: Add description
        """
        return logging.getLogger(name)

    def generate_correlation_id():
        """Generate correlation id."""
        return "dummy_correlation_id"

    def update_log_context(**kwargs: Any) -> None:
        """Update log context.

        Returns:
            TODO: Add return description
        """

    def log_context(**_kwargs: Any):
        """Log context."""
        from contextlib import nullcontext

        return nullcontext()

    def get_log_aggregator():
        """Get log aggregator."""
        return None

    def get_log_analysis_report():
        """Get log analysis report."""
        return "Enhanced logging not available"

    def detect_log_anomalies(**_kwargs: Any) -> dict[str, Any]:
        """Detect log anomalies.

        Returns:
            TODO: Add return description
        """
        return {"anomalies_detected": False, "reason": "Enhanced logging not available"}

    trace_level = 5
    verbose_level = 15
    TRACE_LEVEL = trace_level
    VERBOSE_LEVEL = verbose_level


def example_basic_logging() -> None:
    """Example of basic enhanced logging with custom levels."""
    if not enhanced_available:
        return

    # Standard levels
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")

    # Custom levels
    logger.log(TRACE_LEVEL, "This is a trace message (very detailed)")
    logger.log(VERBOSE_LEVEL, "This is a verbose message (operational details)")

    # Using convenience methods
    logger.trace("Another trace message")  # type: ignore
    logger.verbose("Another verbose message")  # type: ignore


def example_contextual_logging() -> None:
    """Example of contextual logging with correlation IDs."""
    if not enhanced_available:
        return

    # Set up context for a user operation
    correlation_id = generate_correlation_id()
    update_log_context(
        correlation_id=correlation_id,
        user_id="user123",
        session_id="session456",
        component="user_service",
        operation="user_login",
    )

    logger.info("User login attempt started")
    logger.debug("Validating user credentials")

    # Simulate some operation
    time.sleep(0.1)

    logger.info(
        "User login successful",
        extra={"login_method": "password", "ip_address": "192.168.1.100"},
    )

    # Context is automatically included in all log messages


def example_operation_context() -> None:
    """Example of operation-scoped context."""
    if not enhanced_available:
        return

    def process_payment(amount: float, user_id: str) -> None:
        """Process payment.

        Args:
            amount: TODO: Add description
            user_id: TODO: Add description

        Returns:
            TODO: Add return description
        """
        with log_context(
            correlation_id=generate_correlation_id(),
            operation="process_payment",
            component="payment_service",
            user_id=user_id,
            amount=amount,
        ):
            logger.info("Starting payment processing")

            # Simulate payment steps
            logger.debug("Validating payment details")
            time.sleep(0.05)

            logger.debug("Contacting payment gateway")
            time.sleep(0.1)

            logger.info(
                "Payment processed successfully",
                extra={"transaction_id": "txn_12345", "processing_time_ms": 150},
            )

    # Process multiple payments
    process_payment(99.99, "user123")
    process_payment(49.99, "user456")


def example_error_handling() -> None:
    """Example of enhanced error handling with logging."""
    if not enhanced_available:
        return

    def risky_operation() -> str:
        """Risky operation.

        Returns:
            TODO: Add return description
        """
        with log_context(operation="risky_operation", component="data_processor"):
            try:
                # Simulate an operation that might fail
                logger.debug("Attempting risky operation")
                if time.time() % 2 > 1:  # Random failure
                    raise ValueError("Simulated operation failure")
                logger.info("Risky operation completed successfully")
                return "success"
            except Exception as e:
                logger.error(
                    "Risky operation failed: %s",
                    e,
                    extra={
                        "error_type": type(e).__name__,
                        "error_details": str(e),
                        "retryable": True,
                    },
                )
                raise

    # Try the operation multiple times
    for i in range(3):
        try:
            risky_operation()
            break
        except (ValueError, RuntimeError):
            if i < 2:  # Don't log on last attempt
                logger.warning("Attempt %d failed, retrying...", i + 1)
                time.sleep(0.1)


def example_performance_logging() -> None:
    """Example of performance-aware logging."""
    if not enhanced_available:
        return

    def slow_operation() -> None:
        """Slow operation.

        Returns:
            TODO: Add return description
        """
        with log_context(operation="slow_database_query", component="database_service"):
            start_time = time.time()
            logger.debug("Starting database query")

            # Simulate slow operation
            time.sleep(0.5)

            duration = time.time() - start_time
            logger.info(
                "Database query completed",
                extra={
                    "duration_seconds": duration,
                    "query_type": "SELECT",
                    "table": "users",
                    "records_returned": 150,
                },
            )

            # Log performance warning if slow
            if duration > 0.3:
                logger.warning(
                    "Slow database query detected",
                    extra={
                        "duration_seconds": duration,
                        "threshold_seconds": 0.3,
                        "performance_impact": "high",
                    },
                )

    slow_operation()


def example_log_filtering() -> None:
    """Example of log filtering and sampling."""
    if not enhanced_available:
        return

    # Create a logger for a noisy module
    noisy_logger = get_logger("noisy_module")

    # This logger has higher level filter, so DEBUG messages won't appear
    noisy_logger.debug("This debug message will be filtered out")
    noisy_logger.info("This info message will appear")
    noisy_logger.warning("This warning will appear")

    # Regular logger (not filtered)
    logger.debug("This debug message will appear (sampling may apply)")
    logger.info("This info message will appear")


def example_log_aggregation() -> None:
    """Example of log aggregation and analysis."""
    if not enhanced_available:
        return

    # Generate some test logs
    for i in range(20):
        with log_context(
            operation=f"test_operation_{i}",
            component="test_component",
            correlation_id=f"corr_{i}",
        ):
            level = ["DEBUG", "INFO", "WARNING", "ERROR"][i % 4]
            logger.log(getattr(logging, level), "Test message %d", i)

    # Get aggregation summary
    aggregator = get_log_aggregator()
    if aggregator:
        aggregator.get_summary(time_window_seconds=60)

        # Get error patterns
        aggregator.get_error_patterns()
    else:
        pass


def example_anomaly_detection() -> None:
    """Example of anomaly detection in logs."""
    if not enhanced_available:
        return

    # Generate normal logs
    for _ in range(10):
        logger.info("Normal operation")

    # Generate some errors to create anomaly
    for _ in range(5):
        logger.error("Simulated error for anomaly detection")

    # Detect anomalies
    detect_log_anomalies(baseline_window=300)


def example_comprehensive_scenario() -> None:
    """Comprehensive example combining multiple features."""
    if not enhanced_available:
        return

    def user_registration_workflow(user_data: dict[str, Any]) -> dict[str, Any]:
        """User registration workflow.

        Args:
            user_data: TODO: Add description

        Returns:
            TODO: Add return description
        """
        correlation_id = generate_correlation_id()

        with log_context(
            correlation_id=correlation_id,
            operation="user_registration",
            component="user_management",
            user_email=user_data.get("email"),
            registration_type="premium",
        ):
            logger.info("Starting user registration workflow")

            # Step 1: Validate input
            logger.debug("Validating user input data")
            time.sleep(0.05)

            # Step 2: Check for duplicates
            logger.debug("Checking for duplicate email addresses")
            time.sleep(0.1)

            # Step 3: Create user account
            logger.info(
                "Creating user account",
                extra={
                    "account_type": "premium",
                    "features_enabled": ["analytics", "priority_support"],
                },
            )
            time.sleep(0.2)

            # Step 4: Send welcome email
            logger.debug("Sending welcome email")
            time.sleep(0.1)

            # Step 5: Log successful registration
            logger.info(
                "User registration completed successfully",
                extra={
                    "user_id": "user_12345",
                    "welcome_email_sent": True,
                    "account_status": "active",
                },
            )

            return {"user_id": "user_12345", "status": "success"}

    # Execute the workflow
    user_data = {"email": "john.doe@example.com", "name": "John Doe", "plan": "premium"}

    user_registration_workflow(user_data)


def run_all_examples() -> None:
    """Run all logging examples."""

    if not enhanced_available:
        return

    example_basic_logging()
    example_contextual_logging()
    example_operation_context()
    example_error_handling()
    example_performance_logging()
    example_log_filtering()
    example_log_aggregation()
    example_anomaly_detection()
    example_comprehensive_scenario()

    # Final analysis report
    with contextlib.suppress(ImportError, AttributeError, ValueError):
        get_log_analysis_report()


if __name__ == "__main__":
    run_all_examples()
