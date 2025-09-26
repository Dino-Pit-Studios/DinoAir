"""
Database Migration System

This module provides a versioned migration system for DinoAir database schema changes.
Migrations are tracked in a dedicated table and executed in order.
"""

from .base import BaseMigration, MigrationError
from .loader import get_notes_migrations, load_migrations_from_directory
from .runner import MigrationRunner

__all__ = [
    "BaseMigration",
    "MigrationError",
    "MigrationRunner",
    "get_notes_migrations",
    "load_migrations_from_directory",
]
