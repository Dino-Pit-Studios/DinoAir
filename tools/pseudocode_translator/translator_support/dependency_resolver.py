"""
Dependency analysis support module for translator.

This module provides a lightweight DependencyResolver that encapsulates AST parsing
and analysis to discover top-level defined names and import requirements from blocks
of code. It is designed to preserve behavior of translator dependency handling while
isolating policy and reducing nesting in translator.py.

Behavior-preservation constraints:
- No imports from translator.py (avoids cycles).
- Uses stdlib ast; will use parse_cached if available to preserve performance.
- On SyntaxError, analysis returns empty lists without raising.
"""

import ast
from typing import Any

try:
    # Prefer absolute import path to avoid relative ambiguity when used externally.
    from ..ast_cache import parse_cached  # type: ignore
except Exception:  # pragma: no cover
    parse_cached = None  # type: ignore[assignment]


class DependencyResolver:
    """
    Encapsulates AST-based dependency analysis for code blocks.

    - Defined names: top-level function, async function, class definitions, and simple
      top-level assignments to Name targets.
    - Required imports: import statements discovered anywhere in the AST.
    """

    def __init__(self, use_cache: bool = True) -> None:
        """
        Initialize the resolver.

        Args:
            use_cache: When True and parse_cached is available, use it for parsing.
        """
        self.use_cache = bool(use_cache)

    def _parse(self, code: str):
        """Parse code using parse_cached if enabled, else ast.parse."""
        if self.use_cache and parse_cached is not None:
            return parse_cached(code)
        return ast.parse(code)

    def analyze_block(self, code: str) -> dict[str, list[str]]:
        """
        Analyze a single code string.

        Returns:
            A dict with:
              - "defined_names": list[str] of top-level names defined in the block
              - "required_imports": list[str] of import requirements formatted like
                'import x' or 'from m import n'
        """
        if not isinstance(code, str):
            code = "" if code is None else str(code)
        try:
            tree = self._parse(code)
        except SyntaxError:
            return {"defined_names": [], "required_imports": []}

        defined: list[str] = []
        # Collect top-level definitions from module body
        for node in getattr(tree, "body", []):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                defined.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined.append(target.id)

        req_imports: list[str] = []
        # Collect imports anywhere in the tree (matches previous behavior)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    req_imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    req_imports.append(f"from {module} import {alias.name}")

        return {"defined_names": defined, "required_imports": req_imports}

    def analyze_blocks(self, blocks: list[Any]) -> list[dict[str, list[str]]]:
        """
        Analyze a list of block-like objects.

        Each block is expected to have a .text attribute; if absent, .content is used.
        Returns a list of analysis results in the same order as the input.
        """
        results: list[dict[str, list[str]]] = []
        for blk in blocks:
            text = getattr(blk, "text", None)
            if text is None:
                text = getattr(blk, "content", "")
            results.append(self.analyze_block(text or ""))
        return results
