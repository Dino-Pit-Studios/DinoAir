#!/usr/bin/env python3
"""
Simplified configuration management CLI tool

Provides commands for managing configurations for the Pseudocode Translator.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import yaml

from .config import ConfigManager, ConfigProfile

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _ensure_file_readable(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return f"File not found or unreadable: {path}"
    try:
        with open(path):
            pass
    except Exception:
        return f"File not found or unreadable: {path}"
    return None


def _load_raw_config(path: Path) -> tuple[dict, None] | tuple[None, str]:
    try:
        with open(path) as f:
            raw = yaml.safe_load(f) if path.suffix.lower() in (".yaml", ".yml") else json.load(f)
        return raw, None
    except Exception as e:
        msg = f"Failed to read/parse configuration: {e}".strip()
        return None, msg


def validate_config(path: str, lenient: bool = False) -> tuple[int, dict]:
    """
    Validate a configuration file using runtime validators.

    Behavior:
    - Parses the file and builds a Config via Config.from_dict(), then validates with
      ConfigManager's runtime validators. CLI flag takes precedence over PSEUDOCODE_LENIENT_CONFIG.
    - When lenient=False (default): run strict validation (raise on errors -> exit 1).
    - When lenient=True: run non-strict validation, collect warnings and any errors. Exit code
      is 0 if no errors, else 1.

    Returns:
      (exit_code, result_dict) where result_dict includes:
      {"errors": [...], "warnings": [...], "path": path}
    """
    from .config import Config, ModelConfig  # import here to avoid cycles
    from .exceptions import ConfigurationError

    p = Path(path)
    err = _ensure_file_readable(p)
    if err:
        return 1, {
            "errors": [err],
            "warnings": [],
            "path": str(p),
        }

    # Ensure CLI flag takes precedence over env for this operation only
    env_key = "PSEUDOCODE_LENIENT_CONFIG"
    original_env = os.environ.get(env_key)
    os.environ[env_key] = "1" if lenient else "0"

    try:
        raw, err = _load_raw_config(p)
        if err:
            return 1, {"errors": [err], "warnings": [], "path": str(p)}

        # raw must be a mapping
        if not isinstance(raw, dict):
            return 1, {
                "errors": ["Configuration file must contain a mapping/object at the top level"],
                "warnings": [],
                "path": str(p),
            }

        # Build Config in a lenient way: apply only known fields; ignore unknown keys.
        # This preserves backward compatibility with broader fixture schemas.
        try:
            cfg = Config()  # start from defaults

            # Top-level fields (excluding nested dataclasses handled below)
            # type: ignore[attr-defined]
            top_level_fields = set(cfg.__dataclass_fields__.keys())
            # Known nested keys we will handle separately
            nested_keys = {"llm", "streaming"}
            for k, v in raw.items():
                if k in top_level_fields and k not in nested_keys:
                    try:
                        setattr(cfg, k, v)
                    except Exception:
                        # If assignment fails due to type, let validator handle it later
                        setattr(cfg, k, v)

            # Apply LLM section
            llm_data = raw.get("llm", {})
            if isinstance(llm_data, dict):
                # type: ignore[attr-defined]
                llm_fields = set(cfg.llm.__dataclass_fields__.keys())
                # Map common aliases
                alias_map = {
                    "path": "model_path",
                }
                for k, v in llm_data.items():
                    key = alias_map.get(k, k)
                    if key in llm_fields and key != "models":
                        try:
                            setattr(cfg.llm, key, v)
                        except Exception:
                            setattr(cfg.llm, key, v)
                # Models mapping (best-effort)
                models_raw = llm_data.get("models")
                if isinstance(models_raw, dict):
                    cfg.llm.models.clear()
                    for name, m in models_raw.items():
                        if isinstance(m, dict):
                            mc = {
                                "name": m.get("name", name),
                                "enabled": bool(m.get("enabled", True)),
                                "model_path": m.get("model_path", m.get("path")),
                                "temperature": m.get("temperature", cfg.llm.temperature),
                                "max_tokens": m.get("max_tokens", cfg.llm.max_tokens),
                                "auto_download": bool(m.get("auto_download", False)),
                            }
                            try:
                                cfg.llm.models[name] = ModelConfig(**mc)
                            except Exception:
                                # If construction fails, skip this model; validators will catch missing primary model if needed
                                pass

            # Apply Streaming section
            streaming_data = raw.get("streaming", {})
            if isinstance(streaming_data, dict):
                # type: ignore[attr-defined]
                streaming_fields = set(cfg.streaming.__dataclass_fields__.keys())
                for k, v in streaming_data.items():
                    if k in streaming_fields:
                        try:
                            setattr(cfg.streaming, k, v)
                        except Exception:
                            setattr(cfg.streaming, k, v)
        except Exception as e:
            msg = str(e).strip() or e.__class__.__name__
            return 1, {
                "errors": [f"Invalid configuration file: {msg}"],
                "warnings": [],
                "path": str(p),
            }

        # Validate with requested strictness using runtime validators
        mgr = ConfigManager()
        try:
            result = mgr.validate_all(cfg, strict=not lenient)
        except ConfigurationError as e:
            # Strict validation failed
            msg = str(e).strip()
            errors = [m.strip() for m in msg.splitlines() if m.strip()] or [msg]
            return 1, {"errors": errors, "warnings": [], "path": str(p)}
        except Exception as e:
            msg = str(e).strip() or e.__class__.__name__
            return 1, {"errors": [msg], "warnings": [], "path": str(p)}

        errors = result.get("errors", []) if isinstance(result, dict) else []
        warnings = result.get("warnings", []) if isinstance(result, dict) else []
        exit_code = 0 if not errors else 1
        return exit_code, {
            "errors": list(errors),
            "warnings": list(warnings),
            "path": str(p),
        }
    finally:
        # Restore original env
        if original_env is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = original_env


class ConfigTool:
    """Configuration management tool"""

    def __init__(self):
        self.parser = self._create_parser()

    def _create_parser(self) -> argparse.ArgumentParser:
        """Create argument parser"""
        parser = argparse.ArgumentParser(
            prog="config_tool",
            description="Configuration tool for Pseudocode Translator",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

        # Add verbosity flag
        parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")

        # Create subcommands
        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # Validate command
        validate_parser = subparsers.add_parser("validate", help="Validate a configuration file")
        validate_parser.add_argument("--path", required=True, help="Path to configuration file")
        validate_parser.add_argument(
            "--lenient",
            action="store_true",
            help="Run non-strict validation (CLI flag takes precedence over PSEUDOCODE_LENIENT_CONFIG for this operation)",
        )

        # Generate command
        generate_parser = subparsers.add_parser(
            "generate", help="Generate a new configuration file"
        )
        generate_parser.add_argument(
            "-o",
            "--output",
            default="config.yaml",
            help="Output file path (default: config.yaml)",
        )
        generate_parser.add_argument(
            "-p",
            "--profile",
            choices=["development", "production", "testing", "custom"],
            help="Configuration profile (default: development)",
        )
        generate_parser.add_argument(
            "--format",
            choices=["yaml", "json"],
            default="yaml",
            help="Output format (default: yaml)",
        )

        # Check command
        check_parser = subparsers.add_parser("check", help="Check configuration and environment")
        check_parser.add_argument(
            "config_file", nargs="?", help="Path to configuration file (optional)"
        )
        check_parser.add_argument("--env", action="store_true", help="Check environment variables")

        # Wizard command
        wizard_parser = subparsers.add_parser("wizard", help="Interactive configuration wizard")
        wizard_parser.add_argument(
            "-o",
            "--output",
            default="config.yaml",
            help="Output file path (default: config.yaml)",
        )

        # Info command
        info_parser = subparsers.add_parser("info", help="Show configuration information")
        info_parser.add_argument("config_file", help="Path to configuration file")

        # Upgrade command (for old configs)
        upgrade_parser = subparsers.add_parser(
            "upgrade", help="Upgrade old configuration to new format"
        )
        upgrade_parser.add_argument("config_file", help="Path to old configuration file")
        upgrade_parser.add_argument(
            "-o", "--output", help="Output file path (default: overwrite input)"
        )
        upgrade_parser.add_argument(
            "--backup",
            action="store_true",
            default=True,
            help="Create backup of original file (default: true)",
        )

        return parser

    def run(self, args: list[str] | None = None):
        """Run the configuration tool"""
        parsed_args = self.parser.parse_args(args)

        if parsed_args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        if not parsed_args.command:
            self.parser.print_help()
            return 1

        # Execute command
        command_map = {
            "validate": self.cmd_validate,
            "generate": self.cmd_generate,
            "check": self.cmd_check,
            "wizard": self.cmd_wizard,
            "info": self.cmd_info,
            "upgrade": self.cmd_upgrade,
        }

        command_func = command_map.get(parsed_args.command)
        if command_func:
            try:
                return command_func(parsed_args)
            except Exception as e:
                logger.error("Error: %s", e)
                if parsed_args.verbose:
                    import traceback

                    traceback.print_exc()
                return 1
        else:
            logger.error("Unknown command: %s", parsed_args.command)
            return 1

    def cmd_validate(self, args) -> int:
        """Validate configuration file (structured JSON output)."""
        # use CLI flag precedence over env
        cfg_path = getattr(args, "path", None)
        lenient = bool(getattr(args, "lenient", False))
        exit_code, _ = validate_config(str(cfg_path), lenient=lenient)
        return exit_code

    def cmd_generate(self, args) -> int:
        """Generate new configuration file"""
        output_path = Path(args.output)

        # Check if file exists
        if output_path.exists():
            response = input(f"File {output_path} already exists. Overwrite? [y/N]: ")
            if response.lower() != "y":
                logger.info("Generation cancelled")
                return 1

        logger.info("Generating %s configuration", args.profile)

        # Create configuration based on profile
        profile_map = {
            "development": ConfigProfile.DEVELOPMENT,
            "production": ConfigProfile.PRODUCTION,
            "testing": ConfigProfile.TESTING,
            "custom": ConfigProfile.CUSTOM,
        }

        profile = profile_map[args.profile]

        if profile == ConfigProfile.CUSTOM:
            # Use wizard for custom profile
            config = ConfigManager.create_wizard()
        else:
            config = ConfigManager.create_profile(profile)

        # Save configuration
        try:
            ConfigManager.save(config, output_path)
            logger.info("Configuration generated: %s", output_path)
            return 0
        except Exception as e:
            logger.error("Failed to generate configuration: %s", e)
            return 1

    def cmd_check(self, args) -> int:
        """Check configuration and environment"""

        # Check configuration file if provided
        if args.config_file:
            config_path = Path(args.config_file)
            if config_path.exists():
                ConfigManager.get_config_info(str(config_path))
        else:
            # Check default configuration
            default_path = ConfigManager.DEFAULT_CONFIG_PATH
            if default_path.exists():
                ConfigManager.get_config_info()

        # Check environment variables if requested
        if args.env:
            env_vars = [
                "PSEUDOCODE_LLM_MODEL_TYPE",
                "PSEUDOCODE_LLM_TEMPERATURE",
                "PSEUDOCODE_LLM_THREADS",
                "PSEUDOCODE_LLM_GPU_LAYERS",
                "PSEUDOCODE_STREAMING_ENABLED",
                "PSEUDOCODE_STREAMING_CHUNK_SIZE",
                "PSEUDOCODE_VALIDATE_IMPORTS",
                "PSEUDOCODE_CHECK_UNDEFINED_VARS",
            ]

            for var in env_vars:
                _ = os.getenv(var)

        return 0

    def cmd_wizard(self, args) -> int:
        """Interactive configuration wizard"""
        try:
            config = ConfigManager.create_wizard()

            # Save configuration
            output_path = Path(args.output)
            ConfigManager.save(config, output_path)

            return 0

        except KeyboardInterrupt:
            return 1
        except Exception as e:
            logger.error("Wizard failed: %s", e)
            return 1

    def cmd_info(self, args) -> int:
        """Show configuration information"""
        config_path = Path(args.config_file)

        if not config_path.exists():
            logger.error("Configuration file not found: %s", config_path)
            return 1

        try:
            # Load configuration
            config = ConfigManager.load(config_path)

            # Get file stats
            config_path.stat()

            for name, model in config.llm.models.items():
                logger.info("Model '%s': %s", name, model)

            return 0

        except Exception as e:
            logger.error("Failed to load configuration: %s", e)
            return 1

    def cmd_upgrade(self, args) -> int:
        """Upgrade old configuration format"""
        config_path = Path(args.config_file)

        if not config_path.exists():
            logger.error("Configuration file not found: %s", config_path)
            return 1

        output_path = Path(args.output) if args.output else config_path

        logger.info("Upgrading configuration: %s", config_path)

        try:
            # Load old config
            if "../" in str(config_path) or "..\\" in str(config_path):
                raise Exception("Invalid file path")
            with open(config_path) as f:
                if config_path.suffix in [".yaml", ".yml"]:
                    old_data = yaml.safe_load(f)
                else:
                    old_data = json.load(f)

            # Check version
            version = old_data.get("_version", old_data.get("version", "1.0"))

            if version == "3.0":
                logger.info("Configuration is already in the new format")
                return 0

            # Create backup if requested
            if args.backup and output_path == config_path:
                backup_path = config_path.with_suffix(f"{config_path.suffix}.bak")
                import shutil

                shutil.copy2(config_path, backup_path)
                logger.info("Created backup: %s", backup_path)

            # Upgrade configuration
            logger.info("Upgrading from version %s to 3.0", version)

            # Try to load with our new system (it handles migration)
            config = ConfigManager.load(config_path)

            # Save in new format
            ConfigManager.save(config, output_path)

            logger.info("Configuration upgraded successfully: %s", output_path)

            # Validate the new config
            errors = config.validate()
            if errors:
                logger.error("Validation errors: %s", errors)
                return 1

            return 0

        except Exception as e:
            logger.error("Failed to upgrade configuration: %s", e)
            return 1


def main():
    """Main entry point"""
    tool = ConfigTool()
    sys.exit(tool.run())


if __name__ == "__main__":
    main()
