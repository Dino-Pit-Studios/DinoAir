"""Minimal model stubs for testing without extensive mocks"""

from datetime import date, datetime, time
from typing import Any


class CalendarEvent:
    """Minimal CalendarEvent model"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "test-event-1")
        self.title = kwargs.get("title", "Test Event")
        self.description = kwargs.get("description", "")
        self.event_type = kwargs.get("event_type", "meeting")
        self.status = kwargs.get("status", "scheduled")
        self.event_date = kwargs.get("event_date", date.today().isoformat())
        self.start_time = kwargs.get("start_time", "09:00:00")
        self.end_time = kwargs.get("end_time", "10:00:00")
        self.all_day = kwargs.get("all_day", False)
        self.location = kwargs.get("location", "")
        self.participants = kwargs.get("participants", [])
        self.project_id = kwargs.get("project_id")
        self.chat_session_id = kwargs.get("chat_session_id")
        self.recurrence_pattern = kwargs.get("recurrence_pattern", "none")
        self.recurrence_rule = kwargs.get("recurrence_rule")
        self.reminder_minutes_before = kwargs.get("reminder_minutes_before")
        self.reminder_sent = kwargs.get("reminder_sent", False)
        self.tags = kwargs.get("tags", [])
        self.notes = kwargs.get("notes", "")
        self.color = kwargs.get("color", "#007bff")
        self.metadata = kwargs.get("metadata", {})
        self.created_at = kwargs.get("created_at", datetime.now().isoformat())
        self.updated_at = kwargs.get("updated_at", datetime.now().isoformat())
        self.completed_at = kwargs.get("completed_at")

    def to_dict(self) -> dict[str, Any]:
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
            "participants": self.participants,
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
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalendarEvent":
        return cls(**data)

    def get_datetime(self):
        """Get datetime object from event date and time"""
        event_date = date.fromisoformat(self.event_date)
        start_time = time.fromisoformat(self.start_time) if self.start_time else time(0, 0)
        return datetime.combine(event_date, start_time)


class Artifact:
    """Minimal Artifact model"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "test-artifact-1")
        self.name = kwargs.get("name", "Test Artifact")
        self.description = kwargs.get("description", "")
        self.content_type = kwargs.get("content_type", "text/plain")
        self.size = kwargs.get("size", 0)
        self.file_path = kwargs.get("file_path")
        self.collection_id = kwargs.get("collection_id")
        self.project_id = kwargs.get("project_id")
        self.tags = kwargs.get("tags", [])
        self.metadata = kwargs.get("metadata", {})
        self.created_at = kwargs.get("created_at", datetime.now().isoformat())
        self.updated_at = kwargs.get("updated_at", datetime.now().isoformat())


class ArtifactCollection:
    """Minimal ArtifactCollection model"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "test-collection-1")
        self.name = kwargs.get("name", "Test Collection")
        self.description = kwargs.get("description", "")
        self.parent_id = kwargs.get("parent_id")
        self.created_at = kwargs.get("created_at", datetime.now().isoformat())


class ArtifactVersion:
    """Minimal ArtifactVersion model"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "test-version-1")
        self.artifact_id = kwargs.get("artifact_id", "test-artifact-1")
        self.version_number = kwargs.get("version_number", 1)
        self.file_path = kwargs.get("file_path", "/test/path")
        self.size = kwargs.get("size", 100)
        self.created_at = kwargs.get("created_at", datetime.now().isoformat())


class Note:
    """Minimal Note model"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "test-note-1")
        self.title = kwargs.get("title", "Test Note")
        self.content = kwargs.get("content", "")
        self.tags = kwargs.get("tags", [])
        self.project_id = kwargs.get("project_id")
        self.created_at = kwargs.get("created_at", datetime.now().isoformat())
        self.updated_at = kwargs.get("updated_at", datetime.now().isoformat())
        self.deleted_at = kwargs.get("deleted_at")


class Project:
    """Minimal Project model"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "test-project-1")
        self.name = kwargs.get("name", "Test Project")
        self.description = kwargs.get("description", "")
        self.status = kwargs.get("status", "active")
        self.parent_project_id = kwargs.get("parent_project_id")
        self.tags = kwargs.get("tags", [])
        self.created_at = kwargs.get("created_at", datetime.now().isoformat())
        self.updated_at = kwargs.get("updated_at", datetime.now().isoformat())


class ProjectStatistics:
    """Minimal ProjectStatistics model"""


class WatchdogMetricsManager:
    """Minimal WatchdogMetricsManager model"""
