#!/usr/bin/env python3
"""
Configuration System Demonstration and Validation Script
Shows the new versioned configuration system in action
"""

import os
import sys
from pathlib import Path

from config.versioned_config import SchemaValidationError, VersionedConfigManager

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def demo_basic_usage():
    """Demonstrate basic configuration usage"""

    try:
        # Initialize configuration manager
        # Skip validation for demo
        VersionedConfigManager(validate_on_load=False)

        # Show basic configuration access

        return True

    except Exception:
        return False


def demo_precedence():
    """Demonstrate configuration precedence"""

    try:
        config = VersionedConfigManager(validate_on_load=False)

        # Show source information
        for _ in config.get_source_info():
            print(_)

        # Demonstrate value sources
        test_keys = ["app.name", "app.debug", "database.connection_timeout", "ai.temperature"]

        for key in test_keys:
            _ = config.get_with_source(key)

        return True

    except Exception:
        return False


def demo_environment_override():
    """Demonstrate environment variable overrides"""

    try:
        # Set some environment variables
        test_env_vars = {
            "DEBUG": "true",
            "AI_MAX_TOKENS": "4000",
            "UI_FONT_SIZE": "16",
            "LOG_LEVEL": "DEBUG",
        }

        for key, value in test_env_vars.items():
            os.environ[key] = value

        # Create new config instance to pick up env changes
        config = VersionedConfigManager(validate_on_load=False)

        # Show environment mappings

        # Cleanup
        for key in test_env_vars:
            del os.environ[key]

        return True

    except Exception:
        return False


def demo_validation():
    """Demonstrate schema validation"""

    try:
        # Test valid configuration
        config = VersionedConfigManager(validate_on_load=False)

        config.validate()

        # Test invalid values

        test_cases = [
            ("app.debug", "not_a_boolean", "boolean type validation"),
            ("ai.max_tokens", -100, "minimum value validation"),
            ("ui.window_width", 50, "minimum value validation"),
            ("logging.level", "INVALID", "enum validation"),
        ]

        for path, invalid_value, _test_type in test_cases:
            # Save original value
            original = config.get(path)

            try:
                config.set(path, invalid_value)
                config.validate()
            except SchemaValidationError:
                pass
            except Exception:
                pass
            finally:
                # Restore original value
                config.set(path, original)

        return True

    except Exception:
        return False


def demo_settings_overview():
    """Show overview of all settings"""

    try:
        config = VersionedConfigManager(validate_on_load=False)

        # Group settings by category
        settings = config.list_all_settings()
        categories = {}

        for setting in settings:
            category = setting.path.split(".")[0]
            if category not in categories:
                categories[category] = []
            categories[category].append(setting)

        for category, category_settings in sorted(categories.items()):
            for setting in sorted(category_settings, key=lambda s: s.path):
                setting.path.replace(f"{category}.", "  ")

        return True

    except Exception:
        return False


def main():
    """Run all demonstrations"""

    demos = [
        ("Basic Usage", demo_basic_usage),
        ("Precedence", demo_precedence),
        ("Environment Overrides", demo_environment_override),
        ("Schema Validation", demo_validation),
        ("Settings Overview", demo_settings_overview),
    ]

    passed = 0
    total = len(demos)

    for _name, demo_func in demos:
        try:
            if demo_func():
                passed += 1
            else:
                pass
        except Exception:
            pass

    return passed == total


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
