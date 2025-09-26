#!/usr/bin/env python3
"""
Test runner script for the utils package.
Provides convenient commands for running tests with different options.
"""

import shlex
import subprocess
import sys


def run_command(cmd):
    """Run a command and return the result."""
    try:
        # Security fix: Use shell=False and split command into list
        if isinstance(cmd, str):
            # Split command string into components for secure execution
            cmd_list = shlex.split(cmd)
        else:
            cmd_list = cmd

        result = subprocess.run(cmd_list, shell=False, capture_output=True, text=True, check=False)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def run_tests(args=None):
    """Run pytest with given arguments."""
    cmd = "python -m pytest"
    if args:
        cmd += f" {args}"

    success, _, _ = run_command(cmd)

    return success


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        return

    command = sys.argv[1]

    if command == "all":
        success = run_tests()
    elif command == "unit":
        success = run_tests("-m unit")
    elif command == "coverage":
        success = run_tests("--cov=utils --cov-report=term-missing --cov-report=html")
    elif command == "verbose":
        success = run_tests("-v")
    elif command in [
        "logger",
        "config_loader",
        "error_handling",
        "performance_monitor",
        "dependency_container",
        "artifact_encryption",
    ]:
        success = run_tests(f"tests/test_{command}.py -v")
    else:
        return

    if success:
        pass
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
