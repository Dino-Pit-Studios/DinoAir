#!/usr/bin/env python3
"""
Manual docstring generation script for DinoAir project.

This script analyzes Python files and adds basic docstrings following Google style
for functions, classes, and modules that are missing documentation.
"""

import ast
import logging
import os
import re
from pathlib import Path
from typing import Any

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _has_module_docstring(tree: ast.AST) -> bool:
    """Check if the module AST has a docstring."""
    if not tree.body:
        return False
    first_node = tree.body[0]
    return (
        isinstance(first_node, ast.Expr)
        and isinstance(first_node.value, ast.Constant)
        and isinstance(first_node.value.value, str)
    )


def _get_missing_doc_nodes(tree: ast.AST) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return lists of classes and functions missing docstrings."""
    classes_without_docs: list[dict[str, Any]] = []
    functions_without_docs: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if ast.get_docstring(node) is None:
                classes_without_docs.append(
                    {"name": node.name, "lineno": node.lineno, "type": "class"}
                )
        elif isinstance(node, ast.FunctionDef):
            if ast.get_docstring(node) is None:
                functions_without_docs.append(
                    {"name": node.name, "lineno": node.lineno, "type": "function"}
                )
    return classes_without_docs, functions_without_docs


def find_files_missing_docstrings(directories: list[str]) -> list[dict[str, Any]]:
    """
    Find Python files with missing docstrings in specified directories.

    Args:
        directories: List of directory paths to scan

    Returns:
        List of dictionaries containing file info and missing docstring details
    """
    missing_docstrings: list[dict[str, Any]] = []

    for directory in directories:
        if not os.path.exists(directory):
            logger.warning("Directory %s does not exist, skipping...", directory)
            continue

        for py_file in Path(directory).rglob("*.py"):
            if py_file.name == "__init__.py":
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                tree = ast.parse(content)

                has_module_doc = _has_module_docstring(tree)
                classes_without_docs, functions_without_docs = _get_missing_doc_nodes(tree)

                if not has_module_doc or classes_without_docs or functions_without_docs:
                    missing_docstrings.append(
                        {
                            "file": str(py_file),
                            "missing_module_docstring": not has_module_doc,
                            "classes": classes_without_docs,
                            "functions": functions_without_docs,
                        }
                    )
            except Exception as e:
                logger.error("Error parsing %s: %s", py_file, e)

    return missing_docstrings


def generate_function_docstring(func_info: dict[str, Any]) -> str:
    """
    Generate a basic docstring for a function based on its signature.

    Args:
        func_info: Dictionary containing function information

    Returns:
        Generated docstring text
    """
    name = func_info["name"]
    args = func_info.get("args", [])
    has_return = func_info.get("returns", False)

    # Generate a basic description based on function name
    description = generate_description_from_name(name)

    docstring_parts = [f'    """{description}']

    # Add Args section if function has parameters
    if args and len(args) > 0:
        # Filter out 'self' and 'cls'
        filtered_args = [arg for arg in args if arg not in ["self", "cls"]]
        if filtered_args:
            docstring_parts.append("    ")
            docstring_parts.append("    Args:")
            for arg in filtered_args:
                docstring_parts.append(f"        {arg}: TODO: Add description")

    # Add Returns section if function has return annotation
    if has_return:
        if args and len([arg for arg in args if arg not in ["self", "cls"]]) > 0:
            docstring_parts.append("        ")
        else:
            docstring_parts.append("    ")
        docstring_parts.append("    Returns:")
        docstring_parts.append("        TODO: Add return description")

    docstring_parts.append('    """')

    return "\n".join(docstring_parts)


def generate_class_docstring(class_info: dict[str, Any]) -> str:
    """
    Generate a basic docstring for a class.

    Args:
        class_info: Dictionary containing class information

    Returns:
        Generated docstring text
    """
    name = class_info["name"]
    description = generate_description_from_name(name)

    return f'    """{description}"""'


