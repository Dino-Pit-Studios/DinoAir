"""
Appointments utilities

This module will provide calendar/appointment helpers for future integration.
For now, it intentionally contains no executable GUI code.

Notes:
- Keep logic self-contained; GUI wiring happens in the existing PySide6 layer.
- Persist events via DatabaseManager when implemented.

Example (reference only, not executed here):

    From PySide6.QtWidgets import QWidget, QVBoxLayout, QCalendarWidget, QLabel
    from PySide6.QtCore import QDate

    Class CalendarTool(QWidget):
        def __init__(self):
            super().__init__()
            layout = QVBoxLayout(self)
            self.calendar = QCalendarWidget()
            self.info_label = QLabel("Select a date")
            self.calendar.setGridVisible(True)
            self.calendar.clicked.connect(lambda d: self.info_label.setText(d.toString()))
            layout.addWidget(self.calendar)
            layout.addWidget(self.info_label)

"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Appointment:
    """Represents a single appointment."""

    title: str
    start_time: datetime
    end_time: datetime
    description: str = ""


def create_appointment(
    title: str, start_time: str, end_time: str, description: str = ""
) -> Appointment:
    """Creates and returns an Appointment object."""
    return Appointment(
        title=normalize_event_title(title),
        start_time=datetime.fromisoformat(start_time),
        end_time=datetime.fromisoformat(end_time),
        description=description,
    )


def normalize_event_title(title: str) -> str:
    """Return a sanitized, title-cased event title."""
    return " ".join(title.split()).title()


def is_valid_date_string(date_str: str) -> bool:
    """Return True if date_str is exactly YYYY-MM-DD and represents a real calendar date."""
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
        # Enforce exact formatting (rejects non-zero-padded components, whitespace, etc.)
        return date_str == parsed.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return False
