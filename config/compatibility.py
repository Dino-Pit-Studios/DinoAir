"""
Configuration Migration and Compatibility Layer for DinoAir
Provides backward compatibility with existing ConfigLoader and migration utilities
"""

import os
from pathlib import Path
from typing import Any

from .versioned_config import VersionedConfigManager, get_config


class ConfigMigrator:
    """Handles migration from old configuration format to new versioned system"""

    def __init__(self, old_config_path: Path | None = None):
        """
        Initialize migrator

        Args:
            old_config_path: Path to old configuration file
        """
        base_dir = Path(__file__).parent.parent
        self.old_config_path = old_config_path or (base_dir / "config" / "app_config.json")
        self.new_config_path = base_dir / "config" / "app_config.json"
        self.backup_path = base_dir / "config" / "app_config.json.backup"

    @staticmethod
    def needs_migration() -> bool:
        """Check if migration is needed"""
        # For now, assume no migration needed since we're starting fresh
        # In the future, this could check for old format files
        return False

    def migrate(self) -> bool:
        """
        Migrate old configuration to new format

        Returns:
            True if migration was successful
        """
        if not self.needs_migration():
            return True

        # Migration logic would go here
        # For now, return True as no migration is needed
        return True


class CompatibilityConfigLoader:
    """
    Backward-compatible wrapper around VersionedConfigManager
    Provides the same interface as the old ConfigLoader class
    """

    def __init__(self, config_path: Path | None = None):
        """
        Initialize compatibility loader

        Args:
            config_path: Path to configuration file (optional)
        """
        self._config_manager = get_config()

        # If a custom config path is provided, initialize with it
        if config_path is not None:
            self._config_manager = VersionedConfigManager(
                config_file_path=config_path,
                validate_on_load=False,  # More permissive for compatibility
            )

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (backward compatible)"""
        return self._config_manager.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        """Set configuration value (backward compatible)"""
        self._config_manager.set(key, value)
        if save:
            self.save_config()

    def save_config(self) -> None:
        """Save configuration to file (backward compatible)"""
        self._config_manager.save_config_file()

    @staticmethod
    def load_config() -> None:
        """Load configuration (no-op for compatibility)"""
        # The new system loads automatically

    @staticmethod
    def get_env(key: str, default: str = "") -> str:
        """Get environment variable value"""
        return os.environ.get(key, default)

    # Async-specific compatibility methods
    def is_async_enabled(self) -> bool:
        """Check if async operations are enabled globally"""
        return self._config_manager.get("async.enabled", True)

    def should_use_async_file_ops(self) -> bool:
        """Check if async file operations should be used"""
        return self._config_manager.get("async.file_operations.use_async", True)

    def should_use_async_network_ops(self) -> bool:
        """Check if async network operations should be used"""
        return self._config_manager.get("async.network_operations.use_async", True)

    def should_use_async_pdf_processing(self) -> bool:
        """Check if async PDF processing should be used"""
        return self._config_manager.get("async.pdf_processing.use_async", True)

    def get_async_concurrent_limit(self) -> int:
        """Get the concurrent limit for async file operations"""
        return self._config_manager.get("async.file_operations.concurrent_limit", 10)

    def get_async_network_timeout(self) -> float:
        """Get the timeout for async network operations"""
        return self._config_manager.get("async.network_operations.timeout", 30.0)

    def get_async_pdf_timeout(self) -> float:
        """Get the timeout for async PDF processing"""
        return self._config_manager.get("async.pdf_processing.timeout", 60.0)


def migrate_configuration(force: bool = False) -> bool:
    """
    Migrate configuration to new versioned system

    Args:
        force: Force migration even if not needed

    Returns:
        True if migration was successful
    """
    migrator = ConfigMigrator()

    if force or migrator.needs_migration():
        return migrator.migrate()

    return True


# Create compatibility instance
ConfigLoader = CompatibilityConfigLoader
