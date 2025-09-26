"""
Base models and serialization utilities for DinoAir.

Provides consistent patterns for model serialization and validation,
ensuring tags are always arrays in models and only flattened in repository layer.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# Type aliases for clarity
JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
TagList = list[str]
ParticipantList = list[str]


class ModelSerializationMixin(ABC):
    """Abstract base class for models with standardized serialization patterns."""

    @abstractmethod
    def _serialize_for_model(self) -> dict[str, Any]:
        """Serialize for model layer (e.g., tags as arrays)."""
        raise NotImplementedError

    @abstractmethod
    def _serialize_for_repository(self) -> dict[str, Any]:
        """Serialize for repository layer (e.g., tags as comma-separated strings)."""
        raise NotImplementedError

    def to_model_dict(self) -> dict[str, Any]:
        """Public API: Get model-layer representation with tags/participants as arrays."""
        return self._serialize_for_model()

    def to_db_dict(self) -> dict[str, Any]:
        """Public API: Get repository-layer representation with flattened fields."""
        return self._serialize_for_repository()


def normalize_tags(tags: str | list[str] | None) -> TagList:
    """Normalize tags from various input formats to consistent array format.

    Args:
        tags: Tags as string (comma-separated), list, or None

    Returns:
        List of tags, empty if None
    """
    if tags is None:
        return []

    if isinstance(tags, str):
        # Handle comma-separated string from repository layer
        return [tag.strip() for tag in tags.split(",") if tag.strip()]

    if isinstance(tags, list):
        # Handle array from model layer
        return [str(tag).strip() for tag in tags if str(tag).strip()]

    # Fallback for unexpected types
    return []


def normalize_participants(participants: str | list[str] | None) -> ParticipantList:
    """Normalize participants from various input formats to consistent array format.

    Args:
        participants: Participants as string (comma-separated), list, or None

    Returns:
        List of participants, empty if None
    """
    if participants is None:
        return []

    if isinstance(participants, str):
        # Handle comma-separated string from repository layer
        return [p.strip() for p in participants.split(",") if p.strip()]

    if isinstance(participants, list):
        # Handle array from model layer
        return [str(p).strip() for p in participants if str(p).strip()]

    # Fallback for unexpected types
    return []


def serialize_tags_for_db(tags: TagList) -> str:
    """Serialize tags array to comma-separated string for repository layer.

    Args:
        tags: List of tags

    Returns:
        Comma-separated string, empty string if no tags
    """
    if not tags:
        return ""
    return ",".join(tag.strip() for tag in tags if tag.strip())


def serialize_participants_for_db(participants: ParticipantList) -> str:
    """Serialize participants array to comma-separated string for repository layer.

    Args:
        participants: List of participants

    Returns:
        Comma-separated string, empty string if no participants
    """
    if not participants:
        return ""
    return ",".join(p.strip() for p in participants if p.strip())


def normalize_json_metadata(
    metadata: str | dict[str, Any] | list[Any] | None,
) -> dict[str, Any] | None:
    """Normalize JSON metadata from string or dict format.

    Args:
        metadata: Metadata as JSON string, dict, or None

    Returns:
        Dictionary or None
    """
    if metadata is None:
        return None

    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except (json.JSONDecodeError, TypeError):
            return {"raw_value": metadata}

    if isinstance(metadata, dict):
        return metadata

    if isinstance(metadata, list):
        return {"items": metadata}

    # Fallback for unexpected types
    return {"value": str(metadata)}


def serialize_json_for_db(data: JsonValue | None) -> str | None:
    """Serialize JSON data to string for repository layer.

    Args:
        data: JSON-serializable data

    Returns:
        JSON string or None
    """
    if data is None:
        return None

    try:
        return json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError):
        # Fallback for non-serializable data
        return json.dumps({"error": "non_serializable", "value": str(data)})


@dataclass
class BaseModel(ModelSerializationMixin):
    """Base model with common fields and serialization patterns."""

    id: str
    created_at: str | None = None
    updated_at: str | None = None

    def _serialize_for_model(self) -> dict[str, Any]:
        """Default model serialization."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def _serialize_for_repository(self) -> dict[str, Any]:
        """Default repository serialization - same as model for base fields."""
        return self._serialize_for_model()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaseModel:
        """Create base model from dictionary."""
        return cls(
            id=str(data.get("id", "")),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class TaggedModel(ModelSerializationMixin):
    """Base model class for entities with tags."""

    id: str = ""
    tags: TagList = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None

    def _serialize_for_model(self) -> dict[str, Any]:
        """Serialize for model layer with tags as array."""
        return {
            "id": self.id,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def _serialize_for_repository(self) -> dict[str, Any]:
        """Serialize for repository layer with tags as comma-separated string."""
        return {
            "id": self.id,
            "tags": serialize_tags_for_db(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __eq__(self, other: object) -> bool:
        """Check equality based on ID if both objects have IDs, otherwise use dataclass equality."""
        if not isinstance(other, TaggedModel):
            return False
        # If both have meaningful IDs, compare by ID
        if self.id and other.id:
            return self.id == other.id
        # Otherwise, use field-by-field comparison
        return (
            self.id == other.id
            and self.tags == other.tags
            and self.created_at == other.created_at
            and self.updated_at == other.updated_at
        )

    def __hash__(self) -> int:
        """Hash based on ID if available, otherwise on immutable fields."""
        if self.id:
            return hash(self.id)
        return hash((tuple(self.tags), self.created_at, self.updated_at))

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        class_name = self.__class__.__name__
        fields = [
            f"id='{self.id}'",
            f"tags={self.tags}",
            f"created_at='{self.created_at}'",
            f"updated_at='{self.updated_at}'",
        ]
        return f"{class_name}({', '.join(fields)})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        if hasattr(self, "name") and self.name:
            return f"{self.__class__.__name__}(id='{self.id}', name='{self.name}')"
        if hasattr(self, "title") and self.title:
            return f"{self.__class__.__name__}(id='{self.id}', title='{self.title}')"
        return f"{self.__class__.__name__}(id='{self.id}')"


@dataclass
class ParticipantMixin:
    """Mixin for models that have participants."""

    participants: ParticipantList = field(default_factory=list)

    def _serialize_participants_for_model(self) -> dict[str, Any]:
        """Serialize participants for model layer."""
        return {"participants": self.participants}

    def _serialize_participants_for_repository(self) -> dict[str, Any]:
        """Serialize participants for repository layer."""
        return {"participants": serialize_participants_for_db(self.participants)}


def validate_model_invariants(model: ModelSerializationMixin) -> list[str]:
    """Validate model invariants and return list of violations.

    Args:
        model: Model to validate

    Returns:
        List of validation error messages
    """
    errors = []

    # Check that model serialization maintains arrays
    model_dict = model.to_model_dict()
    if hasattr(model, "tags") and "tags" in model_dict and not isinstance(model_dict["tags"], list):
        errors.append(
            f"Model serialization should maintain tags as array, got {type(model_dict['tags'])}"
        )

    if (
        hasattr(model, "participants")
        and "participants" in model_dict
        and not isinstance(model_dict["participants"], list)
    ):
        errors.append(
            f"Model serialization should maintain participants as array, got {type(model_dict['participants'])}"
        )

    # Check that repository serialization flattens arrays
    repo_dict = model.to_db_dict()
    if hasattr(model, "tags") and "tags" in repo_dict and not isinstance(repo_dict["tags"], str):
        errors.append(
            f"Repository serialization should flatten tags to string, got {type(repo_dict['tags'])}"
        )

    if (
        hasattr(model, "participants")
        and "participants" in repo_dict
        and not isinstance(repo_dict["participants"], str)
    ):
        errors.append(
            f"Repository serialization should flatten participants to string, got {type(repo_dict['participants'])}"
        )

    return errors
