#!/usr/bin/env python3
"""
Artifacts Database Manager
Manages all artifact database operations with resilient handling,
version control, and file storage integration.
"""

import contextlib
import hashlib
import json
import sqlite3
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Final, Protocol, TypedDict, cast

from input_processing.stages.sql_protection import SQLInjectionProtection
from models.artifact import Artifact, ArtifactCollection, ArtifactVersion
from utils.artifact_encryption import ArtifactEncryption
from utils.logger import Logger


class DatabaseManager(Protocol):
    """Protocol for database manager interface"""

    def get_artifacts_connection(self) -> sqlite3.Connection: ...

    base_dir: Path
    user_name: str


class ArtifactCreateResult(TypedDict):
    id: str
    storage_uri: str | None
    checksum: str | None
    created_at: str | None
    updated_at: str | None
    version: int
    size_bytes: int | None


class ArtifactStats(TypedDict):
    total_artifacts: int
    artifacts_by_type: dict[str, int]
    total_size_bytes: int
    total_size_mb: float
    encrypted_artifacts: int
    total_collections: int
    versioned_artifacts: int


class ArtifactsDatabase:
    """Manages artifacts database operations with file storage support"""

    # File size threshold for external storage (5MB)
    FILE_SIZE_THRESHOLD: Final[int] = 5 * 1024 * 1024
    _ARTIFACT_INSERT_COLUMNS: ClassVar[tuple[str, ...]] = (
        "id",
        "name",
        "description",
        "content_type",
        "status",
        "content",
        "content_path",
        "size_bytes",
        "mime_type",
        "checksum",
        "collection_id",
        "parent_id",
        "version",
        "is_latest",
        "encrypted_fields",
        "encryption_key_id",
        "project_id",
        "chat_session_id",
        "note_id",
        "tags",
        "metadata",
        "properties",
        "created_at",
        "updated_at",
        "accessed_at",
    )
    _ARTIFACT_UPDATE_FIELDS: ClassVar[tuple[str, ...]] = (
        "name",
        "description",
        "encrypted_fields",
        "tags",
        "metadata",
        "properties",
        "content",
        "content_path",
        "size_bytes",
        "checksum",
    )
    _COLLECTION_UPDATE_FIELDS: ClassVar[tuple[str, ...]] = (
        "name",
        "description",
        "parent_id",
        "project_id",
        "is_encrypted",
        "is_public",
        "tags",
        "properties",
    )
    _INSERT_ARTIFACT_SQL: ClassVar[str] = (
        f"INSERT INTO artifacts ({', '.join(_ARTIFACT_INSERT_COLUMNS)}) "
        f"VALUES ({', '.join(['?'] * len(_ARTIFACT_INSERT_COLUMNS))})"
    )

    def __init__(self, db_manager: DatabaseManager, encryption_password: str | None = None) -> None:
        """Initialize with database manager reference

        Args:
            db_manager: Database manager instance
            encryption_password: Password for encryption-at-rest (optional)
        """
        self.db_manager = db_manager
        self.logger = Logger()
        self.username = db_manager.user_name

        # Initialize encryption if password provided
        self.encryption = ArtifactEncryption(encryption_password) if encryption_password else None
        self.encryption_at_rest = bool(encryption_password)

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        return self.db_manager.get_artifacts_connection()

    def _get_storage_path(self, artifact: Artifact) -> Path:
        """Get file storage path for artifact"""
        storage_path = artifact.get_storage_path(self.username)
        return Path(self.db_manager.base_dir) / storage_path

    @staticmethod
    def _compute_checksum(content: bytes) -> str:
        """Compute SHA256 checksum of content"""
        return hashlib.sha256(content).hexdigest()

    def _encrypt_file_content(self, content: bytes) -> tuple[bytes, dict[str, str] | None]:
        """Encrypt file content for storage

        Args:
            content: Raw file content

        Returns:
            Tuple of (encrypted_content, encryption_metadata)
        """
        if not self.encryption_at_rest or not self.encryption:
            return content, None

        try:
            # Encrypt the content
            encrypted_data = self.encryption.encrypt_data(content)

            # Convert to bytes for storage (JSON + base64)
            encrypted_json = json.dumps(encrypted_data).encode("utf-8")

            # Return metadata for database storage
            metadata: dict[str, str] = {
                "encryption_algorithm": "AES-256-CBC",
                "encrypted": "true",
                "salt": str(encrypted_data["salt"]),
                "iv": str(encrypted_data["iv"]),
            }

            return encrypted_json, {k: str(v) for k, v in metadata.items()} if metadata else None

        except (ValueError, TypeError, OSError) as e:
            self.logger.error(f"Failed to encrypt file content: {e}")
            # Fall back to unencrypted storage
            return content, None

    def _decrypt_file_content(
        self, encrypted_content: bytes, encryption_metadata: dict[str, str] | None
    ) -> bytes:
        """Decrypt file content from storage

        Args:
            encrypted_content: Encrypted file content
            encryption_metadata: Encryption metadata from database

        Returns:
            Decrypted content
        """
        if not encryption_metadata or not encryption_metadata.get("encrypted"):
            return encrypted_content

        if not self.encryption:
            raise ValueError("Encryption password required to decrypt file content")

        try:
            # Parse encrypted JSON
            encrypted_data = json.loads(encrypted_content.decode("utf-8"))

            # Decrypt the content
            return self.encryption.decrypt_data(encrypted_data)

        except (ValueError, TypeError, OSError) as e:
            self.logger.error(f"Failed to decrypt file content: {e}")
            raise ValueError(f"Cannot decrypt file content: {e}") from e

    def _handle_file_storage(self, artifact: Artifact, content: bytes | None = None) -> Artifact:
        """Handle file storage for large artifacts with optional encryption"""
        if content is None:
            return artifact

        size_bytes = len(content)
        artifact.size_bytes = size_bytes
        artifact.checksum = self._compute_checksum(content)

        # Determine storage strategy based on size
        if size_bytes > self.FILE_SIZE_THRESHOLD:
            # Store in filesystem with optional encryption
            storage_path = self._get_storage_path(artifact)
            storage_path.parent.mkdir(parents=True, exist_ok=True)

            # Encrypt content if encryption is enabled
            content_to_store, encryption_metadata = self._encrypt_file_content(content)

            file_path = storage_path / "content.bin"
            with file_path.open("wb") as f:
                f.write(content_to_store)

            artifact.content_path = str(file_path.relative_to(self.db_manager.base_dir))
            artifact.content = None  # Don't store in database

            # Store encryption metadata if content was encrypted
            if encryption_metadata:
                if artifact.metadata is None:
                    artifact.metadata = {}
                if isinstance(artifact.metadata, dict):
                    artifact.metadata.update(encryption_metadata)
                artifact.encryption_key_id = "file_encryption"  # Mark as file-encrypted

            self.logger.info(
                f"Stored artifact {artifact.id} to file: {artifact.content_path} "
                f"(encrypted: {bool(encryption_metadata)})"
            )
        else:
            # Store in database
            artifact.content = content.decode("utf-8", errors="replace")
            artifact.content_path = None

        return artifact

    def _resolve_artifact_file_path(self, relative_path: str) -> Path:
        base_dir = Path(self.db_manager.base_dir).resolve()
        candidate_path = (base_dir / relative_path).resolve()

        try:
            candidate_path.relative_to(base_dir)
        except ValueError as exc:
            raise ValueError("Invalid file path") from exc

        return candidate_path

    @staticmethod
    def _read_file_bytes(file_path: Path) -> bytes | None:
        if not file_path.exists():
            return None
        return file_path.read_bytes()

    @staticmethod
    def _normalize_encryption_metadata(
        metadata: object | None,
    ) -> dict[str, str] | None:
        if not isinstance(metadata, Mapping):
            return None
        normalized_metadata = cast("Mapping[str, object]", metadata)
        return {str(key): str(value) for key, value in normalized_metadata.items()}

    def create_artifact(
        self, artifact: Artifact, content: bytes | None = None
    ) -> ArtifactCreateResult:
        """Create a new artifact with content storage and metadata tracking.

        Args:
            artifact: Artifact object with metadata
            content: Optional binary content to store

        Returns:
            Dictionary with artifact metadata including id, storage_uri, checksum, timestamps

        Raises:
            ValueError: If artifact data is invalid
            RuntimeError: If database operation fails
        """
        try:
            # Validate input
            if not artifact.id:
                artifact.id = str(uuid.uuid4())

            # Handle content storage if provided
            if content is not None:
                artifact = self._handle_file_storage(artifact, content)

            # Set timestamps as ISO format strings
            now = datetime.now(UTC)
            artifact.created_at = now.isoformat()
            artifact.updated_at = now.isoformat()
            artifact.version = 1
            artifact.is_latest = True

            # Insert into database
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Insert artifact record
                artifact_dict = artifact.to_dict()
                values = [artifact_dict.get(column) for column in self._ARTIFACT_INSERT_COLUMNS]
                cursor.execute(self._INSERT_ARTIFACT_SQL, values)

                # Create initial version record
                self._create_version(cursor, artifact)

                # Update collection stats if artifact belongs to collection
                if artifact.collection_id:
                    self._update_collection_stats(cursor, artifact.collection_id)

                conn.commit()

                self.logger.info(f"Created artifact {artifact.id} with version 1")

                result: ArtifactCreateResult = {
                    "id": artifact.id,
                    "storage_uri": artifact.content_path,
                    "checksum": artifact.checksum,
                    "created_at": artifact.created_at,
                    "updated_at": artifact.updated_at,
                    "version": artifact.version,
                    "size_bytes": artifact.size_bytes,
                }
                return result

        except sqlite3.Error as e:
            self.logger.error(f"Database error creating artifact: {e}")
            raise RuntimeError(f"Failed to create artifact: {e}") from e
        except (ValueError, TypeError, OSError) as e:
            self.logger.error(f"Unexpected error creating artifact: {e}")
            raise RuntimeError(f"Failed to create artifact: {e}") from e

    def update_artifact(
        self, artifact_id: str, updates: Mapping[str, object], content: bytes | None = None
    ) -> bool:
        """Update an existing artifact"""
        try:
            # Retrieve current artifact
            current = self.get_artifact(artifact_id)
            if not current:
                return False

            # Prepare content-related updates
            content_updates = self._prepare_content_update(current, content)

            # Combine updates
            merged_updates: dict[str, object] = {**dict(updates), **content_updates}
            # Build SQL clauses and parameters
            set_clauses, params = self._build_update_query(merged_updates)
            if not set_clauses:
                return False

            # Add version and timestamp
            new_version, timestamp = self._prepare_version_update(current)
            set_clauses.extend(["version = ?", "updated_at = ?"])
            # Ensure consistent serialization for timestamp values
            timestamp_iso = timestamp.isoformat()
            params.extend([new_version, timestamp_iso])

            with self._get_connection() as conn:
                cursor = conn.cursor()
                self._reset_latest_flag(cursor, current)
                cursor.execute(self._build_update_statement(set_clauses), (*params, artifact_id))
                conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error updating artifact: {e}")
            return False

    def _prepare_content_update(
        self, current: Artifact, content: bytes | None
    ) -> dict[str, object]:
        updates: dict[str, object] = {}
        if content is not None:
            temp_artifact = Artifact(id=current.id)
            temp_artifact.created_at = current.created_at
            temp_artifact = self._handle_file_storage(temp_artifact, content)
            updates.update(
                {
                    "content": temp_artifact.content,
                    "content_path": temp_artifact.content_path,
                    "size_bytes": temp_artifact.size_bytes,
                    "checksum": temp_artifact.checksum,
                }
            )
        return updates

    def _build_update_query(self, updates: Mapping[str, object]) -> tuple[list[str], list[object]]:
        set_clauses: list[str] = []
        params: list[object] = []
        for key in self._ARTIFACT_UPDATE_FIELDS:
            if key not in updates:
                continue
            formatted = self._format_artifact_value(key, updates[key])
            column = self._validate_column_name(key)
            set_clauses.append(f"{column} = ?")
            params.append(formatted)
        return set_clauses, params

    @staticmethod
    def _build_update_statement(set_clauses: list[str]) -> str:
        clause = ", ".join(set_clauses)
        return f"UPDATE artifacts SET {clause} WHERE id = ?"

    def _build_collection_update(
        self, updates: Mapping[str, object]
    ) -> tuple[list[str], list[object]]:
        set_clauses: list[str] = []
        params: list[object] = []
        for key in self._COLLECTION_UPDATE_FIELDS:
            if key not in updates:
                continue
            formatted = self._format_collection_value(key, updates[key])
            column = self._validate_column_name(key)
            set_clauses.append(f"{column} = ?")
            params.append(formatted)
        return set_clauses, params

    @staticmethod
    def _build_collection_update_statement(set_clauses: list[str]) -> str:
        clause = ", ".join(set_clauses)
        return f"UPDATE artifact_collections SET {clause} WHERE id = ?"

    @staticmethod
    def _format_list(value: object) -> object:
        if isinstance(value, list):
            any_items = cast("list[Any]", value)
            for item in any_items:
                if not isinstance(item, str):
                    raise ValueError("List values must be strings for SQL update formatting")
            string_items = cast("list[str]", any_items)
            return json.dumps(string_items)
        return value

    @staticmethod
    def _format_dict(value: object) -> object:
        if isinstance(value, dict):
            return json.dumps(value)
        return value

    def _format_artifact_value(self, key: str, value: object) -> object:
        if key in {"encrypted_fields", "tags"}:
            return self._format_list(value)
        if key in {"metadata", "properties"}:
            return self._format_dict(value)
        return value

    def _format_collection_value(self, key: str, value: object) -> object:
        if key == "tags":
            return self._format_list(value)
        if key == "properties":
            return self._format_dict(value)
        return value

    @staticmethod
    def _validate_column_name(column: str) -> str:
        if not SQLInjectionProtection.validate_identifier(column):
            raise ValueError(f"Unsafe column name: {column}")
        return column

    def _prepare_version_update(self, current: Artifact) -> tuple[int, datetime]:
        new_version = current.version + 1
        return new_version, datetime.now(UTC)

    def _reset_latest_flag(self, cursor: sqlite3.Cursor, current: Artifact) -> None:
        if current.is_latest:
            cursor.execute("UPDATE artifacts SET is_latest = false WHERE id = ?", (current.id,))
        else:
            cursor.execute(
                "UPDATE artifacts SET is_latest = false WHERE parent_id = ?",
                (current.parent_id,),
            )

    def delete_artifact(self, artifact_id: str, hard_delete: bool = False) -> bool:
        """Delete an artifact (soft delete by default)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                if hard_delete:
                    # Get artifact for cleanup
                    artifact = self.get_artifact(artifact_id)
                    if not artifact:
                        return False

                    # Delete versions first (foreign key constraint)
                    cursor.execute(
                        """DELETE FROM artifact_versions
                                     WHERE artifact_id = ?""",
                        (artifact_id,),
                    )

                    # Delete permissions
                    cursor.execute(
                        """DELETE FROM artifact_permissions
                                     WHERE artifact_id = ?""",
                        (artifact_id,),
                    )

                    # Delete artifact
                    cursor.execute(
                        """DELETE FROM artifacts
                                     WHERE id = ?""",
                        (artifact_id,),
                    )

                    # Clean up file storage if exists
                    if artifact.content_path:
                        file_path = Path(self.db_manager.base_dir) / artifact.content_path
                        if file_path.exists():
                            file_path.unlink()
                            # Try to remove empty directories
                            with contextlib.suppress(OSError):
                                file_path.parent.rmdir()

                    # Update collection stats
                    if artifact.collection_id:
                        self._update_collection_stats(cursor, artifact.collection_id)
                else:
                    # Soft delete
                    cursor.execute(
                        """UPDATE artifacts
                                     SET status = 'deleted',
                                         updated_at = CURRENT_TIMESTAMP
                                     WHERE id = ?""",
                        (artifact_id,),
                    )

                conn.commit()

                return cursor.rowcount > 0

        except Exception as e:
            self.logger.error(f"Failed to delete artifact: {str(e)}")
            return False

    def get_artifact(self, artifact_id: str, update_accessed: bool = True) -> Artifact | None:
        """Get a specific artifact"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM artifacts WHERE id = ?
                """,
                    (artifact_id,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                # Update accessed timestamp if requested
                if update_accessed:
                    cursor.execute(
                        """UPDATE artifacts
                                     SET accessed_at = CURRENT_TIMESTAMP
                                     WHERE id = ?""",
                        (artifact_id,),
                    )
                    conn.commit()

                return self._row_to_artifact(row)

        except Exception as e:
            self.logger.error(f"Failed to get artifact: {str(e)}")
            return None

    def get_artifact_content(self, artifact_id: str) -> bytes | None:
        """Get artifact content (from database or file) with automatic decryption"""
        try:
            artifact = self.get_artifact(artifact_id)
            if not artifact:
                return None

            if artifact.content:
                # Content stored in database
                return artifact.content.encode("utf-8")
            if not artifact.content_path:
                return None

            file_path = self._resolve_artifact_file_path(artifact.content_path)
            file_bytes = self._read_file_bytes(file_path)
            if file_bytes is None:
                return None

            encryption_metadata = self._normalize_encryption_metadata(artifact.metadata)
            if encryption_metadata and encryption_metadata.get("encrypted") == "true":
                result = self._decrypt_file_content(file_bytes, encryption_metadata)
            else:
                result = file_bytes
            return result

        except Exception as e:
            self.logger.error(f"Failed to get artifact content: {str(e)}")
            return None

    def search_artifacts(self, query: str, limit: int = 100) -> list[Artifact]:
        """Search artifacts by name, description, or tags"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                search_pattern = f"%{query}%"
                cursor.execute(
                    """
                    SELECT * FROM artifacts
                    WHERE (name LIKE ? OR description LIKE ? OR tags LIKE ?)
                    AND status != 'deleted'
                    ORDER BY updated_at DESC
                    LIMIT ?
                """,
                    (search_pattern, search_pattern, search_pattern, limit),
                )

                artifacts: list[Artifact] = []
                for row in cursor.fetchall():
                    artifact = self._row_to_artifact(row)
                    artifacts.append(artifact)

                return artifacts

        except Exception as e:
            self.logger.error(f"Failed to search artifacts: {str(e)}")
            return []

    def get_artifacts_by_type(self, content_type: str, limit: int = 100) -> list[Artifact]:
        """Get artifacts by content type"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM artifacts
                    WHERE content_type = ? AND status != 'deleted'
                    ORDER BY updated_at DESC
                    LIMIT ?
                """,
                    (content_type, limit),
                )

                artifacts: list[Artifact] = []
                for row in cursor.fetchall():
                    artifact = self._row_to_artifact(row)
                    artifacts.append(artifact)

                return artifacts

        except Exception as e:
            self.logger.error(f"Failed to get artifacts by type: {str(e)}")
            return []

    def get_artifacts_by_collection(self, collection_id: str) -> list[Artifact]:
        """Get all artifacts in a collection"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM artifacts
                    WHERE collection_id = ? AND status != 'deleted'
                    ORDER BY name, updated_at DESC
                """,
                    (collection_id,),
                )

                artifacts: list[Artifact] = []
                for row in cursor.fetchall():
                    artifact = self._row_to_artifact(row)
                    artifacts.append(artifact)

                return artifacts

        except Exception as e:
            self.logger.error(f"Failed to get artifacts by collection: {str(e)}")
            return []

    def get_artifacts_by_project(self, project_id: str) -> list[Artifact]:
        """Get all artifacts in a project"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM artifacts
                    WHERE project_id = ? AND status != 'deleted'
                    ORDER BY updated_at DESC
                """,
                    (project_id,),
                )

                artifacts: list[Artifact] = []
                for row in cursor.fetchall():
                    artifact = self._row_to_artifact(row)
                    artifacts.append(artifact)

                return artifacts

        except Exception as e:
            self.logger.error(f"Failed to get artifacts by project: {str(e)}")
            return []

    def create_collection(self, collection: ArtifactCollection) -> dict[str, Any]:
        """Create a new artifact collection"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                collection_dict = collection.to_dict()

                cursor.execute(
                    """
                    INSERT INTO artifact_collections
                    (id, name, description, parent_id, project_id,
                     is_encrypted, is_public, tags, properties,
                     artifact_count, total_size_bytes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        collection_dict["id"],
                        collection_dict["name"],
                        collection_dict["description"],
                        collection_dict["parent_id"],
                        collection_dict["project_id"],
                        collection_dict["is_encrypted"],
                        collection_dict["is_public"],
                        collection_dict["tags"],
                        collection_dict["properties"],
                        collection_dict["artifact_count"],
                        collection_dict["total_size_bytes"],
                        collection_dict["created_at"],
                        collection_dict["updated_at"],
                    ),
                )

                conn.commit()

                self.logger.info(f"Created collection: {collection.id}")
                return {"success": True, "id": collection.id}

        except Exception as e:
            self.logger.error(f"Failed to create collection: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_collections(self, parent_id: str | None = None) -> list[ArtifactCollection]:
        """Get all collections or collections under a parent"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                if parent_id is None:
                    # Get root collections
                    cursor.execute(
                        """
                        SELECT * FROM artifact_collections
                        WHERE parent_id IS NULL
                        ORDER BY name
                    """
                    )
                else:
                    # Get child collections
                    cursor.execute(
                        """
                        SELECT * FROM artifact_collections
                        WHERE parent_id = ?
                        ORDER BY name
                    """,
                        (parent_id,),
                    )

                collections: list[ArtifactCollection] = []
                for row in cursor.fetchall():
                    collection = self._row_to_collection(row)
                    collections.append(collection)

                return collections

        except Exception as e:
            self.logger.error(f"Failed to get collections: {str(e)}")
            return []

    def update_collection(self, collection_id: str, updates: Mapping[str, object]) -> bool:
        """Update a collection"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Build dynamic update query
                set_clauses, params = self._build_collection_update(updates)
                if not set_clauses:
                    return False

                # Always update the timestamp
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")

                update_statement = self._build_collection_update_statement(set_clauses)
                cursor.execute(update_statement, (*params, collection_id))

                conn.commit()

                return cursor.rowcount > 0

        except Exception as e:
            self.logger.error(f"Failed to update collection: {str(e)}")
            return False

    def create_version(self, artifact_id: str, change_summary: str | None = None) -> bool:
        """Create a new version of an artifact"""
        try:
            artifact = self.get_artifact(artifact_id)
            if not artifact:
                return False

            with self._get_connection() as conn:
                cursor = conn.cursor()

                version = ArtifactVersion(
                    id=str(uuid.uuid4()),
                    artifact_id=artifact_id,
                    version_number=artifact.version,
                    artifact_data=artifact.to_dict(),
                    change_summary=change_summary or "Manual version created",
                )

                self._create_version_record(cursor, version)
                conn.commit()

                return True

        except Exception as e:
            self.logger.error(f"Failed to create version: {str(e)}")
            return False

    def get_versions(self, artifact_id: str) -> list[ArtifactVersion]:
        """Get all versions of an artifact"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM artifact_versions
                    WHERE artifact_id = ?
                    ORDER BY version_number DESC
                    """,
                    (artifact_id,),
                )

                versions: list[ArtifactVersion] = []
                for row in cursor.fetchall():
                    version = self._row_to_version(row)
                    versions.append(version)

                return versions

        except Exception as e:
            self.logger.error(f"Failed to get versions: {str(e)}")
            return []

    def restore_version(self, artifact_id: str, version_number: int) -> bool:
        """Restore an artifact to a specific version"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Get the version to restore
                cursor.execute(
                    """
                    SELECT artifact_data FROM artifact_versions
                    WHERE artifact_id = ? AND version_number = ?
                """,
                    (artifact_id, version_number),
                )

                row = cursor.fetchone()
                if not row:
                    return False

                # Parse artifact data
                artifact_data = json.loads(row[0])

                # Prepare update data
                updates = {
                    key: value
                    for key, value in artifact_data.items()
                    if key not in ["id", "version", "created_at", "updated_at"]
                }

                # Add restoration metadata
                updates["change_summary"] = f"Restored to version {version_number}"

                # Perform the update
                return self.update_artifact(artifact_id, updates)

        except Exception as e:
            self.logger.error(f"Failed to restore version: {str(e)}")
            return False

    def get_artifact_statistics(self) -> ArtifactStats:
        """Get artifact statistics"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                stats: ArtifactStats = {
                    "total_artifacts": 0,
                    "artifacts_by_type": {},
                    "total_size_bytes": 0,
                    "total_size_mb": 0.0,
                    "encrypted_artifacts": 0,
                    "total_collections": 0,
                    "versioned_artifacts": 0,
                }

                # Total artifacts
                cursor.execute(
                    """SELECT COUNT(*) FROM artifacts
                                 WHERE status != 'deleted' """
                )
                total_artifacts = cursor.fetchone()
                stats["total_artifacts"] = int(total_artifacts[0]) if total_artifacts else 0

                # Artifacts by type
                cursor.execute(
                    """
                    SELECT content_type, COUNT(*)
                    FROM artifacts
                    WHERE status != 'deleted'
                    GROUP BY content_type
                """
                )
                artifacts_by_type: dict[str, int] = {}
                for content_type, count in cursor.fetchall():
                    key = str(content_type) if content_type is not None else "unknown"
                    artifacts_by_type[key] = int(count)
                stats["artifacts_by_type"] = artifacts_by_type

                # Total storage size
                cursor.execute(
                    """
                    SELECT SUM(size_bytes)
                    FROM artifacts
                    WHERE status != 'deleted'
                """
                )
                size_row = cursor.fetchone()
                total_size = int(size_row[0]) if size_row and size_row[0] is not None else 0
                stats["total_size_bytes"] = total_size
                stats["total_size_mb"] = round(total_size / (1024 * 1024), 2)

                # Encrypted artifacts
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM artifacts
                    WHERE encrypted_fields != '' AND status != 'deleted'
                """
                )
                encrypted_row = cursor.fetchone()
                stats["encrypted_artifacts"] = int(encrypted_row[0]) if encrypted_row else 0

                # Collections
                cursor.execute("SELECT COUNT(*) FROM artifact_collections")
                collections_row = cursor.fetchone()
                stats["total_collections"] = int(collections_row[0]) if collections_row else 0

                # Artifacts with versions
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT artifact_id)
                    FROM artifact_versions
                """
                )
                versioned_row = cursor.fetchone()
                stats["versioned_artifacts"] = int(versioned_row[0]) if versioned_row else 0

                return stats

        except Exception as e:
            self.logger.error(f"Failed to get artifact statistics: {str(e)}")
            return {
                "total_artifacts": 0,
                "artifacts_by_type": {},
                "total_size_bytes": 0,
                "total_size_mb": 0.0,
                "encrypted_artifacts": 0,
                "total_collections": 0,
                "versioned_artifacts": 0,
            }

    def _create_version(self, cursor: sqlite3.Cursor, artifact: Artifact) -> ArtifactVersion:
        """Create initial version for new artifact"""
        version = ArtifactVersion(
            id=str(uuid.uuid4()),
            artifact_id=artifact.id,
            version_number=1,
            artifact_data=artifact.to_dict(),
            change_summary="Initial version",
        )
        self._create_version_record(cursor, version)
        return version

    def _create_version_record(self, cursor: sqlite3.Cursor, version: ArtifactVersion) -> None:
        """Insert version record into database"""
        version_dict = version.to_dict()
        cursor.execute(
            """
            INSERT INTO artifact_versions
            (id, artifact_id, version_number, artifact_data,
             change_summary, changed_by, changed_fields, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                version_dict["id"],
                version_dict["artifact_id"],
                version_dict["version_number"],
                version_dict["artifact_data"],
                version_dict["change_summary"],
                version_dict["changed_by"],
                version_dict["changed_fields"],
                version_dict["created_at"],
            ),
        )

    def _update_collection_stats(self, cursor: sqlite3.Cursor, collection_id: str) -> None:
        """Update collection statistics"""
        cursor.execute(
            """
            SELECT COUNT(*), SUM(size_bytes)
            FROM artifacts
            WHERE collection_id = ? AND status != 'deleted'
        """,
            (collection_id,),
        )

        count, total_size = cursor.fetchone()

        cursor.execute(
            """
            UPDATE artifact_collections
            SET artifact_count = ?,
                total_size_bytes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (count or 0, total_size or 0, collection_id),
        )

    @staticmethod
    def _row_to_artifact(row: tuple[Any, ...]) -> Artifact:
        """Convert database row to Artifact object"""
        return Artifact.from_dict(
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "content_type": row[3],
                "status": row[4],
                "content": row[5],
                "content_path": row[6],
                "size_bytes": row[7],
                "mime_type": row[8],
                "checksum": row[9],
                "collection_id": row[10],
                "parent_id": row[11],
                "version": row[12],
                "is_latest": bool(row[13]),
                "encrypted_fields": row[14],
                "encryption_key_id": row[15],
                "project_id": row[16],
                "chat_session_id": row[17],
                "note_id": row[18],
                "tags": row[19],
                "metadata": row[20],
                "properties": row[21],
                "created_at": row[22],
                "updated_at": row[23],
                "accessed_at": row[24],
            }
        )

    @staticmethod
    def _row_to_collection(row: tuple[Any, ...]) -> ArtifactCollection:
        """Convert database row to ArtifactCollection object"""
        return ArtifactCollection.from_dict(
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "parent_id": row[3],
                "project_id": row[4],
                "is_encrypted": bool(row[5]),
                "is_public": bool(row[6]),
                "tags": row[7],
                "properties": row[8],
                "artifact_count": row[9],
                "total_size_bytes": row[10],
                "created_at": row[11],
                "updated_at": row[12],
            }
        )

    @staticmethod
    def _row_to_version(row: tuple[Any, ...]) -> ArtifactVersion:
        """Convert database row to ArtifactVersion object"""
        return ArtifactVersion.from_dict(
            {
                "id": row[0],
                "artifact_id": row[1],
                "version_number": row[2],
                "artifact_data": row[3],
                "change_summary": row[4],
                "changed_by": row[5],
                "changed_fields": row[6],
                "created_at": row[7],
            }
        )

    def update_artifact_project(self, artifact_id: str, project_id: str | None) -> bool:
        """Update a single artifact's project association"""
        return self.update_artifact(artifact_id, {"project_id": project_id})
