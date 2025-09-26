"""
Safe subprocess utilities for DinoAir core (non-API modules).

This module provides hardened wrappers around subprocess to:
- Eliminate shell=True (Windows and POSIX)
- Enforce centralized binary allowlists from configuration
- Capture stdout/stderr safely
- Provide structured, redactable logging
- Offer a safe background Popen when strictly required
- Platform-specific security guards (Windows no-window, Unix close_fds)

Key rules:
- Always pass a list[str] for command. Never pass a string.
- The first element (binary) must be allowlisted by configuration or caller.
- Do not pass user input directly. Validate and sanitize first.
- Prefer safe_run() over safe_popen(); only use Popen for long-running daemons.

Examples:
    # Synchronous, safe execution
    from pathlib import Path
    from utils.process import safe_run, SafeProcessError

    try:
        proc = safe_run(
            ["python", "--version"],
            allowed_binaries={"python", "python.exe"},
            cwd=Path("."),
            timeout=10,
            check=True,        # raise SafeProcessError if non-zero exit
        )
        print(proc.stdout.strip())
    except SafeProcessError as e:
        # Non-zero exit codes will end here if check=True
        print(f"Command failed: {e}, rc={e.returncode}")


Security tests to add elsewhere (outline):
- Passing a string command raises TypeError
- Binary not in allowlist raises PermissionError
- Injection tokens like '&&' in args do not do anything (no shell)
"""

from __future__ import annotations

import contextlib
import json
import logging
import platform
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .performance_monitor import performance_monitor

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Import configuration system
try:
    from config.versioned_config import config
except ImportError:
    # Fallback for when config system is not available
    config = None

# Constants for process execution
MAX_ENV_DISPLAY_SIZE = 20  # Maximum number of env vars to display in logs


