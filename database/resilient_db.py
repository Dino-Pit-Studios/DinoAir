# DinoAir2.0dev - ResilientDB.py
# This file provides a resilient database wrapper for SQLite, ensuring safe initialization and recovery.

import shutil
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path


class ResilientDB:
    """A wrapper that makes SQLite initialization and recovery safer and more user-friendly."""

    def __init__(
        self,
        db_path: Path,
        schema_initializer: Callable[[sqlite3.Connection], None],
        user_feedback: Callable[[str], None] | None = None,
    ):
        self.db_path = db_path
        self.schema_initializer = schema_initializer
        # Backward compatibility alias for tests that expect schema_callback
        self.schema_callback = schema_initializer
        self.user_feedback = user_feedback or print

    def log(self, message: str) -> None:
        """Log.

        Args:
            message: TODO: Add description

        Returns:
            TODO: Add return description
        """
        self.user_feedback(f"{message}")

    def connect(self) -> sqlite3.Connection:
        """Attempts to connect to the DB with recovery logic."""
        try:
            return self._attempt_connection()
        except sqlite3.OperationalError as e:
            if "unable to open database file" in str(e) or "no such file or directory" in str(e):
                self.log("Creating database folder - this is normal for first-time setup.")
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                return self._attempt_connection()
            if "database is locked" in str(e):
                self.log("Database is busy. Waiting a moment and trying again...")
                time.sleep(2)
                return self._attempt_connection()
            raise
        except sqlite3.DatabaseError as e:
            if "file is not a database" in str(e) or "database disk image is malformed" in str(e):
                self.log("Found a damaged database file. Creating a backup and starting fresh...")
                self._backup_corrupted_db()
                return self._attempt_connection()
            raise
        except PermissionError as exc:
            self.log(
                "Permission denied accessing database folder. Please check folder permissions or run as administrator."
            )
            raise RuntimeError("Cannot access database due to permission restrictions.") from exc
        except Exception as e:
            self.log(f"Unexpected database issue: {str(e)}")
            raise RuntimeError("Database setup failed due to an unexpected error.") from e

    def _attempt_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        # Test the connection
        conn.execute("SELECT 1")
        self.schema_initializer(conn)
        return conn

    def _backup_corrupted_db(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Create backups directory if it doesn't exist
        backup_dir = self.db_path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f"{self.db_path.stem}_corrupted_{timestamp}.db"
        try:
            shutil.move(self.db_path, backup_path)
            self.log(f"Backup saved to: {backup_path}")
        except OSError:
            # If we can't move it, just delete it
            self.db_path.unlink(missing_ok=True)
            self.log("Removed damaged database file.")

    def connect_with_retry(self, retries: int = 3, delay: int = 1) -> sqlite3.Connection:
        """Connect with retry.

        Args:
            retries: TODO: Add description
            delay: TODO: Add description

        Returns:
            TODO: Add return description
        """
        attempt = 0
        last_exc: Exception | None = None
        while attempt < retries:
            try:
                return self._attempt_connection()
            except sqlite3.DatabaseError as e:
                last_exc = e
                # Backup corrupted database on database errors
                self._backup_corrupted_db()
                attempt += 1
                if attempt < retries:
                    self.log(
                        f"Setup attempt {attempt} failed. Trying again in {delay * attempt} seconds..."
                    )
                    time.sleep(delay * attempt)
            except (sqlite3.OperationalError, OSError) as e:
                last_exc = e
                attempt += 1
                if attempt < retries:
                    self.log(
                        f"Setup attempt {attempt} failed. Trying again in {delay * attempt} seconds..."
                    )
                    time.sleep(delay * attempt)

        # If we get here, all attempts failed
        if isinstance(last_exc, sqlite3.DatabaseError):
            # Re-raise database errors as-is for test compatibility
            raise last_exc

        self.log("Database setup failed after multiple attempts. Please contact support.")
        raise RuntimeError("Database initialization failed after all retry attempts.") from last_exc
