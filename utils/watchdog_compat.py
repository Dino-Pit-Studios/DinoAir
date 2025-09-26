"""Streamlined watchdog implementation without legacy adapters.

This module provides a clean Qt-based watchdog implementation without
the complexity of legacy fallback mechanisms.
"""

import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from .logger import Logger

logger = Logger()


class WatchdogMode(Enum):
    """Available watchdog implementation modes."""

    QT = "qt"  # Qt-based implementation


@dataclass
class WatchdogConfig:
    """Configuration for watchdog behavior."""

    vram_threshold: float = 95.0
    max_processes: int = 5
    check_interval: int = 30
    self_terminate: bool = False


class StreamlinedWatchdog:
    """Clean Qt-based watchdog implementation without legacy fallbacks.

    This class provides a simplified interface to the Qt-based watchdog
    without the complexity of multiple fallback mechanisms.
    """

    def __init__(
        self,
        alert_callback: Callable | None = None,
        metrics_callback: Callable | None = None,
        vram_threshold_percent: float = 95.0,
        max_dinoair_processes: int = 5,
        check_interval_seconds: int = 30,
        self_terminate_on_critical: bool = False,
    ):
        """Initialize streamlined watchdog.

        Args:
            alert_callback: Function called when alerts are triggered
            metrics_callback: Function called with live metrics updates
            vram_threshold_percent: VRAM usage % that triggers warnings
            max_dinoair_processes: Max DinoAir processes before critical alert
            check_interval_seconds: How often to check system metrics
            self_terminate_on_critical: Whether to perform emergency shutdown
        """
        # Store callbacks and configuration
        self.alert_callback = alert_callback
        self.metrics_callback = metrics_callback

        # Create configuration
        self.config = WatchdogConfig(
            vram_threshold=vram_threshold_percent,
            max_processes=max_dinoair_processes,
            check_interval=check_interval_seconds,
            self_terminate=self_terminate_on_critical,
        )

        # Implementation tracking
        self.controller = None
        self._monitoring = False
        self._startup_time = time.time()
        self._lock = threading.RLock()
        self._qt_app = None
        self._qt_thread = None

        # Initialize Qt controller
        self._initialize_controller()

    def _initialize_controller(self):
        """Initialize Qt-based controller."""
        try:
            from .watchdog_qt import WatchdogController

            # Create controller
            self.controller = WatchdogController(self.config)
            logger.info("Qt-based watchdog controller initialized")
            return True

        except ImportError as e:
            logger.error(f"Qt modules not available: {e}")
            raise RuntimeError("Qt-based watchdog requires Qt modules") from e

        except RuntimeError as e:
            logger.error(f"Failed to initialize Qt controller: {e}")
            raise RuntimeError(f"Qt controller initialization failed: {e}") from e

    def _connect_signals(self):
        """Connect Qt signals to callback functions."""
        if not self.controller or not self.controller.signals:
            return

        try:
            from PySide6.QtCore import Qt

            # Connect alert signal to callback
            if self.alert_callback:
                self.controller.signals.alert_triggered.connect(
                    self._handle_alert, Qt.ConnectionType.QueuedConnection
                )

            # Connect metrics signal to callback
            if self.metrics_callback:
                self.controller.signals.metrics_ready.connect(
                    self._handle_metrics, Qt.ConnectionType.QueuedConnection
                )

        except RuntimeError as e:
            logger.error(f"Failed to connect Qt signals: {e}")

    def _handle_alert(self, level, message: str):
        """Handle alert signal and forward to callback."""
        if self.alert_callback:
            try:
                self.alert_callback(level, message)
            except RuntimeError as e:
                logger.error(f"Error in alert callback: {e}")

    def _handle_metrics(self, metrics):
        """Handle metrics signal and forward to callback."""
        if self.metrics_callback:
            try:
                self.metrics_callback(metrics)
            except RuntimeError as e:
                logger.error(f"Error in metrics callback: {e}")

    def start_monitoring(self) -> None:
        """Start watchdog monitoring."""
        with self._lock:
            if self._monitoring:
                logger.warning("Watchdog already monitoring")
                return

            self._monitoring = True
            logger.info("Starting Qt-based watchdog monitoring")

        try:
            from PySide6.QtCore import QCoreApplication

            # Ensure Qt application exists
            if not QCoreApplication.instance():
                logger.warning("No Qt application found. Creating one.")

                app = QCoreApplication(sys.argv)
                self._qt_app = app

                # Start event loop in background thread
                def run_qt_loop():
                    try:
                        app.exec()
                    except RuntimeError as e:
                        logger.error(f"Qt event loop error: {e}")

                self._qt_thread = threading.Thread(target=run_qt_loop, daemon=True)
                self._qt_thread.start()

            # Start the controller
            if self.controller:
                self.controller.start_watchdog()
                # Connect signals after controller is started
                self._connect_signals()
            else:
                raise RuntimeError("Controller not initialized")

        except RuntimeError as e:
            logger.error(f"Failed to start Qt monitoring: {e}")
            raise RuntimeError(f"Failed to start monitoring: {e}") from e

    def stop_monitoring(self) -> None:
        """Stop watchdog monitoring."""
        with self._lock:
            logger.info("Stopping Qt-based watchdog monitoring")

            if not self._monitoring:
                logger.warning("Watchdog not monitoring")
                return

            self._monitoring = False

        if self.controller:
            try:
                self.controller.stop_watchdog()
            except RuntimeError as e:
                logger.error(f"Error stopping Qt watchdog: {e}")

            # Clean up Qt app if we created it
            if self._qt_app:
                try:
                    self._qt_app.quit()
                    if self._qt_thread:
                        self._qt_thread.join(timeout=2.0)
                except RuntimeError as e:
                    logger.error(f"Error cleaning up Qt app: {e}")

    def get_current_metrics(self):
        """Get current system metrics.

        Returns:
            SystemMetrics: Current resource usage snapshot
        """
        try:
            # Local import to prevent circular import; required in function scope.
            from .Watchdog import SystemWatchdog

            return SystemWatchdog().get_current_metrics(self._startup_time)
        except RuntimeError as e:
            logger.error(f"Failed to get metrics: {e}")

            # Return safe defaults - create a basic metrics object
            class _EmptyMetrics:
                """Placeholder metrics class when system metrics retrieval fails.

                Instances provide default zero values for all metric attributes.
                """

                def __init__(self):
                    self.vram_percent = 0
                    self.ram_percent = 0
                    self.cpu_percent = 0
                    self.process_count = 0
                    self.dinoair_processes = 0
                    self.vram_used_mb = 0
                    self.ram_used_mb = 0

            return _EmptyMetrics()

    def emergency_cleanup(self) -> dict[str, int]:
        """Perform emergency cleanup of runaway processes.

        Returns:
            Dict[str, int]: Statistics of cleanup operation
        """
        # Local import to prevent circular import; required in function scope.
        from .Watchdog import SystemWatchdog

        return SystemWatchdog.emergency_cleanup()

    def get_status_report(self) -> str:
        """Generate a status report for display/logging.

        Returns:
            str: Multi-line status report with current metrics
        """
        # Get current metrics
        metrics = self.get_current_metrics()

        # Format uptime
        uptime_seconds = int(time.time() - self._startup_time)
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60

        # Show self-terminate status
        terminate_status = "ON" if self.config.self_terminate else "OFF"

        # Build status
        status_lines = [
            "🐕 System Watchdog Status (Qt mode)",
            "├─ Implementation: QT",
        ]

        if self.controller and (status := self.controller.get_status()):
            status_lines.extend(
                [
                    f"├─ State: {status.circuit_breaker_state}",
                    f"├─ Error Count: {status.error_count}",
                ]
            )

        status_lines.extend(
            [
                f"├─ Uptime: {hours}h {minutes}m",
                f"├─ VRAM: {metrics.vram_percent:.1f}% ({metrics.vram_used_mb:.0f}MB)",
                f"├─ RAM: {metrics.ram_percent:.1f}% ({metrics.ram_used_mb:.0f}MB)",
                f"├─ CPU: {metrics.cpu_percent:.1f}%",
                f"├─ Total Processes: {metrics.process_count}",
                f"├─ DinoAir Processes: {metrics.dinoair_processes}/{self.config.max_processes}",
                f"└─ Auto-Terminate: {terminate_status}",
            ]
        )

        return "\n".join(status_lines)


def create_watchdog() -> StreamlinedWatchdog:
    """Factory function to create streamlined watchdog implementation.

    Returns:
        StreamlinedWatchdog: Clean Qt-based watchdog instance
    """
    logger.info("Creating streamlined Qt-based watchdog")
    return StreamlinedWatchdog()
