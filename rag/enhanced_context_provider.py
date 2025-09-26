"""
Enhanced Context Provider for RAG Integration
Includes improvements: better error handling, input validation,
search history, suggestions, and export functionality.
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, deque
from datetime import datetime
from typing import Any

from database.file_search_db import FileSearchDB
from utils.logger import Logger

from .vector_search import VectorSearchEngine


class SearchHistory:
    """Manages search history and suggestions"""

    def __init__(self, max_history: int = 100):
        self.history: deque[dict[str, Any]] = deque(maxlen=max_history)
        self.term_frequency: Counter[str] = Counter()

    def add_query(self, query: str, result_count: int) -> None:
        """Add a query to history"""
        entry: dict[str, Any] = {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "result_count": result_count,
        }
        self.history.append(entry)

        # Update term frequency for suggestions
        terms: list[str] = query.lower().split()
        self.term_frequency.update(terms)

    def get_suggestions(self, partial_query: str, limit: int = 5) -> list[str]:
        """Get query suggestions based on history"""
        if not partial_query:
            return []

        partial_lower = partial_query.lower()
        suggestions: list[str] = []

        # Recent queries matching partial
        for entry in reversed(self.history):
            if entry["query"].lower().startswith(partial_lower):
                if entry["query"] not in suggestions:
                    suggestions.append(entry["query"])
                if len(suggestions) >= limit:
                    break

        # Popular terms matching partial
        if len(suggestions) < limit:
            for term, _ in self.term_frequency.most_common():
                if term.startswith(partial_lower) and term not in suggestions:
                    suggestions.append(term)
                if len(suggestions) >= limit:
                    break

        return suggestions[:limit]

    def get_recent_queries(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent search queries"""
        recent: list[dict[str, Any]] = list(reversed(list(self.history)))
        return recent[:limit]

    def clear(self) -> None:
        """Clear search history"""
        self.history.clear()
        self.term_frequency.clear()


class InputValidator:
    """Validates and sanitizes user inputs"""

    @staticmethod
    def validate_query(query: str) -> tuple[bool, str, str | None]:
        """
        Validate search query.
        Returns: (is_valid, sanitized_query, error_message)
        """
        if not query:
            return False, "", "Query cannot be empty"

        # Remove excessive whitespace
        sanitized = " ".join(query.split())

        # Check length
        if len(sanitized) < 2:
            return False, sanitized, "Query too short (minimum 2 characters)"

        if len(sanitized) > 500:
            return False, sanitized[:500], "Query too long (maximum 500 characters)"

        # Remove potentially harmful characters
        sanitized = re.sub(r"[<>{}\\]", "", sanitized)

        return True, sanitized, None

    @staticmethod
    def validate_file_path(file_path: str) -> tuple[bool, str | None]:
        """
        Validate file path.
        Returns: (is_valid, error_message)
        """
        if not file_path:
            return False, "Invalid file path"

        # Basic path validation
        if ".." in file_path or file_path.startswith("/"):
            return False, "Invalid file path format"

        return True, None

    @staticmethod
    def validate_file_types(
        file_types: list[str] | None,
    ) -> tuple[bool, list[str] | None, str | None]:
        """
        Validate file type filter.
        Returns: (is_valid, sanitized_types, error_message)
        """
        if file_types is None:
            return True, None, None

        # file_types is a list[str] at this point
        valid_extensions = {
            ".txt",
            ".pdf",
            ".docx",
            ".doc",
            ".md",
            ".json",
            ".csv",
            ".py",
            ".js",
            ".java",
            ".cpp",
            ".c",
            ".cs",
            ".rb",
            ".go",
            ".php",
            ".swift",
            ".kt",
            ".rs",
            ".ts",
            ".jsx",
            ".tsx",
        }

        sanitized: list[str] = []
        for ext in file_types:
            ext_lower = ext.lower()
            if not ext_lower.startswith("."):
                ext_lower = "." + ext_lower
            if ext_lower in valid_extensions:
                sanitized.append(ext_lower)

        if not sanitized and file_types:
            return False, None, "No valid file types specified"

        return True, sanitized if sanitized else None, None