class SafeProcessError(RuntimeError):
    """Raised when a safe subprocess returns non-zero and check=True.

    Attributes:
        command: The command list executed
        returncode: The integer return code from the process
        stdout: Captured standard output (text)
        stderr: Captured standard error (text)
    """

    def __init__(
        self,
        message: str,
        command: Sequence[str],
        returncode: int,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> None:
        super().__init__(message)
        self.command = list(command)
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""


class SecurityConfig:
    """Manages security configuration for process execution."""

    def __init__(self) -> None:
        self._config = config
        self._default_allowlist = {
            "python",
            "python.exe",
            "python3",
            "python3.exe",
            "git",
            "git.exe",
            "node",
            "node.exe",
            "npm",
            "npm.exe",
            "pip",
            "pip.exe",
            "pip3",
            "pip3.exe",
            "sqlite3",
            "sqlite3.exe",
            "echo",
            "cat",
            "head",
            "tail",
            "find",
            "grep",
            "wc",
            "sort",
            "uniq",
            "ls",
            "dir",
            "pwd",
            "whoami",
            "date",
            "hostname",
            "ping",
            "curl",
            "wget",
        }
        self._default_redact_env_keys = ["secret", "key", "token", "password", "credential", "auth"]
        self._default_redact_arg_patterns = [
            r"--password=.*",
            r"--token=.*",
            r"--secret=.*",
            r"--key=.*",
            r"-p\s+\S+",
            r"--auth\s+\S+",
        ]

    def get_allowed_binaries(self) -> set[str]:
        """Get the configured allowlist of binaries."""
        if self._config:
            try:
                return set(
                    self._config.get("security.process.allowlist.binaries", self._default_allowlist)
                )
            except (KeyError, TypeError, AttributeError):
                logger.warning(
                    "Failed to load security.process.allowlist.binaries from config, using defaults"
                )
        return self._default_allowlist.copy()

    def get_arg_patterns(self, binary: str) -> list[str]:
        """Get argument validation patterns for a specific binary (case-insensitive)."""
        normalized_binary = binary.lower()
        if self._config:
            try:
                patterns = self._config.get("security.process.allowlist.arg_patterns", {})
                # Normalize keys for case-insensitive lookup
                normalized_patterns = {k.lower(): v for k, v in patterns.items()}
                return normalized_patterns.get(normalized_binary, [])
            except (KeyError, TypeError, AttributeError):
                logger.warning("Failed to load arg patterns for %s from config", binary)
        return []

    def get_merge_enabled(self) -> bool:
        """Check if allowlist merging is enabled."""
        if self._config:
            try:
                return self._config.get("security.process.allowlist.enable_merge", False)
            except (KeyError, TypeError, AttributeError):
                logger.warning("Failed to load security.process.allowlist.enable_merge from config")
        return False

    def get_no_window_windows(self) -> bool:
        """Check if Windows no-window flag should be used."""
        if self._config:
            try:
                return self._config.get("security.process.flags.no_window_windows", True)
            except (KeyError, TypeError, AttributeError):
                logger.warning(
                    "Failed to load security.process.flags.no_window_windows from config"
                )
        return True

    def get_close_fds_unix(self) -> bool:
        """Check if Unix close_fds should be used."""
        if self._config:
            try:
                return self._config.get("security.process.flags.close_fds_unix", True)
            except (KeyError, TypeError, AttributeError):
                logger.warning("Failed to load security.process.flags.close_fds_unix from config")
        return True

    def get_disallow_tty(self) -> bool:
        """Check if TTY access should be disallowed."""
        if self._config:
            try:
                return self._config.get("security.process.flags.disallow_tty", True)
            except (KeyError, TypeError, AttributeError):
                logger.warning("Failed to load security.process.flags.disallow_tty from config")
        return True

    def get_stdin_default_devnull(self) -> bool:
        """Check if stdin should default to devnull."""
        if self._config:
            try:
                return self._config.get("security.process.flags.stdin_default_devnull", True)
            except (KeyError, TypeError, AttributeError):
                logger.warning(
                    "Failed to load security.process.flags.stdin_default_devnull from config"
                )
        return True

    def get_redact_env_keys(self) -> list[str]:
        """Get environment variable keys to redact from logs."""
        if self._config:
            try:
                return self._config.get(
                    "security.process.logging.redact_env_keys", self._default_redact_env_keys
                )
            except (KeyError, TypeError, AttributeError):
                logger.warning(
                    "Failed to load security.process.logging.redact_env_keys from config"
                )
        return self._default_redact_env_keys.copy()

    def get_redact_arg_patterns(self) -> list[str]:
        """Get argument patterns to redact from logs."""
        if self._config:
            try:
                return self._config.get(
                    "security.process.logging.redact_arg_patterns",
                    self._default_redact_arg_patterns,
                )
            except (KeyError, TypeError, AttributeError):
                logger.warning(
                    "Failed to load security.process.logging.redact_arg_patterns from config"
                )
        return self._default_redact_arg_patterns.copy()

    def get_log_command_execution(self) -> bool:
        """Check if command execution should be logged."""
        if self._config:
            try:
                return self._config.get("security.process.logging.log_command_execution", True)
            except (KeyError, TypeError, AttributeError):
                logger.warning(
                    "Failed to load security.process.logging.log_command_execution from config"
                )
        return True


# Global security config instance
_security_config = SecurityConfig()


def _ensure_list_command(command: Sequence[str]) -> None:
    """Validate that command is a non-empty sequence of strings."""
    if not isinstance(command, (list, tuple)):
        raise TypeError("command must be a list[str] (or tuple[str])")
    if not command:
        raise ValueError("command cannot be empty")


def _merge_allowlists(
    per_call_allowlist: set[str], config_allowlist: set[str], enable_merge: bool
) -> set[str]:
    """Merge per-call and config allowlists based on merge policy."""
    if enable_merge:
        # Union: more permissive, allows anything from either list
        return per_call_allowlist | config_allowlist
    # When merge is disabled, per_call_allowlist takes precedence if provided
    # If per_call_allowlist is empty, use config_allowlist as fallback
    if not per_call_allowlist:
        return config_allowlist
    # Use per_call_allowlist as-is when merge is disabled
    return per_call_allowlist


def _validate_allowed_binary(command: Sequence[str], allowed_binaries: set[str]) -> str:
    """Validate the invoked binary against merged allowlists.

    Returns:
        The normalized basename (lower-cased) of the binary.

    Raises:
        ValueError if allowed_binaries is empty.
        PermissionError if not allowed.
    """
    # Disallow empty allowed_binaries set for security reasons
    if not allowed_binaries:
        raise ValueError("allowed_binaries must be a non-empty set")

    # Get configuration allowlist
    config_allowlist = _security_config.get_allowed_binaries()
    merge_enabled = _security_config.get_merge_enabled()

    # Merge allowlists based on policy
    effective_allowlist = _merge_allowlists(allowed_binaries, config_allowlist, merge_enabled)

    # If effective allowlist is empty after merging (but allowed_binaries was not empty),
    # this means intersection resulted in empty set - this should be PermissionError
    if not effective_allowlist:
        binary = Path(command[0]).name.lower()
        raise PermissionError(f"Binary '{binary}' is not in the allowed_binaries set")

    binary = Path(command[0]).name.lower()
    normalized_allow = {Path(b).name.lower() for b in effective_allowlist}

    if binary not in normalized_allow:
        raise PermissionError(f"Binary '{binary}' is not in the allowed_binaries set")
    return binary


def _validate_arguments(binary: str, command: Sequence[str]) -> None:
    """Validate command arguments against configured patterns."""
    patterns = _security_config.get_arg_patterns(binary)
    if not patterns:
        return

    # Skip the binary name itself
    args = command[1:]

    for arg in args:
        # Check if any pattern matches this argument
        matched = False
        for pattern in patterns:
            try:
                if re.search(pattern, arg):
                    matched = True
                    break
            except re.error as e:
                logger.warning("Invalid regex pattern '%s' for binary '%s': %s", pattern, binary, e)
                continue

        if not matched and patterns:  # If patterns exist but none match
            raise PermissionError(
                f"Argument '{arg}' for binary '{binary}' does not match any allowed patterns"
            )


def _redact_environment(env: dict[str, str] | None) -> dict[str, str]:
    """Redact sensitive environment variables for logging."""
    if not env:
        return {}

    redact_keys = _security_config.get_redact_env_keys()
    redacted = {}

    for key, value in env.items():
        should_redact = any(redact_key.lower() in key.lower() for redact_key in redact_keys)
        redacted[key] = "[REDACTED]" if should_redact else value

    return redacted


def _redact_arguments(command: Sequence[str]) -> list[str]:
    """Redact sensitive arguments for logging."""
    redact_patterns = _security_config.get_redact_arg_patterns()
    redacted_command = []

    for arg in command:
        redacted_arg = arg
        for pattern in redact_patterns:
            try:
                if re.match(pattern, arg):
                    redacted_arg = "[REDACTED]"
                    break
            except re.error as e:
                logger.warning("Invalid redaction pattern '%s': %s", pattern, e)
                continue
        redacted_command.append(redacted_arg)

    return redacted_command


def _log_invocation(
    binary: str,
    command: Sequence[str],
    cwd: Path | None,
    env: dict[str, str] | None = None,
) -> None:
    """Log invocation details with security redaction."""
    if not _security_config.get_log_command_execution():
        return

    try:
        redacted_command = _redact_arguments(command)
        redacted_env = _redact_environment(env) if env else None

        log_data = {
            "binary": binary,
            "args_count": len(command) - 1,
            "command": redacted_command,
            "cwd": str(cwd) if cwd else None,
            "env_vars": len(env) if env else 0,
        }

        # Only include environment if it's not too large
        if redacted_env and len(redacted_env) <= MAX_ENV_DISPLAY_SIZE:
            log_data["env"] = redacted_env

        with contextlib.suppress(OSError, ValueError, TypeError):
            # Silently ignore logging exceptions
            logger.info("Process execution: %s", json.dumps(log_data))

    except (OSError, ValueError, TypeError):
        # Logging must never break execution - catch common exceptions
        pass


def _get_platform_kwargs(creationflags: int | None = None) -> dict[str, Any]:
    """Get platform-specific subprocess keyword arguments."""
    kwargs: dict[str, Any] = {"shell": False}

    system = platform.system().lower()

    if system == "windows":
        # Windows-specific settings
        if _security_config.get_no_window_windows():
            no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            kwargs["creationflags"] = (creationflags or 0) | no_window
        if creationflags is not None:
            kwargs["creationflags"] = creationflags
        # Note: close_fds defaults to False on Windows, which we maintain
    else:
        # Unix-like systems (Linux, macOS, etc.)
        if _security_config.get_close_fds_unix():
            kwargs["close_fds"] = True

        if creationflags is not None:
            # creationflags is Windows-specific, ignore on Unix
            logger.warning("creationflags parameter ignored on non-Windows platforms")

    return kwargs


def _get_secure_stdin(stdin: Any) -> Any:
    """Get secure stdin configuration."""
    if stdin is not None:
        return stdin

    if _security_config.get_stdin_default_devnull():
        return subprocess.DEVNULL

    return None


def _preflight_process(
    command: Sequence[str],
    allowed_binaries: set[str] | None,
    cwd: Path | None,
    env: dict[str, str] | None,
) -> str:
    """
    Shared validation and logging for process execution functions.
    Returns the normalized binary name after validation.
    """
    _ensure_list_command(command)
    if allowed_binaries is None:
        allowed_binaries = set()
    binary = _validate_allowed_binary(command, allowed_binaries)
    _validate_arguments(binary, command)
    _log_invocation(binary, command, cwd, env)
    return binary


@performance_monitor(operation="safe_run")
def safe_run(
    command: Sequence[str],
    allowed_binaries: set[str] | None = None,
    cwd: Path | None = None,
    timeout: int | None = None,
    check: bool = False,
    env: dict[str, str] | None = None,
    text: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Safely execute a subprocess synchronously with enhanced security.

    Args:
        command: The command as a list of strings (['binary', 'arg1', ...]).
        allowed_binaries: Per-call basename allowlist. Merged with config allowlist.
        cwd: Optional working directory as a Path.
        timeout: Optional timeout in seconds.
        check: If True, raises SafeProcessError on non-zero exit.
        env: Optional environment variables to pass to the process.
        text: Capture output as text (default True).

    Returns:
        subprocess.CompletedProcess with stdout/stderr captured as text.

    Raises:
        TypeError, ValueError: If command is malformed.
        PermissionError: If binary not in effective allowlist.
        SafeProcessError: If check=True and process returns non-zero.
    """
    binary = _preflight_process(command, allowed_binaries, cwd, env)

    # Get platform-specific security settings
    subprocess_kwargs = _get_platform_kwargs()
    subprocess_kwargs.update(
        {
            "cwd": str(cwd) if isinstance(cwd, Path) else cwd,
            "timeout": timeout,
            "capture_output": True,
            "text": text,
            "env": env,
            # check=False is set explicitly in subprocess.run call to handle errors manually for better error reporting
        }
    )

    try:
        proc = subprocess.run(list(command), check=False, **subprocess_kwargs)
    except subprocess.TimeoutExpired:
        logger.warning("Process timed out after %ss: %s", timeout, binary)
        raise
    except FileNotFoundError:
        logger.error("Binary not found: %s", binary)
        raise
    except PermissionError:
        logger.error("Permission denied executing: %s", binary)
        raise

    if check and proc.returncode != 0:
        # Do not log full command to avoid secrets leakage via args
        raise SafeProcessError(
            f"Command '{binary}' failed with return code {proc.returncode}",
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    return proc


@performance_monitor(operation="safe_popen")
def safe_popen(
    command: Sequence[str],
    allowed_binaries: set[str] | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    stdout: Any = subprocess.PIPE,
    stderr: Any = subprocess.PIPE,
    stdin: Any = None,
    creationflags: int | None = None,
) -> subprocess.Popen[Any]:
    """Safely start a background subprocess with enhanced security.

    Use ONLY when a long-running daemon is strictly required. Prefer safe_run().

    Args:
        command: Command list (['binary', 'arg1', ...]).
        allowed_binaries: Per-call basename allowlist. Merged with config allowlist.
        cwd: Optional working directory.
        env: Optional environment variables.
        stdout, stderr, stdin: Standard stream redirections.
        creationflags: Optional Windows-specific flags.

    Returns:
        subprocess.Popen handle.

    Raises:
        TypeError, ValueError: If command is malformed.
        PermissionError: If binary not in effective allowlist.
    """
    _preflight_process(command, allowed_binaries, cwd, env)

    # Get platform-specific security settings
    popen_kwargs = _get_platform_kwargs(creationflags)
    popen_kwargs.update(
        {
            "cwd": str(cwd) if isinstance(cwd, Path) else cwd,
            "env": env,
            "stdout": stdout,
            "stderr": stderr,
            "stdin": _get_secure_stdin(stdin),
        }
    )

    return subprocess.Popen(list(command), **popen_kwargs)


__all__ = ["safe_run", "safe_popen", "SafeProcessError", "SecurityConfig"]
