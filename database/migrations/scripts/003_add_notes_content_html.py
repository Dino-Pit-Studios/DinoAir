"""
Migration: Add content_html column to notes table

This migration adds the content_html column to the note_list table
to support HTML rendering of note content.

Version: 003
Created: 2024-09-16
"""

import sqlite3

# Import will be resolved at runtime when loaded by migration runner
try:
    from database.migrations.base import BaseMigration, MigrationError
except ImportError:
    # Fallback for direct execution or different import paths
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).parent.parent))
    from base import BaseMigration, MigrationError


class AddNotesContentHtmlMigration(BaseMigration):
    """Add content_html column to notes table."""

    def __init__(self):
        super().__init__(
            version="003",
            name="add_notes_content_html",
            description="Add content_html column to notes table for HTML content rendering",
        )

    def up(self, conn: sqlite3.Connection) -> None:
        """Apply the migration: add content_html column."""
        cursor = conn.cursor()

        try:
            # Check if table exists
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='note_list'
            """
            )
            table_exists = cursor.fetchone() is not None

            if table_exists:
                # Check if content_html column already exists
                cursor.execute("PRAGMA table_info(note_list)")
                columns = [row[1] for row in cursor.fetchall()]

                if "content_html" not in columns:
                    # Add the content_html column
                    cursor.execute("ALTER TABLE note_list ADD COLUMN content_html TEXT")
                    conn.commit()
                else:
                    pass
            else:
                # Table doesn't exist yet, this migration will be skipped
                pass

        except sqlite3.Error as e:
            raise MigrationError(f"Failed to add content_html column: {str(e)}") from e

    def down(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration: remove content_html column."""
        raise MigrationError(
            "Rollback not supported: SQLite doesn't support dropping columns easily. "
            "Manual intervention required to remove content_html column."
        )
