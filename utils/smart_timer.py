#!/usr/bin/env python3

"""
Smart Timer Module
Implements a smart timer that can track time spent on various tasks.
Features include starting, stopping, resetting the timer, and running repeats.
"""

import time
from typing import Any


class SmartTimer:
    """Smart timer for tracking time spent on tasks."""

    def __init__(self, name: str):
        self.name = name
        self.start_time = None
        self.elapsed_time = 0
        self.running = False
        self.logs: list[float] = []

    def start(self) -> None:
        """Start the timer."""
        if not self.running:
            self.start_time = time.time()
            self.running = True

    def stop(self) -> None:
        """Stop the timer and log the elapsed time."""
        if self.running and self.start_time is not None:
            elapsed = time.time() - self.start_time
            self.elapsed_time += elapsed
            self.logs.append(elapsed)
            self.start_time = None
            self.running = False

    def reset(self) -> None:
        """Reset the timer to initial state."""
        self.start_time = None
        self.elapsed_time = 0
        self.running = False
        self.logs = []

    def get_elapsed_time(self) -> float:
        """Get the current elapsed time."""
        if self.running and self.start_time is not None:
            return self.elapsed_time + (time.time() - self.start_time)
        return self.elapsed_time

    def get_logs(self) -> list[float]:
        """Get the list of logged elapsed times."""
        return self.logs

    def run_repeats(self, repeats: int, duration_per_run: float) -> None:
        """Run the timer for a specified number of repeats.

        Args:
            repeats: Number of times to run the timer
            duration_per_run: Duration in seconds for each run
        """
        for _ in range(repeats):
            self.start()
            time.sleep(duration_per_run)
            self.stop()

    def __enter__(self) -> "SmartTimer":
        """Context manager entry - starts the timer"""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: Any | None,
    ) -> bool:
        """Context manager exit - stops the timer"""
        self.stop()
        return False


class TimerManager:
    """Manager for multiple timers."""

    def __init__(self):
        self.timers: dict[str, SmartTimer] = {}

    def create_timer(self, task_name: str) -> None:
        """Create a new timer with the given task name."""
        if task_name not in self.timers:
            self.timers[task_name] = SmartTimer(task_name)

    def get_timer(self, task_name: str) -> SmartTimer | None:
        """Get a timer by task name, returns None if not found."""
        return self.timers.get(task_name)

    def remove_timer(self, task_name: str) -> None:
        """Remove a timer by task name."""
        if task_name in self.timers:
            del self.timers[task_name]

    def list_timers(self):
        """Get a list of all timer names.

        Returns:
            List of timer names
        """
        return list(self.timers.keys())
