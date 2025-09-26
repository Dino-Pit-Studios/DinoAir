"""
NotesService - Main service orchestrating notes operations.
Combines repository, security, and validation for complete note management.
"""

from dataclasses import dataclass
from typing import Any

from models.note import Note
from utils.logger import Logger

from .notes_repository import NotesRepository
from .notes_security import NotesSecurity
from .notes_validator import NotesValidator


@dataclass
class OperationResult:
    """Standardized result for service operations"""

    success: bool
    data: Any = None
    error: str = ""
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class NotesService:
    """
    Main service for notes operations.
    Orchestrates repository, security, and validation components.
    This replaces the monolithic NotesDatabase class.
    """

    def __init__(self, user_name: str | None = None):
        self.logger = Logger()
        self.repository = NotesRepository(user_name)
        self.security = NotesSecurity()
        self.validator = NotesValidator()

        # Clean up test data if running in test environment
        self._cleanup_test_data()

    def _cleanup_test_data(self) -> None:
        """Clean up test data in test environments"""
        try:
            # Placeholder for future test data cleanup logic
            # Currently no cleanup operations are needed
            pass
        except Exception as e:
            self.logger.error(f"Error during test data cleanup: {str(e)}")

    def create_note(
        self, note: Note, content_html: str | None = None, project_id: str | None = None
    ) -> OperationResult:
        """
        Create a new note with full validation and security checks.

        Args:
            note: Note object to create
            content_html: Optional HTML content
            project_id: Optional project association

        Returns:
            OperationResult with success status and data
        """
        try:
            # Business validation
            biz_validation = self.validator.validate_note_creation(
                note.title, note.content, note.tags
            )
            if not biz_validation.is_valid:
                return OperationResult(
                    success=False,
                    error="; ".join(biz_validation.errors),
                    warnings=biz_validation.warnings,
                )

            # Security validation
            security_validation = self.security.validate_note_data(
                note.title, note.content, note.tags
            )
            if not security_validation["valid"]:
                return OperationResult(
                    success=False,
                    error="Security validation failed: " + "; ".join(security_validation["errors"]),
                )

            # Security write permission check
            can_write, write_error = self.security.can_perform_write_operation("create_note")
            if not can_write:
                return OperationResult(success=False, error=write_error)

            # Set project_id if provided
            if project_id:
                note.project_id = project_id

            # Create in repository
            repo_result = self.repository.create_note(note, content_html)
            if repo_result.success:
                return OperationResult(
                    success=True,
                    data={"note_id": note.id, "message": "Note created successfully"},
                    warnings=biz_validation.warnings,
                )
            return OperationResult(success=False, error=repo_result.error)

        except Exception as e:
            self.logger.error(f"Error creating note: {str(e)}")
            return OperationResult(success=False, error=f"Failed to create note: {str(e)}")

    def get_note(self, note_id: str) -> OperationResult:
        """Retrieve a single note by ID"""
        repo_result = self.repository.get_note_by_id(note_id)
        if repo_result.success:
            return OperationResult(success=True, data=repo_result.data)
        return OperationResult(success=False, error=repo_result.error)

    def get_all_notes(self) -> OperationResult:
        """Retrieve all non-deleted notes"""
        repo_result = self.repository.get_all_notes()
        if repo_result.success:
            return OperationResult(success=True, data=repo_result.data)
        return OperationResult(success=False, error=repo_result.error)

    def update_note(self, note_id: str, updates: dict[str, Any]) -> OperationResult:
        """
        Update a note with validation and security checks.

        Args:
            note_id: ID of note to update
            updates: Dictionary of fields to update

        Returns:
            OperationResult with success status
        """
        try:
            # Business validation
            biz_validation = self.validator.validate_note_update(updates)
            if not biz_validation.is_valid:
                return OperationResult(
                    success=False,
                    error="; ".join(biz_validation.errors),
                    warnings=biz_validation.warnings,
                )

            # Check if note exists
            existing_result = self.repository.get_note_by_id(note_id)
            if not existing_result.success:
                return OperationResult(success=False, error="Note not found")

            existing_note = existing_result.data

            # Security validation with merged data
            title = updates.get("title", existing_note.title)
            content = updates.get("content", existing_note.content)
            tags = updates.get("tags", existing_note.tags)

            security_validation = self.security.validate_note_data(title, content, tags)
            if not security_validation["valid"]:
                return OperationResult(
                    success=False,
                    error="Security validation failed: " + "; ".join(security_validation["errors"]),
                )

            # Security write permission check
            can_write, write_error = self.security.can_perform_write_operation("update_note")
            if not can_write:
                return OperationResult(success=False, error=write_error)

            # Update in repository
            repo_result = self.repository.update_note(note_id, updates)
            if repo_result.success and repo_result.affected_rows > 0:
                return OperationResult(
                    success=True,
                    data={
                        "message": "Note updated successfully",
                        "updated_fields": list(updates.keys()),
                    },
                    warnings=biz_validation.warnings,
                )
            return OperationResult(success=False, error="Note not found or update failed")

        except Exception as e:
            self.logger.error(f"Error updating note {note_id}: {str(e)}")
            return OperationResult(success=False, error=f"Failed to update note: {str(e)}")

    def delete_note(self, note_id: str, hard_delete: bool = False) -> OperationResult:
        """Delete a note (soft delete by default)"""
        try:
            can_write, write_error = self.security.can_perform_write_operation("delete_note")
            if not can_write:
                return OperationResult(success=False, error=write_error)

            if hard_delete:
                repo_result = self.repository.hard_delete_note(note_id)
                action = "permanently deleted"
            else:
                repo_result = self.repository.soft_delete_note(note_id)
                action = "deleted"

            if repo_result.success and repo_result.affected_rows > 0:
                return OperationResult(
                    success=True, data={"message": f"Note {action} successfully"}
                )
            return OperationResult(success=False, error="Note not found or already deleted")

        except Exception as e:
            self.logger.error(f"Error deleting note {note_id}: {str(e)}")
            return OperationResult(success=False, error=f"Failed to delete note: {str(e)}")

    def restore_note(self, note_id: str) -> OperationResult:
        """Restore a soft-deleted note"""
        try:
            can_write, write_error = self.security.can_perform_write_operation("restore_note")
            if not can_write:
                return OperationResult(success=False, error=write_error)

            repo_result = self.repository.restore_note(note_id)
            if repo_result.success and repo_result.affected_rows > 0:
                return OperationResult(success=True, data={"message": "Note restored successfully"})
            return OperationResult(success=False, error="Note not found in deleted items")

        except Exception as e:
            self.logger.error(f"Error restoring note {note_id}: {str(e)}")
            return OperationResult(success=False, error=f"Failed to restore note: {str(e)}")

    def search_notes(
        self, query: str, filter_option: str = "All", project_id: str | None = None
    ) -> OperationResult:
        """Search notes with validation"""
        try:
            # Validate search parameters
            validation = self.validator.validate_search_query(query, filter_option)
            if not validation.is_valid:
                return OperationResult(
                    success=False, error="; ".join(validation.errors), warnings=validation.warnings
                )

            # Use raw query; repository composes LIKE with ESCAPE and parameterization
            escaped_query = query

            # Perform search
            repo_result = self.repository.search_notes(escaped_query, filter_option, project_id)
            if repo_result.success:
                return OperationResult(
                    success=True, data=repo_result.data, warnings=validation.warnings
                )
            return OperationResult(success=False, error=repo_result.error)

        except Exception as e:
            self.logger.error(f"Error searching notes: {str(e)}")
            return OperationResult(success=False, error=f"Search failed: {str(e)}")

    def get_notes_by_tag(self, tag: str) -> OperationResult:
        """Get all notes with a specific tag"""
        repo_result = self.repository.get_notes_by_tag(tag)
        if repo_result.success:
            return OperationResult(success=True, data=repo_result.data)
        return OperationResult(success=False, error=repo_result.error)

    def get_all_tags(self) -> OperationResult:
        """Get all unique tags with usage counts"""
        repo_result = self.repository.get_all_tags()
        if repo_result.success:
            return OperationResult(success=True, data=repo_result.data)
        return OperationResult(success=False, error=repo_result.error)

    def rename_tag(self, old_tag: str, new_tag: str) -> OperationResult:
        """Rename a tag across all notes"""
        try:
            can_write, write_error = self.security.can_perform_write_operation("rename_tag")
            if not can_write:
                return OperationResult(success=False, error=write_error)

            repo_result = self.repository.update_tag_in_notes(old_tag, new_tag)
            if repo_result.success:
                affected = repo_result.data["affected_notes"]
                return OperationResult(
                    success=True,
                    data={
                        "message": f"Tag renamed successfully in {affected} notes",
                        "affected_notes": affected,
                    },
                )
            return OperationResult(success=False, error=repo_result.error)

        except Exception as e:
            self.logger.error(f"Error renaming tag: {str(e)}")
            return OperationResult(success=False, error=f"Failed to rename tag: {str(e)}")

    def delete_tag(self, tag_to_delete: str) -> OperationResult:
        """Remove a tag from all notes"""
        try:
            can_write, write_error = self.security.can_perform_write_operation("delete_tag")
            if not can_write:
                return OperationResult(success=False, error=write_error)

            repo_result = self.repository.remove_tag_from_notes(tag_to_delete)
            if repo_result.success:
                affected = repo_result.data["affected_notes"]
                return OperationResult(
                    success=True,
                    data={
                        "message": f"Tag deleted from {affected} notes",
                        "affected_notes": affected,
                    },
                )
            return OperationResult(success=False, error=repo_result.error)

        except Exception as e:
            self.logger.error(f"Error deleting tag: {str(e)}")
            return OperationResult(success=False, error=f"Failed to delete tag: {str(e)}")

    def get_notes_by_project(self, project_id: str) -> OperationResult:
        """Get all notes for a specific project"""
        repo_result = self.repository.get_notes_by_project(project_id)
        if repo_result.success:
            return OperationResult(success=True, data=repo_result.data)
        return OperationResult(success=False, error=repo_result.error)

    def get_notes_without_project(self) -> OperationResult:
        """Get all notes not associated with any project"""
        repo_result = self.repository.get_notes_without_project()
        if repo_result.success:
            return OperationResult(success=True, data=repo_result.data)
        return OperationResult(success=False, error=repo_result.error)

    def assign_notes_to_project(self, note_ids: list[str], project_id: str) -> OperationResult:
        """Assign multiple notes to a project"""
        try:
            # Validate bulk operation
            validation = self.validator.validate_bulk_operation(note_ids, "assign_project")
            if not validation.is_valid:
                return OperationResult(
                    success=False, error="; ".join(validation.errors), warnings=validation.warnings
                )

            can_write, write_error = self.security.can_perform_write_operation(
                "assign_notes_to_project"
            )
            if not can_write:
                return OperationResult(success=False, error=write_error)

            repo_result = self.repository.bulk_update_project(note_ids, project_id)
            if repo_result.success:
                return OperationResult(
                    success=True,
                    data={"message": f"Assigned {repo_result.affected_rows} notes to project"},
                    warnings=validation.warnings,
                )
            return OperationResult(success=False, error=repo_result.error)

        except Exception as e:
            self.logger.error(f"Error assigning notes to project: {str(e)}")
            return OperationResult(success=False, error=f"Failed to assign notes: {str(e)}")

    def remove_notes_from_project(self, note_ids: list[str]) -> OperationResult:
        """Remove project association from multiple notes"""
        try:
            validation = self.validator.validate_bulk_operation(note_ids, "remove_from_project")
            if not validation.is_valid:
                return OperationResult(
                    success=False, error="; ".join(validation.errors), warnings=validation.warnings
                )

            can_write, write_error = self.security.can_perform_write_operation(
                "remove_notes_from_project"
            )
            if not can_write:
                return OperationResult(success=False, error=write_error)

            repo_result = self.repository.bulk_update_project(note_ids, None)
            if repo_result.success:
                return OperationResult(
                    success=True,
                    data={
                        "message": f"Removed project association from {repo_result.affected_rows} notes"
                    },
                    warnings=validation.warnings,
                )
            return OperationResult(success=False, error=repo_result.error)

        except Exception as e:
            self.logger.error(f"Error removing notes from project: {str(e)}")
            return OperationResult(success=False, error=f"Failed to remove notes: {str(e)}")

    def get_project_notes_count(self, project_id: str) -> OperationResult:
        """Get the count of notes associated with a project"""
        repo_result = self.repository.get_project_notes_count(project_id)
        if repo_result.success:
            return OperationResult(success=True, data=repo_result.data)
        return OperationResult(success=False, error=repo_result.error)

    def get_deleted_notes(self) -> OperationResult:
        """Get all soft-deleted notes"""
        repo_result = self.repository.get_deleted_notes()
        if repo_result.success:
            return OperationResult(success=True, data=repo_result.data)
        return OperationResult(success=False, error=repo_result.error)

    def update_note_project(self, note_id: str, project_id: str | None) -> OperationResult:
        """Update a single note's project association"""
        return self.update_note(note_id, {"project_id": project_id})
