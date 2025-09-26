"""
Syntax validation module for Python code.

This module handles syntax validation, indentation checking, and
syntax error recovery suggestions.
"""

import ast
import re
import tokenize
from io import StringIO

from ..ast_cache import parse_cached
from ..exceptions import ErrorContext, ValidationError
from .constants import UNSAFE_MODULES
from .params import ErrorFormatContext, IndentationContext
from .result import ValidationResult


class SyntaxValidator:
    """Handles syntax validation and related checks."""

    def __init__(self, config):
        """Initialize with translator configuration."""
        self.config = config
        self.validation_level = config.llm.validation_level
        self.check_imports = config.validate_imports
        self.check_undefined = config.check_undefined_vars
        self.allow_unsafe = config.allow_unsafe_operations

        # Unsafe operation patterns
        self.unsafe_patterns = [
            r"\beval\s*\(",
            r"\bexec\s*\(",
            r"\b__import__\s*\(",
            r"\bcompile\s*\(",
            r'\bopen\s*\([^,)]*["\']w["\']',  # Writing files
            r"\bos\.(system|popen|exec)",
            r"\bsubprocess\.(run|call|Popen)",
            r"\bshutil\.rmtree",
            r"\bos\.remove",
        ]

    def validate_syntax(self, code: str) -> ValidationResult:
        """
        Validate Python code syntax.

        Args:
            code: Python code to validate

        Returns:
            ValidationResult with syntax validation details
        """
        result = ValidationResult(is_valid=True)

        if not code or not code.strip():
            result.add_error("Empty code provided")
            return result

        # Parse AST with error handling
        tree = self._parse_tree_with_syntax_handling(code, result)
        if tree is None:
            return result

        # Apply syntax checks
        self._apply_syntax_checks(tree, code, result)
        return result

    def _parse_tree_with_syntax_handling(
        self, code: str, result: ValidationResult
    ) -> ast.AST | None:
        """Parse code into AST with error handling."""
        try:
            return parse_cached(code)
        except SyntaxError as e:
            lines = code.splitlines()
            context = ErrorContext(
                line_number=e.lineno,
                column_number=e.offset,
                code_snippet=(lines[e.lineno - 1] if e.lineno and e.lineno <= len(lines) else None),
                surrounding_lines=(
                    self._get_surrounding_lines(lines, e.lineno) if e.lineno else []
                ),
            )

            error = ValidationError(
                f"Syntax error: {e.msg}",
                validation_type="syntax",
                failed_code=code,
                context=context,
                cause=e,
            )

            self._add_syntax_suggestions(error, e, code)
            result.add_error(error.format_error())
            return None
        except Exception as e:
            error = ValidationError(
                f"Failed to parse code: {str(e)}",
                validation_type="syntax",
                failed_code=code,
                cause=e,
            )
            error.add_suggestion("Check for severe syntax errors")
            error.add_suggestion("Ensure the code is valid Python")
            result.add_error(error.format_error())
            return None

    def _apply_syntax_checks(self, tree: ast.AST, code: str, result: ValidationResult) -> None:
        """Apply various syntax-related checks."""
        self._apply_indentation_checks(code, result)
        self._apply_import_checks(tree, result)
        self._apply_common_issue_checks(code, result)
        self._apply_unsafe_operation_checks(code, result)
        self._apply_tokenization_checks(code, result)

    def _apply_indentation_checks(self, code: str, result: ValidationResult) -> None:
        """Apply indentation error checks."""
        indentation_errors = self._check_indentation(code)
        for error in indentation_errors:
            result.add_error(error)

    def _apply_import_checks(self, tree: ast.AST, result: ValidationResult) -> None:
        """Apply import validation checks if enabled."""
        if self.check_imports:
            import_errors = self._check_imports(tree)
            for error in import_errors:
                result.add_warning(error)

    def _apply_common_issue_checks(self, code: str, result: ValidationResult) -> None:
        """Apply common coding issue checks based on validation level."""
        if self.validation_level in ["strict", "normal"]:
            common_issues = self._check_common_issues(code)
            for issue in common_issues:
                result.add_warning(issue)

    def _apply_unsafe_operation_checks(self, code: str, result: ValidationResult) -> None:
        """Apply unsafe operation checks if not allowed."""
        if not self.allow_unsafe:
            unsafe_ops = self._check_unsafe_operations(code)
            for op in unsafe_ops:
                result.add_error(f"Unsafe operation detected: {op}")

    def _apply_tokenization_checks(self, code: str, result: ValidationResult) -> None:
        """Apply tokenization validation checks."""
        tokenization_errors = self._check_tokenization(code)
        for error in tokenization_errors:
            result.add_error(error)

    def _check_indentation(self, code: str) -> list[str]:
        """Check for indentation issues."""
        lines = code.split("\n")
        indent_stack = [0]
        errors = []

        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue

            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            # Check for mixed tabs and spaces
            mixed_error = self._check_mixed_tabs_spaces(line, indent, lines, line_num)
            if mixed_error:
                errors.append(mixed_error)

            # Check consistency
            context = IndentationContext(
                stripped=stripped,
                indent=indent,
                indent_stack=indent_stack,
                line=line,
                lines=lines,
                line_num=line_num,
            )
            consistency_error = self._check_indentation_consistency(context)
            if consistency_error:
                errors.append(consistency_error)

        return errors

    def _check_mixed_tabs_spaces(
        self, line: str, indent: int, lines: list[str], line_num: int
    ) -> str | None:
        """Check for mixed tabs and spaces."""
        if "\t" in line[:indent]:
            params = ErrorFormatContext(
                message="Mixed tabs and spaces in indentation",
                line_text=line,
                line_no=line_num,
                all_lines=lines,
                suggestions=[
                    f"Use {self.config.indent_size} spaces for indentation",
                    "Configure your editor to show whitespace characters",
                ],
            )
            return self._format_validation_error(params)
        return None

    def _check_indentation_consistency(self, context: IndentationContext) -> str | None:
        """Check for consistent indentation levels."""
        if context.stripped.endswith(":"):
            context.indent_stack.append(context.indent + self.config.indent_size)
            return None
        if context.indent not in context.indent_stack:
            if context.indent < context.indent_stack[-1]:
                return self._handle_dedent(context)
            params = ErrorFormatContext(
                message="Unexpected indentation level",
                line_text=context.line,
                line_no=context.line_num,
                all_lines=context.lines,
                suggestions=[
                    "Ensure proper nesting of code blocks",
                    "Check for missing or extra colons",
                ],
            )
            return self._format_validation_error(params)
        return None

    def _handle_dedent(self, context: IndentationContext) -> str | None:
        """Handle dedent cases and check for proper alignment."""
        while context.indent_stack and context.indent < context.indent_stack[-1]:
            context.indent_stack.pop()
        if not context.indent_stack or context.indent != context.indent_stack[-1]:
            params = ErrorFormatContext(
                message="Inconsistent indentation",
                line_text=context.line,
                line_no=context.line_num,
                all_lines=context.lines,
                suggestions=[
                    f"Use {self.config.indent_size} spaces per indentation level",
                    "Check that dedent aligns with a previous indentation level",
                ],
            )
            return self._format_validation_error(params)
        return None

    def _check_imports(self, tree: ast.AST) -> list[str]:
        """Check import statements for issues."""
        issues = []
        imported_modules = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                issues.extend(self._check_regular_imports(node, imported_modules))
            elif isinstance(node, ast.ImportFrom):
                issues.extend(self._check_from_imports(node, imported_modules))

        return issues

    def _check_regular_imports(self, node: ast.Import, imported_modules: set) -> list[str]:
        """Check regular import statements."""
        issues = []
        for alias in node.names:
            module_name = alias.name.split(".")[0]
            if module_name in imported_modules:
                issues.append(f"Duplicate import: {module_name} at line {node.lineno}")
            else:
                imported_modules.add(module_name)
                if self._is_unsafe_module(module_name):
                    issues.append(
                        f"Import of potentially unsafe module '{module_name}' at line {node.lineno}"
                    )
        return issues

    def _check_from_imports(self, node: ast.ImportFrom, imported_modules: set) -> list[str]:
        """Check from...import statements."""
        issues = []
        if node.module:
            module_name = node.module.split(".")[0]
            if module_name in imported_modules:
                issues.append(f"Duplicate import: {module_name} at line {node.lineno}")
            else:
                imported_modules.add(module_name)
                if self._is_unsafe_module(module_name):
                    issues.append(
                        f"Import from potentially unsafe module '{module_name}' at line {node.lineno}"
                    )
        return issues

    def _is_unsafe_module(self, module_name: str) -> bool:
        """Check if a module is considered unsafe."""
        return module_name in UNSAFE_MODULES

    def _check_common_issues(self, code: str) -> list[str]:
        """Check for common coding issues."""
        issues = []
        code_smells = {
            re.compile(r"except\s*:"): "Bare except clause - specify exception types",
            re.compile(r"import\s+\*"): "Wildcard imports - consider explicit imports",
            re.compile(r"global\s+"): "Global variable usage - consider refactoring",
            re.compile(r"pass\s*$"): "Empty code block - add implementation or remove",
            re.compile(r"TODO|FIXME|XXX"): "Unfinished code markers found",
            re.compile(r"print\s*\(.*\)\s*#\s*debug"): "Debug print statements found",
        }

        for pattern, message in code_smells.items():
            if pattern.search(code):
                issues.append(message)

        return issues

    def _check_unsafe_operations(self, code: str) -> list[str]:
        """Check for unsafe operations."""
        issues = []
        for pattern in self.unsafe_patterns:
            matches = re.finditer(pattern, code, re.MULTILINE)
            for match in matches:
                line_num = code[: match.start()].count("\n") + 1
                issues.append(f"{match.group()} on line {line_num}")
        return issues

    def _check_tokenization(self, code: str) -> list[str]:
        """Check for tokenization issues."""
        try:
            tokens = tokenize.generate_tokens(StringIO(code).readline)
            list(tokens)  # Consume the generator to trigger any tokenization errors
            return []
        except tokenize.TokenError as e:
            return [f"Tokenization error: {e}"]
        except Exception as e:
            return [f"Unexpected tokenization error: {e}"]

    def _add_syntax_suggestions(self, error: ValidationError, syntax_error: SyntaxError, code: str):
        """Add automatic suggestions for syntax errors."""
        if syntax_error.text:
            suggestion = self._suggest_syntax_fix(code, syntax_error)
            if suggestion:
                error.add_suggestion(f"Try: {suggestion}")

        error.add_suggestion("Check for missing colons, parentheses, or quotes")
        error.add_suggestion("Ensure proper indentation")

    def _suggest_syntax_fix(self, code: str, error: SyntaxError) -> str:
        """Suggest a fix for common syntax errors."""
        if not error.text:
            return ""

        problem_line = error.text.rstrip()

        # Try various common fixes
        suggestions = [
            self._syntax_mismatch_fix(problem_line),
            self._check_missing_colon(problem_line),
            self._check_mismatched_brackets(problem_line),
            self._check_unclosed_strings(problem_line),
        ]

        return next((s for s in suggestions if s), "")

    def _syntax_mismatch_fix(self, problem_line: str) -> str | None:
        """Fix common syntax mismatches."""
        if problem_line.strip().startswith("if ") and not problem_line.rstrip().endswith(":"):
            return problem_line.rstrip() + ":"
        return None

    def _check_missing_colon(self, line: str) -> str | None:
        """Check for missing colons in control structures."""
        keywords = [
            "if",
            "else",
            "elif",
            "for",
            "while",
            "def",
            "class",
            "try",
            "except",
            "finally",
            "with",
        ]
        stripped = line.strip()
        for keyword in keywords:
            if stripped.startswith(keyword + " ") and not stripped.endswith(":"):
                return stripped + ":"
        return None

    def _check_mismatched_brackets(self, line: str) -> str | None:
        """Check for mismatched brackets."""
        brackets = {"(": ")", "[": "]", "{": "}"}
        stack = []

        for char in line:
            mismatch_result = self._process_bracket_char(char, brackets, stack, line)
            if mismatch_result:
                return mismatch_result

        return self._handle_unclosed_brackets(line, stack)

    def _process_bracket_char(
        self, char: str, brackets: dict, stack: list, line: str
    ) -> str | None:
        """Process a single character for bracket matching."""
        if char in brackets:
            stack.append(brackets[char])
        elif char in brackets.values() and (not stack or stack.pop() != char):
            return line + self._get_first_closing_bracket(brackets)
        return None

    def _get_first_closing_bracket(self, brackets: dict) -> str:
        """Get the first closing bracket type."""
        return list(brackets.values())[0]

    def _handle_unclosed_brackets(self, line: str, stack: list) -> str | None:
        """Handle unclosed brackets at end of line."""
        if stack:
            return line + stack[-1]
        return None

    def _check_unclosed_strings(self, line: str) -> str | None:
        """Check for unclosed strings."""
        in_string = False
        quote_char = None

        for i, char in enumerate(line):
            if self._is_quote_character(char, i, line):
                in_string, quote_char = self._process_quote_char(char, in_string, quote_char)

        return self._handle_unclosed_string(line, in_string, quote_char)

    def _is_quote_character(self, char: str, index: int, line: str) -> bool:
        """Check if character is an unescaped quote."""
        return char in ['"', "'"] and (index == 0 or line[index - 1] != "\\")

    def _process_quote_char(
        self, char: str, in_string: bool, quote_char: str | None
    ) -> tuple[bool, str | None]:
        """Process a quote character and update string state."""
        if not in_string:
            return True, char
        if char == quote_char:
            return False, None
        return in_string, quote_char

    def _handle_unclosed_string(
        self, line: str, in_string: bool, quote_char: str | None
    ) -> str | None:
        """Handle unclosed string at end of line."""
        if in_string and quote_char:
            return line + quote_char
        return None

    def _get_surrounding_lines(
        self, lines: list[str], line_no: int, context_size: int = 2
    ) -> list[str]:
        """Get surrounding lines for error context."""
        if not line_no or line_no <= 0:
            return []

        start = max(0, line_no - context_size - 1)
        end = min(len(lines), line_no + context_size)
        return lines[start:end]

    def _format_validation_error(self, params: ErrorFormatContext) -> str:
        """Format validation error with context."""
        context_lines = []
        if params.all_lines and params.line_no:
            start_line = max(1, params.line_no - 2)
            end_line = min(len(params.all_lines), params.line_no + 2)

            for i in range(start_line, end_line + 1):
                if i <= len(params.all_lines):
                    line_content = params.all_lines[i - 1]
                    marker = " -> " if i == params.line_no else "    "
                    context_lines.append(f"{marker}{i:3d}: {line_content}")

        context_str = "\n".join(context_lines) if context_lines else ""
        suggestions_str = "\n".join(f"  • {s}" for s in params.suggestions)

        return f"{params.message}:\n{context_str}\nSuggestions:\n{suggestions_str}"
