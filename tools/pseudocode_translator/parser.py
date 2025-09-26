"""
Parser module for the Pseudocode Translator

Handles parsing of mixed English/Python pseudocode input
"""

import ast
import re
from collections.abc import Iterator
from typing import Any

# Import models and exceptions
try:
    from .exceptions import ErrorContext, ParsingError
    from .models import BlockType, CodeBlock, ParseError, ParseResult
except ImportError:
    # Fallback for when run as a script
    from exceptions import ErrorContext, ParsingError

    from models import BlockType, CodeBlock, ParseError, ParseResult


class ParserModule:
    """Main parser class that processes mixed English/Python pseudocode"""

    # Pre-compiled regex patterns for better performance
    _PYTHON_KEYWORDS_RE = re.compile(
        r"\b(def|class|import|from|if|elif|else|for|while|return|try|except|"
        r"finally|with|as|lambda|yield|assert|break|continue|pass|raise|del|"
        r"global|nonlocal|in|is|and|or|not)\b"
    )
    _PYTHON_OPERATORS_RE = re.compile(r"[\+\-\*\/\%\=\<\>\!\&\|\^\~]+")
    _PYTHON_DELIMITERS_RE = re.compile(r"[\(\)\[\]\{\}\,\:\;]")
    _INDENT_PATTERN_RE = re.compile(r"^[ \t]*")
    _COMMENT_PATTERN_RE = re.compile(r"^\s*#.*$")
    _DOCSTRING_PATTERN_RE = re.compile(r'^\s*["\']["\']["\'].*["\']["\']["\']')

    # Additional pre-compiled patterns used in hot paths
    _FUNCTION_CALL_RE = re.compile(r"\w+\s*\(.*\)")
    _VARIABLE_ASSIGN_RE = re.compile(r"\w+\s*=\s*.+")
    _IMPORT_RE = re.compile(r"^\s*(import|from)\s+")
    _DEF_RE = re.compile(r"^\s*def\s+")
    _CLASS_RE = re.compile(r"^\s*class\s+")
    _INDENT_EXTRACT_RE = re.compile(r"^([ \t]*)")
    _DEF_CLASS_IMPORT_RE = re.compile(r"^(def|class|import|from)\s+")
    _WHITESPACE_RE = re.compile(r"^(\s*)")

    # English pattern regexes
    _ENGLISH_CREATE_RE = re.compile(
        r"^(create|make|define|set|get|calculate|return|display|show|print)",
        re.IGNORECASE,
    )
    _ENGLISH_MODAL_RE = re.compile(
        r"(should|must|need to|have to|will|would|can|could)", re.IGNORECASE
    )
    _ENGLISH_TEMPORAL_RE = re.compile(r"(then|next|after|before|when|while|until)", re.IGNORECASE)
    _ENGLISH_ARTICLE_RE = re.compile(r"(a|an|the|this|that|these|those)\s+\w+", re.IGNORECASE)
    _ENGLISH_CONJUNC_RE = re.compile(r"\b(and|or|but|if|then|else)\b", re.IGNORECASE)
    _SENTENCE_STRUCT_RE = re.compile(r"^[A-Z].*[.!?]$")
    _PYTHON_SYNTAX_RE = re.compile(r"[(){}\[\]:]")
    _WORD_RE = re.compile(r"\b\w+\b")

    def __init__(self):
        """Initialize the parser module"""
        self.errors: list[ParsingError] = []
        self.warnings: list[str] = []
        self.current_line = 1
        self.input_text = ""

    def parse(self, input_text: str) -> list[CodeBlock]:
        """
        Main parsing method that converts input text to CodeBlock list

        Args:
            input_text: Mixed English/Python pseudocode text

        Returns:
            List of CodeBlock objects
        """
        if not input_text or not input_text.strip():
            return []

        # Reset errors and warnings for new parse
        self.errors = []
        self.warnings = []
        self.input_text = input_text
        self.current_line = 1

        try:
            # Split into blocks
            raw_blocks = self._identify_blocks(input_text)
        except Exception as e:
            error = ParsingError(
                "Failed to identify code blocks",
                block_content=input_text[:200],  # First 200 chars
                cause=e,
            )
            error.add_suggestion("Check for severe syntax errors")
            error.add_suggestion("Ensure the input is valid pseudocode")
            self.errors.append(error)
            return []

        # Process each block
        code_blocks = []
        current_line = 1

        for block_text in raw_blocks:
            if not block_text.strip():
                continue

            # Calculate line numbers
            line_count = block_text.count("\n") + 1
            end_line = current_line + line_count - 1

            # Classify the block
            block_type = self._classify_block(block_text)

            # Extract metadata
            metadata = self._extract_metadata(block_text)

            # Create CodeBlock
            try:
                code_block = CodeBlock(
                    type=block_type,
                    content=block_text,
                    line_numbers=(current_line, end_line),
                    metadata=metadata,
                    context=self._get_context(input_text, current_line, end_line),
                )
                code_blocks.append(code_block)
            except ValueError as e:
                # Create detailed parsing error
                context = ErrorContext(
                    line_number=current_line,
                    code_snippet=block_text[:100],  # First 100 chars
                    metadata={
                        "block_type": (block_type.value if block_type else "unknown"),
                        "line_range": f"{current_line}-{end_line}",
                    },
                )

                error = ParsingError(
                    message=str(e),
                    block_content=block_text,
                    block_type=(block_type.value if block_type else "unknown"),
                    context=context,
                    cause=e,
                )

                # Add recovery suggestion
                error.add_suggestion("Check the block structure and syntax")

                self.errors.append(error)

            current_line = end_line + 1

        return code_blocks

    def _identify_blocks(self, text: str) -> list[str]:
        """
        Split text into logical blocks based on structure

        Args:
            text: Input text to split

        Returns:
            List of block strings
        """
        if not text.strip():
            return []

        # Split text into blocks using blank lines as delimiters
        blocks = []
        current_block = []
        lines = text.splitlines()

        for line in lines:
            if line.strip():  # Non-empty line
                current_block.append(line)
            elif current_block:
                blocks.append("\n".join(current_block))
                current_block = []

        # Add final block if it exists
        if current_block:
            blocks.append("\n".join(current_block))

        # If no blocks were created (all text was one continuous block),
        # return the entire text as a single block
        if not blocks:
            return [text]

        return blocks

    def _classify_block(self, block: str) -> BlockType:
        """
        Determine the type of a code block

        Args:
            block: Block text to classify

        Returns:
            BlockType enum value
        """
        lines = block.strip().splitlines()
        if not lines:
            return BlockType.COMMENT

        python_score = 0
        english_score = 0
        total_lines = len(lines)

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check if it's a comment
            if self._COMMENT_PATTERN_RE.match(line):
                # Comments are considered separately
                continue

            # Calculate scores
            line_python_score = self._calculate_python_score(stripped)
            line_english_score = self._calculate_english_score(stripped)

            if line_python_score > line_english_score:
                python_score += 1
            else:
                english_score += 1

        # Determine block type based on scores
        if total_lines == 0:
            return BlockType.COMMENT

        python_ratio = python_score / total_lines

        if python_ratio >= 0.8:
            return BlockType.PYTHON
        if python_ratio <= 0.2:
            return BlockType.ENGLISH
        return BlockType.MIXED

    def _extract_metadata(self, block: str) -> dict[str, Any]:
        """
        Extract metadata from a block

        Args:
            block: Block text to analyze

        Returns:
            Dictionary of metadata
        """
        metadata = {
            "has_imports": False,
            "has_functions": False,
            "has_classes": False,
            "indentation_type": None,
            "max_indent_level": 0,
            "has_docstring": False,
            "likely_complete": True,
            "has_comments": False,
            "line_count": len(block.splitlines()),
        }

        lines = block.splitlines()
        indent_chars = set()
        max_indent = 0

        for line in lines:
            max_indent = self._process_line_metadata(line, metadata, indent_chars, max_indent)

        metadata["max_indent_level"] = max_indent
        if indent_chars:
            metadata["indentation_type"] = "tabs" if "\t" in indent_chars else "spaces"

        self._finalize_metadata(metadata, block)
        return metadata

    def _process_line_metadata(
        self, line: str, metadata: dict[str, Any], indent_chars: set[str], current_max_indent: int
    ) -> int:
        """
        Process a single line of code to extract metadata flags and track indentation.

        Args:
            line: A single line from the code block.
            metadata: Dictionary of metadata being built.
            indent_chars: Set collecting all indentation characters encountered.
            current_max_indent: Current maximum indentation level.

        Returns:
            The updated maximum indentation level for the block.
        """

        # Check for imports
        if self._IMPORT_RE.match(line):
            metadata["has_imports"] = True

        # Check for functions
        if self._DEF_RE.match(line):
            metadata["has_functions"] = True

        # Check for classes
        if self._CLASS_RE.match(line):
            metadata["has_classes"] = True

        # Check for comments
        if self._COMMENT_PATTERN_RE.match(line):
            metadata["has_comments"] = True

        # Check indentation
        indent_match = self._INDENT_EXTRACT_RE.match(line)
        if indent_match:
            indent = indent_match.group(1)
            if indent:
                indent_chars.update(indent)
                current_max_indent = max(current_max_indent, len(indent))

        return current_max_indent

    def _finalize_metadata(self, metadata: dict[str, Any], block: str) -> None:
        """
        Finalize metadata by assessing docstrings, completeness, and indentation details.

        Args:
            metadata: The metadata dictionary collected so far.
            block: The full text block that was analyzed.

        Returns:
            None. Updates metadata in place.
        """
        # Check for docstring
        if self._DOCSTRING_RE.search(block):
            metadata["has_docstring"] = True

        # Determine completeness
        if not block.strip().endswith(":"):
            metadata["likely_complete"] = False

        # Split block into lines and determine indentation characters and max indent
        lines = block.splitlines()
        indent_chars = set()
        max_indent = 0
        for line in lines:
            leading = line[: len(line) - len(line.lstrip())]
            if leading:
                indent_chars.update(leading)
                max_indent = max(max_indent, len(leading))

        # Determine indentation type
        if " " in indent_chars and "\t" not in indent_chars:
            metadata["indentation_type"] = "spaces"
        elif "\t" in indent_chars and " " not in indent_chars:
            metadata["indentation_type"] = "tabs"
        elif " " in indent_chars and "\t" in indent_chars:
            metadata["indentation_type"] = "mixed"
            self.warnings.append("Mixed indentation detected (tabs and spaces)")

        # Assuming 4 spaces per level
        metadata["max_indent_level"] = max_indent // 4

        # Check for docstrings
        if self._DOCSTRING_PATTERN_RE.search(block, re.MULTILINE):
            metadata["has_docstring"] = True

        # Check if block seems incomplete
        if block.strip().endswith(":") and not any(line.strip() for line in lines[1:]):
            metadata["likely_complete"] = False

        return metadata

    def score_line_language(self, line: str) -> float:
        """Return Python-language score for the given line. Stable public API."""
        return self._calculate_python_score(line)

    def _calculate_python_score(self, line: str) -> float:
        """
        Calculate how "Python-like" a line is using AST-based analysis

        Args:
            line: Line to analyze

        Returns:
            Score from 0.0 to 1.0
        """
        score = 0.0

        # Check for Python keywords (higher weight)
        if self._PYTHON_KEYWORDS_RE.search(line):
            score += 0.3

        # Check for Python operators
        if self._PYTHON_OPERATORS_RE.search(line):
            score += 0.15

        # Check for Python delimiters
        if self._PYTHON_DELIMITERS_RE.search(line):
            score += 0.15

        # Check for function/method calls
        if self._FUNCTION_CALL_RE.search(line):
            score += 0.1

        # Check for variable assignments (including walrus)
        if self._VARIABLE_ASSIGN_RE.search(line) or ":=" in line:
            score += 0.1

        # Check for match statement (Python 3.10+)
        match_pattern = re.match(r"^\s*match\s+.+:", line)
        case_pattern = re.match(r"^\s*case\s+", line)
        if match_pattern or case_pattern:
            score += 0.2

        # Check if it's valid Python syntax (higher weight for AST validity)
        if self._is_valid_python(line):
            score += 0.2

        return min(score, 1.0)

    def _calculate_english_score(self, line: str) -> float:
        """
        Calculate how "English-like" a line is

        Args:
            line: Line to analyze

        Returns:
            Score from 0.0 to 1.0
        """
        score = 0.0

        # Check English patterns using pre-compiled regexes
        if self._ENGLISH_CREATE_RE.search(line):
            score += 0.2
        if self._ENGLISH_MODAL_RE.search(line):
            score += 0.2
        if self._ENGLISH_TEMPORAL_RE.search(line):
            score += 0.2
        if self._ENGLISH_ARTICLE_RE.search(line):
            score += 0.2
        if self._ENGLISH_CONJUNC_RE.search(line):
            score += 0.2

        # Check for sentence-like structure
        if self._SENTENCE_STRUCT_RE.match(line.strip()):
            score += 0.2

        # Penalize Python-specific syntax
        if self._PYTHON_SYNTAX_RE.search(line):
            score -= 0.1

        # Check word count (English tends to have more words)
        word_count = len(self._WORD_RE.findall(line))
        if word_count > 5:
            score += 0.1

        return max(0.0, min(score, 1.0))

    def _is_ast_transition(self, prev_line: str, curr_line: str) -> bool:
        """
        Check if there's a transition between English and Python using AST

        Args:
            prev_line: Previous line
            curr_line: Current line

        Returns:
            True if this represents a transition point
        """
        prev_is_python = self._is_valid_python(prev_line.strip())
        curr_is_python = self._is_valid_python(curr_line.strip())

        # Transition happens when validity changes
        if prev_is_python != curr_is_python:
            # But also check scores for mixed lines
            prev_score = self._calculate_python_score(prev_line.strip())
            curr_score = self._calculate_python_score(curr_line.strip())

            # Significant change in Python score indicates transition
            return abs(prev_score - curr_score) > 0.5

        return False

    def _is_valid_python(self, line: str) -> bool:
        """
        Check if a line is valid Python syntax using AST

        Args:
            line: Line to check

        Returns:
            True if valid Python syntax
        """
        if not line:
            return True

        # Skip comments
        if line.strip().startswith("#"):
            return True

        try:
            # Try to parse as a statement
            ast.parse(line)
            return True
        except SyntaxError:
            try:
                # Try to parse as an expression
                ast.parse(line, mode="eval")
                return True
            except SyntaxError:
                # Check if it might be part of a larger construct
                try:
                    # Try with a colon (for statements like if/for/def)
                    if not line.endswith(":"):
                        ast.parse(line + ":")
                        return True
                except SyntaxError:
                    pass

                # Check for common incomplete patterns
                incomplete_patterns = [
                    r"^\s*(if|elif|while|for|def|class|try|except|with)\s+.*$",
                    r"^\s*\w+\s*\($",  # Function call start
                    r"^\s*[\[\{].*$",  # List/dict start
                ]

                for pattern in incomplete_patterns:
                    if re.match(pattern, line):
                        return True

        return False

    def _get_context(
        self, full_text: str, start_line: int, end_line: int, context_lines: int = 2
    ) -> str:
        """
        Get surrounding context for a block

        Args:
            full_text: Complete input text
            start_line: Starting line number (1-based)
            end_line: Ending line number (1-based)
            context_lines: Number of lines to include before/after

        Returns:
            Context string
        """
        lines = full_text.splitlines()

        # Calculate context boundaries
        context_start = max(0, start_line - 1 - context_lines)
        context_end = min(len(lines), end_line + context_lines)

        # Get context lines
        context = lines[context_start:context_end]

        return "\n".join(context)

    def get_parse_result(self, input_text: str) -> ParseResult:
        """
        Parse input and return a ParseResult object

        Args:
            input_text: Mixed English/Python pseudocode text

        Returns:
            ParseResult containing blocks, errors, and warnings
        """
        blocks = self.parse(input_text)

        # Convert ParsingError objects to ParseError for compatibility
        parse_errors = []
        for error in self.errors:
            if isinstance(error, ParsingError):
                parse_error = ParseError(
                    message=error.message,
                    line_number=error.context.line_number,
                    block_content=error.context.code_snippet or "",
                )
                parse_errors.append(parse_error)
            else:
                parse_errors.append(error)

        return ParseResult(blocks=blocks, errors=parse_errors, warnings=self.warnings)

    def streaming_parse(self, input_text: str, chunk_size: int = 4096) -> Iterator[CodeBlock]:
        """
        Parse input text in a streaming fashion

        Args:
            input_text: Mixed English/Python pseudocode text
            chunk_size: Size of chunks to process

        Yields:
            CodeBlock objects as they are parsed
        """
        if not input_text or not input_text.strip():
            return

        # Reset state for streaming
        self.errors = []
        self.warnings = []

        # Split into chunks at logical boundaries
        chunks = self._split_into_stream_chunks(input_text, chunk_size)

        # Track state across chunks
        current_line = 1
        context_buffer = []

        for chunk_text in chunks:
            if not chunk_text.strip():
                continue

            # Add context from previous chunk
            if context_buffer:
                chunk_with_context = "\n".join(context_buffer) + "\n" + chunk_text
            else:
                chunk_with_context = chunk_text

            # Parse the chunk
            chunk_blocks = self._parse_chunk(chunk_with_context, current_line)

            # Yield blocks (excluding context blocks already yielded)
            start_index = len(context_buffer) if context_buffer else 0
            yield from chunk_blocks[start_index:]

            # Update line count
            current_line += chunk_text.count("\n") + 1

            # Keep last few lines as context for next chunk
            chunk_lines = chunk_text.splitlines()
            context_buffer = chunk_lines[-5:] if len(chunk_lines) > 5 else []

    def _split_into_stream_chunks(self, text: str, chunk_size: int) -> list[str]:
        """
        Split text into chunks for streaming, respecting code boundaries

        Args:
            text: Input text
            chunk_size: Target chunk size

        Returns:
            List of text chunks
        """
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        lines = text.splitlines(keepends=True)
        current_chunk = []
        current_size = 0

        for line in lines:
            line_size = len(line.encode("utf-8"))

            # Check if adding this line exceeds chunk size
            if current_size + line_size > chunk_size and current_chunk:
                # Find a good split point
                split_point = self._find_chunk_split_point(current_chunk)

                if split_point > 0:
                    # Split at the found point
                    chunks.append("".join(current_chunk[:split_point]))
                    current_chunk = current_chunk[split_point:]
                    current_size = sum(len(line.encode("utf-8")) for line in current_chunk)
                else:
                    # No good split point, take the whole chunk
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_size = 0

            current_chunk.append(line)
            current_size += line_size

        # Add remaining chunk
        if current_chunk:
            chunks.append("".join(current_chunk))

        return chunks

    def _find_chunk_split_point(self, lines: list[str]) -> int:
        """
        Find a good point to split a chunk of lines

        Args:
            lines: List of lines to split

        Returns:
            Index to split at
        """
        # Look for natural boundaries from the end
        for i in range(len(lines) - 1, len(lines) // 2, -1):
            line = lines[i].strip()

            # Good split points:
            # - Empty lines
            # - Function/class definitions (start of new block)
            # - Import statements
            # - Lines that complete a block (dedented)
            if (
                not line
                or self._DEF_CLASS_IMPORT_RE.match(line)
                or (
                    i > 0
                    and self._get_indent_level(lines[i]) < self._get_indent_level(lines[i - 1])
                )
            ):
                return i

        return len(lines) // 2  # Default to middle

    def _get_indent_level(self, line: str) -> int:
        """Get the indentation level of a line"""
        match = self._WHITESPACE_RE.match(line)
        return len(match.group(1)) if match else 0

    def _parse_chunk(self, chunk_text: str, start_line: int) -> list[CodeBlock]:
        """
        Parse a single chunk of text

        Args:
            chunk_text: Text chunk to parse
            start_line: Starting line number for this chunk

        Returns:
            List of parsed code blocks
        """
        # Use existing parsing logic but adjusted for chunks
        raw_blocks = self._identify_blocks(chunk_text)
        code_blocks = []

        current_line = start_line

        for block_text in raw_blocks:
            if not block_text.strip():
                continue

            line_count = block_text.count("\n") + 1
            end_line = current_line + line_count - 1

            block_type = self._classify_block(block_text)
            metadata = self._extract_metadata(block_text)

            try:
                code_block = CodeBlock(
                    type=block_type,
                    content=block_text,
                    line_numbers=(current_line, end_line),
                    metadata=metadata,
                    context=None,  # Skip context for streaming
                )
                code_blocks.append(code_block)
            except ValueError as e:
                # Create detailed parsing error for streaming
                context = ErrorContext(line_number=current_line, code_snippet=block_text[:100])

                error = ParsingError(
                    message=str(e), block_content=block_text, context=context, cause=e
                )

                self.errors.append(error)

            current_line = end_line + 1

        return code_blocks
