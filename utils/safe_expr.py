"""
Safe boolean expression evaluator for rule/alert evaluation.

This module parses and validates a restricted Python expression AST and evaluates
it against a supplied variables mapping. It is designed to replace any eval/exec
usage in application code.

Supported:
- Literals: bool, int, float, str, None
- Names: must exist in the provided variables dict
- Boolean ops: and, or
- Unary ops: not
- Comparisons: ==, !=, <, <=, >, >=, in, not in
- Arithmetic (optional use in thresholds): +, -, *, /, %, // on numbers
- Parentheses for grouping

Not supported and will raise ValidationError:
- Call, Attribute, Import, Lambda, Comprehensions, Subscript (see note below), Await, Yield, etc.

By default Subscript is disallowed to avoid dynamic indexing. If you need
whitelisted subscript access like variables['key'], consider extending the visitor
safely for very specific, non-user-controlled keys.

Example:
    from utils.safe_expr import evaluate_bool_expr, ValidationError

    variables = {
        "error_rate": 0.2,
        "is_healthy": False,
        "failed_checks": ["db", "gpu"],
        "env": "prod",
    }

    assert evaluate_bool_expr("not is_healthy or error_rate >= 0.1", variables) is True
    assert evaluate_bool_expr("'db' in failed_checks and env == 'prod'", variables) is True

Security notes:
- The expression length is capped to prevent abuse (default 1000 chars).
- All names must be present in 'variables' mapping; no implicit globals/builtins.

Tests (outline):
- function calls like __import__('os') raise ValidationError
- attribute access like foo.bar raises ValidationError
- subscript like a[0] raises ValidationError (default)
- arithmetic and comparisons work on numbers
"""

# Pylint: allow AST NodeVisitor visit_* naming and omit docstrings for visitor methods
# pylint: disable=invalid-name, missing-function-docstring

from __future__ import annotations

import ast
from typing import Any, cast


class ValidationError(ValueError):
    """Raised when an expression fails validation."""


_ALLOWED_BINOPS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.FloorDiv,
)

_ALLOWED_BOOL_OPS = (ast.And, ast.Or)

_ALLOWED_UNARY_OPS = (ast.Not,)

_ALLOWED_CMP_OPS = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
)


class _SafeExprValidator(ast.NodeVisitor):  # pylint: disable=invalid-name, missing-function-docstring
    """AST validator to enforce a restricted expression subset."""

    def __init__(self, variables: dict[str, Any]) -> None:
        self.variables = variables

    # Entry
    def visit_Expression(self, node: ast.Expression) -> Any:
        """Validate the top-level Expression node and its body."""
        return self.visit(node.body)

    # Literals
    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, bool | int | float | str | type(None)):
            return
        raise ValidationError(f"Unsupported constant type: {type(node.value).__name__}")

    # Names must come from variables
    def visit_Name(self, node: ast.Name) -> Any:
        if node.id not in self.variables:
            raise ValidationError(f"Unknown variable: {node.id}")
        if callable(self.variables[node.id]):
            raise ValidationError("Callable variables are not allowed")

    # BoolOp: and/or
    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if not isinstance(node.op, _ALLOWED_BOOL_OPS):
            raise ValidationError(f"Boolean operator not allowed: {type(node.op).__name__}")
        for v in node.values:
            self.visit(v)

    # Unary: not
    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        if not isinstance(node.op, _ALLOWED_UNARY_OPS):
            raise ValidationError(f"Unary operator not allowed: {type(node.op).__name__}")
        self.visit(node.operand)

    # Binary arithmetic (+ - * / % //)
    def visit_BinOp(self, node: ast.BinOp) -> Any:
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise ValidationError(f"Binary operator not allowed: {type(node.op).__name__}")
        self.visit(node.left)
        self.visit(node.right)

    # Comparisons with allowed operators
    def visit_Compare(self, node: ast.Compare) -> Any:
        self.visit(node.left)
        for op in node.ops:
            if not isinstance(op, _ALLOWED_CMP_OPS):
                raise ValidationError(f"Comparison operator not allowed: {type(op).__name__}")
        for comparator in node.comparators:
            self.visit(comparator)

    # Disallowed nodes
    def visit_Call(self, node: ast.Call) -> Any:
        if isinstance(node.func, ast.Attribute):
            raise ValidationError("Attribute access is not allowed")
        raise ValidationError("Function calls are not allowed")

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        raise ValidationError("Attribute access is not allowed")

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        raise ValidationError("Subscript access is not allowed")

    def visit_ListComp(self, node: ast.ListComp) -> Any:
        raise ValidationError("Comprehensions are not allowed")

    def visit_SetComp(self, node: ast.SetComp) -> Any:
        raise ValidationError("Comprehensions are not allowed")

    def visit_DictComp(self, node: ast.DictComp) -> Any:
        raise ValidationError("Comprehensions are not allowed")

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> Any:
        raise ValidationError("Comprehensions are not allowed")

    def generic_visit(self, node: ast.AST) -> Any:
        # Permit tuples and lists/sets/dicts as literal containers of allowed elements
        if isinstance(node, ast.Tuple | ast.List | ast.Set):
            for elt in getattr(node, "elts", []):
                self.visit(elt)
            return
        if isinstance(node, ast.Dict):
            keys = cast("list[ast.AST]", node.keys)
            values = cast("list[ast.AST]", node.values)
            for k in keys:
                self.visit(k)
            for v in values:
                self.visit(v)
            return

        # Whitelist certain benign nodes
        if isinstance(node, ast.Load):
            return

        # Fallback: reject anything not explicitly handled
        raise ValidationError(f"Disallowed expression element: {type(node).__name__}")


