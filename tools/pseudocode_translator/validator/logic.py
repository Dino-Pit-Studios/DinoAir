"""
Logic validation module for Python code.

This module handles logic validation, runtime risk detection,
and validation of code semantics beyond syntax.
"""

import ast
from typing import TYPE_CHECKING

from ..ast_cache import parse_cached
from .constants import get_builtin_names
from .result import ValidationResult
from .runtime_checkers import RuntimeRiskChecker
from .type_checkers import TypeConsistencyChecker
from .variable_trackers import UndefinedVariableChecker

if TYPE_CHECKING:
    from .scope import Scope


class LogicValidator:
    """Handles logic validation and runtime risk analysis."""

    def __init__(self, config):
        """Initialize with translator configuration."""
        self.config = config
        self.check_undefined = config.check_undefined_vars

    def validate_logic(self, code: str) -> ValidationResult:
        """
        Validate code logic and potential runtime issues.

        Args:
            code: Python code to validate

        Returns:
            ValidationResult with logic validation details
        """
        # Parse using helper
        tree, parse_error_result = self._try_parse_tree_for_logic(code)
        if parse_error_result is not None:
            return parse_error_result

        result = ValidationResult(is_valid=True)

        # At this point, parsing succeeded; tree must be non-None
        if tree is None:
            raise AssertionError("Tree must not be None")

        # Collect logic issues
        logic_issues = self._collect_logic_issues(tree)
        for issue in logic_issues:
            result.add_warning(issue)

        # Check for potential runtime errors
        runtime_risks = self._check_runtime_risks(tree)
        for risk in runtime_risks:
            result.add_warning(f"Potential runtime error: {risk}")

        return result

    def _try_parse_tree_for_logic(
        self, code: str
    ) -> tuple[ast.AST | None, ValidationResult | None]:
        """Parse tree for logic validation with error handling."""
        try:
            tree = parse_cached(code)
            return tree, None
        except SyntaxError:
            result = ValidationResult(is_valid=False)
            result.add_error("Cannot validate logic: syntax errors present")
            return None, result
        except Exception as e:
            result = ValidationResult(is_valid=False)
            result.add_error(f"Cannot validate logic: parsing failed ({e})")
            return None, result

    def _collect_logic_issues(self, tree: ast.AST) -> list[str]:
        """Collect various logic-related issues."""
        issues = []

        # Check undefined variables if enabled
        if self.check_undefined:
            undefined_issues = self._check_undefined_names(tree)
            issues.extend(undefined_issues)

        # Basic type consistency checks
        issues.extend(self._check_basic_type_consistency(tree))

        # Other logic checks
        issues.extend(self._find_unreachable_code(tree))
        issues.extend(self._find_unused_variables(tree))
        issues.extend(self._detect_infinite_loops(tree))
        issues.extend(self._check_missing_returns(tree))

        return issues

    def _check_undefined_names(self, tree: ast.AST) -> list[str]:
        """Check for undefined variable names."""
        checker = UndefinedVariableChecker()
        checker.visit(tree)

        # Discover the module scope by walking parents
        module_scope: Scope = checker.current_scope
        while module_scope.parent is not None:
            module_scope = module_scope.parent

        # Suppress undefined-name checking if star-import present
        if getattr(module_scope, "star_import_present", False):
            return ["Star import prevents reliable undefined-name checking"]

        builtin_names = get_builtin_names()
        issues = []

        # Normalize tuples to (name, line, col)
        normalized = []
        for tup in checker.undefined_names:
            if len(tup) == 2:
                name, line = tup
                col = None
            else:
                name, line, col = tup
            normalized.append((name, line, col))

        # Deduplicate and filter builtins
        seen = set()
        for name, line, col in normalized:
            if name in builtin_names:
                continue
            key = (name, line, col)
            if key not in seen:
                seen.add(key)

        # Sort by (line, name)
        sorted_items = sorted(seen, key=lambda x: (x[1], x[0]))

        for name, line, col in sorted_items:
            similar = self._find_similar_name(name, checker.defined_names)
            loc = f"line {line}" + (f", col {col}" if col is not None else "")
            if similar:
                issues.append(f"Undefined variable '{name}' at {loc}. Did you mean '{similar}'?")
            else:
                issues.append(f"Undefined variable '{name}' at {loc}")

        return issues

    def _find_similar_name(self, target: str, candidates: set) -> str | None:
        """Find similar variable names for suggestions."""
        for candidate in candidates:
            if self._is_similar_name(target, candidate):
                return candidate
        return None

    @staticmethod
    def _is_similar_name(name1: str, name2: str) -> bool:
        """Check if two names are similar (for typo suggestions)."""
        if abs(len(name1) - len(name2)) > 2:
            return False

        # Simple edit distance check
        if len(name1) == len(name2):
            diff_count = sum(c1 != c2 for c1, c2 in zip(name1, name2, strict=False))
            return diff_count <= 1

        # Check for single character insertion/deletion
        shorter, longer = (name1, name2) if len(name1) < len(name2) else (name2, name1)
        return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))

    def _check_basic_type_consistency(self, tree: ast.AST) -> list[str]:
        """Check for basic type consistency issues."""
        checker = TypeConsistencyChecker()
        checker.visit(tree)
        return checker.issues

    def _check_runtime_risks(self, tree: ast.AST) -> list[str]:
        """Check for potential runtime errors."""
        checker = RuntimeRiskChecker()
        checker.visit(tree)
        return checker.risks

    def _find_unreachable_code(self, tree: ast.AST) -> list[str]:
        """Find unreachable code after return statements."""

        class UnreachableCodeFinder(ast.NodeVisitor):
            """Detects and reports unreachable code after return statements.
            Traverses function definitions and records statements that occur after a return.
            """

            def __init__(self):
                self.issues = []

            def visit_FunctionDef(self, node: ast.FunctionDef):
                found_return = False
                for stmt in node.body:
                    if found_return and not isinstance(stmt, ast.Pass):
                        self.issues.append(f"Unreachable code after return at line {stmt.lineno}")
                        break
                    if isinstance(stmt, ast.Return):
                        found_return = True
                self.generic_visit(node)

        finder = UnreachableCodeFinder()
        finder.visit(tree)
        return finder.issues

    def _find_unused_variables(self, tree: ast.AST) -> list[str]:
        """Find variables that are assigned but never used."""

        class UnusedVariableFinder(ast.NodeVisitor):
            """Visitor that tracks assigned variables and identifies unused ones in the AST."""

            def __init__(self):
                self.assigned = set()
                self.used = set()
                self.issues = []

            def visit_Assign(self, node: ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.assigned.add(target.id)
                self.generic_visit(node)

            def visit_Name(self, node: ast.Name):
                if isinstance(node.ctx, ast.Load):
                    self.used.add(node.id)

        finder = UnusedVariableFinder()
        finder.visit(tree)

        unused = finder.assigned - finder.used - {"_"}  # Exclude underscore convention
        return [f"Unused variable: {var}" for var in sorted(unused)]

    def _detect_infinite_loops(self, tree: ast.AST) -> list[str]:
        """Detect potential infinite loops."""

        class InfiniteLoopDetector(ast.NodeVisitor):
            """AST NodeVisitor that detects potential infinite loops by finding while True loops without break statements."""

            def __init__(self):
                self.issues = []

            def visit_While(self, node: ast.While):
                # Check for simple infinite loops
                if isinstance(node.test, ast.Constant) and node.test.value is True:
                    # Check if there's a break statement
                    has_break = any(isinstance(stmt, ast.Break) for stmt in ast.walk(node))
                    if not has_break:
                        self.issues.append(f"Potential infinite loop at line {node.lineno}")
                self.generic_visit(node)

        detector = InfiniteLoopDetector()
        detector.visit(tree)
        return detector.issues

    def _check_missing_returns(self, tree: ast.AST) -> list[str]:
        """Check for functions missing return statements."""

        class MissingReturnChecker(ast.NodeVisitor):
            """Visitor that checks function definitions for missing return statements."""

            def __init__(self):
                self.issues = []

            def visit_FunctionDef(self, node: ast.FunctionDef):
                if not node.body:
                    return

                # Check if function has any return statements
                has_return = any(isinstance(stmt, ast.Return) for stmt in ast.walk(node))

                # Skip if function name suggests it doesn't return anything
                if not has_return and not node.name.startswith(
                    ("print", "show", "display", "save", "write")
                ):
                    self.issues.append(
                        f"Function '{node.name}' at line {node.lineno} may be missing return statement"
                    )

                self.generic_visit(node)

        checker = MissingReturnChecker()
        checker.visit(tree)
        return checker.issues
