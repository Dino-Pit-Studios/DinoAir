"""
Updated CalendarEvent model with consistent serialization patterns.

This version uses the new base model classes to ensure tags and participants
are always arrays in the model layer and only flattened in the repository layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .base import ParticipantMixin, TaggedModel, normalize_participants, normalize_tags


@dataclass
class CalendarEvent(TaggedModel, ParticipantMixin):
    """Calendar event model with consistent serialization patterns."""

    title: str = ""
    description: str = ""
    location: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    all_day: bool = False

    def _serialize_common_fields(self) -> dict[str, Any]:
        """Common field serialization used by both model and repository layers."""
        return {
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "all_day": self.all_day,
        }

    def _serialize_for_model(self) -> dict[str, Any]:
        """Serialize for model layer with tags and participants as arrays."""
        data = super()._serialize_for_model()
        data.update(self._serialize_participants_for_model())
        data.update(self._serialize_common_fields())
        return data

    def _serialize_for_repository(self) -> dict[str, Any]:
        """Serialize for repository layer with tags and participants as comma-separated strings."""
        data = super()._serialize_for_repository()
        data.update(self._serialize_participants_for_repository())
        data.update(self._serialize_common_fields())
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalendarEvent:
        """Create CalendarEvent from dictionary, handling both model and repository formats."""
        # Parse datetime fields
        start_time = None
        if data.get("start_time"):
            start_time = datetime.fromisoformat(data["start_time"])

        end_time = None
        if data.get("end_time"):
            end_time = datetime.fromisoformat(data["end_time"])

        event = cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            location=str(data.get("location", "")),
            start_time=start_time,
            end_time=end_time,
            all_day=bool(data.get("all_day", False)),
            tags=normalize_tags(data.get("tags")),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
        # Set participants separately since it's from a mixin
        event.participants = normalize_participants(data.get("participants"))
        return event

    # Convenience methods for date handling
    def get_start_date(self) -> date | None:
        """Get the start date (without time)."""
        return self.start_time.date() if self.start_time else None

    def get_end_date(self) -> date | None:
        """Get the end date (without time)."""
        return self.end_time.date() if self.end_time else None

    def is_multi_day(self) -> bool:
        """Check if event spans multiple days."""
        if not self.start_time or not self.end_time:
            return False
        return self.start_time.date() != self.end_time.date()

    def duration_minutes(self) -> int | None:
        """Get event duration in minutes."""
        if not self.start_time or not self.end_time:
            return None
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)
