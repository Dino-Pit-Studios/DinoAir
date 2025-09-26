"""
NotesDatabase - Backward compatibility layer for notes management.
Now uses the refactored NotesService internally for better maintainability.
"""

from typing import Any, cast

from models.note import Note
from utils.logger import Logger

# Import factory to break circular dependency
from .factory import create_notes_service

# Import OperationResult directly to avoid circular import
from .notes_service import OperationResult


class NotesDatabase:
    """
    Backward compatibility layer for notes management.
    Internally uses the new refactored NotesService architecture.
    """

    def __init__(self, user_name: str | None = None):
        """
        Initialize NotesDatabase with user-specific database connection.

        Args:
            user_name: Username for user-specific database.
                      Defaults to "default_user"
        """
        self.logger = Logger()
        # Use factory to break circular dependency
        self._service = create_notes_service(user_name)

        # Legacy attributes for backward compatibility
        self.table_name = "note_list"
        self._security = None  # Lazy load to avoid circular import
        self._security_is_fallback = False  # Track if fallback security is active

    # ===== HELPER METHODS FOR CODE DEDUPLICATION =====

    def _handle_data_result(
        self, operation_result: OperationResult, default_value: Any = None
    ) -> Any:
        """Handle OperationResult for methods that return data or default value."""
        return operation_result.data if operation_result.success else default_value

    def _handle_success_result(
        self, operation_result: OperationResult, **extra_data: Any
    ) -> dict[str, Any]:
        """Handle OperationResult for methods that return success/error dict."""
        if operation_result.success:
            return {"success": True, **operation_result.data, **extra_data}
        return {"success": False, "error": operation_result.error}

    def _handle_simple_success(self, operation_result: OperationResult) -> bool:
        """Handle OperationResult for methods that return simple boolean success."""
        return operation_result.success

    # ===== LEGACY COMPATIBILITY METHODS =====

    def _get_security(self) -> Any:
        """Legacy method for backward compatibility"""
        # This is now handled by NotesSecurity in the service layer
        return self._service.security

    def _get_database_path(self) -> str:
        """Compatibility helper used in tests to patch DB location."""
        # This is now handled by NotesRepository in the service layer
        return str(self._service.repository.db_manager.notes_db_path)

    def _enforce_security_for_write(self, operation: str) -> tuple[bool, str | None]:
        """Legacy method for backward compatibility"""
        # This is now handled by NotesSecurity in the service layer
        return self._service.security.can_perform_write_operation(operation)

    def _escape_sql_wildcards(self, text: str) -> str:
        """Legacy method for backward compatibility"""
        # This is now handled by NotesSecurity in the service layer
        return self._service.security.escape_sql_wildcards(text)

    # ===== CRUD METHODS =====

    def create_note(
        self,
        note: Note,
        content_html: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Insert a new note into the database with security validation.

        Args:
            note: Note object to be inserted
            content_html: Optional HTML content for rich text formatting
            project_id: Optional project ID to associate with the note

        Returns:
            Dict with success status and note_id or error message
        """
        return self._handle_success_result(
            self._service.create_note(note, content_html, project_id)
        )

    def get_note(self, note_id: str) -> Note | None:
        """
        Retrieve a single note by ID.

        Args:
            note_id: The ID of the note to retrieve

        Returns:
            Note object if found and not deleted, None otherwise
        """
        return cast("Note | None", self._handle_data_result(self._service.get_note(note_id)))

    def get_all_notes(self) -> list[Note]:
        """
        Retrieve all notes for the user (excluding soft-deleted notes).

        Returns:
            List of Note objects
        """
        return cast("list[Note]", self._handle_data_result(self._service.get_all_notes(), []))

    def update_note(self, note_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """
        Update an existing note with security validation.

        Args:
            note_id: ID of the note to update
            updates: Dictionary with fields to update (title, content, tags)

        Returns:
            Dict with success status and message
        """
        return self._handle_success_result(self._service.update_note(note_id, updates))

    def delete_note(self, note_id: str, hard_delete: bool = False) -> dict[str, Any]:
        """
        Delete a note by ID (soft delete by default).

        Args:
            note_id: ID of the note to delete
            hard_delete: If True, permanently remove from database.
                        If False, soft delete.

        Returns:
            Dict with success status and message
        """
        return self._handle_success_result(self._service.delete_note(note_id, hard_delete))

    # ===== SEARCH AND TAG METHODS =====

    def search_notes(
        self, query: str, filter_option: str = "All", project_id: str | None = None
    ) -> list[Note]:
        """
        Search notes by title, content, or tags with SQL-safe filtering.

        Args:
            query: Search query string (will be escaped for SQL safety)
            filter_option: Filter to apply - "All", "Title Only",
                          "Content Only", or "Tags Only"
            project_id: Optional project ID to filter results by

        Returns:
            List of Note objects matching the search criteria
        """
        return cast(
            "list[Note]",
            self._handle_data_result(
                self._service.search_notes(query, filter_option, project_id), []
            ),
        )

    def get_notes_by_tag(self, tag: str) -> list[Note]:
        """
        Get all notes with a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of Note objects containing the specified tag
        """
        return cast("list[Note]", self._handle_data_result(self._service.get_notes_by_tag(tag), []))

    def restore_deleted_note(self, note_id: str) -> dict[str, Any]:
        """
        Restore a soft-deleted note.

        Args:
            note_id: ID of the note to restore

        Returns:
            Dict with success status and message
        """
        return self._handle_success_result(self._service.restore_note(note_id))

    def get_deleted_notes(self) -> list[Note]:
        """
        Get all soft-deleted notes (for potential restoration).

        Returns:
            List of deleted Note objects
        """
        return cast("list[Note]", self._handle_data_result(self._service.get_deleted_notes(), []))

    def get_all_tags(self) -> dict[str, int]:
        """
        Get all unique tags from all notes with their usage counts.

        Returns:
            Dictionary of tag names to their usage counts
        """
        return cast("dict[str, int]", self._handle_data_result(self._service.get_all_tags(), {}))

    def rename_tag(self, old_tag: str, new_tag: str) -> dict[str, Any]:
        """
        Rename a tag across all notes.

        Args:
            old_tag: The tag to rename
            new_tag: The new tag name

        Returns:
            Dict with success status and number of affected notes
        """
        return self._handle_success_result(self._service.rename_tag(old_tag, new_tag))

    def delete_tag(self, tag_to_delete: str) -> dict[str, Any]:
        """
        Remove a tag from all notes.

        Args:
            tag_to_delete: The tag to remove

        Returns:
            Dict with success status and number of affected notes
        """
        return self._handle_success_result(self._service.delete_tag(tag_to_delete))

    # ===== PROJECT MANAGEMENT METHODS =====

    def get_notes_by_project(self, project_id: str) -> list[Note]:
        """
        Get all notes associated with a specific project.

        Args:
            project_id: The ID of the project to retrieve notes for

        Returns:
            List of Note objects belonging to the project
        """
        result = self._service.get_notes_by_project(project_id)
        return cast("list[Note]", self._handle_data_result(result, []))

    def get_notes_without_project(self) -> list[Note]:
        """
        Get all notes that are not associated with any project.

        Returns:
            List of Note objects without project association
        """
        result = self._service.get_notes_without_project()
        return cast("list[Note]", self._handle_data_result(result, []))

    def assign_notes_to_project(self, note_ids: list[str], project_id: str) -> bool:
        """
        Assign multiple notes to a project.

        Args:
            note_ids: List of note IDs to assign to the project
            project_id: The project ID to assign notes to

        Returns:
            True if all notes were successfully assigned, False otherwise
        """
        return self._handle_simple_success(
            self._service.assign_notes_to_project(note_ids, project_id)
        )

    def remove_notes_from_project(self, note_ids: list[str]) -> bool:
        """
        Remove project association from multiple notes.

        Args:
            note_ids: List of note IDs to remove from their projects

        Returns:
            True if all notes were successfully updated, False otherwise
        """
        return self._handle_simple_success(self._service.remove_notes_from_project(note_ids))

    def get_project_notes_count(self, project_id: str) -> int:
        """
        Get the count of notes associated with a specific project.

        Args:
            project_id: The ID of the project to count notes for

        Returns:
            Number of notes in the project
        """
        result = self._service.get_project_notes_count(project_id)
        if result.success:
            return result.data if result.data is not None else 0
        return 0

    def update_note_project(self, note_id: str, project_id: str | None) -> bool:
        """Update a single note's project association"""
        return self._handle_simple_success(self._service.update_note_project(note_id, project_id))
