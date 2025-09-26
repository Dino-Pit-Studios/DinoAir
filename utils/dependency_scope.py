"""
Dependency Scope Context Manager

This module provides the ScopeContext class for managing dependency scopes
in the dependency injection system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import TracebackType

    from dependency_container import DependencyContainer


class ScopeContext:
    """Context manager for dependency scopes."""

    def __init__(self, container: DependencyContainer, scope_name: str):
        self.container = container
        self.scope_name = scope_name
        self._previous_scope: str | None = None

    def __enter__(self) -> ScopeContext:
        # Use container accessors to avoid private attribute usage warnings
        self._previous_scope = self.container.get_current_scope()
        self.container.set_current_scope(self.scope_name)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.container.dispose_scope(self.scope_name)
        self.container.set_current_scope(self._previous_scope)
