"""
Migration: Add is_deleted column to notes table

This migration adds the is_deleted column to the note_list table
to support soft delete functionality.

Version: 002
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


class AddNotesIsDeletedMigration(BaseMigration):
    """Add is_deleted column to notes table."""

    def __init__(self):
        super().__init__(
            version="002",
            name="add_notes_is_deleted",
            description="Add is_deleted column to notes table for soft delete functionality",
        )

    def up(self, conn: sqlite3.Connection) -> None:
        """Apply the migration: add is_deleted column."""
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
                # Check if is_deleted column already exists
                cursor.execute("PRAGMA table_info(note_list)")
                columns = [row[1] for row in cursor.fetchall()]

                if "is_deleted" not in columns:
                    # Add the is_deleted column with default value 0
                    cursor.execute("ALTER TABLE note_list ADD COLUMN is_deleted INTEGER DEFAULT 0")
                    conn.commit()
                else:
                    pass
            else:
                # Table doesn't exist yet, this migration will be skipped
                pass

        except sqlite3.Error as e:
            raise MigrationError(f"Failed to add is_deleted column: {str(e)}") from e

    def down(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration: remove is_deleted column."""
        raise MigrationError(
            "Rollback not supported: SQLite doesn't support dropping columns easily. "
            "Manual intervention required to remove is_deleted column."
        )