def generate_description_from_name(name: str) -> str:
    """
    Generate a description based on a function or class name.

    Args:
        name: The function or class name

    Returns:
        Generated description
    """
    # Convert camelCase and snake_case to readable text
    # Split on capital letters and underscores
    words = re.sub(r"([A-Z])", r" \1", name).replace("_", " ").strip().split()

    templates = {
        "get_": "Get {}.",
        "set_": "Set {}.",
        "create_": "Create {}.",
        "delete_": "Delete {}.",
        "update_": "Update {}.",
        "load_": "Load {}.",
        "save_": "Save {}.",
        "parse_": "Parse {}.",
        "validate_": "Validate {}.",
        "process_": "Process {}.",
        "handle_": "Handle {}.",
        "is_": "Check if {}.",
        "has_": "Check if has {}.",
        "can_": "Check if can {}.",
        "should_": "Check if should {}.",
    }

    for prefix, template in templates.items():
        if name.startswith(prefix):
            rest = " ".join(words[1:]).lower()
            return template.format(rest)

    # Capitalize first word and add period
    words = [w.lower() for w in words]
    if words:
        words[0] = words[0].capitalize()
        return f"{' '.join(words)}."
    return "TODO: Add description."


def add_docstrings_to_file(file_path: str, file_info: dict[str, Any]) -> bool:
    """
    Add docstrings to functions and classes in a specific file.

    Args:
        file_path: Path to the Python file
        file_info: Dictionary containing missing docstring information

    Returns:
        True if file was modified, False otherwise
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

        modified = False

        # Sort items by line number in descending order to avoid line number changes
        all_items = []

        for func_info in file_info["functions_without_docs"]:
            all_items.append(("function", func_info))

        for class_info in file_info["classes_without_docs"]:
            all_items.append(("class", class_info))

        # Sort by line number (descending) to process from bottom to top
        all_items.sort(key=lambda x: x[1]["lineno"], reverse=True)

        for item_type, item_info in all_items:
            line_num = item_info["lineno"]

            # Find the line with the function/class definition
            if line_num <= len(lines):
                definition_line = lines[line_num - 1]  # Convert to 0-based index

                # Get indentation level

                # Generate appropriate docstring
                if item_type == "function":
                    docstring = generate_function_docstring(item_info)
                else:  # class
                    docstring = generate_class_docstring(item_info)

                # Insert docstring after the definition line
                docstring_lines = [line + "\n" for line in docstring.split("\n")]
                lines[line_num:line_num] = docstring_lines
                modified = True

                logger.info(
                    "Added docstring to %s '%s' at line %s", item_type, item_info["name"], line_num
                )

        # Write back if modified
        if modified:
            # Create backup
            backup_path = f"{file_path}.backup"
            with open(backup_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            # Read original content for backup
            with open(file_path, encoding="utf-8") as f:
                original_content = f.read()

            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(original_content)

            # Write updated file
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            logger.info("Updated %s with generated docstrings (backup: %s)", file_path, backup_path)

        return modified

    except Exception as e:
        logger.error("Error processing %s: %s", file_path, e)
        return False


def main():
    """Main function to orchestrate docstring generation."""

    # Directories to scan for missing docstrings
    target_directories = ["utils", "models", "database", "tools"]

    logger.info("Starting manual docstring generation for DinoAir project...")

    # Find files with missing docstrings
    logger.info("Scanning directories: %s", target_directories)
    missing_files = find_files_missing_docstrings(target_directories)

    logger.info("Found %d files with missing docstrings", len(missing_files))

    # Display summary
    for file_info in missing_files[:10]:  # Show first 10
        print(
            f"- {file_info['file']}: "
            f"Module: {'✓' if file_info['module_docstring'] else '✗'}, "
            f"Classes: {len(file_info['classes_without_docs'])}, "
            f"Functions: {len(file_info['functions_without_docs'])}"
        )

    if len(missing_files) > 10:
        print(f"... and {len(missing_files) - 10} more files")

    # Ask for confirmation
    print(f"\nWould you like to add basic docstrings to {len(missing_files)} files?")
    print("This will create .backup files and add Google-style docstrings.")
    response = input("Continue? (y/N): ")
    if response.lower() != "y":
        logger.info("Operation cancelled by user")
        return

    # Process files
    success_count = 0
    total_functions = 0
    total_classes = 0

    for file_info in missing_files:
        total_functions += len(file_info["functions_without_docs"])
        total_classes += len(file_info["classes_without_docs"])

        if add_docstrings_to_file(file_info["absolute_path"], file_info):
            success_count += 1

    logger.info("Successfully processed %d/%d files", success_count, len(missing_files))
    logger.info("Added docstrings to %d functions and %d classes", total_functions, total_classes)


if __name__ == "__main__":
    main()
