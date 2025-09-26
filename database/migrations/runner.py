"""Migration runner for executing database migrations in order."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import (
    BaseMigration,
    MigrationError,
    ensure_migrations_table,
    get_applied_migrations,
    is_migration_applied,
    record_migration,
)

if TYPE_CHECKING:
    import sqlite3

LOGGER = logging.getLogger(__name__)


class MigrationRunner:
    """Manages and executes database migrations."""

    def __init__(self, db_key: str = "notes"):
        """
        Initialize the migration runner.

        Args:
            db_key: Database key (used for logging and identification)
        """
        self.db_key = db_key
        self.migrations: list[BaseMigration] = []

    def register_migration(self, migration: BaseMigration) -> None:
        """
        Register a migration to be managed by this runner.

        Args:
            migration: Migration instance to register
        """
        self.migrations.append(migration)
        # Sort migrations by version to ensure proper order
        self.migrations.sort(key=lambda m: m.version)

    def register_migrations(self, migrations: list[BaseMigration]) -> None:
        """
        Register multiple migrations.

        Args:
            migrations: List of migration instances
        """
        for migration in migrations:
            self.register_migration(migration)

    def get_pending_migrations(self, conn: sqlite3.Connection) -> list[BaseMigration]:
        """
        Get migrations that haven't been applied yet.

        Args:
            conn: Database connection

        Returns:
            List of pending migrations in execution order
        """
        ensure_migrations_table(conn)

        pending = []
        for migration in self.migrations:
            if not is_migration_applied(conn, migration):
                pending.append(migration)

        return pending

    def run_migrations(
        self, conn: sqlite3.Connection, dry_run: bool = False, target_version: str | None = None
    ) -> list[BaseMigration]:
        """
        Run all pending migrations.

        Args:
            conn: Database connection
            dry_run: If True, don't actually execute migrations
            target_version: If specified, run migrations up to this version

        Returns:
            List of migrations that were executed (or would be in dry run)

        Raises:
            MigrationError: If any migration fails
        """
        ensure_migrations_table(conn)

        pending = self.get_pending_migrations(conn)

        # Filter by target version if specified
        if target_version:
            pending = [m for m in pending if m.version <= target_version]

        if not pending:
            LOGGER.info("No pending migrations for database '%s'", self.db_key)
            return []

        if dry_run:
            LOGGER.info(
                "DRY RUN: Would execute %d migrations for database '%s': %s",
                len(pending),
                self.db_key,
                [m.full_name for m in pending],
            )
            return pending

        executed = []
        for migration in pending:
            try:
                LOGGER.info(
                    "Executing migration %s for database '%s': %s",
                    migration.full_name,
                    self.db_key,
                    migration.description,
                )

                # Execute the migration
                migration.up(conn)

                # Record that it was applied
                record_migration(conn, migration)
                executed.append(migration)

                LOGGER.info(
                    "Successfully applied migration %s for database '%s'",
                    migration.full_name,
                    self.db_key,
                )

            except Exception as e:
                error_msg = (
                    f"Failed to execute migration {migration.full_name} "
                    f"for database '{self.db_key}': {str(e)}"
                )
                LOGGER.error(error_msg)
                raise MigrationError(error_msg) from e

        LOGGER.info(
            "Successfully executed %d migrations for database '%s'", len(executed), self.db_key
        )
        return executed

    def get_migration_status(self, conn: sqlite3.Connection) -> dict:
        """
        Get the current migration status.

        Args:
            conn: Database connection

        Returns:
            Dictionary with migration status information
        """
        ensure_migrations_table(conn)

        applied_records = get_applied_migrations(conn)

        pending = self.get_pending_migrations(conn)

        return {
            "total_migrations": len(self.migrations),
            "applied_count": len(applied_records),
            "pending_count": len(pending),
            "applied_migrations": [record.full_name for record in applied_records],
            "pending_migrations": [migration.full_name for migration in pending],
            "is_up_to_date": len(pending) == 0,
        }

    def rollback_migration(self, conn: sqlite3.Connection, version: str, name: str) -> None:
        """
        Rollback a specific migration.

        Args:
            conn: Database connection
            version: Migration version to rollback
            name: Migration name to rollback

        Raises:
            MigrationError: If migration doesn't exist or rollback fails
        """
        # Find the migration
        migration = None
        for m in self.migrations:
            if m.version == version and m.name == name:
                migration = m
                break

        if not migration:
            raise MigrationError(f"Migration {version}_{name} not found")

        # Check if it's applied
        if not is_migration_applied(conn, migration):
            raise MigrationError(f"Migration {migration.full_name} is not applied")

        try:
            LOGGER.info(
                "Rolling back migration %s for database '%s'", migration.full_name, self.db_key
            )

            # Execute rollback
            migration.down(conn)

            # Remove from migrations table
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM schema_migrations
                WHERE version = ? AND name = ?
            """,
                (version, name),
            )
            conn.commit()

            LOGGER.info(
                "Successfully rolled back migration %s for database '%s'",
                migration.full_name,
                self.db_key,
            )

        except Exception as e:
            error_msg = (
                f"Failed to rollback migration {migration.full_name} "
                f"for database '{self.db_key}': {str(e)}"
            )
            LOGGER.error(error_msg)
            raise MigrationError(error_msg) from e
