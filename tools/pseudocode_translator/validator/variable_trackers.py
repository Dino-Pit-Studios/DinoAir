"""
Variable tracking and undefined variable detection.

This module provides AST visitors for tracking variable definitions
and usage across different scopes.
"""

import ast
import contextlib
from collections.abc import Iterable

from .scope import Scope


class UndefinedVariableChecker(ast.NodeVisitor):
    """AST visitor for tracking undefined variables across different scopes."""

    def __init__(self):
        self.current_scope: Scope = Scope("module")
        # Stable reference to the module scope
        self.module_scope: Scope = self.current_scope
        # We will append (name, line) or (name, line, col)
        self.undefined_names: list[tuple[str, int] | tuple[str, int, int | None]] = []
        self.defined_names: set[str] = set()
        self.in_annotation = False
        # Suppression counters and state
        self._suppress_loads: int = 0
        self._inside_comprehension: int = 0

    def visit_Module(self, node: ast.Module):
        """Process module-level code."""
        # Process imports first to ensure they're available throughout
        for child in node.body:
            if isinstance(child, ast.Import | ast.ImportFrom):
                self.visit(child)

        # Then process the rest
        for child in node.body:
            if not isinstance(child, ast.Import | ast.ImportFrom):
                self.visit(child)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Handle function definitions and their scopes."""
        # Define function name in current scope
        self.current_scope.define(node.name, node.lineno)
        self.defined_names.add(node.name)

        # Visit decorators in current scope
        for decorator in node.decorator_list:
            self.visit(decorator)

        # Create new scope for function body
        func_scope = Scope(f"function:{node.name}", self.current_scope)
        old_scope = self.current_scope
        self.current_scope = func_scope

        # Add function parameters to the function scope
        for arg in node.args.args:
            func_scope.define(arg.arg, node.lineno)
            self.defined_names.add(arg.arg)
        for arg in node.args.posonlyargs:
            func_scope.define(arg.arg, node.lineno)
            self.defined_names.add(arg.arg)
        for arg in node.args.kwonlyargs:
            func_scope.define(arg.arg, node.lineno)
            self.defined_names.add(arg.arg)
        if node.args.vararg:
            func_scope.define(node.args.vararg.arg, node.lineno)
            self.defined_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            func_scope.define(node.args.kwarg.arg, node.lineno)
            self.defined_names.add(node.args.kwarg.arg)

        # Visit parameter defaults in parent scope
        self.current_scope = old_scope
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default:
                self.visit(default)

        # Visit return annotation in function scope
        self.current_scope = func_scope
        if node.returns:
            old_in_annotation = self.in_annotation
            self.in_annotation = True
            self.visit(node.returns)
            self.in_annotation = old_in_annotation

        # Visit parameter annotations in function scope
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            if arg.annotation:
                old_in_annotation = self.in_annotation
                self.in_annotation = True
                self.visit(arg.annotation)
                self.in_annotation = old_in_annotation

        # Visit function body
        for stmt in node.body:
            self.visit(stmt)

        # Restore parent scope
        self.current_scope = old_scope

    def visit_ClassDef(self, node: ast.ClassDef):
        """Handle class definitions and their scopes."""
        # Define class name in current scope
        self.current_scope.define(node.name, node.lineno)
        self.defined_names.add(node.name)

        # Visit decorators in current scope
        for decorator in node.decorator_list:
            self.visit(decorator)

        # Visit base classes and keywords in parent (current) scope
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)

        # Create new scope for class body; resolve against module scope
        class_scope = Scope(f"class:{node.name}", parent=self._module_scope())
        old_scope = self.current_scope
        self.current_scope = class_scope

        # Visit class body
        for stmt in node.body:
            self.visit(stmt)

        # Restore parent scope
        self.current_scope = old_scope

    def visit_Import(self, node: ast.Import):
        """Handle import statements."""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name.split(".")[0]
            self.current_scope.define(name, node.lineno)
            self.defined_names.add(name)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Handle from...import statements."""
        for alias in node.names:
            if alias.name == "*":
                # Record star import policy on module scope
                self._module_scope().star_import_present = True
                continue
            name = alias.asname if alias.asname else alias.name
            self.current_scope.define(name, node.lineno)
            self.defined_names.add(name)

    def visit_Assign(self, node: ast.Assign):
        """Handle variable assignments."""
        # Visit the value first
        self.visit(node.value)

        # Then define the targets
        for target in node.targets:
            self._define_names(target, node.lineno)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        """Handle annotated assignments."""
        # Visit annotation
        if node.annotation:
            old_in_annotation = self.in_annotation
            self.in_annotation = True
            self.visit(node.annotation)
            self.in_annotation = old_in_annotation

        # Visit value if present
        if node.value:
            self.visit(node.value)

        # Define the target
        if isinstance(node.target, ast.Name):
            self.current_scope.define(node.target.id, node.lineno)
            self.defined_names.add(node.target.id)

    def visit_AugAssign(self, node: ast.AugAssign):
        """Handle augmented assignments (+=, -=, etc.)."""
        # Visit value first
        self.visit(node.value)

        # Target must be previously defined; do not bind new names here
        if isinstance(node.target, ast.Name):
            if not self.current_scope.is_defined(node.target.id, node.lineno):
                self.undefined_names.append(
                    (node.target.id, node.lineno, getattr(node, "col_offset", None))
                )
        else:
            # Suppress loads while visiting complex target
            self._suppress_loads += 1
            try:
                self.visit(node.target)
            finally:
                self._suppress_loads -= 1

    def visit_Name(self, node: ast.Name):
        """Handle name references."""
        if isinstance(node.ctx, ast.Load) and not self.in_annotation:
            if self._suppress_loads == 0 and not self.current_scope.is_defined(
                node.id, node.lineno
            ):
                self.undefined_names.append(
                    (node.id, node.lineno, getattr(node, "col_offset", None))
                )
        elif isinstance(node.ctx, ast.Store):
            # Respect global/nonlocal bindings
            if node.id in self.current_scope.global_vars:
                self._module_scope().define(node.id, node.lineno)
                self.defined_names.add(node.id)
            elif node.id in self.current_scope.nonlocal_vars:
                scope = self._nearest_enclosing_function_scope() or self.current_scope
                scope.define(node.id, node.lineno)
                self.defined_names.add(node.id)
            else:
                self.current_scope.define(node.id, node.lineno)
                self.defined_names.add(node.id)
        # Del handled by visit_Delete

    def visit_For(self, node: ast.For):
        """Handle for loop variable definitions."""
        # Visit iter first
        self.visit(node.iter)

        # Define loop variables
        self._define_names(node.target, node.lineno)

        # Visit body and orelse
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_With(self, node: ast.With):
        """Handle with statement variable definitions."""
        for item in node.items:
            # Visit context expression
            self.visit(item.context_expr)

            # Define optional variable
            if item.optional_vars:
                self._define_names(item.optional_vars, node.lineno)

        # Visit body
        for stmt in node.body:
            self.visit(stmt)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        """Handle exception handler variable definitions."""
        # Visit exception type
        if node.type:
            self.visit(node.type)

        temp_name = None
        # Define exception variable temporarily
        if node.name:
            temp_name = node.name
            self.current_scope.define(temp_name, node.lineno)
            self.defined_names.add(temp_name)

        # Visit body
        for stmt in node.body:
            self.visit(stmt)

        # Remove the temporary exception variable with tombstone
        if temp_name:
            self.current_scope.remove_definition(temp_name, node.lineno)

    def _define_names(self, node: ast.AST, line_no: int, target_scope: Scope | None = None):
        """Helper to define names from assignment targets."""
        scope = target_scope or self.current_scope
        if isinstance(node, ast.Name):
            scope.define(node.id, line_no)
            self.defined_names.add(node.id)
        elif isinstance(node, ast.Tuple | ast.List):
            for elt in node.elts:
                self._define_names(elt, line_no, target_scope=scope)
        elif isinstance(node, ast.Starred):
            self._define_names(node.value, line_no, target_scope=scope)
        # Other assignment target types (attributes/subscripts) do not create new bindings

    # ---- New visitors and helpers ----

    def visit_Lambda(self, node: ast.Lambda):
        """Handle lambda: defaults in parent, params in lambda scope, body in lambda scope."""
        # Visit defaults in parent scope
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default:
                self.visit(default)

        # Create lambda scope
        lambda_scope = Scope("lambda", self.current_scope)
        old_scope = self.current_scope
        self.current_scope = lambda_scope

        # Bind parameters
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            self.current_scope.define(arg.arg, node.lineno)
            self.defined_names.add(arg.arg)
        if node.args.vararg:
            self.current_scope.define(node.args.vararg.arg, node.lineno)
            self.defined_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            self.current_scope.define(node.args.kwarg.arg, node.lineno)
            self.defined_names.add(node.args.kwarg.arg)

        # Visit body
        self.visit(node.body)

        # Restore
        self.current_scope = old_scope

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Mirror FunctionDef for async functions."""
        # Define function name in current scope
        self.current_scope.define(node.name, node.lineno)
        self.defined_names.add(node.name)

        # Visit decorators in current scope
        for decorator in node.decorator_list:
            self.visit(decorator)

        # Create new scope for function body
        func_scope = Scope(f"function:{node.name}", self.current_scope)
        old_scope = self.current_scope
        self.current_scope = func_scope

        # Bind parameters
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            func_scope.define(arg.arg, node.lineno)
            self.defined_names.add(arg.arg)
        if node.args.vararg:
            func_scope.define(node.args.vararg.arg, node.lineno)
            self.defined_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            func_scope.define(node.args.kwarg.arg, node.lineno)
            self.defined_names.add(node.args.kwarg.arg)

        # Visit parameter defaults in parent scope
        self.current_scope = old_scope
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default:
                self.visit(default)

        # Visit return annotation and parameter annotations in function scope
        self.current_scope = func_scope
        if node.returns:
            old_in_annotation = self.in_annotation
            self.in_annotation = True
            self.visit(node.returns)
            self.in_annotation = old_in_annotation

        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            if arg.annotation:
                old_in_annotation = self.in_annotation
                self.in_annotation = True
                self.visit(arg.annotation)
                self.in_annotation = old_in_annotation

        # Visit body
        for stmt in node.body:
            self.visit(stmt)

        # Restore parent scope
        self.current_scope = old_scope

    # Comprehensions
    def _visit_comprehension(self, generators: list[ast.comprehension], body_visit, line_no: int):
        """Visit a comprehension with a dedicated scope."""
        old_scope = self.current_scope
        comp_scope = Scope("comprehension", old_scope)
        self._inside_comprehension += 1
        try:
            for gen in generators:
                # iter is evaluated in the parent scope
                self.current_scope = old_scope
                self.visit(gen.iter)
                # bind target and evaluate ifs in the comprehension scope
                self.current_scope = comp_scope
                self._define_names(gen.target, line_no, target_scope=comp_scope)
                for if_clause in gen.ifs:
                    self.visit(if_clause)
            # visit the body in the comprehension scope
            self.current_scope = comp_scope
            body_visit()
        finally:
            self.current_scope = old_scope
            self._inside_comprehension -= 1

    def visit_ListComp(self, node: ast.ListComp):
        self._visit_comprehension(node.generators, lambda: self.visit(node.elt), node.lineno)

    def visit_SetComp(self, node: ast.SetComp):
        self._visit_comprehension(node.generators, lambda: self.visit(node.elt), node.lineno)

    def visit_DictComp(self, node: ast.DictComp):
        self._visit_comprehension(
            node.generators,
            lambda: (self.visit(node.key), self.visit(node.value)),
            node.lineno,
        )

    def visit_GeneratorExp(self, node: ast.GeneratorExp):
        self._visit_comprehension(node.generators, lambda: self.visit(node.elt), node.lineno)

    def visit_NamedExpr(self, node: ast.NamedExpr):
        """Walrus operator: visit value, then bind target in current (possibly comp) scope."""
        self.visit(node.value)
        self._define_names(node.target, node.lineno)

    def visit_Global(self, node: ast.Global):
        for name in node.names:
            self.current_scope.global_vars.add(name)

    def visit_Nonlocal(self, node: ast.Nonlocal):
        for name in node.names:
            self.current_scope.nonlocal_vars.add(name)

    def visit_Delete(self, node: ast.Delete):
        for target in node.targets:
            for name in self._iter_delete_names(target):
                self.current_scope.mark_deleted(name, node.lineno)

    def _iter_delete_names(self, node: ast.AST) -> Iterable[str]:
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Tuple | ast.List):
            for elt in node.elts:
                yield from self._iter_delete_names(elt)
        elif isinstance(node, ast.Starred):
            yield from self._iter_delete_names(node.value)
        # ignore attributes and subscripts per deletion policy

    def visit_AsyncFor(self, node: ast.AsyncFor):
        """Mirror For for async for-loops."""
        self.visit(node.iter)
        self._define_names(node.target, node.lineno)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_AsyncWith(self, node: ast.AsyncWith):
        """Mirror With for async with-statements."""
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self._define_names(item.optional_vars, node.lineno)
        for stmt in node.body:
            self.visit(stmt)

    # Structural pattern matching (Python 3.10+)
    def visit_Match(self, node: ast.Match):
        self.visit(node.subject)
        for case in node.cases:
            bound = self._collect_pattern_binds(case.pattern)
            with self._temporarily_defined(bound, getattr(case.pattern, "lineno", node.lineno)):
                if case.guard:
                    self.visit(case.guard)
                for stmt in case.body:
                    self.visit(stmt)

    def _collect_pattern_binds(self, pattern: ast.AST) -> set[str]:
        for pat_type, handler in (
            (ast.MatchAs, self._bind_match_as),
            (ast.MatchStar, self._bind_match_star),
            (ast.MatchOr, self._bind_match_or),
            (ast.MatchSequence, self._bind_match_sequence),
            (ast.MatchMapping, self._bind_match_mapping),
            (ast.MatchClass, self._bind_match_class),
        ):
            if isinstance(pattern, pat_type):
                return handler(pattern)
        return set()

    def _bind_match_as(self, pattern: ast.MatchAs) -> set[str]:
        """Bind names in 'as' pattern and return set of bound names."""
        names: set[str] = set()
        if pattern.name:
            names.add(pattern.name)
        if pattern.pattern:
            names.update(self._collect_pattern_binds(pattern.pattern))
        return names

    def _bind_match_star(self, pattern: ast.MatchStar) -> set[str]:
        """Bind the star variable in pattern matching, returning its name if present."""
        return {pattern.name} if pattern.name else set()

    def _bind_match_or(self, pattern: ast.MatchOr) -> set[str]:
        """Bind names common to all alternatives in 'or' pattern."""
        alts = [self._collect_pattern_binds(p) for p in pattern.patterns]
        if not alts:
            return set()
        common = set(alts[0])
        for a in alts[1:]:
            common &= a
        return common

    def _bind_match_sequence(self, pattern: ast.MatchSequence) -> set[str]:
        """Bind names in sequence patterns by collecting names from all subpatterns."""
        names: set[str] = set()
        for p in pattern.patterns:
            names.update(self._collect_pattern_binds(p))
        return names

    def _bind_match_mapping(self, pattern: ast.MatchMapping) -> set[str]:
        """Bind names in mapping patterns, including rest variable if present."""
        names: set[str] = set()
        for p in pattern.patterns:
            names.update(self._collect_pattern_binds(p))
        if pattern.rest:
            names.add(pattern.rest)
        return names

    def _bind_match_class(self, pattern: ast.MatchClass) -> set[str]:
        """Bind names in class patterns by collecting names from positional and keyword patterns."""
        names: set[str] = set()
        for p in pattern.patterns:
            names.update(self._collect_pattern_binds(p))
        for p in pattern.kwd_patterns:
            names.update(self._collect_pattern_binds(p))
        return names

    @contextlib.contextmanager
    def _temporarily_defined(self, names: Iterable[str], line_no: int):
        defined_now = []
        try:
            for n in names:
                self.current_scope.define(n, line_no)
                self.defined_names.add(n)
                defined_now.append(n)
            yield
        finally:
            for n in defined_now:
                self.current_scope.remove_definition(n, line_no)

    def _module_scope(self) -> Scope:
        scope = self.current_scope
        while scope.parent:
            scope = scope.parent
        return scope

    def _nearest_enclosing_function_scope(self) -> Scope | None:
        scope = self.current_scope
        while scope:
            if scope.name.startswith("function:"):
                return scope
            scope = scope.parent
        return None


class VariableScopeAnalyzer(ast.NodeVisitor):
    """Analyze variable scope usage patterns."""

    def __init__(self):
        self.issues: list[str] = []
        self.current_function = None
        self.local_vars = set()
        self.nonlocal_vars = set()
        self.global_vars = set()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Analyze function scope."""
        old_function = self.current_function
        old_locals = self.local_vars.copy()
        old_nonlocals = self.nonlocal_vars.copy()
        old_globals = self.global_vars.copy()

        self.current_function = node.name
        self.local_vars.clear()
        self.nonlocal_vars.clear()
        self.global_vars.clear()

        # Add parameters to locals
        for arg in node.args.args:
            self.local_vars.add(arg.arg)

        self.generic_visit(node)

        # Restore previous state
        self.current_function = old_function
        self.local_vars = old_locals
        self.nonlocal_vars = old_nonlocals
        self.global_vars = old_globals

    def visit_Global(self, node: ast.Global):
        """Track global declarations."""
        for name in node.names:
            self.global_vars.add(name)
            if self.current_function:
                self.issues.append(
                    f"Global variable '{name}' used in function '{self.current_function}' at line {node.lineno}"
                )

    def visit_Nonlocal(self, node: ast.Nonlocal):
        """Track nonlocal declarations."""
        for name in node.names:
            self.nonlocal_vars.add(name)

    def visit_Name(self, node: ast.Name):
        """Track variable usage."""
        if isinstance(node.ctx, ast.Store) and self.current_function:
            self.local_vars.add(node.id)
        self.generic_visit(node)
