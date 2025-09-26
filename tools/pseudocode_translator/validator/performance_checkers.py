"""
Performance analysis and optimization suggestions.

This module provides AST visitors for detecting performance issues
and suggesting optimizations.
"""

import ast


class PerformanceChecker(ast.NodeVisitor):
    """AST visitor for detecting performance issues."""

    def __init__(self):
        self.in_loop = False
        self.append_calls_in_loops: list[tuple[str, int]] = []
        self.suggestions: list[str] = []

    def visit_For(self, node: ast.For):
        """Check for performance issues in for loops."""
        # Check for range(len()) pattern
        self._check_range_len_pattern(node)

        # Track that we're in a loop for append detection
        old_in_loop = self.in_loop
        self.in_loop = True
        self.generic_visit(node)
        self.in_loop = old_in_loop

    def visit_While(self, node: ast.While):
        """Track while loops for performance checks."""
        old_in_loop = self.in_loop
        self.in_loop = True
        self.generic_visit(node)
        self.in_loop = old_in_loop

    def visit_ListComp(self, node: ast.ListComp):
        """List comprehensions are generally performant."""
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Check function calls for performance issues."""
        # Check for repeated append in loops
        if isinstance(node.func, ast.Attribute) and node.func.attr == "append" and self.in_loop:
            # Track append calls in loops
            obj = node.func.value
            if isinstance(obj, ast.Name):
                list_name = obj.id
                self.append_calls_in_loops.append((list_name, node.lineno))

        # Check for inefficient string concatenation
        # "".join()
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
            and isinstance(node.func.value, ast.Constant)
            and isinstance(node.func.value.value, str)
            and node.func.value.value == ""
        ):
            self.suggestions.append(
                f"Good use of join() for string concatenation at line {node.lineno}"
            )

        self.generic_visit(node)

    def _check_range_len_pattern(self, node: ast.For):
        """Check for range(len()) anti-pattern."""
        if (
            isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
            and node.iter.args
            and isinstance(node.iter.args[0], ast.Call)
            and isinstance(node.iter.args[0].func, ast.Name)
            and node.iter.args[0].func.id == "len"
        ):
            self.suggestions.append(
                f"Use enumerate() instead of range(len()) at line {node.lineno}"
            )

    def visit_BinOp(self, node: ast.BinOp):
        """Check binary operations for performance issues."""
        # Check for string concatenation in loops
        if (
            isinstance(node.op, ast.Add)
            and self.in_loop
            and self._involves_string_concatenation(node)
        ):
            self.suggestions.append(
                f"Avoid string concatenation in loops at line {node.lineno} - use list and join()"
            )

        self.generic_visit(node)

    def _involves_string_concatenation(self, node: ast.BinOp) -> bool:
        """Check if binary operation involves string concatenation."""
        # Simple heuristic: if either operand is a string constant
        left_is_str = isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)
        right_is_str = isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)
        return left_is_str or right_is_str


class MemoryChecker(ast.NodeVisitor):
    """Check for memory usage patterns."""

    def __init__(self):
        self.suggestions: list[str] = []
        self.large_data_structures = []

    def visit_List(self, node: ast.List):
        """Check list creation patterns."""
        if len(node.elts) > 100:
            self.suggestions.append(
                f"Large list literal at line {node.lineno} - consider using a generator or loading from file"
            )

        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict):
        """Check dictionary creation patterns."""
        if len(node.keys) > 50:
            self.suggestions.append(
                f"Large dictionary literal at line {node.lineno} - consider using a more efficient data structure"
            )

        self.generic_visit(node)

    def visit_SetComp(self, node: ast.SetComp):
        """Set comprehensions are generally efficient."""
        self.generic_visit(node)

    def visit_DictComp(self, node: ast.DictComp):
        """Dictionary comprehensions are generally efficient."""
        self.generic_visit(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp):
        """Generator expressions are memory efficient."""
        self.suggestions.append(f"Good use of generator expression at line {node.lineno}")
        self.generic_visit(node)


class AlgorithmicComplexityChecker(ast.NodeVisitor):
    """Check for algorithmic complexity issues."""

    def __init__(self):
        self.suggestions: list[str] = []
        self.nested_loops = 0

    def visit_For(self, node: ast.For):
        """Track nested loops for complexity analysis."""
        self.nested_loops += 1

        if self.nested_loops > 2:
            self.suggestions.append(
                f"Deeply nested loops at line {node.lineno} - consider algorithmic optimization"
            )

        self.generic_visit(node)
        self.nested_loops -= 1

    def visit_While(self, node: ast.While):
        """Track nested while loops."""
        self.nested_loops += 1

        if self.nested_loops > 2:
            self.suggestions.append(
                f"Deeply nested loops at line {node.lineno} - consider algorithmic optimization"
            )

        self.generic_visit(node)
        self.nested_loops -= 1

    def visit_Call(self, node: ast.Call):
        """Check function calls for complexity issues."""
        # Check for expensive operations in loops
        if (
            self.nested_loops > 0
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ["sort", "sorted", "reverse"]
        ):
            self.suggestions.append(
                f"Expensive operation '{node.func.attr}' in loop at line {node.lineno} - consider moving outside loop"
            )

        self.generic_visit(node)


class DataStructureChecker(ast.NodeVisitor):
    """Check for appropriate data structure usage."""

    def __init__(self):
        self.suggestions: list[str] = []

    def visit_Call(self, node: ast.Call):
        """Check function calls for data structure optimization."""
        # Check for list.count() in conditions (suggests set might be better)
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "count"
            and isinstance(node.func.value, ast.Name)
        ):
            self.suggestions.append(
                f"Using list.count() at line {node.lineno} - consider using 'in' operator or set for membership testing"
            )

        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare):
        """Check comparison patterns."""
        # Check for x in list (where list is large) - suggest set
        for op, right in zip(node.ops, node.comparators, strict=False):
            if isinstance(op, ast.In) and isinstance(right, ast.List) and len(right.elts) > 10:
                self.suggestions.append(
                    f"'in' operation on large list at line {node.lineno} - consider using set for O(1) lookup"
                )

        self.generic_visit(node)
