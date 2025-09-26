from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Note:
    """Note model with consistent type hints and serialization."""

    id: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    project_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # content_html is a derived cache of `content`; it is always recomputed to prevent inconsistencies
    content_html: str | None = None

    def __post_init__(self) -> None:
        # Always derive HTML from content to avoid inconsistencies with persisted content_html
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
        """Common field serialization used by to_dict."""
        return {
            "title": self.title,
            "content": self.content,
            "project_id": self.project_id,
            "content_html": self.content_html,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Note:
        # Ignore incoming content_html to prevent mismatches; it will be derived in __post_init__
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            content=str(data.get("content", "")),
            tags=(list(data.get("tags", [])) if isinstance(data.get("tags"), list) else []),
            project_id=data.get("project_id"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            # content_html is intentionally not accepted from input to avoid inconsistencies
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "tags": list(self.tags or []),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        data.update(self._common_fields())
        return data

    def __eq__(self, other: object) -> bool:
        """Check equality based on ID if both notes have IDs."""
        if not isinstance(other, Note):
            return False
        # If both have meaningful IDs, compare by ID
        if self.id and other.id:
            return self.id == other.id
        # Otherwise, compare by title and content
        return self.title == other.title and self.content == other.content

    def __hash__(self) -> int:
        """Hash based on ID if available, otherwise on title."""
        if self.id:
            return hash(self.id)
        return hash((self.title, self.content))

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        # Use a constant for content preview length
        content_preview_length = 50
        content_preview = (
            (self.content[:content_preview_length] + "...")
            if len(self.content) > content_preview_length
            else self.content
        )
        return (
            f"Note("
            f"id='{self.id}', "
            f"title='{self.title}', "
            f"content='{content_preview}', "
            f"tags={self.tags}, "
            f"project_id='{self.project_id}'"
            f")"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        project_info = f" (in {self.project_id})" if self.project_id else ""
        tag_info = f" #{', #'.join(self.tags)}" if self.tags else ""
        return f"📝 {self.title}{project_info}{tag_info}"
