"""
Migration: Add project_id column to notes table

This migration adds the project_id column to the note_list table
to support project association functionality.

Version: 001
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


class AddNotesProjectIdMigration(BaseMigration):
    """Add project_id column to notes table."""

    def __init__(self):
        super().__init__(
            version="001",
            name="add_notes_project_id",
            description="Add project_id column to notes table for project association",
        )

    def up(self, conn: sqlite3.Connection) -> None:
        """Apply the migration: add project_id column."""
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
                # Check if project_id column already exists
                cursor.execute("PRAGMA table_info(note_list)")
                columns = [row[1] for row in cursor.fetchall()]

                if "project_id" not in columns:
                    # Add the project_id column
                    cursor.execute("ALTER TABLE note_list ADD COLUMN project_id TEXT")
                    conn.commit()
                else:
                    pass
            else:
                # Table doesn't exist yet, this migration will be skipped
                # as the table creation in SCHEMA_DDLS already includes project_id
                pass

        except sqlite3.Error as e:
            raise MigrationError(f"Failed to add project_id column: {str(e)}") from e

    def down(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration: remove project_id column."""
        # SQLite doesn't support dropping columns directly in older versions
        # This would require recreating the table, which is complex and risky
        # For now, we don't support rollback of this migration
        raise MigrationError(
            "Rollback not supported: SQLite doesn't support dropping columns easily. "
            "Manual intervention required to remove project_id column."
        )
