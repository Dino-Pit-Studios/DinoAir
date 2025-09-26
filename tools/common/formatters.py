"""Common formatters for Note and Project models.

These helpers convert domain models into plain dicts with stable shapes that match
existing tool outputs. Pure functions with no side effects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from models.note import Note
    from models.project import Project


def format_note(note: Note, preview_len: int | None = None) -> dict[str, Any]:
    """Format a Note into a dictionary suitable for tool responses.

    If preview_len is None, include full content. Otherwise, truncate to preview_len
    and append "..." only if truncation occurred.

    Returns keys:
      - id, title, content, tags, project_id, created_at, updated_at
    """
    content = note.content
    if preview_len is not None:
        preview_len = max(0, int(preview_len))
        content = content[:preview_len] + "..." if len(content) > preview_len else content

    return {
        "id": note.id,
        "title": note.title,
        "content": content,
        "tags": note.tags,
        "project_id": note.project_id,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


def format_project(project: Project) -> dict[str, Any]:
    """Format a Project into a dictionary with keys used across tools.

    Returns keys exactly as used across tools:
      - id, name, description, status, color, icon, parent_project_id, tags,
        metadata (if attribute exists), created_at, updated_at, completed_at, archived_at

    Include completed_at and archived_at even if None to preserve shape.
    """
    data: dict[str, Any] = {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        # Ensure status is serialized consistently (enum or str)
        "status": (project.status.value if hasattr(project.status, "value") else project.status),
        "color": project.color,
        "icon": project.icon,
        "parent_project_id": project.parent_project_id,
        "tags": project.tags,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "completed_at": project.completed_at,
        "archived_at": project.archived_at,
    }

    # Include metadata if attribute exists on the model
    if hasattr(project, "metadata"):
        data["metadata"] = project.metadata  # type: ignore[attr-defined]

    return data
