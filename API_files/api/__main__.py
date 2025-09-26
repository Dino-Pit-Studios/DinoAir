"""
Alternative entry point for the DinoAir API server with enhanced development features.

- Binds only to 127.0.0.1 for security.
- Reads port and log_level from Settings.
- Enables colored output and access logging in dev (when TTY).
- Supports optional auto-reload in dev if Settings.reload is truthy.
- Returns conventional exit codes and logs meaningful errors.
"""

from __future__ import annotations

import logging
import sys
from typing import Final

import uvicorn

from api.settings import Settings

LOGGER = logging.getLogger(__name__)

EXIT_SUCCESS: Final[int] = 0
EXIT_SIGINT: Final[int] = 130
EXIT_FAILURE: Final[int] = 1
LOCAL_HOST: Final[str] = "127.0.0.1"


def _is_tty() -> bool:
    """
    True if either stdout or stderr is attached to a TTY.
    Kept minimal to avoid expensive checks; suitable for dev-only color gating.
    """
    return sys.stdout.isatty() or sys.stderr.isatty()


def build_uvicorn_config(settings: Settings) -> uvicorn.Config:
    """
    Construct a uvicorn.Config from Settings with sane, secure defaults.

    - Always binds to LOCAL_HOST.
    - Dev toggles (access log, color, reload) are enabled only when is_dev is True.
    """
    is_dev = bool(getattr(settings, "is_dev", False))
    log_level = str(getattr(settings, "log_level", "info") or "info").lower()
    use_colors = is_dev and _is_tty()
    access_log = is_dev
    reload_enabled = bool(getattr(settings, "reload", False)) if is_dev else False
    port = int(getattr(settings, "port", 8000))

    return uvicorn.Config(
        app="api.app:create_app",
        factory=True,
        host=LOCAL_HOST,
        port=port,
        log_level=log_level,
        proxy_headers=False,
        access_log=access_log,
        use_colors=use_colors,
        reload=reload_enabled,
    )


def run_server(settings: Settings) -> int:
    """Build and run the uvicorn server. Returns an exit code suitable for sys.exit()."""
    config = build_uvicorn_config(settings)
    server = uvicorn.Server(config)

    try:
        server.run()
    except KeyboardInterrupt:
        # 130 is conventional for SIGINT
        return EXIT_SIGINT
    except (OSError, RuntimeError) as e:
        LOGGER.error("Server error: %s", e)
        return EXIT_FAILURE
    return EXIT_SUCCESS


def main() -> int:
    """Programmatic entrypoint. Constructs Settings and runs the server."""
    settings = Settings()
    return run_server(settings)


if __name__ == "__main__":
    sys.exit(main())
