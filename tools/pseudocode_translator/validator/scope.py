"""
Scope management for variable tracking in code validation.

This module contains the Scope class which is used to track variable
definitions and usage across different code scopes (module, function, class, etc.).
"""

from typing import Optional


class Scope:
    """Represents a scope in the code for undefined variable tracking"""

    def __init__(self, name: str, parent: Optional["Scope"] = None):
        self.name = name
        self.parent = parent
        self.defined: dict[str, int] = {}  # name -> last line defined
        self.used: dict[str, list[int]] = {}  # name -> lines used
        self.imported: set[str] = set()
        self.nonlocal_vars: set[str] = set()
        self.global_vars: set[str] = set()
        # Deletion tombstones (name -> deletion line)
        self.deleted: dict[str, int] = {}
        # Whether a star-import was present in the module (suppresses undefined-name reliability)
        self.star_import_present: bool = False

    def define(self, name: str, line: int):
        """Mark a variable as defined in this scope"""
        # Always record the latest definition line
        self.defined[name] = line

    def use(self, name: str, line: int):
        """Mark a variable as used in this scope"""
        if name not in self.used:
            self.used[name] = []
        self.used[name].append(line)

    def is_defined(self, name: str, line: int) -> bool:
        """Check if a name is defined at a given line"""
        # Check if it's a global or nonlocal declaration
        if name in self.global_vars:
            return self._check_global(name, line)
        if name in self.nonlocal_vars:
            return self._check_nonlocal(name, line)

        # Respect explicit deletions (tombstones)
        if name in self.deleted and self.deleted[name] <= line:
            # Only considered defined if there is a strictly later redefinition that
            # also occurs before or at the query line.
            if not (
                name in self.defined
                and self.defined[name] > self.deleted[name]
                and self.defined[name] <= line
            ):
                return False

        # Check local scope
        if name in self.defined and self.defined[name] <= line:
            return True
        if name in self.imported:
            return True

        # Check parent scopes; class scopes resolve against module scope
        if self.parent:
            if self.name.startswith("class:"):
                return self.nearest_module().is_defined(name, line)
            return self.parent.is_defined(name, line)

        return False

    def _check_global(self, name: str, line: int) -> bool:
        """Check if a global variable is defined"""
        scope = self
        while scope.parent:
            scope = scope.parent
        return name in scope.defined and scope.defined[name] <= line

    def _check_nonlocal(self, name: str, line: int) -> bool:
        """Check if nonlocal variable is defined in enclosing scope"""
        scope = self.parent
        while scope:
            if name in scope.defined and scope.defined[name] <= line:
                return True
            scope = scope.parent
        return False

    # ---- New helpers ----
    def remove_definition(self, name: str, line: int | None = None):
        """Remove a definition; optionally record deletion tombstone at given line."""
        if name in self.defined:
            del self.defined[name]
        if line is not None:
            self.deleted[name] = line

    def mark_deleted(self, name: str, line: int):
        """Record deletion tombstone and clear earlier definition if not after deletion."""
        self.deleted[name] = line
        if name in self.defined and self.defined[name] <= line:
            del self.defined[name]

    def nearest_module(self) -> "Scope":
        """Return the outermost (module) scope."""
        scope = self
        while scope.parent:
            scope = scope.parent
        return scope
