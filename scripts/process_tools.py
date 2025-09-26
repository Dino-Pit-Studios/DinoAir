#!/usr/bin/env python3
"""Process tools directory for docstring generation."""

import ast
import logging
import re
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TOOL_MAPPING = {
    "get_": "Get",
    "create_": "Create",
    "list_": "List",
    "search_": "Search",
    "update_": "Update",
    "delete_": "Delete",
}

STANDARD_MAPPING = {
    "get_": "Get",
    "set_": "Set",
    "create_": "Create",
    "delete_": "Delete",
    "update_": "Update",
    "list_": "List",
    "search_": "Search",
    "find_": "Find",
    "add_": "Add",
    "remove_": "Remove",
    "process_": "Process",
    "handle_": "Handle",
    "validate_": "Validate",
    "parse_": "Parse",
    "format_": "Format",
    "render_": "Render",
    "build_": "Build",
}


def _get_verb(name: str, mapping: dict) -> str:
    for prefix, verb in mapping.items():
        if name.startswith(prefix):
            return verb
    return None


def generate_description_from_name(name: str) -> str:
    """Generate a description based on a function or class name."""
    words = re.sub(r"([A-Z])", r" \1", name).replace("_", " ").strip().split()
    lower_name = name.lower()
    tail = " ".join(words[1:]).lower()
    full = " ".join(words).lower()

    mapping = TOOL_MAPPING if "tool" in lower_name else STANDARD_MAPPING
    verb = _get_verb(name, mapping)
    if verb:
        return f"{verb} {tail}."
    if "tool" in lower_name:
        return f"Tool function for {full}."
    if name.startswith("execute_"):
        return f"Execute {' '.join(words[1:]).lower()}."
    if name.startswith("run_"):
        return f"Run {' '.join(words[1:]).lower()}."
    if name.startswith("start_"):
        return f"Start {' '.join(words[1:]).lower()}."
    if name.startswith("stop_"):
        return f"Stop {' '.join(words[1:]).lower()}."
    if name.startswith("init"):
        return f"Initialize {' '.join(words[1:]).lower() if len(words) > 1 else 'the instance'}."
    if name.startswith("setup"):
        return f"Set up {' '.join(words[1:]).lower()}."
    if name.startswith("cleanup"):
        return f"Clean up {' '.join(words[1:]).lower()}."

    # Generic description
    words = [w.lower() for w in words]
    if words:
        words[0] = words[0].capitalize()
        return f"{' '.join(words)}."
    return "TODO: Add description."


def generate_function_docstring(name: str, args: list, has_return: bool, indent: int) -> str:
    """Generate a Google-style docstring for a function."""
    base_indent = " " * indent
    description = generate_description_from_name(name)

    docstring_parts = [f'{base_indent}"""{description}']

    # Add Args section if function has parameters
    if args:
        filtered_args = [arg for arg in args if arg not in ["self", "cls"]]
        if filtered_args:
            docstring_parts.append(f"{base_indent}")
            docstring_parts.append(f"{base_indent}Args:")
            for arg in filtered_args:
                docstring_parts.append(f"{base_indent}    {arg}: TODO: Add description")

    # Add Returns section if function has return annotation
    if has_return:
        if args and len([arg for arg in args if arg not in ["self", "cls"]]) > 0:
            docstring_parts.append(f"{base_indent}    ")
        else:
            docstring_parts.append(f"{base_indent}")
        docstring_parts.append(f"{base_indent}Returns:")
        docstring_parts.append(f"{base_indent}    TODO: Add return description")

    docstring_parts.append(f'{base_indent}"""')
    return "\n".join(docstring_parts)


def process_file(file_path: str) -> bool:
    """Process a single file to add missing docstrings."""
    logger.info("Processing: %s", file_path)

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
            lines = content.split("\n")

        tree = ast.parse(content)

        # Find functions without docstrings
        missing_functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                has_docstring = ast.get_docstring(node) is not None
                if not has_docstring and not node.name.startswith("_"):
                    args = [arg.arg for arg in node.args.args]
                    missing_functions.append(
                        {
                            "name": node.name,
                            "lineno": node.lineno,
                            "args": args,
                            "has_return": node.returns is not None,
                        }
                    )

        if not missing_functions:
            logger.info("No missing docstrings found")
            return False

        logger.info("Found %d functions missing docstrings", len(missing_functions))

        # Sort by line number in reverse order
        missing_functions.sort(key=lambda x: x["lineno"], reverse=True)

        modified = False
        for func in missing_functions:
            line_num = func["lineno"] - 1

            if line_num >= len(lines):
                continue

            # Get indentation
            def_line = lines[line_num]
            indent = len(def_line) - len(def_line.lstrip())

            # Find the colon
            colon_line = line_num
            while colon_line < len(lines) and ":" not in lines[colon_line]:
                colon_line += 1

            if colon_line >= len(lines):
                continue

            # Generate docstring
            docstring = generate_function_docstring(
                func["name"], func["args"], func["has_return"], indent + 4
            )

            # Insert docstring
            docstring_lines = docstring.split("\n")
            for i, ds_line in enumerate(docstring_lines):
                lines.insert(colon_line + 1 + i, ds_line)

            modified = True
            logger.info("Added docstring to function '%s'", func["name"])

        if modified:
            # Create backup
            backup_path = f"{file_path}.backup"
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Write updated file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            logger.info("Updated %s (backup: %s)", file_path, backup_path)

        return modified

    except Exception as e:
        logger.error("Error processing %s: %s", file_path, e)
        return False


def main():
    """Process tools files for docstring generation."""

    # Key tool files to process
    target_files = [
        "tools/notes_tool.py",
        "tools/projects_tool.py",
        "tools/basic_tools.py",
        "tools/file_search_tool.py",
    ]

    logger.info("Starting docstring generation for tools...")

    processed_count = 0
    total_functions = 0

    for file_path in target_files:
        if Path(file_path).exists():
            logger.info("\n--- Processing %s ---", file_path)

            # Count functions before processing
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
                tree = ast.parse(content)

                file_functions = 0
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.FunctionDef)
                        and not ast.get_docstring(node)
                        and not node.name.startswith("_")
                    ):
                        file_functions += 1

                total_functions += file_functions
                logger.info("Expected: %s functions", file_functions)

            except Exception as e:
                logger.warning("Could not analyze %s: %s", file_path, e)

            if process_file(file_path):
                processed_count += 1
        else:
            logger.warning("File not found: %s", file_path)

    logger.info("\nProcessing complete!")
    logger.info("Files modified: %s", processed_count)
    logger.info("Expected functions documented: %s", total_functions)


if __name__ == "__main__":
    main()
