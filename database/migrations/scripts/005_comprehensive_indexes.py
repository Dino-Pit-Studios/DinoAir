"""
Migration 005: Comprehensive Index Coverage

This migration adds comprehensive index coverage for all common query patterns
in the notes system, including compound indexes for frequently combined filters.

Changes:
1. Add missing single-column indexes (is_deleted, updated_at)
2. Add compound indexes for common query patterns
3. Optimize existing indexes for better performance
4. Add partial indexes for specific use cases

Benefits:
- Dramatically improves query performance for common operations
- Optimizes compound WHERE clauses and ORDER BY operations
- Reduces full table scans for filtered queries
- Improves search functionality performance
"""

import sqlite3

from database.migrations.base import BaseMigration, MigrationError


class ComprehensiveIndexMigration(BaseMigration):
    """Migration to add comprehensive index coverage for note_list table"""

    def __init__(self):
        super().__init__(
            version="005",
            name="comprehensive_index_coverage",
            description="Add comprehensive index coverage for all common query patterns",
        )

    def up(self, conn: sqlite3.Connection) -> None:
        """Add comprehensive index coverage"""
        cursor = conn.cursor()

        try:
            # Add missing single-column indexes
            self._add_single_column_indexes(cursor)

            # Add compound indexes for common query patterns
            self._add_compound_indexes(cursor)

            # Add partial indexes for specific use cases
            self._add_partial_indexes(cursor)

            # Update existing indexes if needed
            self._optimize_existing_indexes(cursor)

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise MigrationError(f"Failed to add comprehensive indexes: {e}") from e

    def _add_single_column_indexes(self, cursor: sqlite3.Cursor) -> None:
        """Add missing single-column indexes"""

        # Add is_deleted index if not exists (critical for all queries)
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notes_is_deleted
            ON note_list(is_deleted)
        """
        )

        # Add updated_at index if not exists (for ordering)
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notes_updated
            ON note_list(updated_at)
        """
        )

    def _add_compound_indexes(self, cursor: sqlite3.Cursor) -> None:
        """Add compound indexes for common query patterns"""

        # Most common pattern: is_deleted + updated_at DESC for chronological listings
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notes_active_updated
            ON note_list(is_deleted, updated_at DESC)
        """
        )

        # Search pattern: is_deleted + title for title searches
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notes_active_title
            ON note_list(is_deleted, title)
        """
        )

        # Project listings: is_deleted + project_id + updated_at DESC
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notes_project_active
            ON note_list(is_deleted, project_id, updated_at DESC)
        """
        )

        # Search with project filter: is_deleted + project_id + title
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notes_project_title
            ON note_list(is_deleted, project_id, title)
        """
        )

    def _add_partial_indexes(self, cursor: sqlite3.Cursor) -> None:
        """Add partial indexes for specific use cases"""

        # Index for notes with tags (excludes NULL and empty JSON arrays)
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notes_has_tags
            ON note_list(is_deleted)
            WHERE tags IS NOT NULL AND tags != '[]'
        """
        )

        # Index for active notes with tags for tag-related queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notes_active_tags
            ON note_list(is_deleted, tags)
            WHERE is_deleted = 0 AND tags IS NOT NULL
        """
        )

        # Index for notes without project (orphaned notes)
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notes_no_project
            ON note_list(is_deleted, updated_at DESC)
            WHERE project_id IS NULL OR project_id = ''
        """
        )

    def _optimize_existing_indexes(self, cursor: sqlite3.Cursor) -> None:
        """Optimize existing indexes by dropping and recreating if needed"""

        # Check if we need to update the tags index to be more specific
        try:
            # Drop old basic tags index if it exists
            cursor.execute("DROP INDEX IF EXISTS idx_notes_tags")

            # Create enhanced tags index
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notes_tags_enhanced
                ON note_list(tags)
                WHERE tags IS NOT NULL
            """
            )

        except sqlite3.Error:
            # Continue if index optimization fails - not critical
            pass

    def down(self, conn: sqlite3.Connection) -> None:
        """Remove the comprehensive indexes"""
        cursor = conn.cursor()

        try:
            # Remove compound indexes
            cursor.execute("DROP INDEX IF EXISTS idx_notes_active_updated")
            cursor.execute("DROP INDEX IF EXISTS idx_notes_active_title")
            cursor.execute("DROP INDEX IF EXISTS idx_notes_project_active")
            cursor.execute("DROP INDEX IF EXISTS idx_notes_project_title")

            # Remove partial indexes
            cursor.execute("DROP INDEX IF EXISTS idx_notes_has_tags")
            cursor.execute("DROP INDEX IF EXISTS idx_notes_active_tags")
            cursor.execute("DROP INDEX IF EXISTS idx_notes_no_project")

            # Remove enhanced indexes
            cursor.execute("DROP INDEX IF EXISTS idx_notes_tags_enhanced")

            # Keep basic single-column indexes as they're generally useful
            # (is_deleted and updated_at indexes)

            # Restore basic tags index
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notes_tags ON note_list(tags)
            """
            )

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise MigrationError(f"Failed to rollback comprehensive indexes: {e}") from e


# Migration instance
migration = ComprehensiveIndexMigration()
