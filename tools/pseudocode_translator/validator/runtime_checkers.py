"""
Runtime risk detection and analysis.

This module provides AST visitors for detecting potential runtime errors
and risky code patterns.
"""

import ast

from ..exceptions import ErrorContext, ValidationError


class RuntimeRiskChecker(ast.NodeVisitor):
    """AST visitor for detecting potential runtime errors."""

    def __init__(self):
        self.risks: list[str] = []

    def visit_Subscript(self, node: ast.Subscript):
        """Check subscript operations for potential index errors."""
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
            # Flag large indices
            if abs(node.slice.value) > 1000:
                self.risks.append(f"Large index {node.slice.value} at line {node.lineno}")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp):
        """Check binary operations for runtime risks."""
        # Check for division by zero
        if (
            isinstance(node.op, ast.Div | ast.FloorDiv | ast.Mod)
            and isinstance(node.right, ast.Constant)
            and node.right.value == 0
        ):
            context = ErrorContext(line_number=node.lineno, metadata={"operation": "division"})

            error = ValidationError(
                "Division by zero detected",
                validation_type="logic",
                context=context,
            )
            error.add_suggestion("Add a check for zero before division")
            error.add_suggestion("Use try/except to handle ZeroDivisionError")

            self.risks.append(error.format_error(include_context=False))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Check function calls for runtime risks."""
        # Check for risky built-in functions
        if isinstance(node.func, ast.Name):
            if node.func.id in ["eval", "exec", "compile"]:
                self.risks.append(f"Risky function call '{node.func.id}' at line {node.lineno}")
            elif node.func.id == "open" and len(node.args) > 1:
                # Check for file operations without error handling
                if isinstance(node.args[1], ast.Constant) and "w" in node.args[1].value:
                    self.risks.append(
                        f"File write operation at line {node.lineno} - ensure proper error handling"
                    )

        self.generic_visit(node)


class ExceptionHandlingChecker(ast.NodeVisitor):
    """Check exception handling patterns."""

    def __init__(self):
        self.suggestions: list[str] = []

    def visit_Try(self, node: ast.Try):
        """Analyze try/except blocks."""
        # Check for bare except clauses
        for handler in node.handlers:
            if handler.type is None:
                self.suggestions.append(
                    f"Bare except clause at line {handler.lineno} - specify exception types"
                )

        # Check for empty except blocks
        for handler in node.handlers:
            if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                self.suggestions.append(
                    f"Empty except block at line {handler.lineno} - add proper error handling"
                )

        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise):
        """Check raise statements."""
        # Could check for proper exception types
        self.generic_visit(node)


class NullPointerChecker(ast.NodeVisitor):
    """Check for potential None/null reference issues."""

    def __init__(self):
        self.risks: list[str] = []

    def visit_Attribute(self, node: ast.Attribute):
        """Check attribute access that might fail on None."""
        # Look for patterns where value might be None
        if isinstance(node.value, ast.Name):
            # This is a simple heuristic - in practice would need flow analysis
            if node.value.id.endswith("_optional") or "maybe" in node.value.id:
                self.risks.append(f"Potential None access at line {node.lineno} - add None check")

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Check method calls that might fail on None."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Attribute)
            and node.func.value.func.attr in ["get", "find", "search"]
        ):
            # Check for common patterns that might return None
            self.risks.append(
                f"Chained call at line {node.lineno} - intermediate result might be None"
            )

        self.generic_visit(node)


class ResourceManagementChecker(ast.NodeVisitor):
    """Check resource management patterns."""

    def __init__(self):
        self.suggestions: list[str] = []
        self.open_calls = []

    def visit_Call(self, node: ast.Call):
        """Check resource allocation calls."""
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            self.open_calls.append(node.lineno)
            # Check if it's used with 'with' statement
            # This would require parent node analysis
            self.suggestions.append(
                f"File open at line {node.lineno} - consider using 'with' statement for automatic cleanup"
            )

        self.generic_visit(node)

    def visit_With(self, node: ast.With):
        """Proper resource management with context managers."""
        # Remove suggestions for properly managed resources
        for item in node.items:
            if isinstance(item.context_expr, ast.Call) and (
                isinstance(item.context_expr.func, ast.Name) and item.context_expr.func.id == "open"
            ):
                # This open() is properly managed
                if item.context_expr.lineno in self.open_calls:
                    # Remove the suggestion for this line
                    self.suggestions = [
                        s for s in self.suggestions if f"line {item.context_expr.lineno}" not in s
                    ]

        self.generic_visit(node)


class ConcurrencyRiskChecker(ast.NodeVisitor):
    """Check for concurrency-related risks."""

    def __init__(self):
        self.risks: list[str] = []

    def visit_Global(self, node: ast.Global):
        """Check global variable usage."""
        self.risks.append(
            f"Global variable usage at line {node.lineno} - potential thread safety issue"
        )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Check for thread-unsafe operations."""
        self.generic_visit(node)
