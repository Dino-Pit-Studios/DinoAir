"""
Code Assembler module for the Pseudocode Translator

This module handles the intelligent assembly of code blocks into cohesive
Python scripts, including import organization, function merging, and
consistency checks.
"""

from __future__ import annotations

import ast
import logging
import re
from collections import OrderedDict
from typing import TYPE_CHECKING, TypedDict

from .ast_cache import parse_cached
from .exceptions import AssemblyError
from .models import BlockType, CodeBlock

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .config import TranslatorConfig

logger = logging.getLogger(__name__)

# Formatting invariants
SECTION_JOIN = "\n\n\n"
DEDENT_KEYWORDS = ("else:", "elif ", "except:", "except ", "finally:", "case ")
GLOBALS_CONSTANTS_HEADER = "# Constants"
GLOBALS_VARIABLES_HEADER = "# Global variables"
CONSTANT_ASSIGNMENT_PATTERN = r"^[A-Z_]+\s*="
IMPORT_GROUPS = ("standard", "third_party", "local")


class CodeSections(TypedDict):
    """
    Type definition for organized code sections returned by _organize_code_sections.

    Attributes:
        module_docstring: Optional module-level docstring
        functions: List of function definition code strings
        classes: List of class definition code strings
        globals: List of global variable assignment code strings
        main: List of main execution code strings
    """

    module_docstring: str | None
    functions: list[str]
    classes: list[str]
    globals: list[str]
    main: list[str]


