"""
NotesValidator - Data validation for notes operations.
Handles input validation and business rule enforcement.
"""

from dataclasses import dataclass
from typing import Any

from utils.logger import Logger


@dataclass
class ValidationResult:
    """Result of a validation operation"""

    is_valid: bool
    errors: list[str]
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class NotesValidator:
    """
    Validator for notes data and operations.
    Handles business rule validation separate from security concerns.
    """

    def __init__(self):
        self.logger = Logger()

    def validate_note_creation(self, title: str, content: str, tags: list[str]) -> ValidationResult:
        """Validate data for note creation"""
        errors = []
        warnings = []

        # Business rules for note creation
        if not title or not title.strip():
            errors.append("Note title cannot be empty")
        elif len(title.strip()) < 3:
            warnings.append("Note title is very short (less than 3 characters)")

        if len(content) > 50000:  # Business limit vs security limit
            errors.append("Note content exceeds maximum allowed length (50,000 characters)")

        if len(tags) > 20:  # Business limit for usability
            warnings.append("Many tags may make organization difficult")

        # Check for duplicate tags
        if len(tags) != len({tag.lower() for tag in tags}):
            warnings.append("Duplicate tags detected (case-insensitive)")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_note_update(self, updates: dict[str, Any]) -> ValidationResult:
        """Validate data for note updates"""
        errors = []
        warnings = []

        allowed_fields = {"title", "content", "tags", "content_html", "project_id"}

        # Check for unknown fields
        unknown_fields = set(updates.keys()) - allowed_fields
        if unknown_fields:
            errors.append(f"Unknown fields: {', '.join(unknown_fields)}")

        # Validate specific fields
        if "title" in updates:
            title = updates["title"]
            if not isinstance(title, str):
                errors.append("Title must be a string")
            elif not title.strip():
                errors.append("Title cannot be empty")

        if "content" in updates:
            content = updates["content"]
            if not isinstance(content, str):
                errors.append("Content must be a string")

        if "tags" in updates:
            tags = updates["tags"]
            if not isinstance(tags, list):
                errors.append("Tags must be a list")
            else:
                for tag in tags:
                    if not isinstance(tag, str):
                        errors.append("All tags must be strings")
                        break

        if "project_id" in updates:
            project_id = updates["project_id"]
            if project_id is not None and not isinstance(project_id, str):
                errors.append("Project ID must be a string or None")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_search_query(self, query: str, filter_option: str) -> ValidationResult:
        """Validate search parameters"""
        errors = []
        warnings = []

        if not query or not query.strip():
            errors.append("Search query cannot be empty")

        valid_filters = {"All", "Title Only", "Content Only", "Tags Only"}
        if filter_option not in valid_filters:
            errors.append(f"Invalid filter option. Must be one of: {', '.join(valid_filters)}")

        if len(query) > 500:
            warnings.append("Search query is very long, results may be slow")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_bulk_operation(self, note_ids: list[str], operation: str) -> ValidationResult:
        """Validate parameters for bulk operations"""
        errors = []
        warnings = []

        if not note_ids:
            errors.append("No note IDs provided for bulk operation")

        if len(note_ids) > 100:
            warnings.append("Bulk operation affects many notes, consider smaller batches")

        # Check for duplicates
        if len(note_ids) != len(set(note_ids)):
            errors.append("Duplicate note IDs in bulk operation")

        # Validate operation type
        valid_operations = {"assign_project", "remove_from_project", "delete", "restore"}
        if operation not in valid_operations:
            errors.append(f"Invalid operation. Must be one of: {', '.join(valid_operations)}")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)
