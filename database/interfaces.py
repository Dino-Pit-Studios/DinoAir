"""
Database Layer Interface Abstractions - Phase 4A Sprint 1
Protocol-based interfaces for breaking circular dependencies using dependency injection.
"""

from dataclasses import dataclass
from typing import Any, Protocol

# Import existing result types to maintain compatibility
from database.notes_repository import QueryResult
from database.notes_service import OperationResult
from database.notes_validator import ValidationResult
from models.note import Note


@dataclass
class ConnectionInfo:
    """Database connection configuration"""

    db_path: str
    user_name: str | None
    connection_pool_size: int = 5


@dataclass
class SecurityResult:
    """Result of security validation"""

    is_valid: bool
    violations: list[str]
    risk_level: str


# ===== DATABASE LAYER INTERFACES =====


class IDatabaseManager(Protocol):
    """Database manager interface for connection and transaction management."""

    def get_connection(self) -> Any:
        """Get database connection from pool."""
        ...

    def execute_query(self, query: str, params: tuple[Any, ...] = ()) -> QueryResult:
        """Execute SQL query with parameters."""
        ...

    def begin_transaction(self) -> None:
        """Begin database transaction."""
        ...

    def commit_transaction(self) -> None:
        """Commit current transaction."""
        ...

    def rollback_transaction(self) -> None:
        """Rollback current transaction."""
        ...

    def run_migrations(self) -> bool:
        """Run database migrations."""
        ...

    @property
    def notes_db_path(self) -> str:
        """Get path to notes database."""
        ...

    def get_notes_connection(self) -> Any:
        """Get connection to notes database."""
        ...


class INotesRepository(Protocol):
    """Notes repository interface for data access operations."""

    def create_note(self, note: Note, content_html: str | None = None) -> QueryResult:
        """Create new note in database."""
        ...

    def get_note_by_id(self, note_id: str) -> QueryResult:
        """Retrieve note by ID."""
        ...

    def get_all_notes(self) -> QueryResult:
        """Retrieve all non-deleted notes."""
        ...

    def update_note(self, note_id: str, updates: dict[str, Any]) -> QueryResult:
        """Update existing note."""
        ...

    def soft_delete_note(self, note_id: str) -> QueryResult:
        """Soft delete note by ID."""
        ...

    def hard_delete_note(self, note_id: str) -> QueryResult:
        """Permanently delete note by ID."""
        ...

    def restore_note(self, note_id: str) -> QueryResult:
        """Restore soft-deleted note."""
        ...

    def get_deleted_notes(self) -> QueryResult:
        """Get all soft-deleted notes."""
        ...

    def search_notes(
        self, query: str, filter_option: str = "All", project_id: str | None = None
    ) -> QueryResult:
        """Search notes by text content."""
        ...

    def get_notes_by_tag(self, tag: str) -> QueryResult:
        """Get all notes with specific tag."""
        ...

    def get_all_tags(self) -> QueryResult:
        """Get all unique tags with usage counts."""
        ...

    def update_tag_in_notes(self, old_tag: str, new_tag: str) -> QueryResult:
        """Rename a tag across all notes."""
        ...

    def remove_tag_from_notes(self, tag_to_remove: str) -> QueryResult:
        """Remove a tag from all notes."""
        ...

    def get_notes_by_project(self, project_id: str) -> QueryResult:
        """Get all notes for a specific project."""
        ...

    def get_notes_without_project(self) -> QueryResult:
        """Get all notes not associated with any project."""
        ...

    def bulk_update_project(
        self, note_ids: list[str], project_id: str | None = None
    ) -> QueryResult:
        """Assign multiple notes to a project or remove project association."""
        ...

    def get_project_notes_count(self, project_id: str) -> QueryResult:
        """Get the count of notes associated with a project."""
        ...


class INotesSecurity(Protocol):
    """Notes security interface for validation and sanitization."""

    def validate_note_data(self, title: str, content: str, tags: list[str]) -> dict[str, Any]:
        """Validate note data for security issues."""
        ...

    def escape_sql_wildcards(self, text: str) -> str:
        """Escape SQL wildcard characters for safe queries."""
        ...

    def can_perform_write_operation(self, operation: str) -> tuple[bool, str | None]:
        """Check user permissions for write operation."""
        ...


