"""
Code improvement suggestions module.

This module analyzes Python code and provides suggestions for
style, performance, readability, best practices, and security improvements.
"""

import ast
import re

from ..ast_cache import parse_cached
from .performance_checkers import PerformanceChecker


class ImprovementAnalyzer:
    """Analyzes code and suggests improvements."""

    def __init__(self, config):
        """Initialize with translator configuration."""
        self.config = config

    def suggest_improvements(self, code: str) -> list[str]:
        """
        Suggest improvements for the code.

        Args:
            code: Python code to analyze

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        try:
            tree = parse_cached(code)
        except (SyntaxError, ValueError):
            return ["Fix syntax errors before requesting improvements"]

        # Various improvement categories
        suggestions.extend(self._check_style(code))
        suggestions.extend(self._check_performance(tree, code))
        suggestions.extend(self._check_readability(tree, code))
        suggestions.extend(self._check_best_practices(tree, code))
        suggestions.extend(self._check_security(code))

        # Remove duplicates and return
        return list(dict.fromkeys(suggestions))

    def _check_style(self, code: str) -> list[str]:
        """Check for PEP 8 style violations."""
        suggestions = []
        lines = code.split("\n")

        for i, line in enumerate(lines, 1):
            suggestions.extend(self._style_violations_for_line(i, line))

        return suggestions

    def _style_violations_for_line(self, line_num: int, line: str) -> list[str]:
        """Check style violations for a single line."""
        violations = []
        violations.extend(ImprovementAnalyzer._check_line_length(line, line_num))
        violations.extend(ImprovementAnalyzer._check_trailing_whitespace(line, line_num))
        violations.extend(self._check_naming_conventions(line))
        violations.extend(self._check_spacing_style(line, line_num))
        return violations

    @staticmethod
    def _check_line_length(line: str, line_num: int) -> list[str]:
        """Check if line exceeds length limit."""
        if len(line) > 88:  # Slightly more lenient than PEP 8's 79
            return [f"Line {line_num} exceeds 88 characters"]
        return []

    @staticmethod
    def _check_trailing_whitespace(line: str, line_num: int) -> list[str]:
        """Check for trailing whitespace."""
        if line.rstrip() != line and line.strip():
            return [f"Line {line_num} has trailing whitespace"]
        return []

    def _check_naming_conventions(self, line: str) -> list[str]:
        """Check function and class naming conventions."""
        violations = []
        violations.extend(ImprovementAnalyzer._check_function_naming(line))
        violations.extend(ImprovementAnalyzer._check_class_naming(line))
        return violations

    @staticmethod
    def _check_function_naming(line: str) -> list[str]:
        """Check function naming conventions."""
        function_match = re.match(r"^\s*def\s+([A-Za-z_]\w*)", line)
        if function_match:
            func_name = function_match.group(1)
            if (
                func_name != func_name.lower() or not re.match(r"^[a-z_][a-z0-9_]*$", func_name)
            ) and not func_name.startswith("_"):  # Allow private methods to be different
                return [f"Function '{func_name}' should use snake_case naming"]
        return []

    @staticmethod
    def _check_class_naming(line: str) -> list[str]:
        """Check class naming conventions."""
        class_match = re.match(r"^\s*class\s+([A-Za-z_]\w*)", line)
        if class_match:
            class_name = class_match.group(1)
            if not re.match(r"^[A-Z][A-Za-z0-9]*$", class_name):
                return [f"Class '{class_name}' should use PascalCase naming"]
        return []

    def _check_spacing_style(self, line: str, line_num: int) -> list[str]:
        """Check spacing style issues."""
        issues = []

        # Multiple spaces around operators (simple check)
        if re.search(r"\w  +[=+\-*/]|[=+\-*/]  +\w", line):
            issues.append(f"Line {line_num} has excessive spacing around operators")

        # No space after comma
        if re.search(r",[^ \n]", line) and "," in line:
            issues.append(f"Line {line_num} missing space after comma")

        return issues

    def _check_performance(self, tree: ast.AST, code: str) -> list[str]:
        """Check for performance issues."""
        checker = PerformanceChecker()
        checker.visit(tree)

        suggestions = checker.suggestions.copy()

        # Analyze append calls in loops
        if checker.append_calls_in_loops:
            append_suggestions = self._analyze_append_calls_in_loops(checker.append_calls_in_loops)
            suggestions.extend(append_suggestions)

        return suggestions

    def _analyze_append_calls_in_loops(self, append_calls: list[tuple[str, int]]) -> list[str]:
        """Analyze append calls in loops and suggest improvements."""
        suggestions = []
        grouped = self._group_appends_by_list(append_calls)

        for list_name, line_numbers in grouped.items():
            if len(line_numbers) > 3:  # Multiple appends to same list
                suggestions.append(
                    f"Consider using list comprehension instead of multiple appends to '{list_name}' "
                    f"(lines {', '.join(map(str, sorted(line_numbers)))})"
                )
            elif len(line_numbers) == 1:
                suggestions.append(
                    f"Consider pre-allocating list size or using list comprehension for '{list_name}' "
                    f"(line {line_numbers[0]})"
                )

        return suggestions

    def _group_appends_by_list(self, pairs: list[tuple[str, int]]) -> dict[str, list[int]]:
        """Group append calls by list name."""
        grouped = {}
        for list_name, line_no in pairs:
            if list_name not in grouped:
                grouped[list_name] = []
            grouped[list_name].append(line_no)
        return grouped

    def _check_readability(self, tree: ast.AST, code: str) -> list[str]:
        """Check for readability improvements."""
        suggestions = []
        suggestions.extend(self._check_ast_readability(tree))
        suggestions.extend(self._readability_misc_suggestions(tree, code))
        return suggestions

    def _check_ast_readability(self, tree: ast.AST) -> list[str]:
        """Check AST-based readability issues."""
        suggestions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                suggestions.extend(self._check_function_readability(node))
            elif isinstance(node, ast.ClassDef):
                suggestions.extend(self._check_class_readability(node))

        return suggestions

    def _check_function_readability(self, node: ast.FunctionDef) -> list[str]:
        """Check readability for a single function."""
        if len(node.body) > 20:
            return [
                f"Function '{node.name}' is quite long ({len(node.body)} statements). Consider breaking it into smaller functions."
            ]
        return []

    def _check_class_readability(self, node: ast.ClassDef) -> list[str]:
        """Check readability for a single class."""
        method_count = sum(1 for n in node.body if isinstance(n, ast.FunctionDef))
        if method_count > 15:
            return [
                f"Class '{node.name}' has many methods ({method_count}). Consider splitting into smaller classes."
            ]
        return []

    def _readability_misc_suggestions(self, tree: ast.AST, code: str) -> list[str]:
        """Additional readability suggestions."""
        suggestions = []

        # Check for deeply nested code
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                depth = self._calculate_nesting_depth(node)
                if depth > 3:
                    suggestions.append(
                        f"Deeply nested if statement at line {node.lineno} (depth {depth}). Consider extracting to functions."
                    )

        # Check for very long lines with complex expressions
        lines = code.split("\n")
        for i, line in enumerate(lines, 1):
            if len(line) > 100 and ("(" in line or "[" in line or "{" in line):
                suggestions.append(
                    f"Line {i} is complex and long. Consider breaking into multiple lines or variables."
                )

        return suggestions

    def _calculate_nesting_depth(self, node: ast.AST) -> int:
        """Calculate the nesting depth of control structures."""
        depth = 0
        for child in ast.walk(node):
            if (
                isinstance(child, ast.If | ast.For | ast.While | ast.With | ast.Try)
                and child != node
            ):  # Don't count the node itself
                depth = max(depth, 1 + self._calculate_nesting_depth(child))
        return depth

    def _check_best_practices(self, tree: ast.AST, code: str) -> list[str]:
        """Check for best practice violations."""
        suggestions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                suggestions.extend(self._check_function_best_practices(node))

        return suggestions

    def _check_function_best_practices(self, node: ast.FunctionDef) -> list[str]:
        """Check best practices for a single function."""
        suggestions = []

        # Check for missing docstrings
        if not ast.get_docstring(node) and not node.name.startswith("_") and len(node.body) > 5:
            suggestions.append(
                f"Function '{node.name}' at line {node.lineno} should have a docstring"
            )

        # Check for too many arguments
        arg_count = self._count_function_arguments(node)
        if arg_count > 5:
            suggestions.append(
                f"Function '{node.name}' has too many arguments ({arg_count}). Consider using a parameter object or reducing complexity."
            )

        return suggestions

    def _count_function_arguments(self, node: ast.FunctionDef) -> int:
        """Count the total number of function arguments."""
        return (
            len(node.args.args)
            + len(node.args.kwonlyargs)
            + (1 if node.args.vararg else 0)
            + (1 if node.args.kwarg else 0)
        )

    def _check_security(self, code: str) -> list[str]:
        """Check for security-related improvements."""
        suggestions = []

        # Check for hardcoded secrets (simple patterns)
        secret_patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', "Avoid hardcoded passwords"),
            (r'api_key\s*=\s*["\'][^"\']+["\']', "Avoid hardcoded API keys"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "Avoid hardcoded secrets"),
            (r'token\s*=\s*["\'][^"\']+["\']', "Avoid hardcoded tokens"),
        ]

        for pattern, message in secret_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                suggestions.append(f"{message} - use environment variables or config files")

        # Check for SQL concatenation
        if re.search(r'["\'][^"\']*SELECT[^"\']*["\'].*\+', code, re.IGNORECASE):
            suggestions.append("Potential SQL injection risk - use parameterized queries")

        # Check for shell command construction
        if re.search(r'os\.system\s*\(["\'][^"\']*["\'].*\+', code):
            suggestions.append(
                "Potential command injection risk - validate inputs and use subprocess with shell=False"
            )

        return suggestions
