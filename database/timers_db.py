"""TimersDatabase - centralized timer logging via DatabaseManager/ResilientDB."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from utils.logger import Logger

from .initialize_db import DatabaseManager

if TYPE_CHECKING:
    from datetime import datetime


class TimersDatabase:
    """Handles timer log persistence using DatabaseManager.

    Schema is created by DatabaseManager._setup_timers_schema.
    """

    def __init__(self, db_manager: DatabaseManager | None = None):
        self.logger = Logger()
        self.db_manager = db_manager or DatabaseManager()

    def create_log(
        self,
        task_name: str,
        start_time: datetime,
        end_time: datetime,
        elapsed_seconds: float,
    ) -> dict[str, Any]:
        """Create log.

        Args:
            task_name: TODO: Add description
            start_time: TODO: Add description
            end_time: TODO: Add description
            elapsed_seconds: TODO: Add description

        Returns:
            TODO: Add return description
        """
        try:
            with self.db_manager.get_timers_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO timer_logs (task_name, start_time, end_time, elapsed_seconds)
                    VALUES (?, ?, ?, ?)
                    """,
                    (task_name, start_time, end_time, elapsed_seconds),
                )
                conn.commit()
            return {"success": True}
        except sqlite3.Error as e:
            self.logger.error(f"Timer log DB error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            self.logger.error(f"Failed to create timer log: {e}")
            return {"success": False, "error": str(e)}
