"""
Simple demonstration of model serialization patterns.

This script shows the key concepts without complex imports.
"""

from dataclasses import dataclass, field
from typing import Any

# Type aliases
TagList = list[str]


def normalize_tags(tags) -> TagList:
    """Normalize tags input to a list of strings."""
    if not tags:
        return []
    if isinstance(tags, str):
        # Handle comma-separated string from repository layer
        return [tag.strip() for tag in tags.split(",") if tag.strip()]
    if isinstance(tags, list):
        # Handle list from model layer
        return [str(tag) for tag in tags if str(tag).strip()]
    return []


def serialize_tags_for_db(tags: TagList) -> str:
    """Serialize tags for repository layer as comma-separated string."""
    return ",".join(tags) if tags else ""


@dataclass
class SimpleNote:
    """Simple note model demonstrating serialization patterns."""

    title: str = ""
    content: str = ""
    tags: TagList = field(default_factory=list)

    def to_model_dict(self) -> dict[str, Any]:
        """Model layer format - tags as array."""
        return {
            "title": self.title,
            "content": self.content,
            "tags": self.tags,  # Array
        }

    def to_db_dict(self) -> dict[str, Any]:
        """Repository layer format - tags as comma-separated string."""
        return {
            "title": self.title,
            "content": self.content,
            "tags": serialize_tags_for_db(self.tags),  # String
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimpleNote":
        """Create from either format."""
        return cls(
            title=str(data.get("title", "")),
            content=str(data.get("content", "")),
            tags=normalize_tags(data.get("tags")),
        )


def main():
    # Create a note with tags
    note = SimpleNote(
        title="Project Planning",
        content="Need to plan the next sprint",
        tags=["planning", "sprint", "project-management"],
    )

    # Model layer serialization (tags as array)
    note.to_model_dict()

    # Repository layer serialization (tags as string)
    db_data = note.to_db_dict()

    # Round-trip from repository format
    SimpleNote.from_dict(db_data)

    # Show the pattern handles both input formats

    # From model format (array)
    SimpleNote.from_dict({"title": "From Model", "tags": ["tag1", "tag2", "tag3"]})

    # From repository format (string)
    SimpleNote.from_dict({"title": "From DB", "tags": "tag1,tag2,tag3"})


if __name__ == "__main__":
    main()
