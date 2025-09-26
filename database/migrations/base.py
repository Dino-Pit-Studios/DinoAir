"""Base migration classes and utilities for the DinoAir migration system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3


class MigrationError(Exception):
    """Exception raised during migration execution."""


class BaseMigration(ABC):
    """
    Base class for all database migrations.

    Each migration must implement the `up` method to apply the migration
    and optionally the `down` method to rollback the migration.
    """

    def __init__(self, version: str, name: str, description: str = ""):
        """
        Initialize a migration.

        Args:
            version: Migration version (e.g., "001", "002")
            name: Migration name (e.g., "add_notes_project_id")
            description: Optional description of what the migration does
        """
        self.version = version
        self.name = name
        self.description = description
        self.applied_at: datetime | None = None

    @abstractmethod
    def up(self, conn: sqlite3.Connection) -> None:
        """
        Apply the migration.

        Args:
            conn: Database connection to execute migration on

        Raises:
            MigrationError: If migration fails
        """

    def down(self, conn: sqlite3.Connection) -> None:
        """
        Rollback the migration (optional).

        Args:
            conn: Database connection to execute rollback on

        Raises:
            MigrationError: If rollback fails
        """
        raise NotImplementedError(f"Migration {self.version}_{self.name} does not support rollback")

    @property
    def full_name(self) -> str:
        """Get the full migration identifier."""
        return f"{self.version}_{self.name}"

    def __str__(self) -> str:
        return f"Migration({self.full_name})"

    def __repr__(self) -> str:
        return f"Migration(version='{self.version}', name='{self.name}')"


class MigrationRecord:
    """Represents a migration record from the database."""

    def __init__(
        self,
        version: str,
        name: str,
        applied_at: datetime,
        description: str = "",
        checksum: str | None = None,
    ):
        self.version = version
        self.name = name
        self.applied_at = applied_at
        self.description = description
        self.checksum = checksum

    @property
    def full_name(self) -> str:
        """Get the full migration identifier."""
        return f"{self.version}_{self.name}"

    @classmethod
    def from_row(cls, row: tuple) -> MigrationRecord:
        """Create a MigrationRecord from a database row."""
        version, name, applied_at_str, description, checksum = row
        applied_at = datetime.fromisoformat(applied_at_str)
        return cls(version, name, applied_at, description, checksum)

    def __str__(self) -> str:
        return f"MigrationRecord({self.full_name}, applied_at={self.applied_at})"


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    """
    Ensure the migrations tracking table exists.

    Args:
        conn: Database connection
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT NOT NULL,
            name TEXT NOT NULL,
            applied_at DATETIME NOT NULL,
            description TEXT DEFAULT '',
            checksum TEXT DEFAULT NULL,
            PRIMARY KEY (version, name)
        )
    """
    )

    # Create index for efficient lookups
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_migrations_version
        ON schema_migrations(version)
    """
    )

    conn.commit()


def record_migration(conn: sqlite3.Connection, migration: BaseMigration) -> None:
    """
    Record a migration as applied in the migrations table.

    Args:
        conn: Database connection
        migration: The migration that was applied
    """
    cursor = conn.cursor()
    applied_at = datetime.now().isoformat()

    cursor.execute(
        """
        INSERT OR REPLACE INTO schema_migrations
        (version, name, applied_at, description)
        VALUES (?, ?, ?, ?)
    """,
        (migration.version, migration.name, applied_at, migration.description),
    )

    conn.commit()


def get_applied_migrations(conn: sqlite3.Connection) -> list[MigrationRecord]:
    """
    Get all applied migrations from the database.

    Args:
        conn: Database connection

    Returns:
        List of applied migration records, sorted by version
    """
    ensure_migrations_table(conn)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT version, name, applied_at, description, checksum
        FROM schema_migrations
        ORDER BY version, name
    """
    )

    return [MigrationRecord.from_row(row) for row in cursor.fetchall()]


def is_migration_applied(conn: sqlite3.Connection, migration: BaseMigration) -> bool:
    """
    Check if a migration has been applied.

    Args:
        conn: Database connection
        migration: Migration to check

    Returns:
        True if migration has been applied, False otherwise
    """
    ensure_migrations_table(conn)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1 FROM schema_migrations
        WHERE version = ? AND name = ?
    """,
        (migration.version, migration.name),
    )

    return cursor.fetchone() is not None
