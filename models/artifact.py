"""Artifact DTOs for database/artifacts_db integration."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Union

JsonLike = Union[dict[str, Any], list[Any], str]


def _dump_json_if_needed(value: JsonLike | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _load_json_list(value: str | list[str] | None) -> list[str] | None:
    """Safely decode JSON string to list, handling None and invalid JSON."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return decoded
            # If it's not a list, return the original string wrapped in a list
            return [value]
        except (json.JSONDecodeError, TypeError):
            # If JSON decode fails, return the original string wrapped in a list
            return [value]


def _load_json_dict(value: str | dict[str, Any] | None) -> dict[str, Any] | None:
    """Safely decode JSON string to dict, handling None and invalid JSON."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, dict):
                return decoded
            # If it's not a dict, return None or could wrap in a dict
            return None
        except (json.JSONDecodeError, TypeError):
            return None


def _list_to_string(value: list[str] | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ",".join(value)
    return value


def _apply_list_to_json_string_if_list(data: dict[str, Any], fields: tuple[str, ...]) -> None:
    """Mutate dict by JSON-encoding values for provided fields only when they are lists."""
    for field in fields:
        value = data.get(field)
        if isinstance(value, list):
            # Keep semantics identical to existing code: direct json.dumps without try/except
            data[field] = json.dumps(value)


def _apply_json_dump(data: dict[str, Any], fields: tuple[str, ...]) -> None:
    """Mutate dict by applying _dump_json_if_needed to the provided fields."""
    for field in fields:
        data[field] = _dump_json_if_needed(data.get(field))


@dataclass
class Artifact:
    """Represents an artifact with metadata and content, providing methods to serialize to/from dict and compute storage paths."""

    id: str
    name: str | None = None
    description: str | None = None
    content_type: str = "text"
    status: str = "active"
    content: str | None = None
    content_path: str | None = None
    size_bytes: int = 0
    mime_type: str | None = None
    checksum: str | None = None
    collection_id: str | None = None
    parent_id: str | None = None
    version: int = 1
    is_latest: bool = True
    encrypted_fields: str | list[str] | None = None
    encryption_key_id: str | None = None
    project_id: str | None = None
    chat_session_id: str | None = None
    note_id: str | None = None
    tags: str | list[str] | None = None
    metadata: JsonLike | None = None
    properties: JsonLike | None = None
    created_at: str | None = None
    updated_at: str | None = None
    accessed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        # Create a shallow copy to avoid in-place mutation of asdict() output
        data = asdict(self).copy()

        # JSON-encode list fields for safe storage (strings left as-is)
        _apply_list_to_json_string_if_list(data, ("tags", "encrypted_fields"))

        # Serialize dict-like fields to JSON strings for database storage
        _apply_json_dump(data, ("metadata", "properties"))

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Artifact:
        return cls(
            id=str(data.get("id") or data.get("artifact_id") or ""),
            name=data.get("name"),
            description=data.get("description"),
            content_type=data.get("content_type", "text"),
            status=data.get("status", "active"),
            content=data.get("content"),
            content_path=data.get("content_path"),
            size_bytes=int(data.get("size_bytes") or 0),
            mime_type=data.get("mime_type"),
            checksum=data.get("checksum"),
            collection_id=data.get("collection_id"),
            parent_id=data.get("parent_id"),
            version=int(data.get("version") or 1),
            is_latest=bool(data.get("is_latest") if data.get("is_latest") is not None else True),
            encrypted_fields=_load_json_list(data.get("encrypted_fields")),
            encryption_key_id=data.get("encryption_key_id"),
            project_id=data.get("project_id"),
            chat_session_id=data.get("chat_session_id"),
            note_id=data.get("note_id"),
            tags=_load_json_list(data.get("tags")),
            metadata=_load_json_dict(data.get("metadata")),
            properties=_load_json_dict(data.get("properties")),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            accessed_at=data.get("accessed_at"),
        )

    def get_storage_path(self, username: str) -> Path:
        # Use created_at if available and ISO-like; fallback to current UTC
        try:
            dt = datetime.fromisoformat((self.created_at or "").replace("Z", "+00:00"))
        except (ValueError, TypeError):
            dt = datetime.utcnow()
        return Path("user_data") / username / "artifacts" / f"{dt:%Y}" / f"{dt:%m}" / self.id


@dataclass
class ArtifactCollection:
    """Represents a collection of artifacts, maintaining metadata, counts, and providing serialization utilities."""

    id: str
    name: str
    description: str | None = None
    parent_id: str | None = None
    project_id: str | None = None
    is_encrypted: bool = False
    is_public: bool = False
    tags: str | list[str] | None = None
    properties: JsonLike | None = None
    artifact_count: int = 0
    total_size_bytes: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parent_id": self.parent_id,
            "project_id": self.project_id,
            "is_encrypted": self.is_encrypted,
            "is_public": self.is_public,
            "tags": _list_to_string(self.tags),
            "properties": _dump_json_if_needed(self.properties),
            "artifact_count": self.artifact_count,
            "total_size_bytes": self.total_size_bytes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactCollection:
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            description=data.get("description"),
            parent_id=data.get("parent_id"),
            project_id=data.get("project_id"),
            is_encrypted=bool(data.get("is_encrypted")),
            is_public=bool(data.get("is_public")),
            tags=data.get("tags"),
            properties=data.get("properties"),
            artifact_count=int(data.get("artifact_count") or 0),
            total_size_bytes=int(data.get("total_size_bytes") or 0),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class ArtifactVersion:
    """Represents a specific version of an artifact, tracking changes and providing serialization to/from dict."""

    id: str
    artifact_id: str
    version_number: int
    artifact_data: JsonLike
    change_summary: str | None = None
    changed_by: str | None = None
    changed_fields: list[str] | str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "artifact_id": self.artifact_id,
            "version_number": int(self.version_number),
            "artifact_data": _dump_json_if_needed(self.artifact_data),
            "change_summary": self.change_summary,
            "changed_by": self.changed_by,
            "changed_fields": _dump_json_if_needed(
                self.changed_fields if isinstance(self.changed_fields, list) else None
            ),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactVersion:
        return cls(
            id=str(data.get("id", "")),
            artifact_id=str(data.get("artifact_id", "")),
            version_number=int(data.get("version_number") or 1),
            artifact_data=data.get("artifact_data") or {},
            change_summary=data.get("change_summary"),
            changed_by=data.get("changed_by"),
            changed_fields=data.get("changed_fields"),
            created_at=data.get("created_at"),
        )
