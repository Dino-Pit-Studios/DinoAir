#!/usr/bin/env python3
"""
Circular Dependency Detection Script for DinoAir
==============================================

This script analyzes Python modules for circular dependencies and provides
detailed reporting with recommendations for resolution.

Usage:
    python scripts/check_circular_dependencies.py [options]

Options:
    --path PATH     Path to analyze (default: current directory)
    --format FORMAT Output format: json, text, or github (default: text)
    --fix           Suggest fixes for detected circular dependencies
    --verbose       Enable verbose output
"""

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path


class CircularDependencyDetector:
    """Detects and analyzes circular dependencies in Python code."""

    def __init__(self, root_path: Path, verbose: bool = False):
        self.root_path = root_path
        self.verbose = verbose
        self.dependencies: dict[str, set[str]] = defaultdict(set)
        self.module_paths: dict[str, Path] = {}

    def analyze_file(self, file_path: Path) -> set[str]:
        """Extract import dependencies from a Python file."""
        if self.verbose:
            print(f"Analyzing {file_path}")

        try:
            with open(file_path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception as e:
            if self.verbose:
                print(f"Warning: Could not parse {file_path}: {e}")
            return set()

        imports = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Use full module path for import
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                # Handle relative imports
                if node.level > 0:
                    # Convert relative import to absolute
                    module_parts = self._get_module_parts(file_path)
                    if len(module_parts) > node.level:
                        base_module = ".".join(module_parts[: -node.level])
                        if node.module:
                            imports.add(f"{base_module}.{node.module}")
                        else:
                            imports.add(base_module)
                else:
                    imports.add(node.module)

        return imports

    def _get_module_parts(self, file_path: Path) -> list[str]:
        """Get module parts from file path."""
        relative_path = file_path.relative_to(self.root_path)
        parts = list(relative_path.parts[:-1])  # Exclude filename
        if relative_path.stem != "__init__":
            parts.append(relative_path.stem)
        return parts

    def scan_directory(self) -> None:
        """Scan directory for Python files and build dependency graph."""
        python_files = list(self.root_path.rglob("*.py"))

        # Filter out test files, __pycache__, and other non-source files
        python_files = [
            f
            for f in python_files
            if not any(
                part in str(f)
                for part in [
                    "__pycache__",
                    ".git",
                    "test",
                    "tests",
                    "venv",
                    ".venv",
                    "build",
                    "dist",
                    "site-packages",
                ]
            )
        ]

        if self.verbose:
            print(f"Found {len(python_files)} Python files to analyze")

        for file_path in python_files:
            module_name = self._path_to_module(file_path)
            self.module_paths[module_name] = file_path
            imports = self.analyze_file(file_path)
            self.dependencies[module_name] = imports

    def _path_to_module(self, file_path: Path) -> str:
        """Convert file path to module name."""
        relative_path = file_path.relative_to(self.root_path)
        parts = list(relative_path.parts)

        # Handle __init__.py files
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = relative_path.stem

        return ".".join(parts) if parts else "__main__"

    def detect_cycles(self) -> list[list[str]]:
        """Detect all circular dependencies using DFS."""
        cycles = []
        visited = set()
        rec_stack = set()
        path = []

        def dfs(node: str) -> bool:
            if node in rec_stack:
                # Found cycle - extract it
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return True

            if node in visited:
                return False

            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            # Only check dependencies that exist in our module map
            for dep in self.dependencies.get(node, []):
                if dep in self.dependencies:  # Only check internal dependencies
                    dfs(dep)

            path.pop()
            rec_stack.remove(node)
            return False

        # Check all nodes
        for module in self.dependencies:
            if module not in visited:
                dfs(module)

        return self._deduplicate_cycles(cycles)

    def _deduplicate_cycles(self, cycles: list[list[str]]) -> list[list[str]]:
        """Remove duplicate cycles (same cycle with different starting points)."""
        unique_cycles = []
        seen_cycles = set()

        for cycle in cycles:
            # Normalize cycle by rotating to start with lexicographically smallest element
            if len(cycle) > 1:
                # Exclude last element (duplicate)
                min_idx = cycle.index(min(cycle[:-1]))
                normalized = cycle[min_idx:-1] + cycle[:min_idx]
                cycle_key = tuple(normalized)

                if cycle_key not in seen_cycles:
                    seen_cycles.add(cycle_key)
                    # Remove duplicate last element
                    unique_cycles.append(cycle[:-1])

        return unique_cycles

    def suggest_fixes(self, cycles: list[list[str]]) -> dict[str, list[str]]:
        """Suggest fixes for detected circular dependencies."""
        suggestions = {}

        for cycle in cycles:
            cycle_key = " -> ".join(cycle)
            fixes = []

            # Analyze the cycle to suggest appropriate fixes
            if len(cycle) == 2:
                fixes.extend(
                    [
                        "Consider using dependency injection pattern",
                        "Move common functionality to a separate module",
                        "Use factory pattern to break direct dependency",
                        "Consider using imports inside functions (lazy loading)",
                    ]
                )
            else:
                fixes.extend(
                    [
                        "Break the cycle by introducing an interface/protocol module",
                        "Use dependency injection container",
                        "Refactor to use observer pattern",
                        "Move shared dependencies to a common base module",
                    ]
                )

            suggestions[cycle_key] = fixes

        return suggestions


def format_output(
    cycles: list[list[str]],
    suggestions: dict[str, list[str]],
    format_type: str,
    module_paths: dict[str, Path],
) -> str:
    """Format output in the specified format."""

    if format_type == "json":
        result = {
            "circular_dependencies": [
                {
                    "cycle": cycle,
                    "files": [str(module_paths.get(module, "unknown")) for module in cycle],
                    "suggestions": suggestions.get(" -> ".join(cycle), []),
                }
                for cycle in cycles
            ],
            "total_cycles": len(cycles),
            "status": "failed" if cycles else "passed",
        }
        return json.dumps(result, indent=2)

    if format_type == "github":
        if not cycles:
            return "[OK] No circular dependencies detected"

        output = ["[ERROR] Circular dependencies detected:\n"]
        for cycle in cycles:
            cycle_str = " -> ".join(cycle + [cycle[0]])  # Close the loop
            output.append(
                f"::error file={module_paths.get(cycle[0], 'unknown')}::Circular dependency: {cycle_str}"
            )

        return "\n".join(output)

    # text format
    if not cycles:
        return "[OK] No circular dependencies detected"

    output = [f"[ERROR] Found {len(cycles)} circular dependency cycle(s):\n"]

    for i, cycle in enumerate(cycles, 1):
        output.append(f"Cycle #{i}:")
        cycle_str = " -> ".join(cycle + [cycle[0]])  # Close the loop
        output.append(f"  {cycle_str}")

        # Show file paths
        output.append("  Files involved:")
        for module in cycle:
            file_path = module_paths.get(module, "unknown")
            output.append(f"    - {file_path}")

        # Show suggestions if available
        cycle_key = " -> ".join(cycle)
        if cycle_key in suggestions:
            output.append("  Suggested fixes:")
            for suggestion in suggestions[cycle_key]:
                output.append(f"    • {suggestion}")

        output.append("")  # Empty line between cycles

    return "\n".join(output)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Detect circular dependencies in Python code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--path", type=Path, default=Path(), help="Path to analyze (default: current directory)"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "github"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--fix", action="store_true", help="Suggest fixes for detected circular dependencies"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    if not args.path.exists():
        print(f"Error: Path {args.path} does not exist", file=sys.stderr)
        sys.exit(1)

    # Initialize detector
    detector = CircularDependencyDetector(args.path, args.verbose)

    # Scan for dependencies
    detector.scan_directory()

    # Detect cycles
    cycles = detector.detect_cycles()

    # Generate suggestions if requested
    suggestions = {}
    if args.fix:
        suggestions = detector.suggest_fixes(cycles)

    # Output results
    output = format_output(cycles, suggestions, args.format, detector.module_paths)
    print(output)

    # Exit with appropriate code
    sys.exit(1 if cycles else 0)


if __name__ == "__main__":
    main()
