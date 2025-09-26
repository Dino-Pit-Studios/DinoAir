"""
Type checking and consistency validation.

This module provides AST visitors for type-related validation checks.
"""

import ast

from ..exceptions import ErrorContext, ValidationError


class TypeConsistencyChecker(ast.NodeVisitor):
    """AST visitor for basic type consistency checks."""

    def __init__(self):
        self.issues: list[str] = []

    def visit_BinOp(self, node: ast.BinOp):
        """Check binary operations for type consistency."""
        if isinstance(node.op, ast.Add) and self._is_string_number_addition(node):
            self._add_string_number_error(node)
        self.generic_visit(node)

    @staticmethod
    def _is_string_number_addition(node: ast.BinOp) -> bool:
        """Check if this is a string + number operation."""
        left_is_str = isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)
        right_is_num = isinstance(node.right, ast.Constant) and isinstance(
            node.right.value, int | float
        )
        right_is_str = isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)
        left_is_num = isinstance(node.left, ast.Constant) and isinstance(
            node.left.value, int | float
        )

        return (left_is_str and right_is_num) or (left_is_num and right_is_str)

    def _add_string_number_error(self, node: ast.BinOp):
        """Add a string+number type mismatch error."""
        context = ErrorContext(
            line_number=node.lineno,
            metadata={
                "operation": "addition",
                "types": "string and number",
            },
        )

        error = ValidationError(
            "Type mismatch: cannot add string and number",
            validation_type="logic",
            context=context,
        )
        error.add_suggestion("Convert the number to string using str()")
        error.add_suggestion("Use f-strings for string formatting")
        error.add_suggestion("Use .format() method for string formatting")

        self.issues.append(error.format_error(include_context=False))


class AnnotationChecker(ast.NodeVisitor):
    """Check type annotations and hints."""

    def __init__(self):
        self.issues: list[str] = []
        self.in_annotation = False

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Check function type annotations."""
        # Check parameter annotations
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            if not arg.annotation and not arg.arg.startswith("_"):
                self.issues.append(
                    f"Function parameter '{arg.arg}' at line {node.lineno} lacks type annotation"
                )

        # Check return annotation for non-trivial functions
        if not node.returns and len(node.body) > 3 and not node.name.startswith("_"):
            self.issues.append(
                f"Function '{node.name}' at line {node.lineno} should have a return type annotation"
            )

        self.generic_visit(node)

    def visit_arg(self, node: ast.arg):
        """Visit function arguments."""
        if node.annotation:
            old_in_annotation = self.in_annotation
            self.in_annotation = True
            self.visit(node.annotation)
            self.in_annotation = old_in_annotation

    def visit_Name(self, node: ast.Name):
        """Check name usage in annotations."""
        self.generic_visit(node)