class _SafeExprEvaluator(ast.NodeVisitor):  # pylint: disable=invalid-name, missing-function-docstring
    """
    Safely evaluates a restricted Python expression AST, as validated by _SafeExprValidator.

    Security Model:
        - This evaluator never uses eval(), exec(), or any form of code execution.
        - It only traverses AST nodes that have been validated to be safe by _SafeExprValidator.
        - If an unsupported or unexpected node is encountered, a ValidationError is raised.
        - Only the provided variables are accessible; no builtins or global state.

    Supported Operations:
        - Literals: bool, int, float, str, None, tuples, lists, sets, dicts.
        - Variable names (must be present in the provided variables dict).
        - Boolean operations: and, or, not.
        - Arithmetic: +, -, *, /, %, //.
        - Comparisons: ==, !=, <, <=, >, >=, in, not in.
        - Container literals: tuple, list, set, dict.
        - No function calls, attribute access, or subscripting.

    Relationship to Validator:
        - This class assumes the AST has already been checked by _SafeExprValidator.
        - It will raise ValidationError if an unsupported node is encountered at runtime.
    """

    def __init__(self, variables: dict[str, Any]) -> None:
        self.variables = variables

    def visit_Expression(self, node: ast.Expression) -> Any:
        """Evaluate the top-level Expression node by visiting its body."""
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        return self.variables[node.id]

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            return all(self.visit(v) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(self.visit(v) for v in node.values)
        raise ValidationError(f"Unsupported boolean operator: {type(node.op).__name__}")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not operand
        raise ValidationError(f"Unsupported unary operator: {type(node.op).__name__}")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)

        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        raise ValidationError(f"Unsupported binary operator: {type(node.op).__name__}")

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)

        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = self.visit(comparator)

            if isinstance(op, ast.Eq):
                result = left == right
            elif isinstance(op, ast.NotEq):
                result = left != right
            elif isinstance(op, ast.Lt):
                result = left < right
            elif isinstance(op, ast.LtE):
                result = left <= right
            elif isinstance(op, ast.Gt):
                result = left > right
            elif isinstance(op, ast.GtE):
                result = left >= right
            elif isinstance(op, ast.In):
                result = left in right
            elif isinstance(op, ast.NotIn):
                result = left not in right
            else:
                raise ValidationError(f"Unsupported comparison operator: {type(op).__name__}")

            if not result:
                return False
            left = right  # For chained comparisons like a < b < c

        return True

    def visit_Tuple(self, node: ast.Tuple) -> Any:
        return tuple(self.visit(elt) for elt in node.elts)

    def visit_List(self, node: ast.List) -> Any:
        return [self.visit(elt) for elt in node.elts]

    def visit_Set(self, node: ast.Set) -> Any:
        return {self.visit(elt) for elt in node.elts}

    def visit_Dict(self, node: ast.Dict) -> Any:
        """
        Visit a dictionary AST node.

        Raises:
            ValueError: If a dictionary key is None. This prevents silent data loss.
        """
        # Typed to satisfy static checkers (keys/values are dynamic but safe by prior validation)
        result: dict[Any, Any] = {}
        for k, v in zip(node.keys, node.values, strict=False):
            if k is None:
                raise ValueError(
                    "Dictionary key is None (possibly from **kwargs "
                    "expansion); this is not allowed."
                )
            key = self.visit(k)
            value = self.visit(v)
            result[key] = value
        return result


def evaluate_bool_expr(expr: str, variables: dict[str, Any], max_length: int = 1000) -> bool:
    """Validate and evaluate a restricted boolean expression.

    Args:
        expr: The expression string to evaluate.
        variables: Mapping for variable names used in the expression.
        max_length: Maximum allowed expression length (default 1000).

    Returns:
        bool: The evaluated boolean result.

    Raises:
        ValidationError: If validation fails (unsupported nodes/operators, etc.).
        ValueError: If expression is empty or too long.
        TypeError: If the evaluated result is not a boolean.
    """
    if not expr.strip():
        raise ValueError("Expression must be a non-empty string")
    if len(expr) > max_length:
        raise ValueError(f"Expression exceeds maximum length of {max_length} characters")

    # Parse and validate AST
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValidationError(f"Invalid expression syntax: {e}") from e

    # Validate the AST contains only allowed nodes
    validator = _SafeExprValidator(variables)
    validator.visit(tree)

    # Evaluate safely using our custom AST evaluator (no eval() needed)
    evaluator = _SafeExprEvaluator(variables)
    result = evaluator.visit(tree)

    # Coerce truthiness to bool if it's a non-bool but truthy/falsy value
    if isinstance(result, bool):
        return result
    if isinstance(result, int | float | str | list | dict | set | tuple | type(None)):
        return bool(cast("object", result))

    # For any other type (unexpected), reject
    raise TypeError(
        f"Expression did not evaluate to a boolean-compatible value: {type(result).__name__}"
    )


__all__ = ["evaluate_bool_expr", "ValidationError"]