class INotesValidator(Protocol):
    """Notes validator interface for business rule validation."""

    def validate_note_creation(self, title: str, content: str, tags: list[str]) -> ValidationResult:
        """Validate data for note creation."""
        ...

    def validate_note_update(self, updates: dict[str, Any]) -> ValidationResult:
        """Validate data for note updates."""
        ...

    def validate_search_query(self, query: str, filter_option: str) -> ValidationResult:
        """Validate search parameters."""
        ...

    def validate_bulk_operation(self, note_ids: list[str], operation: str) -> ValidationResult:
        """Validate parameters for bulk operations."""
        ...


class INotesService(Protocol):
    """Notes service interface for orchestrated operations."""

    def create_note(
        self, note: Note, content_html: str | None = None, project_id: str | None = None
    ) -> OperationResult:
        """Create note with security validation."""
        ...

    def get_note(self, note_id: str) -> OperationResult:
        """Retrieve a single note by ID."""
        ...

    def get_all_notes(self) -> OperationResult:
        """Retrieve all non-deleted notes."""
        ...

    def update_note(self, note_id: str, updates: dict[str, Any]) -> OperationResult:
        """Update note with validation and security checks."""
        ...

    def delete_note(self, note_id: str, hard_delete: bool = False) -> OperationResult:
        """Delete note with permission verification."""
        ...

    def restore_note(self, note_id: str) -> OperationResult:
        """Restore a soft-deleted note."""
        ...

    def search_notes(
        self, query: str, filter_option: str = "All", project_id: str | None = None
    ) -> OperationResult:
        """Search notes with user permission filtering."""
        ...

    def get_notes_by_tag(self, tag: str) -> OperationResult:
        """Get all notes with a specific tag."""
        ...

    def get_all_tags(self) -> OperationResult:
        """Get all unique tags with usage counts."""
        ...

    def rename_tag(self, old_tag: str, new_tag: str) -> OperationResult:
        """Rename a tag across all notes."""
        ...

    def delete_tag(self, tag_to_delete: str) -> OperationResult:
        """Remove a tag from all notes."""
        ...

    def get_notes_by_project(self, project_id: str) -> OperationResult:
        """Get all notes for a specific project."""
        ...

    def get_notes_without_project(self) -> OperationResult:
        """Get all notes not associated with any project."""
        ...

    def assign_notes_to_project(self, note_ids: list[str], project_id: str) -> OperationResult:
        """Assign multiple notes to a project."""
        ...

    def remove_notes_from_project(self, note_ids: list[str]) -> OperationResult:
        """Remove project association from multiple notes."""
        ...

    def get_project_notes_count(self, project_id: str) -> OperationResult:
        """Get the count of notes associated with a project."""
        ...

    def get_deleted_notes(self) -> OperationResult:
        """Get all soft-deleted notes."""
        ...

    def update_note_project(self, note_id: str, project_id: str | None = None) -> OperationResult:
        """Update a single note's project association."""
        ...


# ===== DEPENDENCY INJECTION INTERFACES =====


class IDependencyContainer(Protocol):
    """Dependency injection container interface."""

    def register(self, interface: type, implementation: type, singleton: bool = False) -> None:
        """Register service implementation for interface."""
        ...

    def get(self, interface: type, **kwargs: Any) -> Any:
        """Get service instance for interface."""
        ...

    def is_registered(self, interface: type) -> bool:
        """Check if interface is registered."""
        ...


class INotesServiceFactory(Protocol):
    """Factory interface for creating notes services."""

    def create_notes_service(self, user_name: str | None = None) -> INotesService:
        """Create fully configured notes service with all dependencies."""
        ...

    def create_database_manager(self, user_name: str | None = None) -> IDatabaseManager:
        """Create database manager instance."""
        ...

    def create_notes_repository(self, db_manager: IDatabaseManager) -> INotesRepository:
        """Create notes repository with database manager dependency."""
        ...

    def create_notes_security(self) -> INotesSecurity:
        """Create notes security validator."""
        ...

    def create_notes_validator(self) -> INotesValidator:
        """Create notes data validator."""
        ...
