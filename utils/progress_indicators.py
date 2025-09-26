"""
CLI Progress Indicators for DinoAir 2.0
Provides simple progress indicators for command-line operations
"""

import sys
import time
from collections.abc import Callable, Generator, Sequence
from typing import Any


class ProgressBar:
    """Simple progress bar for command-line operations"""

    def __init__(self, total: int, width: int = 50, prefix: str = "Progress"):
        self.total = total
        self.width = width
        self.prefix = prefix
        self.current = 0
        self.start_time = time.time()

    def update(self, amount: int = 1, suffix: str = ""):
        """Update progress bar"""
        self.current += amount
        self.current = min(self.current, self.total)

        percent = 100 * (self.current / float(self.total))
        filled_length = int(self.width * self.current // self.total)
        bar_str = "█" * filled_length + "-" * (self.width - filled_length)

        elapsed = time.time() - self.start_time
        if self.current > 0 and self.current < self.total:
            eta = elapsed * (self.total - self.current) / self.current
            eta_str = f" ETA: {eta:.1f}s"
        else:
            eta_str = ""

        output = (
            f"\r{self.prefix}: |{bar_str}| {percent:.1f}% "
            f"({self.current}/{self.total}){eta_str} {suffix}"
        )
        sys.stdout.write(output)
        sys.stdout.flush()

        if self.current >= self.total:
            sys.stdout.write("\n")

    def finish(self, message: str = "Complete!"):
        """Finish progress bar with message"""
        self.current = self.total
        self.update(0, message)


class Spinner:
    """Simple spinner for indeterminate progress"""

    def __init__(self, message: str = "Working"):
        self.message = message
        self.spinning = False
        self.chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.index = 0

    def start(self):
        """Start spinner"""
        self.spinning = True
        self._spin()

    def _spin(self):
        """Show spinner animation"""
        if self.spinning:
            sys.stdout.write(f"\r{self.chars[self.index]} {self.message}")
            sys.stdout.flush()
            self.index = (self.index + 1) % len(self.chars)

    def stop(self, message: str = "Done!"):
        """Stop spinner with message"""
        self.spinning = False
        sys.stdout.write(f"\r✓ {message}\n")
        sys.stdout.flush()

    def tick(self) -> None:
        """Advance the spinner one frame (public wrapper to avoid accessing _spin externally)."""
        self._spin()


def with_progress(
    items: Sequence[Any],
    description: str = "Processing",
    process_func: Callable[[Any], Any] | None = None,
) -> Generator[Any, None, None]:
    """
    Context manager for processing items with progress bar

    Args:
        items: List of items to process
        description: Description for progress bar
        process_func: Optional function to apply to each item
    """
    progress = ProgressBar(len(items), prefix=description)

    for i, item in enumerate(items):
        result = process_func(item) if process_func else item

        progress.update(1, f"Item {i + 1}")

        if process_func:
            yield result
        else:
            yield item

    progress.finish()


class StepProgress:
    """Multi-step progress indicator"""

    def __init__(self, steps: list[str]):
        self.steps = steps
        self.current_step = 0
        self.total_steps = len(steps)

    def next_step(self, status: str = "✓"):
        """Move to next step"""
        if self.current_step < self.total_steps:
            self.current_step += 1

    def complete(self):
        """Mark all steps as complete"""
        while self.current_step < self.total_steps:
            self.next_step()


# Example usage functions
def demo_progress_bar():
    """Demo progress bar functionality"""
    progress = ProgressBar(100, prefix="Processing")

    for i in range(100):
        time.sleep(0.01)  # Simulate work
        progress.update(1, f"Processing item {i + 1}")

    progress.finish("All items processed!")


def demo_spinner():
    """Demo spinner functionality"""
    spinner = Spinner("Loading data")
    spinner.start()

    # Simulate work
    for _ in range(30):
        time.sleep(0.1)
        spinner.tick()

    spinner.stop("Data loaded successfully!")


def demo_step_progress():
    """Demo step progress functionality"""
    steps = [
        "Initialize system",
        "Load configuration",
        "Connect to database",
        "Process data",
        "Generate report",
    ]

    progress = StepProgress(steps)

    for _ in range(len(steps)):
        time.sleep(0.5)  # Simulate work
        progress.next_step()

    progress.complete()


if __name__ == "__main__":
    demo_progress_bar()

    demo_spinner()

    demo_step_progress()
