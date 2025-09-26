"""
Main entry point for the DinoAir API server.

This module provides the uvicorn launcher for the FastAPI application,
configured with security-first defaults and proper error handling.
"""

from __future__ import annotations

import sys

import uvicorn

from .settings import Settings


def main() -> int:
    """
    Programmatic uvicorn launcher.
    - Binds ONLY to 127.0.0.1 (ignore any host override for security).
    - Uses configured port from settings.
    - Disables uvicorn access log (we emit our own structured logs).
    - Graceful shutdown on KeyboardInterrupt.
    """
    settings = Settings()

    config = uvicorn.Config(
        app="API_files.app:create_app",
        factory=True,
        host="127.0.0.1",  # enforce local-only binding
        port=int(settings.port),
        log_level=(settings.log_level or "info").lower(),
        proxy_headers=False,
        access_log=False,
        use_colors=False,
    )
    server = uvicorn.Server(config)

    try:
        server.run()
        return 0  # Server ran successfully
    except KeyboardInterrupt:
        # Graceful shutdown
        return 130  # 130 is commonly used for script terminated by Ctrl+C
    except (OSError, RuntimeError) as e:
        # Log or handle specific server-related exceptions
        import logging

        logging.getLogger(__name__).error("Server error: %s", e)
        return 1  # Non-zero for general errors


if __name__ == "__main__":
    sys.exit(main())
