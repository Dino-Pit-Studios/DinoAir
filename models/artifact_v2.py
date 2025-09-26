"""
Updated Artifact model with consistent serialization patterns.

This version uses the new base model classes to ensure tags are always
arrays in the model layer and only flattened in the repository layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import TaggedModel, normalize_tags


@dataclass
class Artifact(TaggedModel):
    """Artifact model with consistent tag serialization patterns."""

    name: str = ""
    file_path: str = ""
    file_type: str = ""
    size_bytes: int = 0
    description: str = ""

    def _common_fields(self) -> dict[str, Any]:
        """Common field serialization for both model and repository layers."""
        return {
            "name": self.name,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "size_bytes": self.size_bytes,
            "description": self.description,
        }

    def _serialize_for_model(self) -> dict[str, Any]:
        """Serialize for model layer with tags as array."""
        data = super()._serialize_for_model()
        data.update(self._common_fields())
        return data

    def _serialize_for_repository(self) -> dict[str, Any]:
        """Serialize for repository layer with tags as comma-separated string."""
        data = super()._serialize_for_repository()
        data.update(self._common_fields())
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Artifact:
        """Create Artifact from dictionary, handling both model and repository formats."""
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            file_path=str(data.get("file_path", "")),
            file_type=str(data.get("file_type", "")),
            size_bytes=int(data.get("size_bytes", 0)),
            description=str(data.get("description", "")),
            tags=normalize_tags(data.get("tags")),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    # Convenience methods
    def get_file_path(self) -> Path:
        """Get file path as Path object."""
        return Path(self.file_path)

    def get_file_extension(self) -> str:
        """Get file extension from file path."""
        return self.get_file_path().suffix.lower()

    def get_file_name(self) -> str:
        """Get filename from file path."""
        return self.get_file_path().name

    def size_mb(self) -> float:
        """Get size in megabytes."""
        return self.size_bytes / (1024 * 1024)

    def size_kb(self) -> float:
        """Get size in kilobytes."""
        return self.size_bytes / 1024
