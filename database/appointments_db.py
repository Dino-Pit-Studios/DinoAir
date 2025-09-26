#!/usr/bin/env python3
"""
Appointments Database Manager
Manages all calendar event database operations with resilient handling.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any, Protocol, cast

from models.calendar_event import CalendarEvent
from utils.logger import Logger


class _AppointmentsConnectionProvider(Protocol):
    """Protocol for objects providing appointments DB connections."""

    def get_appointments_connection(self) -> sqlite3.Connection:
        """Return a connection to the appointments database."""
        ...


_UPDATE_FIELD_SET_CLAUSES: dict[str, str] = {
    "title": "title = ?",
    "description": "description = ?",
    "event_type": "event_type = ?",
    "status": "status = ?",
    "event_date": "event_date = ?",
    "start_time": "start_time = ?",
    "end_time": "end_time = ?",
    "all_day": "all_day = ?",
    "location": "location = ?",
    "participants": "participants = ?",
    "project_id": "project_id = ?",
    "chat_session_id": "chat_session_id = ?",
    "recurrence_pattern": "recurrence_pattern = ?",
    "recurrence_rule": "recurrence_rule = ?",
    "reminder_minutes_before": "reminder_minutes_before = ?",
    "reminder_sent": "reminder_sent = ?",
    "tags": "tags = ?",
    "notes": "notes = ?",
    "color": "color = ?",
    "metadata": "metadata = ?",
    "completed_at": "completed_at = ?",
}


class AppointmentsDatabase:
    """Manages appointments/calendar events database operations"""

    def __init__(self, db_manager: _AppointmentsConnectionProvider) -> None:
        """Initialize with database manager reference"""
        self.db_manager = db_manager
        self.logger = Logger()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = self.db_manager.get_appointments_connection()
        if not isinstance(conn, sqlite3.Connection):
            raise TypeError("Expected sqlite3.Connection from db_manager")
        return conn

    @staticmethod
    def _normalize_update_value(field: str, value: object) -> object:
        """Normalize incoming update values for storage."""
        if field in {"participants", "tags"} and isinstance(value, list):
            return ",".join(value) if value else None
        if field == "metadata" and isinstance(value, dict):
            return json.dumps(value)
        return value

    def _prepare_update_components(
        self, updates: dict[str, object]
    ) -> tuple[list[str], list[object]]:
        """Build SET clauses and parameters for an update statement."""
        set_clauses: list[str] = []
        params: list[object] = []

        for field, value in updates.items():
            clause = _UPDATE_FIELD_SET_CLAUSES.get(field)
            if clause is None:
                continue

            set_clauses.append(clause)
            params.append(self._normalize_update_value(field, value))

        return set_clauses, params

    def create_event(self, event: CalendarEvent) -> dict[str, Any]:
        """Create a new calendar event"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                event_dict = event.to_dict()

                # Prepare serialized fields for storage
                participants_value: str | None = None
                raw_participants = event_dict.get("participants")
                if isinstance(raw_participants, list):
                    participants_value = ",".join(raw_participants) if raw_participants else None
                elif isinstance(raw_participants, str):
                    participants_value = raw_participants or None

                tags_value: str | None = None
                raw_tags = event_dict.get("tags")
                if isinstance(raw_tags, list):
                    tags_value = ",".join(raw_tags) if raw_tags else None
                elif isinstance(raw_tags, str):
                    tags_value = raw_tags or None

                metadata_value = (
                    json.dumps(event.metadata) if isinstance(event.metadata, dict) else None
                )

                # Normalize recurrence_pattern; bind "none" when None to align with schema default
                recurrence_pattern = (
                    event.recurrence_pattern if event.recurrence_pattern is not None else "none"
                )

                cursor.execute(
                    """
                    INSERT INTO calendar_events
                    (id, title, description, event_type, status, event_date,
                     start_time, end_time, all_day, location, participants,
                     project_id, chat_session_id, recurrence_pattern,
                     recurrence_rule, reminder_minutes_before, reminder_sent,
                     tags, notes, color, metadata, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        event_dict["id"],
                        event_dict["title"],
                        event_dict["description"],
                        event_dict["event_type"],
                        event_dict["status"],
                        event_dict["event_date"],
                        event_dict["start_time"],
                        event_dict["end_time"],
                        event_dict["all_day"],
                        event_dict["location"],
                        participants_value,
                        event_dict["project_id"],
                        event_dict["chat_session_id"],
                        recurrence_pattern,
                        event_dict["recurrence_rule"],
                        event_dict["reminder_minutes_before"],
                        event_dict["reminder_sent"],
                        tags_value,
                        event_dict["notes"],
                        event_dict["color"],
                        metadata_value,
                        event_dict["completed_at"],
                    ),
                )

                # Create reminder if specified (explicit None check to allow 0-minute reminders)
                if event.reminder_minutes_before is not None and event.event_date:
                    self._create_reminder(cursor, event)

                conn.commit()

                self.logger.info(f"Created calendar event: {event.id}")
                return {"success": True, "id": event.id}

        except Exception as e:
            self.logger.error(f"Failed to create event: {str(e)}")
            return {"success": False, "error": str(e)}

    def update_event(self, event_id: str, updates: dict[str, object]) -> bool:
        """Update an existing calendar event"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Build atomic update statement with parameterized placeholders
                set_clauses, params = self._prepare_update_components(updates)
                reminder_raw = updates.get("reminder_minutes_before") if updates else None
                reminder_update_requested = "reminder_minutes_before" in updates

                if not set_clauses:
                    return False

                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                params.append(event_id)

                set_clause_sql = ", ".join(set_clauses)
                update_query = "".join(
                    ["UPDATE calendar_events SET ", set_clause_sql, " WHERE id = ?"]
                )

                cursor.execute(update_query, tuple(params))
                rows_updated = cursor.rowcount or 0
                if rows_updated <= 0:
                    return False

                # Update reminder if reminder time changed
                if reminder_update_requested:
                    reminder_value = cast("int | None", reminder_raw)
                    self._update_reminder(cursor, event_id, reminder_value)

                conn.commit()

                return True

        except Exception as e:
            self.logger.error(f"Failed to update event: {str(e)}")
            return False

    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event and all its related data"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Delete reminders first (foreign key constraint)
                cursor.execute(
                    """DELETE FROM event_reminders
                                 WHERE event_id = ?""",
                    (event_id,),
                )

                # Delete attachments
                cursor.execute(
                    """DELETE FROM event_attachments
                                 WHERE event_id = ?""",
                    (event_id,),
                )

                # Delete event
                cursor.execute(
                    """DELETE FROM calendar_events
                                 WHERE id = ?""",
                    (event_id,),
                )

                conn.commit()

                rows_deleted = cursor.rowcount or 0
                return rows_deleted > 0

        except Exception as e:
            self.logger.error(f"Failed to delete event: {str(e)}")
            return False

    def get_event(self, event_id: str) -> CalendarEvent | None:
        """Get a specific calendar event"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM calendar_events WHERE id = ?
                """,
                    (event_id,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                return self._row_to_event(row)

        except Exception as e:
            self.logger.error(f"Failed to get event: {str(e)}")
            return None

    def get_events_for_date_range(self, start_date: date, end_date: date) -> list[CalendarEvent]:
        """Get all events within a date range"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM calendar_events
                    WHERE event_date >= ? AND event_date <= ?
                    ORDER BY event_date, start_time
                """,
                    (start_date.isoformat(), end_date.isoformat()),
                )

                events = []
                for row in cursor.fetchall():
                    event = self._row_to_event(row)
                    events.append(event)

                return events

        except Exception as e:
            self.logger.error(f"Failed to get events for date range: {str(e)}")
            return []

    def get_events_for_date(self, target_date: date) -> list[CalendarEvent]:
        """Get all events for a specific date"""
        return self.get_events_for_date_range(target_date, target_date)

    def search_events(self, query: str) -> list[CalendarEvent]:
        """Search events by title, description, location, or notes"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                search_pattern = f"%{query}%"
                cursor.execute(
                    """
                    SELECT * FROM calendar_events
                    WHERE title LIKE ? OR description LIKE ?
                    OR location LIKE ? OR notes LIKE ?
                    ORDER BY event_date DESC, start_time DESC
                    LIMIT 100
                """,
                    (search_pattern, search_pattern, search_pattern, search_pattern),
                )

                events = []
                for row in cursor.fetchall():
                    event = self._row_to_event(row)
                    events.append(event)

                return events

        except Exception as e:
            self.logger.error(f"Failed to search events: {str(e)}")
            return []

    def get_upcoming_reminders(self) -> list[dict[str, Any]]:
        """Get all upcoming reminders that need to be sent"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT r.*, e.title, e.description, e.event_date,
                           e.start_time, e.location
                    FROM event_reminders r
                    JOIN calendar_events e ON r.event_id = e.id
                    WHERE r.sent = 0 AND r.reminder_time <= datetime('now')
                    ORDER BY r.reminder_time
                """
                )

                reminders = []
                for row in cursor.fetchall():
                    reminder = {
                        "id": row[0],
                        "event_id": row[1],
                        "reminder_time": row[2],
                        "sent": bool(row[3]),
                        "sent_at": row[4],
                        "event_title": row[5],
                        "event_description": row[6],
                        "event_date": row[7],
                        "start_time": row[8],
                        "location": row[9],
                    }
                    reminders.append(reminder)

                return reminders

        except Exception as e:
            self.logger.error(f"Failed to get upcoming reminders: {str(e)}")
            return []

    def mark_reminder_sent(self, reminder_id: str) -> bool:
        """Mark a reminder as sent"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    UPDATE event_reminders
                    SET sent = 1, sent_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (reminder_id,),
                )
                first_update_count = cursor.rowcount or 0

                # Also update the event's reminder_sent flag
                cursor.execute(
                    """
                    UPDATE calendar_events
                    SET reminder_sent = 1
                    WHERE id = (SELECT event_id FROM event_reminders
                               WHERE id = ?)
                """,
                    (reminder_id,),
                )
                conn.commit()

                return first_update_count > 0

        except Exception as e:
            self.logger.error(f"Failed to mark reminder sent: {str(e)}")
            return False

    def get_events_by_status(self, status: str, limit: int = 100) -> list[CalendarEvent]:
        """Get events by status"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM calendar_events
                    WHERE status = ?
                    ORDER BY event_date DESC, start_time DESC
                    LIMIT ?
                """,
                    (status, limit),
                )

                events = []
                for row in cursor.fetchall():
                    event = self._row_to_event(row)
                    events.append(event)

                return events

        except Exception as e:
            self.logger.error(f"Failed to get events by status: {str(e)}")
            return []

    def get_events_by_project(self, project_id: str) -> list[CalendarEvent]:
        """Get all events for a specific project"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM calendar_events
                    WHERE project_id = ?
                    ORDER BY event_date DESC, start_time DESC
                """,
                    (project_id,),
                )

                events = []
                for row in cursor.fetchall():
                    event = self._row_to_event(row)
                    events.append(event)

                return events

        except Exception as e:
            self.logger.error(f"Failed to get events by project: {str(e)}")
            return []

    def get_event_statistics(self) -> dict[str, Any]:
        """Get calendar event statistics"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                stats = {}

                # Total events
                cursor.execute("SELECT COUNT(*) FROM calendar_events")
                stats["total_events"] = cursor.fetchone()[0]

                # Events by status
                cursor.execute(
                    """
                    SELECT status, COUNT(*)
                    FROM calendar_events
                    GROUP BY status
                """
                )
                stats["events_by_status"] = {row[0]: row[1] for row in cursor.fetchall()}

                # Events by type
                cursor.execute(
                    """
                    SELECT event_type, COUNT(*)
                    FROM calendar_events
                    GROUP BY event_type
                """
                )
                stats["events_by_type"] = {row[0]: row[1] for row in cursor.fetchall()}

                # Upcoming events (next 7 days)
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM calendar_events
                    WHERE event_date >= date('now')
                    AND event_date <= date('now', '+7 days')
                    AND status = 'scheduled'
                """
                )
                stats["upcoming_events_week"] = cursor.fetchone()[0]

                # Events with reminders
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM calendar_events
                    WHERE reminder_minutes_before IS NOT NULL
                """
                )
                stats["events_with_reminders"] = cursor.fetchone()[0]

                return stats

        except Exception as e:
            self.logger.error(f"Failed to get event statistics: {str(e)}")
            return {}

    def _create_reminder(self, cursor: sqlite3.Cursor, event: CalendarEvent) -> None:
        """Create a reminder for an event"""
        if not event.event_date or event.reminder_minutes_before is None:
            return

        # Calculate reminder time
        event_datetime = event.get_datetime()
        if event_datetime:
            reminder_time = event_datetime - timedelta(minutes=event.reminder_minutes_before)

            cursor.execute(
                """
                INSERT INTO event_reminders
                (id, event_id, reminder_time, sent, sent_at)
                VALUES (?, ?, ?, 0, NULL)
            """,
                (
                    str(uuid.uuid4()),
                    event.id,
                    reminder_time.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )

    def _update_reminder(
        self, cursor: sqlite3.Cursor, event_id: str, reminder_minutes: int | None
    ) -> None:
        """Update or create reminder for an event"""
        # Delete existing reminder
        cursor.execute("DELETE FROM event_reminders WHERE event_id = ?", (event_id,))

        # Create new reminder if needed
        if reminder_minutes is not None:
            cursor.execute(
                """
                SELECT event_date, start_time FROM calendar_events
                WHERE id = ?
            """,
                (event_id,),
            )

            row = cursor.fetchone()
            if row and row[0]:
                event_date = date.fromisoformat(row[0])
                start_time = time.fromisoformat(row[1]) if row[1] else time(0, 0)
                event_datetime = datetime.combine(event_date, start_time)
                reminder_time = event_datetime - timedelta(minutes=reminder_minutes)

                cursor.execute(
                    """
                    INSERT INTO event_reminders
                    (id, event_id, reminder_time, sent, sent_at)
                    VALUES (?, ?, ?, 0, NULL)
                """,
                    (
                        str(uuid.uuid4()),
                        event_id,
                        reminder_time.strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )

    @staticmethod
    def _row_to_event(row: tuple[Any, ...]) -> CalendarEvent:
        """Convert database row to CalendarEvent object"""
        # Normalize tags (stored as CSV TEXT) and metadata (stored as JSON TEXT)
        tags_list = [t for t in (row[17] or "").split(",") if t]
        metadata_dict = json.loads(row[20]) if row[20] else None

        return CalendarEvent.from_dict(
            {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "event_type": row[3],
                "status": row[4],
                "event_date": row[5],
                "start_time": row[6],
                "end_time": row[7],
                "all_day": bool(row[8]),
                "location": row[9],
                "participants": row[10],
                "project_id": row[11],
                "chat_session_id": row[12],
                "recurrence_pattern": row[13],
                "recurrence_rule": row[14],
                "reminder_minutes_before": row[15],
                "reminder_sent": bool(row[16]),
                "tags": tags_list,
                "notes": row[18],
                "color": row[19],
                "metadata": metadata_dict,
                "created_at": row[21],
                "updated_at": row[22],
                "completed_at": row[23],
            }
        )
