#!/usr/bin/env python3
"""Extended docstring generator for models and database modules."""

import ast
import logging
import re
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def generate_description_from_name(name: str) -> str:
    """Generate a description based on a function or class name."""
    words = re.sub(r"([A-Z])", r" \1", name).replace("_", " ").strip().split()
    prefix_actions = [
        ("get_", lambda obj: f"Get {obj}."),
        ("set_", lambda obj: f"Set {obj}."),
        ("create_", lambda obj: f"Create {obj}."),
        ("delete_", lambda obj: f"Delete {obj}."),
        ("update_", lambda obj: f"Update {obj}."),
        ("save_", lambda obj: f"Save {obj}."),
        ("load_", lambda obj: f"Load {obj}."),
        ("find_", lambda obj: f"Find {obj}."),
        ("search_", lambda obj: f"Search {obj}."),
        ("validate_", lambda obj: f"Validate {obj}."),
        ("process_", lambda obj: f"Process {obj}."),
        ("handle_", lambda obj: f"Handle {obj}."),
        ("init", lambda obj: f"Initialize {obj if obj else 'the instance'}."),
        ("build", lambda obj: f"Build {obj}."),
        ("parse", lambda obj: f"Parse {obj}."),
        ("serialize", lambda obj: f"Serialize {obj}."),
        ("deserialize", lambda obj: f"Deserialize {obj}."),
        ("to_", lambda obj: f"Convert to {obj}."),
        ("from_", lambda obj: f"Create from {obj}."),
        ("is_", lambda obj: f"Check if {obj}."),
        ("has_", lambda obj: f"Check if has {obj}."),
        ("can_", lambda obj: f"Check if can {obj}."),
    ]
    for prefix, action in prefix_actions:
        if name.startswith(prefix):
            obj = " ".join(words[1:]).lower()
            return action(obj)
    # Generic description
    return f"{' '.join(words).capitalize()}."


def generate_class_docstring(name: str, indent: int) -> str:
    """Generate a Google-style docstring for a class."""
    base_indent = " " * indent

    # Special handling for common class patterns
    if name.endswith("Database") or name.endswith("DB"):
        description = f"{name} class for database operations."
    elif name.endswith("Service"):
        description = f"{name} class for service operations."
    elif name.endswith("Manager"):
        description = f"{name} class for management operations."
    elif name.endswith("Handler"):
        description = f"{name} class for handling operations."
    elif name.endswith("Config"):
        description = f"{name} configuration class."
    elif name.endswith("Model"):
        description = f"{name} data model class."
    elif name.endswith("Exception"):
        description = f"{name} exception class."
    elif name.endswith("Error"):
        description = f"{name} error class."
    else:
        description = generate_description_from_name(name)

    return f'{base_indent}"""{description}"""'


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


def get_missing_docstring_items(content: str) -> list:
    """Extract missing docstring items from file content."""
    tree = ast.parse(content)
    missing_items = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if ast.get_docstring(node) is None:
                missing_items.append({"type": "class", "name": node.name, "lineno": node.lineno})
        elif isinstance(node, ast.FunctionDef):
            if ast.get_docstring(node) is None and not node.name.startswith("_"):
                args = [arg.arg for arg in node.args.args]
                missing_items.append(
                    {
                        "type": "function",
                        "name": node.name,
                        "lineno": node.lineno,
                        "args": args,
                        "has_return": node.returns is not None,
                    }
                )
    return sorted(missing_items, key=lambda x: x["lineno"], reverse=True)


def insert_docstrings(lines: list, missing_items: list) -> (list, bool):
    """Insert docstrings into the list of lines for missing items."""
    modified = False
    for item in missing_items:
        idx = item["lineno"] - 1
        if idx >= len(lines):
            continue
        indent = len(lines[idx]) - len(lines[idx].lstrip())
        if item["type"] == "class":
            doc = generate_class_docstring(item["name"], indent)
        else:
            doc = generate_function_docstring(
                item["name"], item["args"], item["has_return"], indent
            )
        lines.insert(idx + 1, doc)
        modified = True
    return lines, modified


def process_file(file_path: str) -> bool:
    """Process a single file to add missing docstrings."""
    filename = Path(file_path).name
    allowed_filenames = {"models.py", "database.py"}
    if filename not in allowed_filenames:
        logger.error("Unauthorized file access attempt: %s", filename)
        return False
    safe_path = Path(__file__).parent / filename
    logger.info("Processing: %s", safe_path)
    try:
        with open(safe_path, encoding="utf-8") as f:
            content = f.read()
        lines = content.split("\n")
    except Exception:
        logger.exception("Failed to read file: %s", safe_path)
        return False

    missing_items = get_missing_docstring_items(content)
    if not missing_items:
        logger.info("No missing docstrings found")
        return False

    logger.info("Found %s items missing docstrings", len(missing_items))
    lines, modified = insert_docstrings(lines, missing_items)
    if modified:
        try:
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return True
        except Exception:
            logger.exception("Failed to write file: %s", safe_path)
            return False
    return False


def main():
    """Process models and database files for docstring generation."""

    # Key files to process
    target_files = [
        # Models
        "models/note_v2.py",
        "models/calendar_event.py",
        "models/calendar_event_v2.py",
        "models/project.py",
        "models/base.py",
        # Database
        "database/notes_service.py",
        "database/notes_repository.py",
        "database/notes_validator.py",
        "database/projects_db.py",
        "database/appointments_db.py",
        "database/artifacts_db.py",
        "database/timers_db.py",
        "database/file_search_db.py",
        "database/factory.py",
        "database/interfaces.py",
        "database/resilient_db.py",
    ]

    logger.info("Starting extended docstring generation for models and database...")

    processed_count = 0
    total_functions = 0
    total_classes = 0

    for file_path in target_files:
        if Path(file_path).exists():
            logger.info("\n--- Processing %s ---", file_path)

            # Count items before processing
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
                tree = ast.parse(content)

                file_functions = 0
                file_classes = 0

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        if not ast.get_docstring(node):
                            file_classes += 1
                    elif isinstance(node, ast.FunctionDef):
                        if not ast.get_docstring(node) and not node.name.startswith("_"):
                            file_functions += 1

                total_functions += file_functions
                total_classes += file_classes

                logger.info("Expected: %s functions, %s classes", file_functions, file_classes)

            except Exception as e:
                logger.warning("Could not analyze %s: %s", file_path, e)

            if process_file(file_path):
                processed_count += 1
        else:
            logger.warning("File not found: %s", file_path)

    logger.info("\nProcessing complete!")
    logger.info("Files modified: %s", processed_count)
    logger.info("Expected functions documented: %s", total_functions)
    logger.info("Expected classes documented: %s", total_classes)


if __name__ == "__main__":
    main()
