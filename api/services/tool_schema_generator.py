"""OpenAI Function Calling Schema Generator

This module provides functionality to convert Python tool functions with docstrings
into OpenAI function calling schema format.
"""

import inspect
from collections.abc import Callable
from typing import Any, get_type_hints


def generate_schema(func: Callable) -> dict[str, Any]:
    """Generate OpenAI function calling schema for a Python function."""
    sig = inspect.signature(func)

    # Extract description from docstring
    docstring = inspect.getdoc(func) or f"Function {func.__name__}"
    description = docstring.split("\n")[0].strip()

    # Get type hints
    try:
        type_hints = get_type_hints(func)
    except (NameError, AttributeError):
        type_hints = {}

    # Build parameters schema
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue

        if param.default is param.empty:
            required.append(param_name)

        param_type = type_hints.get(param_name)
        schema_type = "string"

        if param_type:
            if param_type == int:
                schema_type = "integer"
            elif param_type == float:
                schema_type = "number"
            elif param_type == bool:
                schema_type = "boolean"

        properties[param_name] = {"type": schema_type, "description": f"Parameter {param_name}"}

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }
