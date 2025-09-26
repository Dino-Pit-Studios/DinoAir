"""Database factory helpers for tool modules.

These small factory functions centralize construction of database classes.
They are intentionally thin and do not swallow exceptions; callers should handle errors.
"""

from __future__ import annotations

# Use absolute imports to keep module importable regardless of package execution context.
from database.file_search_db import FileSearchDB
from database.initialize_db import DatabaseManager
from database.notes_db import NotesDatabase
from database.projects_db import ProjectsDatabase


def get_file_search_db(user_name: str) -> FileSearchDB:
    """Return a FileSearchDB instance for the given user."""
    return FileSearchDB(user_name)


def get_notes_db(user_name: str) -> NotesDatabase:
    """Return a NotesDatabase instance for the given user."""
    return NotesDatabase(user_name)


def get_projects_db(user_name: str) -> ProjectsDatabase:
    """Return a ProjectsDatabase instance for the given user.

    Constructs a DatabaseManager first, then uses it to construct ProjectsDatabase.
    """
    db_manager = DatabaseManager(user_name)
    return ProjectsDatabase(db_manager)
