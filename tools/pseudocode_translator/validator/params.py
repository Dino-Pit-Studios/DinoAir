"""
Parameter classes for validator methods to reduce argument count complexity.

This module defines data classes that group related parameters together,
improving code readability and reducing method argument counts.
"""

from dataclasses import dataclass


@dataclass
class IndentationContext:
    """Context for indentation validation methods."""

    stripped: str
    indent: int
    indent_stack: list[int]
    line: str
    lines: list[str]
    line_num: int


@dataclass
class ErrorFormatContext:
    """Context for formatting validation errors."""

    message: str
    line_text: str
    line_no: int
    all_lines: list[str]
    suggestions: list[str]


@dataclass
class ValidationContext:
    """General context for validation operations."""

    code: str
    tree: object = None  # ast.AST
    lines: list[str] = None

    def __post_init__(self):
        if self.lines is None:
            self.lines = self.code.split("\n")