class EnhancedContextProvider:
    """
    Enhanced context provider with improved features:
    - Better error handling
    - Input validation
    - Search history and suggestions
    - Export functionality
    - Improved relevance scoring
    """

    def __init__(self, user_name: str = "default_user"):
        """Initialize the enhanced context provider"""
        self.user_name = user_name
        self.logger = Logger()

        # Initialize components
        try:
            self.search_engine = VectorSearchEngine(user_name)
            self.file_search_db = FileSearchDB(user_name)
            self.search_history = SearchHistory()
            self.validator = InputValidator()

            # Configuration
            self.max_context_length = 2000
            self.max_results = 10
            self.min_score_threshold = 0.5

            # Export formats
            self.export_formats = ["json", "csv", "markdown"]

            self.logger.info("Enhanced context provider initialized successfully")

        except Exception as e:
            self.logger.error("Failed to initialize context provider: %s", str(e))
            raise

    def get_context_for_query(
        self,
        query: str,
        file_types: list[str] | None = None,
        max_results: int | None = None,
        include_suggestions: bool = True,
    ) -> dict[str, Any]:
        """
        Get relevant file context for a given query with enhanced features.

        Returns:
            Dictionary containing:
                - success: bool
                - results: List of context items
                - suggestions: List of related queries (if enabled)
                - error: Error message (if failed)
        """
        try:
            # Validate query
            is_valid, sanitized_query, error_msg = self.validator.validate_query(query)
            if not is_valid:
                return {
                    "success": False,
                    "error": f"Invalid query: {error_msg}",
                    "results": [],
                }

            # Validate file types
            is_valid, sanitized_types, error_msg = self.validator.validate_file_types(file_types)
            if not is_valid:
                return {
                    "success": False,
                    "error": f"Invalid file types: {error_msg}",
                    "results": [],
                }

            # Perform search
            results = self.search_engine.hybrid_search(
                query=sanitized_query,
                top_k=max_results or self.max_results,
                file_types=sanitized_types,
                rerank=True,
            )

            # Filter by improved relevance scoring
            filtered_results = self._apply_relevance_scoring(results)

            # Build context items
            context_items: list[dict[str, Any]] = []
            for result in filtered_results:
                try:
                    context_item = self._build_context_item(result)
                    context_items.append(context_item)
                except Exception as e:
                    self.logger.error("Error building context item: %s", str(e))
                    continue

            # Add to search history
            self.search_history.add_query(sanitized_query, len(context_items))

            # Get suggestions if requested
            suggestions: list[str] = []
            if include_suggestions and context_items:
                suggestions = self._generate_suggestions(sanitized_query, context_items)

            return {
                "success": True,
                "results": context_items,
                "suggestions": suggestions,
                "query": sanitized_query,
                "result_count": len(context_items),
            }

        except Exception as e:
            self.logger.error("Failed to get context: %s", str(e))
            return {
                "success": False,
                "error": f"Search failed: {str(e)}",
                "results": [],
            }

    def _apply_relevance_scoring(self, results: list[Any]) -> list[Any]:
        """Apply improved relevance scoring and filtering"""
        if not results:
            return []

        # Calculate score statistics
        scores = [r.score for r in results]
        if not scores:
            return []

        avg_score = sum(scores) / len(scores)

        # Dynamic threshold based on score distribution
        dynamic_threshold = max(
            self.min_score_threshold,
            avg_score * 0.7,  # Keep results above 70% of average
        )

        # Filter and boost scores
        filtered: list[Any] = []
        for result in results:
            # Apply threshold
            if result.score < dynamic_threshold:
                continue

            # Boost score based on factors
            boost = 0.0

            # Recency boost (if file modified recently)
            # File type boost (prefer documents over code for general queries)
            # Length boost (prefer substantial content)
            if len(result.content) > 100:
                boost += 0.05

            # Apply boost (max 10% increase)
            result.score = min(1.0, result.score + boost)
            filtered.append(result)

        # Sort by boosted score
        filtered.sort(key=lambda x: getattr(x, "score", 0.0), reverse=True)

        return filtered

    def _build_context_item(self, result: Any) -> dict[str, Any]:
        """Build enhanced context item with metadata"""
        context_item: dict[str, Any] = {
            "file_path": result.file_path,
            "file_name": os.path.basename(result.file_path),
            "content": result.content,
            "chunk_index": result.chunk_index,
            "score": result.score,
            "match_type": result.match_type,
            "relevance_level": self._get_relevance_level(result.score),
        }

        # Add file metadata
        try:
            file_info = self.file_search_db.get_file_by_path(result.file_path)
            if file_info:
                context_item.update(
                    {
                        "file_type": file_info.get("file_type", "unknown"),
                        "file_size": file_info.get("size", 0),
                        "last_modified": file_info.get("modified_date", ""),
                        "file_hash": file_info.get("file_hash", ""),
                    }
                )
        except Exception as e:
            self.logger.debug("Could not retrieve file metadata: %s", str(e))

        # Add content preview with highlighting
        context_item["preview"] = self._create_preview(
            result.content, getattr(result, "query_terms", [])
        )

        return context_item

    def _get_relevance_level(self, score: float) -> str:
        """Convert score to human-readable relevance level"""
        if score >= 0.9:
            return "Excellent"
        if score >= 0.7:
            return "Good"
        if score >= 0.5:
            return "Fair"
        return "Weak"

    def _create_preview(self, content: str, highlight_terms: list[str] = None) -> str:
        """Create content preview with optional term highlighting"""
        preview = content[:200]
        if len(content) > 200:
            preview += "..."

        # Simple highlighting (in real app, use proper HTML/markdown)
        if highlight_terms:
            for term in highlight_terms:
                preview = preview.replace(term, f"**{term}**")

        return preview

    def _generate_suggestions(self, query: str, results: list[dict[str, Any]]) -> list[str]:
        """Generate query suggestions based on results"""
        suggestions = []

        # Get suggestions from search history
        history_suggestions = self.search_history.get_suggestions(query, limit=3)
        suggestions.extend(history_suggestions)

        # Extract key terms from top results
        if results:
            term_counter = Counter()
            for result in results[:3]:  # Top 3 results
                # Extract nouns and important terms from content
                words = result["content"].lower().split()
                important_words = [w for w in words if len(w) > 4 and w not in query.lower()]
                term_counter.update(important_words)

            # Add most common terms as suggestions
            for term, _ in term_counter.most_common(3):
                suggestion = f"{query} {term}"
                if suggestion not in suggestions:
                    suggestions.append(suggestion)

        return suggestions[:5]  # Limit total suggestions

    def export_results(
        self,
        results: list[dict[str, Any]],
        format: str = "json",
        file_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Export search results to file.

        Args:
            results: Search results to export
            format: Export format ('json', 'csv', 'markdown')
            file_path: Optional output file path

        Returns:
            Dictionary with export status
        """
        try:
            if format not in self.export_formats:
                return {"success": False, "error": f"Unsupported format: {format}"}

            if not results:
                return {"success": False, "error": "No results to export"}

            # Generate default filename if not provided
            if not file_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_path = f"search_results_{timestamp}.{format}"

            # Export based on format
            if format == "json":
                self._export_json(results, file_path)
            elif format == "csv":
                self._export_csv(results, file_path)
            elif format == "markdown":
                self._export_markdown(results, file_path)

            return {
                "success": True,
                "file_path": file_path,
                "format": format,
                "result_count": len(results),
            }

        except Exception as e:
            self.logger.error("Export failed: %s", str(e))
            return {"success": False, "error": f"Export failed: {str(e)}"}

    def _export_json(self, results: list[dict[str, Any]], file_path: str) -> None:
        """Export results as JSON"""
        allowed_filenames = {"export.json", "results.json", "data_export.json"}
        filename = os.path.basename(file_path)
        if filename not in allowed_filenames:
            raise ValueError(f"Invalid file name: {filename}")
        safe_dir = os.getcwd()
        safe_path = os.path.join(safe_dir, filename)

        export_data = {
            "export_date": datetime.now().isoformat(),
            "result_count": len(results),
            "results": results,
        }

        with open(safe_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

    def _export_csv(self, results: list[dict[str, Any]], file_path: str) -> None:
        """Export results as CSV"""
        if not results:
            return

        # Validate file path input to prevent path traversal
        filename = os.path.basename(file_path)
        allowed_filenames = ["results.csv", "export.csv"]
        if filename not in allowed_filenames:
            raise ValueError(f"Export filename '{filename}' is not permitted.")

        # Get all unique keys
        all_keys = set()
        for result in results:
            all_keys.update(result.keys())

        # Write CSV
        safe_path = os.path.join(os.getcwd(), filename)
        with open(safe_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=sorted(all_keys))
            writer.writeheader()
            writer.writerows(results)

    def get_search_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent search history"""
        return self.search_history.get_recent_queries(limit)

    def clear_search_history(self) -> None:
        """Clear search history"""
        self.search_history.clear()
        self.logger.info("Search history cleared")

    def get_query_suggestions(self, partial_query: str) -> list[str]:
        """Get query suggestions for autocomplete"""
        return self.search_history.get_suggestions(partial_query)

    def get_stats(self) -> dict[str, Any]:
        """Get enhanced statistics about indexed content"""
        try:
            base_stats = super().get_stats() if hasattr(super(), "get_stats") else {}

            # Add search history stats
            history_queries = self.search_history.get_recent_queries(100)

            return {
                **base_stats,
                "search_history_count": len(history_queries),
                "popular_terms": self.search_history.term_frequency.most_common(10),
                "average_results_per_search": (
                    sum(q["result_count"] for q in history_queries) / len(history_queries)
                    if history_queries
                    else 0
                ),
            }

        except Exception as e:
            self.logger.error("Failed to get stats: %s", str(e))
            return {}

    def validate_index_health(self) -> dict[str, Any]:
        """Validate the health of the search index"""
        try:
            issues = []

            # Check database connection
            try:
                stats = self.file_search_db.get_indexed_files_stats()
                if not stats:
                    issues.append("Cannot retrieve index statistics")
            except Exception as e:
                issues.append(f"Database connection issue: {str(e)}")

            # Check for orphaned entries
            # This would need implementation in the database layer

            # Check embedding generator
            try:
                test_embedding = self.search_engine.embedding_generator.generate_embedding("test")
                if test_embedding is None:
                    issues.append("Embedding generator not functioning")
            except Exception as e:
                issues.append(f"Embedding generator issue: {str(e)}")

            return {
                "healthy": len(issues) == 0,
                "issues": issues,
                "checked_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "healthy": False,
                "issues": [f"Health check failed: {str(e)}"],
                "checked_at": datetime.now().isoformat(),
            }
