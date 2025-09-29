"""OpenAI Function Calling Schema Generator for DinoAir Tools

This module provides utilities to generate OpenAI function calling schemas
from Python functions with properly formatted docstrings.
"""

import inspect
import re
from collections.abc import Callable
from typing import Any


def extract_docstring_info(func: Callable[..., Any]) -> dict[str, Any]:
    """Extract parameter information from function docstring.

    Args:
        func: Function to extract docstring info from

    Returns:
        dict: Parsed parameter information including descriptions and types
    """
    docstring = func.__doc__ or ""
    lines = docstring.strip().split("\n")

    desc_lines: list[str] = []
    params: dict[str, dict[str, str]] = {}
    in_args = False

    for line in lines:
        stripped = line.strip()

        if stripped.lower().startswith("args:"):
            in_args = True
            continue
        if stripped.lower().startswith(
            (
                "returns:",
                "return:",
                "yields:",
                "yield:",
                "raises:",
                "note:",
                "notes:",
                "example:",
                "examples:",
            )
        ):
            in_args = False
            continue

        if in_args and stripped and (match := re.match(r"^(\w+)\s*\([^)]*\):\s*(.+)$", stripped)):
            name, type_str, desc = match.groups()
            params[name] = {"type": type_str.strip(), "description": desc.strip()}
        elif not in_args and stripped:
            desc_lines.append(stripped)

    description = " ".join(desc_lines)

    return {"description": description, "parameters": params}


def generate_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Generate OpenAI function calling schema for a function.

    Args:
        func: Function to generate schema for

    Returns:
        dict: OpenAI-compatible function schema
    """
    sig = inspect.signature(func)
    doc_info = extract_docstring_info(func)

    properties: dict[str, dict[str, str]] = {}
    required: list[str] = []

    try:
        for name, param in sig.parameters.items():
            param_info = {"type": "string"}  # Default type

            if name in doc_info["parameters"]:
                info = doc_info["parameters"][name]
                param_info |= info

            properties[name] = param_info

            if param.default is param.empty:
                required.append(name)

    except Exception:
        # Fallback if signature inspection fails
        for name, info in doc_info["parameters"].items():
            properties[name] = info
            required.append(name)

    return {
        "name": func.__name__,
        "description": doc_info["description"] or f"Call the {func.__name__} function",
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


class ToolRegistry:
    """Simple tool registry stub for now."""

    def __init__(self) -> None:
        """Initialize an empty internal tool registry."""
        self._tools: dict[str, Callable[..., Any]] = {}

    @staticmethod
    def get_tool_schemas(requested_tools: list[str] | None = None) -> list[dict[str, Any]]:
        """Return empty tool schemas for now."""
        return []


def get_tool_registry() -> ToolRegistry:
    """Get the tool registry instance."""
    return ToolRegistry()
