#!/usr/bin/env python3
"""
Development and Testing Cleanup Utilities for DinoAir

This module provides comprehensive cleanup tools for development and testing,
extending beyond the basic memory DB cleanup to handle all user data safely.
"""

import logging
import os
import shutil
import tempfile
from pathlib import Path

from database.initialize_db import DatabaseManager, _get_default_user_data_directory

LOGGER = logging.getLogger(__name__)


class UserDataCleanupManager:
    """Manages cleanup of user data for development and testing."""

    def __init__(self, dry_run: bool = False, verbose: bool = False):
        """Initialize cleanup manager.

        Args:
            dry_run: If True, only report what would be cleaned without actually doing it
            verbose: If True, provide detailed logging of operations
        """
        self.dry_run = dry_run
        self.verbose = verbose

        # Configure logging
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s")

    @staticmethod
    def get_user_data_directories() -> dict[str, Path]:
        """Get all potential user data directories.

        Returns:
            Dict mapping location type to path
        """
        locations = {}

        # Default location (outside repo)
        try:
            locations["default"] = _get_default_user_data_directory()
        except Exception as e:
            LOGGER.warning("Could not determine default user data directory: %s", e)

        # Repository location (legacy, should be empty now)
        repo_root = Path(__file__).parent.parent
        repo_user_data = repo_root / "user_data"
        if repo_user_data.exists():
            locations["repository"] = repo_user_data

        # Environment override
        if env_path := os.environ.get("DINOAIR_USER_DATA"):
            locations["environment"] = Path(env_path).expanduser().resolve()

        # Test directories in temp
        temp_dir = Path(tempfile.gettempdir())
        test_patterns = ["DinoAir*", "DinoAirTests*", "test_db_*"]
        for pattern in test_patterns:
            for test_dir in temp_dir.glob(pattern):
                if test_dir.is_dir():
                    locations[f"temp_{test_dir.name}"] = test_dir

        return locations

    def analyze_user_data(self) -> dict[str, dict]:
        """Analyze user data directories and their contents.

        Returns:
            Dict mapping location to analysis results
        """
        directories = self.get_user_data_directories()
        analysis = {}

        for location, path in directories.items():
            try:
                if not path.exists():
                    analysis[location] = {"status": "not_found", "path": str(path)}
                    continue

                # Analyze directory contents
                info = {
                    "status": "found",
                    "path": str(path),
                    "size_mb": 0,
                    "file_count": 0,
                    "db_files": [],
                    "users": [],
                    "subdirs": [],
                }

                # Walk directory tree
                for root, dirs, files in os.walk(path):
                    root_path = Path(root)
                    info["subdirs"].extend([str(root_path / d) for d in dirs])

                    for file in files:
                        file_path = root_path / file
                        try:
                            size = file_path.stat().st_size
                            info["size_mb"] += size / (1024 * 1024)
                            info["file_count"] += 1

                            if file.endswith((".db", ".sqlite", ".sqlite3")):
                                info["db_files"].append(str(file_path))
                        except OSError:
                            LOGGER.warning("Could not access %s", file_path)

                # Extract user names from directory structure
                user_data_path = path / "user_data"
                if user_data_path.exists():
                    try:
                        info["users"] = [
                            d.name
                            for d in user_data_path.iterdir()
                            if d.is_dir() and not d.name.startswith(".")
                        ]
                    except OSError:
                        LOGGER.warning("Could not list users in %s", user_data_path)

                info["size_mb"] = round(info["size_mb"], 2)
                analysis[location] = info

            except Exception as e:
                analysis[location] = {"status": "error", "path": str(path), "error": str(e)}
                LOGGER.error("Error analyzing %s: %s", path, e)

        return analysis

    def cleanup_test_data(self, max_age_hours: int = 24) -> dict[str, int]:
        """Clean up old test data.

        Args:
            max_age_hours: Maximum age in hours for test data to keep

        Returns:
            Dict with cleanup statistics
        """
        stats = {"directories_removed": 0, "files_removed": 0, "space_freed_mb": 0}

        temp_dir = Path(tempfile.gettempdir())
        cutoff_time = os.path.getmtime(temp_dir) - (max_age_hours * 3600)

        # Clean test directories
        test_patterns = ["DinoAir*", "DinoAirTests*", "test_db_*"]
        for pattern in test_patterns:
            for test_dir in temp_dir.glob(pattern):
                if not test_dir.is_dir():
                    continue

                try:
                    # Check if directory is old enough
                    if os.path.getmtime(test_dir) > cutoff_time:
                        if self.verbose:
                            LOGGER.debug("Skipping recent test directory: %s", test_dir)
                        continue

                    # Calculate size before removal
                    size_mb = self._calculate_directory_size(test_dir)

                    if self.dry_run:
                        LOGGER.info("Would remove test directory: %s (%.2f MB)", test_dir, size_mb)
                    else:
                        LOGGER.info("Removing test directory: %s (%.2f MB)", test_dir, size_mb)
                        shutil.rmtree(test_dir)

                    stats["directories_removed"] += 1
                    stats["space_freed_mb"] += size_mb

                except OSError as e:
                    LOGGER.warning("Could not remove %s: %s", test_dir, e)

        return stats

    def cleanup_repository_user_data(self, backup: bool = True) -> dict[str, int]:
        """Clean user_data from repository (legacy location).

        Args:
            backup: If True, create backup before removal

        Returns:
            Dict with cleanup statistics
        """
        stats = {"files_removed": 0, "space_freed_mb": 0, "backup_created": False}

        repo_root = Path(__file__).parent.parent
        repo_user_data = repo_root / "user_data"

        if not repo_user_data.exists():
            LOGGER.info("No user_data directory found in repository")
            return stats

        # Calculate size
        size_mb = self._calculate_directory_size(repo_user_data)

        # Create backup if requested
        if backup and not self.dry_run:
            backup_path = repo_root / f"user_data_backup_{int(os.time())}"
            try:
                shutil.copytree(repo_user_data, backup_path)
                stats["backup_created"] = True
                LOGGER.info("Created backup at: %s", backup_path)
            except OSError as e:
                LOGGER.warning("Could not create backup: %s", e)

        # Remove directory
        if self.dry_run:
            LOGGER.info("Would remove repository user_data: %s (%.2f MB)", repo_user_data, size_mb)
        else:
            try:
                LOGGER.info("Removing repository user_data: %s (%.2f MB)", repo_user_data, size_mb)
                shutil.rmtree(repo_user_data)
                stats["files_removed"] = 1
                stats["space_freed_mb"] = size_mb
            except OSError as e:
                LOGGER.error("Could not remove %s: %s", repo_user_data, e)

        return stats

    def cleanup_database_connections(self, user_name: str | None = None) -> dict[str, int]:
        """Clean up active database connections and memory data.

        Args:
            user_name: Specific user to clean up, or None for test cleanup

        Returns:
            Dict with cleanup statistics
        """
        stats = {"connections_closed": 0, "memory_cleaned": 0}

        try:
            # For development/testing, create a manager and clean it
            if self.dry_run:
                LOGGER.info("Would clean database connections and memory data")
                return stats

            # Create a database manager for cleanup
            manager = DatabaseManager(user_name=user_name or "cleanup_user")

            # Clean memory database (this also closes connections)
            manager.clean_memory_database(watchdog_retention_days=0)  # Aggressive cleanup
            stats["memory_cleaned"] = 1

            LOGGER.info("Cleaned database connections and memory data")

        except Exception as e:
            LOGGER.error("Error cleaning database connections: %s", e)

        return stats

    def full_cleanup(
        self, max_age_hours: int = 24, cleanup_repo: bool = True, backup_repo_data: bool = True
    ) -> dict[str, dict]:
        """Perform full cleanup of all user data.

        Args:
            max_age_hours: Maximum age for test data to keep
            cleanup_repo: Whether to clean repository user_data
            backup_repo_data: Whether to backup repository data before cleanup

        Returns:
            Dict with detailed cleanup results
        """
        results = {}

        LOGGER.info("Starting full user data cleanup...")

        # 1. Clean test data
        LOGGER.info("Cleaning test data...")
        results["test_data"] = self.cleanup_test_data(max_age_hours)

        # 2. Clean repository user_data if requested
        if cleanup_repo:
            LOGGER.info("Cleaning repository user_data...")
            results["repository"] = self.cleanup_repository_user_data(backup_repo_data)

        # 3. Clean database connections
        LOGGER.info("Cleaning database connections...")
        results["database"] = self.cleanup_database_connections()

        # 4. Summary
        total_space_freed = sum(r.get("space_freed_mb", 0) for r in results.values())
        total_items_removed = sum(
            r.get("directories_removed", 0) + r.get("files_removed", 0) for r in results.values()
        )

        results["summary"] = {
            "total_space_freed_mb": round(total_space_freed, 2),
            "total_items_removed": total_items_removed,
            "dry_run": self.dry_run,
        }

        LOGGER.info(
            "Cleanup completed. Space freed: %.2f MB, Items removed: %d",
            total_space_freed,
            total_items_removed,
        )

        return results

    @staticmethod
    def _calculate_directory_size(path: Path) -> float:
        """Calculate total size of directory in MB."""
        total_size = 0
        try:
            for root, _dirs, files in os.walk(path):
                for file in files:
                    try:
                        file_path = Path(root) / file
                        total_size += file_path.stat().st_size
                    except OSError:
                        pass
        except OSError:
            pass
        return total_size / (1024 * 1024)


def main():
    """Command-line interface for cleanup tools."""
    import argparse

    parser = argparse.ArgumentParser(description="DinoAir User Data Cleanup Utility")
    parser.add_argument(
        "--analyze", action="store_true", help="Analyze user data directories without cleaning"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be cleaned without actually doing it",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=24,
        help="Maximum age for test data to keep (default: 24)",
    )
    parser.add_argument(
        "--no-repo-cleanup", action="store_true", help="Skip cleaning repository user_data"
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="Skip creating backup of repository data"
    )

    args = parser.parse_args()

    cleanup_manager = UserDataCleanupManager(dry_run=args.dry_run, verbose=args.verbose)

    if args.analyze:
        cleanup_manager.analyze_user_data()
    else:
        cleanup_manager.full_cleanup(
            max_age_hours=args.max_age_hours,
            cleanup_repo=not args.no_repo_cleanup,
            backup_repo_data=not args.no_backup,
        )


if __name__ == "__main__":
    main()
