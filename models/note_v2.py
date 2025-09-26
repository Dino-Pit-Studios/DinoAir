"""
Updated Note model with consistent serialization patterns.

This version uses the new base model classes to ensure tags are always
arrays in the model layer and only flattened in the repository layer.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any

from models.base import TaggedModel, normalize_tags


@dataclass
class Note(TaggedModel):
    """Note model with consistent tag serialization patterns."""

    title: str = ""
    content: str = ""
    project_id: str | None = None
    content_html: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Always derive HTML from content to avoid inconsistencies."""
        self.content_html = self._render_html_from_content(self.content)

    @staticmethod
    def _render_html_from_content(content: str) -> str:
        """
        Render a safe, minimal HTML version of content:
        - Escape HTML
        - Convert single newlines to <br>
        - Convert double newlines to paragraph breaks
        """
        escaped = html.escape(content or "")
        if not escaped:
            return ""
        paragraphs = [p.replace("\n", "<br>") for p in escaped.split("\n\n")]
        return "<p>" + "</p><p>".join(paragraphs) + "</p>"

    def sync_html(self) -> None:
        """Force-recompute HTML from the current content."""
        self.content_html = self._render_html_from_content(self.content)

    def update_content(self, new_content: str) -> None:
        """Update content and keep content_html consistent by always deriving it."""
        self.content = new_content
        self.content_html = self._render_html_from_content(new_content)

    def _common_fields(self) -> dict[str, Any]:
        """Common field serialization for both model and repository layers."""
        return {
            "title": self.title,
            "content": self.content,
            "project_id": self.project_id,
            "content_html": self.content_html,
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
    def from_dict(cls, data: dict[str, Any]) -> Note:
        """Create Note from dictionary, handling both model and repository formats."""
        # Ignore incoming content_html to prevent mismatches; it will be derived in __post_init__
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            content=str(data.get("content", "")),
            tags=normalize_tags(data.get("tags")),
            project_id=data.get("project_id"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
