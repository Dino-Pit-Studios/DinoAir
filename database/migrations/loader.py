"""
Migration loader utilities for loading migration scripts from the scripts directory.
"""

import importlib.util
import logging
from pathlib import Path

from .base import BaseMigration

LOGGER = logging.getLogger(__name__)


def load_migration_from_file(migration_file: Path) -> BaseMigration:
    """
    Load a migration class from a Python file.

    Args:
        migration_file: Path to the migration Python file

    Returns:
        Instantiated migration object

    Raises:
        ImportError: If migration file cannot be imported
        AttributeError: If migration class cannot be found
    """
    # Load the module from file
    spec = importlib.util.spec_from_file_location(
        f"migration_{migration_file.stem}", migration_file
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load migration from {migration_file}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Find the migration class in the module
    migration_class = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type) and issubclass(attr, BaseMigration) and attr != BaseMigration:
            migration_class = attr
            break

    if migration_class is None:
        raise AttributeError(f"No migration class found in {migration_file}")

    return migration_class()


def load_migrations_from_directory(migrations_dir: Path) -> list[BaseMigration]:
    """
    Load all migration scripts from a directory.

    Args:
        migrations_dir: Path to directory containing migration scripts

    Returns:
        List of migration instances, sorted by version
    """
    migrations = []

    if not migrations_dir.exists():
        LOGGER.warning("Migrations directory does not exist: %s", migrations_dir)
        return migrations

    # Find all Python files in the migrations directory
    migration_files = sorted(migrations_dir.glob("*.py"))

    for migration_file in migration_files:
        # Skip __init__.py and other special files
        if migration_file.name.startswith("__"):
            continue

        try:
            migration = load_migration_from_file(migration_file)
            migrations.append(migration)
            LOGGER.debug("Loaded migration: %s", migration.full_name)
        except (ImportError, AttributeError, OSError) as e:
            LOGGER.error("Failed to load migration from %s: %s", migration_file, str(e))
            # Continue loading other migrations instead of failing completely

    # Sort by version to ensure proper execution order
    migrations.sort(key=lambda m: m.version)

    return migrations


def get_notes_migrations() -> list[BaseMigration]:
    """
    Get all notes database migrations.

    Returns:
        List of migration instances for the notes database
    """
    migrations_dir = Path(__file__).parent / "scripts"
    return load_migrations_from_directory(migrations_dir)