class CodeAssembler:
    """
    Intelligently combines code segments into complete Python scripts.

    This class handles the assembly of parsed code blocks into cohesive Python
    scripts with proper import organization, function merging, and consistency
    checks. It maintains code structure while ensuring valid Python syntax.
    """

    def __init__(self, config: TranslatorConfig) -> None:
        """
        Initialize the Code Assembler.

        Args:
            config: Translator configuration object containing assembly preferences
                   including indentation, line length, and import behavior.
        """
        self.config: TranslatorConfig = config
        self.indent_size: int = config.indent_size
        self.max_line_length: int = config.max_line_length
        self.preserve_comments: bool = config.preserve_comments
        self.preserve_docstrings: bool = config.preserve_docstrings
        self.auto_import_common: bool = config.auto_import_common

        # Common imports that might be auto-added
        self.common_imports: dict[str, list[str]] = {
            "math": ["sin", "cos", "sqrt", "pi", "tan", "log", "exp"],
            "os": ["path", "getcwd", "listdir", "mkdir", "remove"],
            "sys": ["argv", "exit", "path", "platform"],
            "datetime": ["datetime", "date", "time", "timedelta"],
            "json": ["dumps", "loads", "dump", "load"],
            "re": ["match", "search", "findall", "sub", "compile"],
            "typing": ["List", "Dict", "Tuple", "Optional", "Union", "Any"],
        }

    def assemble(self, blocks: list[CodeBlock]) -> str:
        """
        Assemble code blocks into complete executable Python code.

        Args:
            blocks: List of processed code blocks to assemble into complete Python code.

        Returns:
            Complete assembled Python code as a string, ready for execution.
            Returns empty string if no valid Python blocks are provided.

        Raises:
            AssemblyError: If any step of the assembly process fails.
        """
        # Guard invalid inputs early
        if not blocks:
            return ""

        logger.info("Assembling %d code blocks", len(blocks))

        try:
            # Extract → normalize → collect imports → stitch → postprocess
            python_blocks = self._extract_sections(blocks)
            if not python_blocks:
                # Prior behavior: warn (already logged) and return empty string
                return ""

            imports_section = self._collect_imports(python_blocks)
            main_code_sections = self._normalize_sections(python_blocks)
            assembled_code = self._stitch_sections(main_code_sections, imports_section)
            final_code = self._postprocess_output(assembled_code)

            logger.info("Code assembly complete")
            return final_code

        except Exception as e:
            error = AssemblyError(
                "Failed to assemble code blocks",
                blocks_info=[{"type": b.type.value, "lines": b.line_numbers} for b in blocks],
                assembly_stage="assembly",
                cause=e,
            )
            error.add_suggestion("Check block compatibility")
            error.add_suggestion("Verify all blocks contain valid Python syntax")
            raise error from e

    def assemble_streaming(self, block_iterator: Iterator[CodeBlock]) -> str:
        """
        Assemble code from a streaming iterator of blocks.

        Args:
            block_iterator: Iterator yielding CodeBlock objects to be assembled.

        Returns:
            Complete assembled Python code as a string.

        Raises:
            AssemblyError: If assembly of collected blocks fails.
        """
        # Collect blocks from iterator
        blocks = list(block_iterator)
        # Use regular assemble method
        return self.assemble(blocks)

    def _extract_sections(self, blocks: list[CodeBlock]) -> list[CodeBlock]:
        """
        Filter input to only Python blocks with proper logging.

        Args:
            blocks: List of code blocks to filter for Python content.

        Returns:
            List of Python code blocks, excluding other block types.
        """
        python_blocks = [
            block for block in blocks if block.type in (BlockType.PYTHON, BlockType.MIXED)
        ]

        if not python_blocks:
            logger.warning("No Python blocks found in input")
        else:
            logger.debug("Found %d Python blocks out of %d total", len(python_blocks), len(blocks))

        return python_blocks

    def _collect_imports(self, python_blocks: list[CodeBlock]) -> str:
        """
        Collect and organize import statements from code blocks.

        Args:
            python_blocks: List of Python code blocks to extract imports from.

        Returns:
            Organized import section as a string.
        """
        imports: dict[str, set[str]] = {"standard": set(), "third_party": set(), "local": set()}
        from_imports: dict[str, dict[str, set[str]]] = {
            "standard": {},
            "third_party": {},
            "local": {},
        }

        # Extract imports from blocks
        for block in python_blocks:
            self._extract_imports_from_block(block, imports, from_imports)

        # Auto-add common imports if enabled
        if self.auto_import_common:
            self._add_common_imports(python_blocks, imports, from_imports)

        # Build import section
        return self._build_import_section(imports, from_imports)

    def _normalize_sections(self, python_blocks: list[CodeBlock]) -> CodeSections:
        """
        Organize code blocks into logical sections.

        Args:
            python_blocks: List of Python code blocks to organize into sections.

        Returns:
            Organized code sections with proper structure and typing.

        Raises:
            AssemblyError: If code section organization fails.
        """
        try:
            return self._organize_code_sections(python_blocks)
        except Exception as e:
            error = AssemblyError(
                "Failed to organize code sections", assembly_stage="sections", cause=e
            )
            error.add_suggestion("Check code block structure")
            error.add_suggestion("Ensure valid Python syntax in all blocks")
            raise error from e

    def _stitch_sections(self, sections: CodeSections, imports_section: str) -> str:
        """
        Combine organized sections into final code string.

        Args:
            sections: Organized code sections with proper structure.
            imports_section: Formatted import statements.

        Returns:
            Complete assembled code as a string.

        Raises:
            AssemblyError: If any step of the stitching process fails.
        """
        try:
            # Merge functions and classes
            merged_functions, merged_classes = self._merge_definitions(
                sections["functions"], sections["classes"]
            )

            # Organize global variables and constants
            globals_section = self._organize_globals(sections["globals"])

            # Organize main execution code
            main_section = self._organize_main_code(sections["main"])

            # Assemble final code
            module_docstring = sections.get("module_docstring")
            sections_list = self._collect_final_sections(
                module_docstring,
                imports_section,
                globals_section,
                merged_functions,
                merged_classes,
                main_section,
            )
            return self._join_sections(sections_list)

        except Exception as e:
            error = AssemblyError(
                "Failed to stitch code sections", assembly_stage="stitching", cause=e
            )
            error.add_suggestion("Check for naming conflicts")
            error.add_suggestion("Ensure function/class definitions are valid")
            raise error from e

    def _postprocess_output(self, code: str) -> str:
        """
        Apply final formatting and consistency checks.

        Args:
            code: Assembled code requiring final processing.

        Returns:
            Final processed code with consistent formatting.

        Raises:
            AssemblyError: If consistency checks or cleanup fails.
        """
        try:
            final_code = self._ensure_consistency(code)
            return self._final_cleanup(final_code)
        except Exception as e:
            logger.error("Consistency check failed: %s", str(e))
            raise AssemblyError("Consistency or cleanup failed") from e

    # === Helper Methods ===

    def _organize_code_sections(self, blocks: list[CodeBlock]) -> CodeSections:
        """
        Organize code into sections (functions, classes, globals, main).

        Args:
            blocks: List of Python code blocks to organize into logical sections.

        Returns:
            Dictionary with categorized code sections, properly typed as CodeSections.
        """
        sections: CodeSections = {
            "module_docstring": None,
            "functions": [],
            "classes": [],
            "globals": [],
            "main": [],
        }

        for block in blocks:
            try:
                tree = parse_cached(block.content)
                if isinstance(tree, ast.Module):
                    self._maybe_set_module_docstring(tree, sections)
                    # Categorize each top-level node
                    for node in tree.body:
                        self._categorize_node(node, block, tree, sections)
            except SyntaxError:
                self._record_block_syntax_failure(block, sections)

        return sections

    def _merge_definitions(self, functions: list[str], classes: list[str]) -> tuple[str, str]:
        """
        Merge function and class definitions, handling duplicates.

        Args:
            functions: List of function code strings to merge.
            classes: List of class code strings to merge.

        Returns:
            Tuple of (merged_functions, merged_classes) as strings.
        """
        merged_functions = self._merge_functions(functions)
        merged_classes = self._merge_classes(classes)
        return merged_functions, merged_classes

    def _collect_final_sections(
        self,
        module_doc: str | None,
        imports_section: str,
        globals_section: str,
        merged_functions: str,
        merged_classes: str,
        main_section: str,
    ) -> list[str]:
        """
        Build list of non-empty sections in proper order.

        Returns:
            List of section strings in order: module docstring, imports, globals, functions, classes, main.
        """
        final_sections: list[str] = []
        if isinstance(module_doc, str) and module_doc:
            final_sections.append(module_doc)
        if imports_section:
            final_sections.append(imports_section)
        if globals_section:
            final_sections.append(globals_section)
        if merged_functions:
            final_sections.append(merged_functions)
        if merged_classes:
            final_sections.append(merged_classes)
        if main_section:
            final_sections.append(main_section)
        return final_sections

    def _join_sections(self, sections: list[str]) -> str:
        """Join sections using the module-level SECTION_JOIN."""
        return SECTION_JOIN.join(sections)

    # === Import Handling ===

    def _extract_imports_from_block(
        self,
        block: CodeBlock,
        imports: dict[str, set[str]],
        from_imports: dict[str, dict[str, set[str]]],
    ) -> None:
        """Extract import statements from a code block."""
        try:
            tree = parse_cached(block.content)
            if isinstance(tree, ast.Module):
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            category = self._categorize_import(alias.name)
                            imports[category].add(f"import {alias.name}")
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        category = self._categorize_import(module)
                        if module not in from_imports[category]:
                            from_imports[category][module] = set()
                        for alias in node.names:
                            from_imports[category][module].add(alias.name)
        except SyntaxError:
            logger.warning("Could not parse imports from block: %s", block.line_numbers)

    def _categorize_import(self, module_name: str) -> str:
        """
        Categorize an import into standard, third_party, or local.

        Args:
            module_name: Name of the module to categorize.

        Returns:
            Category string: 'standard', 'third_party', or 'local'.
        """
        # Expanded standard library modules for better categorization
        standard_lib = {
            "abc",
            "argparse",
            "array",
            "ast",
            "asyncio",
            "base64",
            "bisect",
            "builtins",
            "calendar",
            "collections",
            "configparser",
            "contextlib",
            "copy",
            "csv",
            "dataclasses",
            "datetime",
            "decimal",
            "difflib",
            "enum",
            "functools",
            "glob",
            "gzip",
            "hashlib",
            "heapq",
            "html",
            "http",
            "io",
            "itertools",
            "json",
            "logging",
            "math",
            "multiprocessing",
            "operator",
            "os",
            "pathlib",
            "pickle",
            "platform",
            "random",
            "re",
            "shutil",
            "socket",
            "sqlite3",
            "statistics",
            "string",
            "subprocess",
            "sys",
            "tempfile",
            "threading",
            "time",
            "typing",
            "urllib",
            "uuid",
            "warnings",
            "weakref",
            "xml",
            "zipfile",
        }

        # Get top-level module name
        top_level = module_name.split(".")[0]

        if top_level in standard_lib:
            return "standard"
        if module_name.startswith(".") or not module_name:
            return "local"
        return "third_party"

    def _add_common_imports(
        self,
        blocks: list[CodeBlock],
        imports: dict[str, set[str]],
        from_imports: dict[str, dict[str, set[str]]],
    ) -> None:
        """Auto-add common imports based on code usage patterns."""
        # Combine all code for analysis
        all_code = "\n".join(block.content for block in blocks)

        for module, common_names in self.common_imports.items():
            for name in common_names:
                # Check if the name is used in the code
                pattern = rf"\b{name}\s*\("
                if re.search(pattern, all_code):
                    # Check if already imported
                    if not self._already_imported(module, name, imports, from_imports):
                        # Add the import
                        if module not in from_imports["standard"]:
                            from_imports["standard"][module] = set()
                        from_imports["standard"][module].add(name)
                        logger.debug("Auto-adding import: from %s import %s", module, name)

    def _already_imported(
        self,
        module: str,
        name: str,
        imports: dict[str, set[str]],
        from_imports: dict[str, dict[str, set[str]]],
    ) -> bool:
        """Check if a name is already imported from a module."""
        # Check plain imports
        for category_imports in imports.values():
            if f"import {module}" in category_imports:
                return True

        # Check from imports
        for category_from_imports in from_imports.values():
            if module in category_from_imports and name in category_from_imports[module]:
                return True

        return False

    def _build_import_section(
        self, imports: dict[str, set[str]], from_imports: dict[str, dict[str, set[str]]]
    ) -> str:
        """Build the final imports section with proper grouping and formatting."""
        import_lines: list[str] = []

        for group in IMPORT_GROUPS:
            group_lines: list[str] = []

            # Add plain imports
            if group in imports and imports[group]:
                sorted_imports = sorted(imports[group])
                group_lines.extend(sorted_imports)

            # Add from imports
            if group in from_imports and from_imports[group]:
                for module in sorted(from_imports[group].keys()):
                    names = sorted(from_imports[group][module])
                    if len(names) == 1:
                        group_lines.append(f"from {module} import {names[0]}")
                    else:
                        names_str = ", ".join(names)
                        group_lines.append(f"from {module} import {names_str}")

            if group_lines:
                if import_lines:  # Add blank line between groups
                    import_lines.append("")
                import_lines.extend(group_lines)

        return "\n".join(import_lines)

    # === Section Processing ===

    def _maybe_set_module_docstring(self, tree: ast.Module, sections: CodeSections) -> None:
        """Extract and set module docstring if present and not already set."""
        if (
            not sections["module_docstring"]
            and tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)
        ):
            docstring = tree.body[0].value.value
            sections["module_docstring"] = f'"""{docstring}"""'

    def _categorize_node(
        self, node: ast.AST, block: CodeBlock, tree: ast.Module, sections: CodeSections
    ) -> None:
        """Categorize an AST node into the appropriate section bucket."""
        if isinstance(node, ast.FunctionDef):
            self._append_node_source(node, block, sections["functions"])
        elif isinstance(node, ast.ClassDef):
            self._append_node_source(node, block, sections["classes"])
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            if self._is_top_level_assignment(node, tree):
                self._append_node_source(node, block, sections["globals"])
            else:
                self._append_node_source(node, block, sections["main"])
        elif isinstance(node, (ast.Expr, ast.If, ast.For, ast.While, ast.With, ast.Try)):
            # Executable statements go to main
            self._append_node_source(node, block, sections["main"])
        elif not isinstance(node, (ast.Import, ast.ImportFrom)):
            # Other statements (return, break, continue, etc.) go to main
            self._append_node_source(node, block, sections["main"])

    def _append_node_source(self, node: ast.AST, block: CodeBlock, target_list: list[str]) -> None:
        """Extract source code for a node and append to target list."""
        try:
            # For small blocks or when line numbers are unreliable, use the whole block
            lines = block.content.splitlines()
            if len(lines) <= 3 or not hasattr(node, "lineno"):
                # Small block or no line info - use entire content if not already added
                if block.content not in target_list:
                    target_list.append(block.content)
                return

            # Extract specific node lines
            start_line = max(0, node.lineno - 1)
            end_line = getattr(node, "end_lineno", len(lines))

            if start_line < len(lines):
                end_line = min(end_line, len(lines))
                node_lines = lines[start_line:end_line]
                if node_lines:
                    node_content = "\n".join(node_lines)
                    if node_content not in target_list:
                        target_list.append(node_content)
        except Exception:
            # Fallback: use the entire block content if not already added
            if block.content not in target_list:
                target_list.append(block.content)

    def _record_block_syntax_failure(self, block: CodeBlock, sections: CodeSections) -> None:
        """Record syntax errors by adding to main section."""
        logger.warning("Could not parse block: %s", block.line_numbers)
        sections["main"].append(block.content)

    def _is_top_level_assignment(self, node: ast.stmt, tree: ast.Module) -> bool:
        """Check if an assignment is at the top level (not inside a function/class)."""
        # Simple heuristic: if node is directly in module body, it's top-level
        return hasattr(tree, "body") and node in tree.body

    # === Definition Merging ===

    def _merge_functions(self, functions: list[str]) -> str:
        """Merge function definitions, handling duplicates by keeping later definitions."""
        if not functions:
            return ""

        unique_functions: OrderedDict[str, str] = OrderedDict()

        for func_code in functions:
            try:
                tree = parse_cached(func_code)
                func_name = self._first_function_name(tree)
                if func_name:
                    # If duplicate, keep the later definition (assumed to be more complete)
                    if func_name in unique_functions:
                        logger.debug("Replacing duplicate function: %s", func_name)
                    unique_functions[func_name] = func_code
                else:
                    # If we can't parse a name, use the code as-is with a unique key
                    unique_key = f"func_{len(unique_functions)}"
                    unique_functions[unique_key] = func_code
            except SyntaxError as e:
                logger.warning("Could not parse function: %s", str(e))
                unique_functions[f"func_{len(unique_functions)}"] = func_code

        return "\n\n".join(unique_functions.values())

    def _merge_classes(self, classes: list[str]) -> str:
        """Merge class definitions, handling duplicates by keeping later definitions."""
        if not classes:
            return ""

        unique_classes: OrderedDict[str, str] = OrderedDict()

        for class_code in classes:
            try:
                tree = parse_cached(class_code)
                class_name = self._first_class_name(tree)
                if class_name:
                    # If duplicate, keep the later definition (assumed to be more complete)
                    if class_name in unique_classes:
                        logger.debug("Replacing duplicate class: %s", class_name)
                    unique_classes[class_name] = class_code
                else:
                    unique_classes[f"class_{len(unique_classes)}"] = class_code
            except SyntaxError as e:
                logger.warning("Could not parse class: %s", str(e))
                unique_classes[f"class_{len(unique_classes)}"] = class_code

        return "\n\n".join(unique_classes.values())

    def _first_function_name(self, tree: ast.AST) -> str | None:
        """Return the first top-level function name from an ast.Module, else None."""
        if isinstance(tree, ast.Module) and tree.body:
            first = tree.body[0]
            if isinstance(first, ast.FunctionDef):
                return first.name
        return None

    def _first_class_name(self, tree: ast.AST) -> str | None:
        """Return the first top-level class name from an ast.Module, else None."""
        if isinstance(tree, ast.Module) and tree.body:
            first = tree.body[0]
            if isinstance(first, ast.ClassDef):
                return first.name
        return None

    # === Global and Main Organization ===

    def _organize_globals(self, globals_list: list[str]) -> str:
        """Organize global variables and constants with proper categorization."""
        if not globals_list:
            return ""

        constants: list[str] = []
        variables: list[str] = []

        for global_code in globals_list:
            stripped = global_code.strip()
            if re.search(CONSTANT_ASSIGNMENT_PATTERN, stripped):
                constants.append(stripped)
            else:
                variables.append(stripped)

        lines: list[str] = []
        if constants:
            lines.append(GLOBALS_CONSTANTS_HEADER)
            lines.extend(constants)
        if variables:
            if constants:
                lines.append("")
            lines.append(GLOBALS_VARIABLES_HEADER)
            lines.extend(variables)

        return "\n".join(lines)

    def _organize_main_code(self, main_sections: list[str]) -> str:
        """Organize main execution code with appropriate guard if needed."""
        if not main_sections:
            return ""

        main_code = "\n\n".join(main_sections)

        # Check if main guard is already present
        if 'if __name__ == "__main__"' in main_code or "if __name__ == '__main__'" in main_code:
            return main_code

        # Check if we should wrap in if __name__ == "__main__":
        # More comprehensive detection of executable code
        needs_main_guard = any(
            [
                "print(" in main_code,
                "input(" in main_code,
                re.search(r"\b(main|run|execute|start)\s*\(", main_code),
                re.search(r"\b(sys\.exit|quit|exit)\s*\(", main_code),
                # Direct function calls (not in assignments or definitions)
                re.search(r"^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\(", main_code, re.MULTILINE),
            ]
        )

        if needs_main_guard:
            # Indent the main code
            indented_code = "\n".join(
                f"{' ' * self.indent_size}{line}" if line.strip() else line
                for line in main_code.splitlines()
            )
            return f'if __name__ == "__main__":\n{indented_code}'

        return main_code

    # === Consistency and Cleanup ===

    def _ensure_consistency(self, code: str) -> str:
        """Ensure consistency in the assembled code by fixing indentation and formatting."""
        # Fix indentation
        code = self._fix_indentation(code)

        # Ensure consistent line endings
        code = code.replace("\r\n", "\n").replace("\r", "\n")

        # Remove excessive blank lines
        code = re.sub(r"\n{4,}", "\n\n\n", code)
        # Ensure newline at end of file
        if code and not code.endswith("\n"):
            code += "\n"

        return code

    def _fix_indentation(self, code: str) -> str:
        """Fix and standardize indentation in the code."""
        try:
            lines = code.splitlines()
            fixed_lines: list[str] = []

            # Convert all indentation to spaces
            indent_stack = [0]

            for line in lines:
                stripped = line.strip()

                if not stripped:
                    fixed_lines.append("")
                    continue

                # Calculate current indentation
                current_indent = len(line) - len(line.lstrip())

                # Adjust indentation based on context
                if current_indent < indent_stack[-1] and len(indent_stack) > 1:
                    # Dedent detected
                    while len(indent_stack) > 1 and current_indent < indent_stack[-1]:
                        indent_stack.pop()
                    current_indent = indent_stack[-1]

                # Check for block start
                if stripped.endswith(":") and not stripped.startswith("#"):
                    fixed_lines.append(" " * current_indent + stripped)
                    indent_stack.append(current_indent + self.indent_size)
                else:
                    fixed_lines.append(" " * current_indent + stripped)

            return "\n".join(fixed_lines)

        except Exception as e:
            error = AssemblyError(
                "Failed to fix indentation", assembly_stage="indentation", cause=e
            )
            error.add_suggestion("Check for severe indentation errors")
            error.add_suggestion("Ensure consistent use of spaces or tabs")
            raise error from e

    def _final_cleanup(self, code: str) -> str:
        """Perform final cleanup on the assembled code with proper formatting."""
        lines = self._remove_trailing_whitespace(code)
        cleaned_lines = self._ensure_spacing_around_definitions(lines)
        final_code = "\n".join(cleaned_lines)
        return self._ensure_single_newline_end(final_code)

    def _remove_trailing_whitespace(self, code: str) -> list[str]:
        return [line.rstrip() for line in code.splitlines()]

    def _ensure_spacing_around_definitions(self, lines: list[str]) -> list[str]:
        cleaned_lines: list[str] = []
        prev_was_definition = False

        for line in lines:
            is_definition = line.startswith(("def ", "class ")) and not line[0].isspace()

            if is_definition and prev_was_definition and cleaned_lines:
                cleaned_lines = self._add_blank_lines_before_definition(cleaned_lines)

            cleaned_lines.append(line)
            prev_was_definition = is_definition and bool(line.strip())

        return cleaned_lines

    def _add_blank_lines_before_definition(self, cleaned_lines: list[str]) -> list[str]:
        while len(cleaned_lines) >= 2 and not cleaned_lines[-1] and not cleaned_lines[-2]:
            cleaned_lines.pop()
        if cleaned_lines and cleaned_lines[-1]:
            cleaned_lines.append("")
        if len(cleaned_lines) < 2 or cleaned_lines[-2]:
            cleaned_lines.append("")
        return cleaned_lines

    def _ensure_single_newline_end(self, code: str) -> str:
        if code and not code.endswith("\n"):
            code += "\n"
        return code
