#!/usr/bin/env python3
"""
Test runner script for pseudocode_translator

This script provides a convenient way to run all tests with various options.
"""

import argparse
import subprocess
import sys

from .environment import change_to_project_dir, configure_environment
from .quality import run_quality_checks
from .test_args import add_quality_args


def run_command(cmd, cwd=None):
    """Run a command and return the result"""
    result = subprocess.run(cmd, cwd=cwd, check=False)
    return result.returncode


def add_test_selection_args(parser):
    """Add arguments for selecting specific tests or directories to run."""
    parser.add_argument(
        "tests",
        nargs="*",
        default=["tests"],
        help="Specific test files or directories to run (default: all tests)",
    )


def add_test_options_args(parser):
    """Add standard test options like verbosity, exit on first failure, keyword and mark filtering."""
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-vv", "--very-verbose", action="store_true", help="Very verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet output")
    parser.add_argument("-x", "--exitfirst", action="store_true", help="Exit on first failure")
    parser.add_argument(
        "-k",
        "--keyword",
        metavar="EXPRESSION",
        help="Only run tests matching the expression",
    )
    parser.add_argument(
        "-m",
        "--mark",
        metavar="MARKEXPR",
        help="Only run tests matching given mark expression",
    )


def add_coverage_args(parser):
    """Add coverage-related arguments to the parser for coverage analysis and reporting."""
    parser.add_argument(
        "--cov", "--coverage", action="store_true", help="Run with coverage analysis"
    )
    parser.add_argument(
        "--cov-report",
        choices=["term", "html", "xml", "json"],
        default="term",
        help="Coverage report format (default: term)",
    )
    parser.add_argument("--cov-html", action="store_true", help="Generate HTML coverage report")


def add_performance_args(parser):
    """Add performance testing arguments for parallel test execution and benchmarks."""
    parser.add_argument(
        "-n",
        "--numprocesses",
        type=int,
        metavar="NUM",
        help="Number of processes to use for parallel testing",
    )
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark tests")


def add_general_args(parser):
    """Add general test and collection options to the parser."""
    parser.add_argument("--pdb", action="store_true", help="Drop into debugger on failures")
    parser.add_argument(
        "--lf",
        "--last-failed",
        action="store_true",
        dest="last_failed",
        help="Rerun only the tests that failed last time",
    )
    parser.add_argument(
        "--ff",
        "--failed-first",
        action="store_true",
        dest="failed_first",
        help="Run all tests but run failed tests first",
    )
    parser.add_argument("--markers", action="store_true", help="Show available markers")
    parser.add_argument("--fixtures", action="store_true", help="Show available fixtures")


def run_post_quality_format_check(args):
    if args.all_checks or args.format:
        return run_command(
            [
                sys.executable,
                "-m",
                "ruff",
                "format",
                "--check",
                ".",
            ]
        )
    return None


def build_pytest_cmd(args):
    cmd = [sys.executable, "-m", "pytest"]
    verbosity_map = {
        "very_verbose": "-vv",
        "verbose": "-v",
        "quiet": "-q",
    }
    for attr, flag in verbosity_map.items():
        if getattr(args, attr):
            cmd.append(flag)
            break
    if args.exitfirst:
        cmd.append("-x")
    if args.keyword:
        cmd.extend(["-k", args.keyword])
    return cmd


def run_pytest_based_on_args(args):
    cmd = build_pytest_cmd(args)
    if args.mark:
        cmd.extend(["-m", args.mark])
    if args.pdb:
        cmd.append("--pdb")
    if args.last_failed:
        cmd.append("--lf")
    if args.failed_first:
        cmd.append("--ff")
    if args.markers:
        cmd.append("--markers")
        return run_command(cmd)
    if args.fixtures:
        cmd.append("--fixtures")
        return run_command(cmd)
    if args.collect_only:
        cmd.append("--collect-only")
        return run_command(cmd)
    return run_command(cmd)


def main():
    """Parse command-line arguments, configure the test environment, and execute the test runner."""
    parser = argparse.ArgumentParser(description="Run tests for pseudocode_translator")
    add_test_selection_args(parser)
    add_test_options_args(parser)
    add_coverage_args(parser)
    add_performance_args(parser)
    add_general_args(parser)
    add_quality_args(parser)

    args = parser.parse_args()

    # Auto environment setup for local runs
    configure_environment()
    change_to_project_dir()

    # Track exit codes
    exit_codes = run_quality_checks(args)

    format_exit = run_post_quality_format_check(args)
    if format_exit is not None:
        exit_codes.append(format_exit)

    pytest_exit = run_pytest_based_on_args(args)
    exit_codes.append(pytest_exit)
    return max(exit_codes) if exit_codes else 0


if __name__ == "__main__":
    sys.exit(main())
