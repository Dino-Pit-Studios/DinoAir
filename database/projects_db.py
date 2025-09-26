#!/usr/bin/env python3
"""
Projects Database Manager
Manages all project database operations with resilient handling,
hierarchical organization, and cross-tool integration.

Refactor goals addressed:
- Strict typing with sqlite3-specific annotations and a DBManagerProtocol
- Normalized return types (e.g., update_project returns only bool)
- Merged nested hierarchy validation in create flow
- Introduced helpers: _exec_count, _fetch_projects, _iso_to_dt, _max_updated_at, _recent_activity
- Reduced duplication and complexity across query methods
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import Any, Protocol, TypeGuard

from models.project import Project, ProjectStatistics, ProjectStatus, ProjectSummary
from utils.logger import Logger

# Type aliases for clarity
Connection = sqlite3.Connection
Cursor = sqlite3.Cursor
Row = Sequence[Any]

# Module-level constants for updates and status-driven timestamps
ALLOWED_UPDATE_FIELDS: list[str] = [
    "name",
    "description",
    "status",
    "color",
    "icon",
    "parent_project_id",
    "tags",
    "metadata",
    "completed_at",
    "archived_at",
]

STATUS_TIMESTAMPS: dict[str, dict[str, Any]] = {
    ProjectStatus.ACTIVE.value: {"completed_at": None, "archived_at": None},
    ProjectStatus.COMPLETED.value: {"completed_at": "NOW"},
    ProjectStatus.ARCHIVED.value: {"archived_at": "NOW"},
}


def _is_list_any(x: Any) -> TypeGuard[list[Any]]:
    return isinstance(x, list)


class DBManagerProtocol(Protocol):
    """Protocol for database manager expected by ProjectsDatabase."""

    def get_projects_connection(self) -> sqlite3.Connection:
        """Get projects connection.

        Returns:
            TODO: Add return description
        """
        ...


class ProjectsDatabase:
    """Manages projects database operations with hierarchical support"""

    def __init__(self, db_manager: DBManagerProtocol) -> None:
        """Initialize with database manager reference"""
        self.db_manager: DBManagerProtocol = db_manager
        self.logger = Logger()

    def _get_connection(self) -> Connection:
        """Get database connection"""
        return self.db_manager.get_projects_connection()

    # ------------- Private Helpers -------------

    @staticmethod
    def _iso_to_dt(value: str | None) -> datetime | None:
        """Parse an ISO-like datetime string to datetime, robust to minor variations."""
        if not value:
            return None
        try:
            # Handle common variants like "Z" suffix or space separator
            v = value.strip()
            if v.endswith("Z"):
                # Treat Z as UTC
                v = f"{v[:-1]}+00:00"
            if " " in v and "T" not in v:
                v = v.replace(" ", "T", 1)
            return datetime.fromisoformat(v)
        except Exception:
            return None

    @staticmethod
    def _exec_count(cursor: Cursor, sql: str, params: tuple[Any, ...] = ()) -> int:
        """Execute a scalar COUNT(*) query and return an int."""
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if not row:
            return 0
        val = row[0]
        try:
            return int(val) if val is not None else 0
        except Exception:
            return 0

    def _fetch_projects(
        self, cursor: Cursor, sql: str, params: tuple[Any, ...] = ()
    ) -> list[Project]:
        """Execute a query returning projects and map rows to Project."""
        cursor.execute(sql, params)
        return [ProjectsDatabase._row_to_project(row) for row in cursor.fetchall()]

    def _max_updated_at(self, cursor: Cursor, table: str, project_id: str) -> datetime | None:
        """Return MAX(updated_at) for a given table and project_id, or None if unavailable."""
        # Whitelist known tables to prevent SQL injection
        allowed_tables = {
            "notes": "notes",
            "artifacts": "artifacts",
            "calendar_events": "calendar_events",
        }
        table_name = allowed_tables.get(table)
        if not table_name:
            return None
        try:
            sql = f"SELECT MAX(updated_at) FROM {table_name} WHERE project_id = ?"
            cursor.execute(
                sql,
                (project_id,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                return self._iso_to_dt(row[0])
        except Exception:
            # Table might not exist yet
            return None
        return None

    def _recent_activity(
        self, cursor: Cursor, project_id: str, cutoff_iso: str
    ) -> tuple[int, datetime | None, str | None]:
        """
        Compute recent activity across related tables since cutoff_iso.
        Returns: (recent_count, last_activity_dt, last_activity_type)
        """
        recent_total = 0
        last_activity: datetime | None = None
        last_type: str | None = None

        specs: Iterable[tuple[str, str]] = (
            ("notes", "note_updated"),
            ("artifacts", "artifact_updated"),
            ("calendar_events", "event_updated"),
        )

        for table, label in specs:
            try:
                cursor.execute(
                    f"""
                    SELECT COUNT(*), MAX(updated_at)
                    FROM {table}
                    WHERE project_id = ? AND updated_at >= ?
                    """,
                    (project_id, cutoff_iso),
                )
                row = cursor.fetchone()
                if not row:
                    continue
                count = int(row[0] or 0)
                max_date_str = row[1] if len(row) > 1 else None
                if count > 0:
                    recent_total += count
                    candidate = self._iso_to_dt(max_date_str) if max_date_str else None
                    if candidate and (last_activity is None or candidate > last_activity):
                        last_activity = candidate
                        last_type = label
            except Exception:
                # Table may not exist yet
                continue

        return recent_total, last_activity, last_type

    # ------------- Additional Private Helpers -------------

    def _order_by_clause(self, key: str) -> str:
        """Map an order key to a safe SQL ORDER BY fragment (without ORDER BY)."""
        mapping = {
            "name": "name",
            "created_at": "created_at",
            "updated_at": "updated_at",
            "updated_at_desc": "updated_at DESC",
            "created_at_desc": "created_at DESC",
            "name_then_created_desc": "name, created_at DESC",
        }
        return mapping.get(key, "name")

    def _fetch_projects_where(
        self,
        cursor: Cursor,
        where: str = "",
        params: tuple[Any, ...] = (),
        order_by: str = "name",
    ) -> list[Project]:
        """Fetch projects using a composed WHERE and ORDER BY clause."""
        base = "SELECT * FROM projects"
        sql = base if not where else f"{base} WHERE {where}"
        order = self._order_by_clause(order_by)
        sql = f"{sql} ORDER BY {order}" if order else sql
        return self._fetch_projects(cursor, sql, params)

    @staticmethod
    def _count_where(cursor: Cursor, table: str, where: str, params: tuple[Any, ...]) -> int:
        """
        Execute SELECT COUNT(*) FROM {table} WHERE {where} with params for allowed tables.
        Returns 0 for disallowed tables or on any exception.
        """
        try:
            allowed_tables = {
                "projects": "SELECT COUNT(*) FROM projects WHERE {where}",
                "notes": "SELECT COUNT(*) FROM notes WHERE {where}",
                "artifacts": "SELECT COUNT(*) FROM artifacts WHERE {where}",
                "calendar_events": "SELECT COUNT(*) FROM calendar_events WHERE {where}",
            }
            if table not in allowed_tables:
                return 0
            sql = allowed_tables[table].format(where=where)
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if not row:
                return 0
            val = row[0]
            return int(val) if val is not None else 0
        except Exception:
            return 0

    @staticmethod
    def _build_update_clauses(updates: dict[str, Any]) -> tuple[list[str], list[Any]]:
        """
        Build update SET clauses and parameter list from provided updates.
        - Filters to ALLOWED_UPDATE_FIELDS
        - tags: list-like -> comma-joined
        - metadata: dict -> json.dumps
        - status: applies STATUS_TIMESTAMPS side effects
        - Always appends 'updated_at = CURRENT_TIMESTAMP' (no param)
        """
        set_clauses: list[str] = []
        params: list[Any] = []

        for key, value in updates.items():
            if key in ALLOWED_UPDATE_FIELDS:
                processed = value
                if key == "tags" and _is_list_any(value):
                    processed = ",".join(str(v) for v in value)
                elif key == "metadata" and isinstance(value, dict):
                    processed = json.dumps(value)
                set_clauses.append(f"{key} = ?")
                params.append(processed)

        # Apply status-driven timestamp changes if status provided
        if "status" in updates:
            status_val = updates.get("status")
            ts_map: dict[str, Any] = {}
            if isinstance(status_val, str) and status_val in STATUS_TIMESTAMPS:
                ts_map = STATUS_TIMESTAMPS[status_val]
            for field, sentinel in ts_map.items():
                set_clauses.append(f"{field} = ?")
                if sentinel == "NOW":
                    params.append(datetime.now().isoformat())
                else:
                    params.append(sentinel)

        # Always update the timestamp
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")

        return set_clauses, params

    @staticmethod
    def _has_tag(project: Project, tag: str) -> bool:
        """
        Check if a project has an exact tag.
        - If tags is list-like: membership check
        - If tags is string: split by ',' and strip spaces, then equality check
        """
        tags = getattr(project, "tags", None)
        if isinstance(tags, list):
            return tag in tags
        if isinstance(tags, str):
            parts = [t.strip() for t in tags.split(",")]
            return tag in parts
        return False

    def _build_project_summary(
        self, cursor: Cursor, project: Project, cutoff_iso: str
    ) -> ProjectSummary | None:
        """
        Build a ProjectSummary for a project if it has recent activity,
        otherwise return None.
        """
        summary = ProjectSummary.from_project(project)

        recent_count, last_activity, last_type = self._recent_activity(
            cursor, project.id, cutoff_iso
        )
        if recent_count <= 0:
            return None

        summary.recent_activity_count = recent_count
        summary.last_activity_date = last_activity
        summary.last_activity_type = last_type

        # Total counts
        summary.total_item_count = (
            self.get_project_notes_count(project.id)
            + self.get_project_artifacts_count(project.id)
            + self.get_project_events_count(project.id)
        )

        # Child project count
        summary.child_project_count = self._exec_count(
            cursor,
            """
            SELECT COUNT(*) FROM projects
            WHERE parent_project_id = ?
            """,
            (project.id,),
        )

        return summary

    def _safe_max_updated_at(self, cursor: Cursor, table: str, project_id: str) -> datetime | None:
        """Safe wrapper around _max_updated_at with table allowlist."""
        if table not in {"notes", "artifacts", "calendar_events"}:
            return None
        return self._max_updated_at(cursor, table, project_id)

    # ------------- Public API -------------

    def create_project(self, project: Project) -> dict[str, Any]:
        """Create a new project"""
        try:
            # Merge hierarchy validation into a single conditional
            if project.parent_project_id and not self._validate_project_hierarchy(
                project.id, project.parent_project_id
            ):
                return {
                    "success": False,
                    "error": "Invalid parent project or circular reference",
                }

            with self._get_connection() as conn:
                cursor = conn.cursor()
                project_dict = project.to_db_dict()  # Use to_db_dict() for proper serialization

                cursor.execute(
                    """
                    INSERT INTO projects
                    (id, name, description, status, color, icon,
                     parent_project_id, tags, metadata,
                     created_at, updated_at, completed_at, archived_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        project_dict["id"],
                        project_dict["name"],
                        project_dict["description"],
                        project_dict["status"],
                        project_dict["color"],
                        project_dict["icon"],
                        project_dict["parent_project_id"],
                        project_dict["tags"],
                        project_dict["metadata"],
                        project_dict["created_at"],
                        project_dict["updated_at"],
                        project_dict["completed_at"],
                        project_dict["archived_at"],
                    ),
                )

                conn.commit()

                self.logger.info(f"Created project: {project.id}")
                return {"success": True, "id": project.id}

        except Exception as e:
            self.logger.error(f"Failed to create project: {str(e)}")
            return {"success": False, "error": str(e)}

    def update_project(self, project_id: str, updates: dict[str, Any]) -> bool:
        """Update an existing project"""
        try:
            # Validate hierarchy if parent being updated
            if "parent_project_id" in updates:
                parent_id = updates["parent_project_id"]
                if parent_id and not self._validate_project_hierarchy(project_id, parent_id):
                    self.logger.error(f"Invalid parent project {parent_id} for {project_id}")
                    return False

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Build update clauses safely using parameterized queries
                permitted_fields = {"name", "description", "parent_project_id"}
                params_list: list[Any] = []
                set_clauses: list[str] = []
                for field, value in updates.items():
                    if field not in permitted_fields:
                        self.logger.warning(f"Ignoring update to unsupported field: {field}")
                        continue
                    set_clauses.append(f"{field} = ?")
                    params_list.append(value)
                # Always update updated_at
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")

                # If only the auto-added updated_at is present, no permissible fields were provided
                if len(set_clauses) == 1:
                    return False

                set_clause_str = ", ".join(set_clauses)
                query = "".join(["UPDATE projects SET ", set_clause_str, " WHERE id = ?"])
                cursor.execute(query, tuple(params_list + [project_id]))

                conn.commit()

                return bool(cursor.rowcount and cursor.rowcount > 0)

        except Exception as e:
            self.logger.error(f"Failed to update project: {str(e)}")
            return False

    def delete_project(self, project_id: str, cascade: bool = False) -> bool:
        """Delete a project and optionally cascade to child projects"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                deleted_total = 0
                descendants: list[str] = []
                if cascade:
                    # Precompute descendants for logging
                    descendants = self._get_all_descendants(project_id)

                    # Single CTE-based delete for project and its descendants
                    cursor.execute(
                        """
                        WITH RECURSIVE descendants(id) AS (
                          SELECT id FROM projects WHERE parent_project_id = ?
                          UNION ALL
                          SELECT p.id FROM projects p
                          JOIN descendants d ON p.parent_project_id = d.id
                        )
                        DELETE FROM projects
                        WHERE id IN (SELECT id FROM descendants) OR id = ?
                        """,
                        (project_id, project_id),
                    )
                    deleted_total = cursor.rowcount or 0
                else:
                    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                    deleted_total = cursor.rowcount or 0

                conn.commit()

                msg = f"Deleted project {project_id}"
                if cascade and descendants:
                    msg += f" and {len(descendants)} descendants"
                self.logger.info(msg)

                return deleted_total > 0

        except Exception as e:
            self.logger.error(f"Failed to delete project: {str(e)}")
            return False

    def get_project(self, project_id: str) -> Project | None:
        """Get a specific project"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM projects WHERE id = ?
                """,
                    (project_id,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                return ProjectsDatabase._row_to_project(row)

        except Exception as e:
            self.logger.error(f"Failed to get project: {str(e)}")
            return None

    def get_all_projects(self) -> list[Project]:
        """Get all projects"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                return self._fetch_projects_where(cursor, "", (), "name_then_created_desc")

        except Exception as e:
            self.logger.error(f"Failed to get all projects: {str(e)}")
            return []

    def get_child_projects(self, parent_id: str) -> list[Project]:
        """Get all direct child projects of a parent"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                return self._fetch_projects_where(
                    cursor, "parent_project_id = ?", (parent_id,), "name"
                )

        except Exception as e:
            self.logger.error(f"Failed to get child projects: {str(e)}")
            return []

    def get_root_projects(self) -> list[Project]:
        """Get all root projects (projects with no parent)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                return self._fetch_projects_where(cursor, "parent_project_id IS NULL", (), "name")

        except Exception as e:
            self.logger.error(f"Failed to get root projects: {str(e)}")
            return []

    def get_project_tree(self, project_id: str) -> dict[str, Any]:
        """Get project tree structure starting from a project"""
        try:
            project = self.get_project(project_id)
            if not project:
                return {}

            tree: dict[str, Any] = {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "status": project.status,
                "color": project.color,
                "icon": project.icon,
                "children": [],
            }

            # Recursively get children
            children = self.get_child_projects(project_id)
            for child in children:
                child_tree = self.get_project_tree(child.id)
                tree["children"].append(child_tree)

            return tree

        except Exception as e:
            self.logger.error(f"Failed to get project tree: {str(e)}")
            return {}

    def get_project_statistics(self, project_id: str) -> ProjectStatistics:
        """Get comprehensive statistics for a project"""
        project: Project | None = None
        try:
            project = self.get_project(project_id)
            if not project:
                return ProjectStatistics(project_id=project_id, project_name="Unknown")

            stats = ProjectStatistics(project_id=project_id, project_name=project.name)

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Related object counts
                stats.total_notes = self.get_project_notes_count(project_id)
                stats.total_artifacts = self.get_project_artifacts_count(project_id)
                stats.total_calendar_events = self.get_project_events_count(project_id)

                # Child projects count
                stats.child_project_count = self._exec_count(
                    cursor,
                    """
                    SELECT COUNT(*) FROM projects
                    WHERE parent_project_id = ?
                    """,
                    (project_id,),
                )

                # Last activity across tables
                last_activity = None
                for table in ("notes", "artifacts", "calendar_events"):
                    candidate = self._safe_max_updated_at(cursor, table, project_id)
                    if candidate and (last_activity is None or candidate > last_activity):
                        last_activity = candidate

                stats.last_activity_date = last_activity
                stats.calculate_days_since_activity()

                # Completion metrics from calendar_events
                completed_events = self._exec_count(
                    cursor,
                    """
                    SELECT COUNT(*) FROM calendar_events
                    WHERE project_id = ? AND status = 'completed'
                    """,
                    (project_id,),
                )
                total_events = self._exec_count(
                    cursor,
                    """
                    SELECT COUNT(*) FROM calendar_events
                    WHERE project_id = ?
                    """,
                    (project_id,),
                )

                stats.completed_items = completed_events
                stats.total_items = total_events
                stats.calculate_completion_percentage()

                return stats

        except Exception as e:
            self.logger.error(f"Failed to get project statistics: {str(e)}")
            # Use project name if available, otherwise "Unknown"
            project_name = project.name if project else "Unknown"
            return ProjectStatistics(project_id=project_id, project_name=project_name)

    def get_project_notes_count(self, project_id: str) -> int:
        """Get count of notes associated with a project"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                return self._count_where(
                    cursor, "notes", "project_id = ? AND is_deleted = 0", (project_id,)
                )
        except Exception:
            # Table might not exist or have project_id column yet
            return 0

    def get_project_artifacts_count(self, project_id: str) -> int:
        """Get count of artifacts associated with a project"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                return self._count_where(
                    cursor,
                    "artifacts",
                    "project_id = ? AND status != 'deleted'",
                    (project_id,),
                )
        except Exception:
            # Table might not exist or have project_id column yet
            return 0

    def get_project_events_count(self, project_id: str) -> int:
        """Get count of calendar events associated with a project"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                return self._count_where(cursor, "calendar_events", "project_id = ?", (project_id,))
        except Exception:
            # Table might not exist or have project_id column yet
            return 0

    def get_projects_with_activity(self, days: int = 7) -> list[ProjectSummary]:
        """Get projects with recent activity within specified days"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_iso = cutoff_date.isoformat()

            with self._get_connection() as conn:
                cursor = conn.cursor()

                projects = self.get_all_projects()
                summaries: list[ProjectSummary] = []

                for project in projects:
                    summary = self._build_project_summary(cursor, project, cutoff_iso)
                    if summary:
                        summaries.append(summary)

                # Sort by most recent activity
                summaries.sort(key=lambda s: s.last_activity_date or datetime.min, reverse=True)

                return summaries

        except Exception as e:
            self.logger.error(f"Failed to get projects with activity: {str(e)}")
            return []

    def search_projects(self, query: str) -> list[Project]:
        """Search projects by name, description, or tags"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                search_pattern = f"%{query}%"
                return self._fetch_projects(
                    cursor,
                    """
                    SELECT * FROM projects
                    WHERE name LIKE ? OR description LIKE ? OR tags LIKE ?
                    ORDER BY updated_at DESC
                """,
                    (search_pattern, search_pattern, search_pattern),
                )

        except Exception as e:
            self.logger.error(f"Failed to search projects: {str(e)}")
            return []

    def get_projects_by_status(self, status: str) -> list[Project]:
        """Get all projects with a specific status"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                return self._fetch_projects_where(cursor, "status = ?", (status,), "name")

        except Exception as e:
            self.logger.error(f"Failed to get projects by status: {str(e)}")
            return []

    def get_projects_by_tag(self, tag: str) -> list[Project]:
        """Get all projects containing a specific tag"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Use LIKE prefilter to leverage indexes
                tag_pattern = f"%{tag}%"
                projects = self._fetch_projects_where(cursor, "tags LIKE ?", (tag_pattern,), "name")

                # Exact-match filter preserving existing semantics
                return [p for p in projects if self._has_tag(p, tag)]

        except Exception as e:
            self.logger.error(f"Failed to get projects by tag: {str(e)}")
            return []

    # ------------- Row Mapping and Hierarchy Utilities -------------

    @staticmethod
    def _row_to_project(row: Row) -> Project:
        """Convert database row to Project object"""
        return Project.from_dict(
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "status": row[3],
                "color": row[4],
                "icon": row[5],
                "parent_project_id": row[6],
                "tags": row[7],
                "metadata": row[8],
                "created_at": row[9],
                "updated_at": row[10],
                "completed_at": row[11],
                "archived_at": row[12],
            }
        )

    def _validate_project_hierarchy(self, project_id: str, parent_id: str) -> bool:
        """
        Validate project hierarchy to prevent circular references.
        Returns True if the hierarchy is valid, False otherwise.
        """
        try:
            # Can't be parent of itself
            if project_id == parent_id:
                return False

            # Check if parent exists
            parent = self.get_project(parent_id)
            if not parent:
                return False

            # Check for circular reference by traversing up the hierarchy from parent
            current_id: str | None = parent_id
            visited: set[str] = set()

            while current_id:
                if current_id == project_id:
                    # Circular reference detected
                    return False

                if current_id in visited:
                    # Infinite loop protection
                    break

                visited.add(current_id)

                current = self.get_project(current_id)
                if current:
                    current_id = current.parent_project_id
                else:
                    break

            return True

        except Exception as e:
            self.logger.error(f"Error validating project hierarchy: {str(e)}")
            return False

    def _get_all_descendants(self, project_id: str) -> list[str]:
        """Get all descendant project IDs recursively using a CTE."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    WITH RECURSIVE descendants(id) AS (
                      SELECT id FROM projects WHERE parent_project_id = ?
                      UNION ALL
                      SELECT p.id FROM projects p
                      JOIN descendants d ON p.parent_project_id = d.id
                    )
                    SELECT id FROM descendants
                    """,
                    (project_id,),
                )
                rows = cursor.fetchall()
                return [r[0] for r in rows] if rows else []
        except Exception as e:
            self.logger.error(f"Error getting descendants for {project_id}: {str(e)}")
            return []
