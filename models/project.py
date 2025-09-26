from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ProjectStatus(str, Enum):
    """Project status enumeration with string values."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


@dataclass
class Project:
    """Project model with consistent type hints and Optional field handling."""

    id: str
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.ACTIVE
    color: str | None = None
    icon: str | None = None
    parent_project_id: str | None = None
    # Tags: consistent semantics - list[str] in model, comma-separated in DB
    tags: list[str] = field(default_factory=list)
    # Metadata: dict in model, JSON string in DB
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    archived_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        """Create Project from dictionary with proper type conversion."""
        # Handle tags conversion from DB format (string) to model format (list)
        tags_raw = data.get("tags")
        if isinstance(tags_raw, str) and tags_raw:
            tags = [tag.strip() for tag in tags_raw.split(",") if tag.strip()]
        elif isinstance(tags_raw, list):
            tags = [str(tag) for tag in tags_raw]
        else:
            tags = []

        # Handle metadata conversion from DB format (JSON string) to model format (dict)
        metadata_raw = data.get("metadata")
        metadata: dict[str, Any] | None = None
        if isinstance(metadata_raw, str) and metadata_raw:
            try:
                parsed = json.loads(metadata_raw)
                metadata = parsed if isinstance(parsed, dict) else {"value": parsed}
            except (json.JSONDecodeError, TypeError):
                metadata = {"raw_value": metadata_raw}
        elif isinstance(metadata_raw, dict):
            metadata = metadata_raw

        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            status=ProjectStatus(str(data.get("status") or ProjectStatus.ACTIVE.value)),
            color=data.get("color"),
            icon=data.get("icon"),
            parent_project_id=data.get("parent_project_id"),
            tags=tags,
            metadata=metadata,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            completed_at=data.get("completed_at"),
            archived_at=data.get("archived_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with model-layer format (tags as list, metadata as dict)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": (
                self.status.value if isinstance(self.status, ProjectStatus) else str(self.status)
            ),
            "color": self.color,
            "icon": self.icon,
            "parent_project_id": self.parent_project_id,
            "tags": self.tags,  # List format for model layer
            "metadata": self.metadata,  # Dict format for model layer
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "archived_at": self.archived_at,
        }

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to dictionary with repository-layer format (tags as string, metadata as JSON)."""
        # Convert tags to comma-separated string for DB storage
        tags_str = ",".join(self.tags) if self.tags else ""

        # Convert metadata to JSON string for DB storage
        metadata_str: str | None = None
        if self.metadata is not None:
            try:
                metadata_str = json.dumps(self.metadata, ensure_ascii=False)
            except (TypeError, ValueError):
                metadata_str = json.dumps(
                    {"error": "serialization_failed", "raw": str(self.metadata)}
                )

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": (
                self.status.value if isinstance(self.status, ProjectStatus) else str(self.status)
            ),
            "color": self.color,
            "icon": self.icon,
            "parent_project_id": self.parent_project_id,
            "tags": tags_str,  # String format for DB layer
            "metadata": metadata_str,  # JSON string for DB layer
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "archived_at": self.archived_at,
        }

    def __eq__(self, other: object) -> bool:
        """Check equality based on ID if both projects have IDs."""
        if not isinstance(other, Project):
            return False
        # If both have meaningful IDs, compare by ID
        if self.id and other.id:
            return self.id == other.id
        # Otherwise, use name as identifier
        return self.name == other.name

    def __hash__(self) -> int:
        """Hash based on ID if available, otherwise on name."""
        if self.id:
            return hash(self.id)
        return hash(self.name)

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"Project("
            f"id='{self.id}', "
            f"name='{self.name}', "
            f"status={self.status.value}, "
            f"tags={self.tags}, "
            f"parent_project_id='{self.parent_project_id}'"
            f")"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        status_emoji = {
            ProjectStatus.ACTIVE: "🟢",
            ProjectStatus.COMPLETED: "✅",
            ProjectStatus.ARCHIVED: "📦",
        }
        emoji = status_emoji.get(self.status, "❓")
        parent_info = f" (child of {self.parent_project_id})" if self.parent_project_id else ""
        return f"{emoji} {self.name}{parent_info}"


@dataclass
class ProjectSummary:
    """Data class representing a concise summary of a project, including its ID, name, and recent activity metrics."""

    project_id: str
    project_name: str
    recent_activity_count: int = 0
    last_activity_date: datetime | None = None
    last_activity_type: str | None = None
    total_item_count: int = 0
    child_project_count: int = 0

    @classmethod
    def from_project(cls, project: Project) -> ProjectSummary:
        """Create from project.

        Args:
            project: Project instance to create summary from

        Returns:
            ProjectSummary instance with project ID and name
        """
        return cls(project_id=project.id, project_name=project.name)


@dataclass
class ProjectStatistics:
    """Data class representing detailed statistics of a project, including counts of notes, artifacts, calendar events, child projects, and activity metrics such as last activity date and completion percentage."""

    project_id: str
    project_name: str
    total_notes: int = 0
    total_artifacts: int = 0
    total_calendar_events: int = 0
    child_project_count: int = 0
    last_activity_date: datetime | None = None
    days_since_activity: int | None = None
    completed_items: int = 0
    total_items: int = 0
    completion_percentage: float = 0.0

    def calculate_days_since_activity(self) -> None:
        """Calculate days since last activity with proper error handling."""
        if not self.last_activity_date:
            self.days_since_activity = None
            return
        try:
            # last_activity_date may be datetime or iso string
            dt = self.last_activity_date
            if isinstance(self.last_activity_date, str):
                dt = datetime.fromisoformat(self.last_activity_date)
            if dt is not None:
                delta = datetime.now() - dt
                self.days_since_activity = max(delta.days, 0)
        except (ValueError, TypeError, AttributeError):
            self.days_since_activity = None

    def calculate_completion_percentage(self) -> None:
        """Calculate completion percentage with proper error handling."""
        try:
            self.completion_percentage = (
                (self.completed_items / self.total_items) * 100.0 if self.total_items else 0.0
            )
        except (ZeroDivisionError, TypeError, AttributeError):
            self.completion_percentage = 0.0
