"""Lightweight logging helpers and a decorator for consistent operational logs.

These utilities avoid side effects beyond logging and preserve wrapped function
signatures for unit-friendly usage.
"""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

P = ParamSpec("P")
R = TypeVar("R")


def log_exception(logger: logging.Logger, msg: str, exc: Exception) -> None:
    """Log an exception with a consistent format."""
    logger.error(f"{msg}: {exc}")


def logged_operation(
    logger: logging.Logger, op_name: str
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that logs start and completion; logs and re-raises on exception.

    Usage:
        @logged_operation(logger, "my_operation")
        def do_work(...): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            logger.info(f"{op_name} started")
            try:
                result = func(*args, **kwargs)
                logger.info(f"{op_name} completed")
                return result
            except Exception as e:
                log_exception(logger, f"{op_name} failed", e)
                raise

        return wrapper

    return decorator
