"""Sentry integration for error tracking and monitoring."""

import os

import sentry_sdk
from fastapi import FastAPI


def _get_sentry_dsn() -> str | None:
    """Get Sentry DSN from file or environment variable."""
    # Try file-based secret first (Docker/K8s)
    dsn_file = os.getenv("SENTRY_DSN_FILE")
    if dsn_file:
        try:
            with open(dsn_file, encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass

    # Fallback to environment variable
    return os.getenv("SENTRY_DSN")


# Initialize Sentry with secure configuration
sentry_dsn = _get_sentry_dsn()
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
    )

app = FastAPI()
