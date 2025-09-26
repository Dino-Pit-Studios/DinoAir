"""
Fallback tag implementation for systems without JSON1 extension support.

This provides a normalized tag table approach as an alternative to JSON1-based
tag queries for SQLite installations that don't support the JSON1 extension.
"""

import json
import re
import sqlite3

from database.migrations.base import BaseMigration, MigrationError


class TagTableFallbackMigration(BaseMigration):
    """Migration to create normalized tag table for non-JSON1 systems"""

    def __init__(self):
        super().__init__(
            version="005",
            name="tag_table_fallback",
            description="Create normalized tag table for systems without JSON1 support",
        )

    def up(self, conn: sqlite3.Connection) -> None:
        """Create normalized tag table and populate from existing JSON data"""
        cursor = conn.cursor()

        try:
            # Create normalized tag table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS note_tags (
                    note_id TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (note_id, tag),
                    FOREIGN KEY (note_id) REFERENCES note_list(id) ON DELETE CASCADE
                )
            """
            )

            # Create indexes for efficient tag queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_note_tags_tag ON note_tags(tag)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_note_tags_note_id ON note_tags(note_id)
            """
            )

            # Populate tag table from existing JSON data
            self._populate_tag_table(cursor)

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise MigrationError(f"Failed to create tag table fallback: {e}") from e

    def _populate_tag_table(self, cursor: sqlite3.Cursor) -> None:
        """Populate tag table from existing JSON tag data"""

        # Get all notes with tags
        cursor.execute("SELECT id, tags FROM note_list WHERE tags IS NOT NULL AND tags != ''")

        tag_insertions = []
        for row in cursor.fetchall():
            note_id, tags_json = row
            if tags_json:
                try:
                    tags = json.loads(tags_json)
                    if isinstance(tags, list):
                        for tag in tags:
                            if isinstance(tag, str) and tag.strip():
                                # Normalize tag to lowercase
                                normalized_tag = tag.lower().strip()
                                tag_insertions.append((note_id, normalized_tag))
                except (json.JSONDecodeError, TypeError):
                    # Skip malformed tag data
                    continue

        # Insert tags into normalized table
        if tag_insertions:
            cursor.executemany(
                "INSERT OR IGNORE INTO note_tags (note_id, tag) VALUES (?, ?)", tag_insertions
            )

    def down(self, conn: sqlite3.Connection) -> None:
        """Remove normalized tag table"""
        cursor = conn.cursor()

        try:
            cursor.execute("DROP TABLE IF EXISTS note_tags")
            conn.commit()

        except Exception as e:
            conn.rollback()
            raise MigrationError(f"Failed to remove tag table: {e}") from e


class TagTableHelper:
    """Helper class for tag operations when using normalized tag table fallback"""

    def __init__(self, db_manager):
        self.db_manager = db_manager

    def sync_note_tags(self, note_id: str, tags: list[str]) -> None:
        """Sync tags for a note in the normalized tag table"""
        with self.db_manager.get_notes_connection() as conn:
            cursor = conn.cursor()

            # Remove existing tags for the note
            cursor.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))

            # Insert new tags
            if tags:
                normalized_tags = [(note_id, tag.lower().strip()) for tag in tags if tag.strip()]
                cursor.executemany(
                    "INSERT INTO note_tags (note_id, tag) VALUES (?, ?)", normalized_tags
                )

    def get_notes_by_tag_fallback(self, tag: str, table_name: str = "note_list") -> list[tuple]:
        """Get notes by tag using normalized tag table"""
        if not re.match("^[a-zA-Z0-9_]+$", str(table_name)):
            raise ValueError("Invalid input")
        normalized_tag = tag.lower().strip()

        with self.db_manager.get_notes_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT n.id, n.title, n.content, n.content_html, n.tags,
                       n.created_at, n.updated_at, n.project_id
                FROM {table_name} n
                INNER JOIN note_tags nt ON n.id = nt.note_id
                WHERE n.is_deleted = 0 AND nt.tag = ?
                ORDER BY n.updated_at DESC
            """,
                (normalized_tag,),
            )

            return cursor.fetchall()

    def get_all_tags_fallback(self) -> list[tuple[str, int]]:
        """Get all tags with counts using normalized tag table"""
        with self.db_manager.get_notes_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT nt.tag, COUNT(*) as count
                FROM note_tags nt
                INNER JOIN note_list n ON nt.note_id = n.id
                WHERE n.is_deleted = 0
                GROUP BY nt.tag
                ORDER BY count DESC, nt.tag
            """
            )

            return cursor.fetchall()


# Migration instance
migration = TagTableFallbackMigration()
