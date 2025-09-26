"""
Constants and static data for the validator module.

This module contains all constant data used throughout the validator,
helping to reduce complexity and improve maintainability.
"""

# Python builtin names and common typing imports
PYTHON_BUILTINS = {
    # Standard builtin attributes
    "self",
    "cls",
    "__name__",
    "__file__",
    "__doc__",
    "__package__",
    "__loader__",
    "__spec__",
    "__annotations__",
    "__cached__",
}

# Common typing module imports
TYPING_NAMES = {
    "Union",
    "Optional",
    "List",
    "Dict",
    "Tuple",
    "Set",
    "FrozenSet",
    "Type",
    "Callable",
    "Any",
    "TypeVar",
    "Generic",
    "Protocol",
    "Literal",
    "Final",
    "TypedDict",
    "NotRequired",
    "Required",
    "Annotated",
    "TypeAlias",
    "ParamSpec",
    "TypeVarTuple",
    "Unpack",
    "Self",
    "Never",
    "assert_type",
    "assert_never",
    "reveal_type",
}

# Modules considered unsafe for code execution
UNSAFE_MODULES = {
    "os",
    "subprocess",
    "shutil",
    "sys",
    "__builtin__",
    "__builtins__",
    "imp",
    "importlib",
    "marshal",
    "pickle",
    "cPickle",
    "eval",
    "exec",
    "compile",
}


def get_builtin_names() -> set[str]:
    """
    Get a comprehensive set of builtin and common names for validation.

    Returns:
        Set of builtin names that should not be flagged as undefined
    """
    builtin_names: set[str] = set(dir(__builtins__))
    builtin_names.update(PYTHON_BUILTINS)
    builtin_names.update(TYPING_NAMES)
    return builtin_names
