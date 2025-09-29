"""Removed Qt-based watchdog.

This module previously provided PySide6/Qt-based watchdog threading utilities.
The project is now React-only for UI, so all Qt dependencies were removed.

This stub remains to avoid import errors. It exposes minimal no-op types and
constants so that any stale imports won't crash, but functionality is disabled.
"""

IS_QT_AVAILABLE: bool = False


class WatchdogController:
    """No-op placeholder for the old Qt watchdog controller."""

    def __init__(self, *_: object, **__: object) -> None:  # pragma: no cover - stub
        pass

    def start(self) -> None:  # pragma: no cover - stub
        pass

    def stop(self) -> None:  # pragma: no cover - stub
        pass

    def get_current_metrics(self) -> dict[str, object]:  # pragma: no cover - stub
        return {}


__all__ = ["IS_QT_AVAILABLE", "WatchdogController"]
