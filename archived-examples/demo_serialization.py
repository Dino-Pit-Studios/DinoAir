"""
Demonstration of the new model serialization patterns.

This script shows how the new base classes ensure consistent serialization:
- Tags and participants are always arrays in the model layer
- They're automatically flattened to comma-separated strings in the repository layer
- Clear separation between model and database concerns
"""

import contextlib
import sys
from datetime import datetime
from pathlib import Path

from .artifact_v2 import Artifact
from .calendar_event_v2 import CalendarEvent
from .note_v2 import Note

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent))


def demonstrate_note_serialization():
    """Demonstrate Note model serialization patterns."""

    # Create a note with tags
    note = Note(
        id="note-123",
        title="Project Planning",
        content="Need to plan the next sprint",
        tags=["planning", "sprint", "project-management"],
        project_id="proj-456",
    )

    # Model layer serialization (tags as array)
    note.to_model_dict()

    # Repository layer serialization (tags as comma-separated string)
    db_data = note.to_db_dict()

    # Demonstrate round-trip from repository format
    Note.from_dict(db_data)


def demonstrate_calendar_event_serialization():
    """Demonstrate CalendarEvent model serialization patterns."""

    # Create a calendar event with tags and participants
    event = CalendarEvent(
        id="event-789",
        title="Sprint Planning Meeting",
        description="Plan upcoming sprint tasks",
        location="Conference Room A",
        start_time=datetime(2024, 3, 15, 10, 0),
        end_time=datetime(2024, 3, 15, 11, 30),
        tags=["meeting", "planning", "sprint"],
    )
    # Set participants separately (from mixin)
    event.participants = ["alice@company.com", "bob@company.com", "charlie@company.com"]

    # Model layer serialization (arrays)
    event.to_model_dict()

    # Repository layer serialization (comma-separated strings)
    db_data = event.to_db_dict()

    # Demonstrate round-trip from repository format
    CalendarEvent.from_dict(db_data)


def demonstrate_artifact_serialization():
    """Demonstrate Artifact model serialization patterns."""

    # Create an artifact with tags
    artifact = Artifact(
        id="artifact-101",
        name="Design Mockups",
        file_path="/uploads/designs/mockups.psd",
        file_type="image/psd",
        size_bytes=15728640,  # 15 MB
        description="UI mockups for the new dashboard",
        tags=["design", "ui", "dashboard", "mockups"],
    )

    # Model layer serialization (tags as array)
    artifact.to_model_dict()

    # Repository layer serialization (tags as comma-separated string)
    artifact.to_db_dict()


def demonstrate_validation():
    """Demonstrate model validation."""

    from base import validate_model_invariants

    # Valid model
    note = Note(title="Valid Note", tags=["valid", "tags"])

    with contextlib.suppress(ValueError):
        validate_model_invariants(note)

    # Invalid model (empty title)
    try:
        invalid_note = Note(title="", tags=["test"])
        validate_model_invariants(invalid_note)
    except ValueError:
        pass


if __name__ == "__main__":
    demonstrate_note_serialization()
    demonstrate_calendar_event_serialization()
    demonstrate_artifact_serialization()
    demonstrate_validation()
