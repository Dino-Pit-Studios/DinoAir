from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any


@dataclass
class CalendarEvent:
    """
    Represents a calendar event with details such as title, description, event timing,
    participants, and additional metadata.
    """

    id: str
    title: str
    description: str = ""
    event_type: str = "meeting"
    status: str = "scheduled"
    event_date: str | None = None  # ISO date string YYYY-MM-DD
    start_time: str | None = None  # HH:MM:SS
    end_time: str | None = None  # HH:MM:SS
    all_day: bool = False
    location: str = ""
    participants: list[str] = field(default_factory=list)
    project_id: str | None = None
    chat_session_id: str | None = None
    recurrence_pattern: str | None = None
    recurrence_rule: str | None = None
    reminder_minutes_before: int | None = None
    reminder_sent: bool = False
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    color: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalendarEvent:
        """Create from dict.

        Args:
            data: Dictionary containing calendar event data

        Returns:
            CalendarEvent instance created from the provided data
        """
        parts = data or {}
        participants = parts.get("participants")
        if isinstance(participants, str):
            participants_list = [p for p in (participants.split(",") if participants else []) if p]
        else:
            participants_list = list(participants or [])
        return cls(
            id=str(parts.get("id", "")),
            title=str(parts.get("title", "")),
            description=str(parts.get("description", "")),
            event_type=str(parts.get("event_type", "meeting")),
            status=str(parts.get("status", "scheduled")),
            event_date=parts.get("event_date"),
            start_time=parts.get("start_time"),
            end_time=parts.get("end_time"),
            all_day=bool(parts.get("all_day", False)),
            location=str(parts.get("location", "")),
            participants=participants_list,
            project_id=parts.get("project_id"),
            chat_session_id=parts.get("chat_session_id"),
            recurrence_pattern=parts.get("recurrence_pattern"),
            recurrence_rule=parts.get("recurrence_rule"),
            reminder_minutes_before=parts.get("reminder_minutes_before"),
            reminder_sent=bool(parts.get("reminder_sent", False)),
            tags=list(parts.get("tags", []) if isinstance(parts.get("tags"), list) else []),
            notes=str(parts.get("notes", "")),
            color=parts.get("color"),
            metadata=parts.get("metadata"),
            created_at=parts.get("created_at"),
            updated_at=parts.get("updated_at"),
            completed_at=parts.get("completed_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict.

        Returns:
            Dictionary representation of the calendar event
        """
        # participants are stored as comma-separated string by DB layer
        participants_str = ",".join(self.participants) if self.participants else ""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "event_type": self.event_type,
            "status": self.status,
            "event_date": self.event_date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "all_day": self.all_day,
            "location": self.location,
            "participants": participants_str,
            "project_id": self.project_id,
            "chat_session_id": self.chat_session_id,
            "recurrence_pattern": self.recurrence_pattern,
            "recurrence_rule": self.recurrence_rule,
            "reminder_minutes_before": self.reminder_minutes_before,
            "reminder_sent": self.reminder_sent,
            "tags": self.tags,
            "notes": self.notes,
            "color": self.color,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }

    def get_datetime(self) -> datetime | None:
        """Combine event_date and start_time to a datetime object if possible."""
        try:
            if not self.event_date:
                return None
            d = date.fromisoformat(self.event_date)
            if self.all_day or not self.start_time:
                # Default to midnight if all-day or no start time
                t = time(0, 0)
            else:
                # start_time may be HH:MM or HH:MM:SS
                parts = self.start_time.split(":")
                if len(parts) == 2:
                    t = time(int(parts[0]), int(parts[1]))
                else:
                    t = time(int(parts[0]), int(parts[1]), int(parts[2]))
            return datetime.combine(d, t)
        except Exception:
            return None
