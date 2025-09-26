from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .common import guard_imports, resp

if TYPE_CHECKING:
    from ..settings import Settings

log = logging.getLogger("api.services.rag_monitor")
RAG_UNAVAILABLE_MSG = "RAG components unavailable"


class RagMonitorService:
    """
    Service to manage the lifecycle of RAG file monitoring.
    Allows starting and stopping file monitoring on configured directories and file extensions.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._monitor: Any = None  # mirrors semantics from RagService

    def monitor_start(
        self, directories: list[str], file_extensions: list[str] | None = None
    ) -> dict[str, Any]:
        if not getattr(self.settings, "rag_enabled", True):
            return resp(False, None, RAG_UNAVAILABLE_MSG, 501)
        if not getattr(self.settings, "rag_watchdog_enabled", False):
            return resp(False, None, "RAG monitor disabled by settings", 501)

        guard = guard_imports(("rag.file_monitor",))
        if guard is not None:
            return guard

        try:
            # pylint: disable=import-outside-toplevel
            from rag.file_monitor import FileMonitor  # type: ignore
        except ImportError:
            return resp(False, None, RAG_UNAVAILABLE_MSG, 501)

        try:
            if self._monitor is None:
                self._monitor = FileMonitor(user_name="default_user")
            if hasattr(self._monitor, "start_monitoring"):
                self._monitor.start_monitoring(
                    directories=directories or [], file_extensions=file_extensions
                )
            return resp(
                True,
                {
                    "status": "started",
                    "directories": directories,
                    "extensions": file_extensions,
                },
                None,
                200,
            )
        except (AttributeError, RuntimeError, OSError) as e:
            log.exception("monitor_start failed")
            return resp(False, None, str(e), 500)

    def monitor_stop(self) -> dict[str, Any]:
        try:
            if self._monitor is not None:
                self._monitor.stop_monitoring()
                self._monitor = None
            return resp(True, {"status": "stopped"}, None, 200)
        except (AttributeError, RuntimeError) as e:
            log.exception("monitor_stop failed")
            return resp(False, None, str(e), 500)

    def monitor_status(self) -> dict[str, Any]:
        try:
            if self._monitor is None:
                return resp(
                    True,
                    {
                        "is_monitoring": False,
                        "monitored_directories": [],
                        "file_extensions": [],
                    },
                    None,
                    200,
                )
            status = self._monitor.get_status()
            return resp(True, status, None, 200)
        except (AttributeError, RuntimeError) as e:
            log.exception("monitor_status failed")
            return resp(False, None, str(e), 500)
