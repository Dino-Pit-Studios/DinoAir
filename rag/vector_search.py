"""
Vector search module for DinoAir 2.0 RAG File Search system.
Provides vector similarity search and hybrid search capabilities.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import numpy as np

from database.file_search_db import FileSearchDB

# Import DinoAir components
from utils.logger import Logger

# Import RAG components
from .embedding_generator import EmbeddingGenerator, get_embedding_generator
from .search_common import compute_cosine_scores, extract_keywords  # shared utilities


@dataclass
class SearchResult:
    """Represents a search result with metadata."""

    chunk_id: str
    file_id: str
    file_path: str
    content: str
    score: float
    chunk_index: int
    start_pos: int
    end_pos: int
    file_type: str | None = None
    metadata: dict[str, Any] | None = None
    match_type: str = "vector"  # 'vector', 'keyword', or 'hybrid'


class VectorSearchEngine:
    """
    Handles vector similarity search and hybrid search operations.
    Combines semantic search with keyword matching for better results.
    """

    # Default search parameters
    DEFAULT_TOP_K = 10
    DEFAULT_SIMILARITY_THRESHOLD = 0.5
    DEFAULT_VECTOR_WEIGHT = 0.7  # Weight for vector similarity
    DEFAULT_KEYWORD_WEIGHT = 0.3  # Weight for keyword match

    def __init__(
        self,
        user_name: str | None = None,
        embedding_generator: EmbeddingGenerator | None = None,
    ):
        """
        Initialize the VectorSearchEngine.

        Args:
            user_name: Username for database operations
            embedding_generator: Optional pre-configured embedding generator
        """
        self.logger = Logger()
        self.user_name = user_name
        self.db = FileSearchDB(user_name)

        # Use provided generator or create default one
        if embedding_generator:
            self.embedding_generator = embedding_generator
        else:
            self.embedding_generator = get_embedding_generator()

        self.logger.info("VectorSearchEngine initialized")

    @staticmethod
    def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity score between -1 and 1
        """
        # Ensure numpy arrays
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)

        # Calculate cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    @staticmethod
    def euclidean_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Calculate Euclidean-based similarity between two vectors.
        Converts distance to similarity score.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Similarity score between 0 and 1
        """
        # Calculate Euclidean distance
        distance = np.linalg.norm(np.array(vec1) - np.array(vec2))

        # Convert to similarity (1 / (1 + distance))
        return float(1.0 / (1.0 + float(distance)))

    # --- Internal helpers to reduce cognitive complexity in search() ---
    def _normalize_similarity_threshold(self, threshold: float | None) -> float:
        """Clamp/normalize similarity threshold into [0, 1] and apply default when None."""
        if threshold is None:
            return self.DEFAULT_SIMILARITY_THRESHOLD
        try:
            return max(0.0, min(1.0, float(threshold)))
        except (ValueError, TypeError):
            # Fallback to default on invalid input
            return self.DEFAULT_SIMILARITY_THRESHOLD

    def _normalize_distance_metric(self, metric: str | None) -> str:
        """Normalize distance metric and fallback to 'cosine' with a warning if unsupported."""
        normalized = (metric or "cosine").lower()
        if normalized not in {"cosine", "euclidean"}:
            self.logger.warning(
                f"search(): unsupported distance_metric='{metric}', defaulting to 'cosine'"
            )
            return "cosine"
        return normalized

    @staticmethod
    def _build_search_result(emb: dict[str, Any], score: float) -> SearchResult:
        """Construct a SearchResult from a DB embedding row and score with safe casting."""
        return SearchResult(
            chunk_id=str(emb["chunk_id"]),
            file_id=str(emb["file_id"]),
            file_path=str(emb["file_path"]),
            content=str(emb["content"]),
            score=float(score),
            chunk_index=int(emb["chunk_index"]),
            start_pos=int(emb["start_pos"]),
            end_pos=int(emb["end_pos"]),
            file_type=(str(emb.get("file_type")) if emb.get("file_type") is not None else None),
            metadata=(
                emb.get("chunk_metadata") if isinstance(emb.get("chunk_metadata"), dict) else None
            ),
            match_type="vector",
        )

    @staticmethod
    def _parse_embedding_vector(raw: str) -> list[float] | None:
        """
        Parse a serialized embedding vector string into a list[float]. Returns None if invalid.
        """
        try:
            data = json.loads(raw)
            vec = [float(x) for x in data]
            return vec or None
        except (ValueError, TypeError):
            return None

    def _cosine_results(
        self,
        query_embedding: Any,
        all_embeddings: list[dict[str, Any]],
        similarity_threshold: float,
    ) -> list[SearchResult]:
        """Compute cosine similarity scores and return results above threshold."""
        # Parse document vectors and keep only valid rows
        doc_vectors: list[list[float]] = []
        valid_embeddings: list[dict[str, Any]] = []
        for emb in all_embeddings:
            vec = self._parse_embedding_vector(emb["embedding_vector"])
            if vec is None:
                self.logger.warning(
                    f"search(): skipping invalid embedding for chunk_id={emb.get('chunk_id')}"
                )
                continue
            doc_vectors.append(vec)
            valid_embeddings.append(emb)

        if not valid_embeddings:
            return []

        query_vec: list[float] = [
            float(x) for x in np.asarray(query_embedding, dtype=np.float64).tolist()
        ]
        scores = compute_cosine_scores(query_vec, doc_vectors, mode="auto")

        results: list[SearchResult] = [
            self._build_search_result(emb_data, score)
            for emb_data, score in zip(valid_embeddings, scores, strict=False)
            if score >= similarity_threshold
        ]
        return results

    def _euclidean_results(
        self,
        query_embedding: Any,
        all_embeddings: list[dict[str, Any]],
        similarity_threshold: float,
    ) -> list[SearchResult]:
        """Compute euclidean-based similarity scores and return results above threshold."""
        q_vec: np.ndarray = np.asarray(query_embedding, dtype=np.float64)
        results: list[SearchResult] = []
        for emb in all_embeddings:
            d_vec_list = self._parse_embedding_vector(emb["embedding_vector"])
            if d_vec_list is None:
                self.logger.warning(
                    f"search(): skipping invalid embedding for chunk_id={emb.get('chunk_id')}"
                )
                continue
            d_vec = np.asarray(d_vec_list, dtype=np.float64)
            score = self.euclidean_similarity(q_vec, d_vec)
            if score >= similarity_threshold:
                results.append(self._build_search_result(emb, score))
        return results

    @staticmethod
    def _top_k_sorted(results: list[SearchResult], k: int) -> list[SearchResult]:
        """Return the top-k results by score in descending order."""
        if not results or k <= 0:
            return []
        from heapq import nlargest

        return nlargest(k, results, key=lambda r: r.score)

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        similarity_threshold: float | None = None,
        file_types: list[str] | None = None,
        distance_metric: str = "cosine",
    ) -> list[SearchResult]:
        """
        Perform vector similarity search.

        Args:
            query: Search query text
            top_k: Number of top results to return
            similarity_threshold: Minimum similarity score
            file_types: Filter by file types (e.g., ['pdf', 'txt'])
            distance_metric: 'cosine' or 'euclidean'

        Returns:
            List[SearchResult]: Results sorted by similarity (descending)
        """
        # Validate inputs early
        if not query.strip():
            self.logger.warning("search(): empty query provided")
            return []

        if top_k <= 0:
            # Nothing to return; avoid doing unnecessary work
            self.logger.info("search(): top_k <= 0, returning empty list")
            return []

        # Normalize/validate similarity threshold
        similarity_threshold = self._normalize_similarity_threshold(similarity_threshold)

        # Validate distance metric
        metric = self._normalize_distance_metric(distance_metric)

        try:
            # Generate query embedding
            preview = query[:50].replace("\n", " ")
            self.logger.info("Generating embedding for query: %s...", preview)
            query_embedding = self.embedding_generator.generate_embedding(query, normalize=True)

            # Retrieve all embeddings from database
            all_embeddings = self._retrieve_all_embeddings(file_types)

            if not all_embeddings:
                self.logger.info("search(): no embeddings found in database")
                return []

            # Compute similarities
            results: list[SearchResult] = []

            # Construct results in metric-specific helpers

            if metric == "cosine":
                results = self._cosine_results(
                    query_embedding, all_embeddings, similarity_threshold
                )
            else:
                results = self._euclidean_results(
                    query_embedding, all_embeddings, similarity_threshold
                )

            if not results:
                self.logger.info("search(): no results above threshold")
                return []

            top_results: list[SearchResult] = self._top_k_sorted(results, top_k)

            self.logger.info(
                f"Vector search found {len(top_results)} results (from {len(results)} above threshold)"
            )
            return top_results

        except Exception as exc:
            # Include full stack trace for diagnostics while staying compatible with Logger
            # Many Logger wrappers accept an exc parameter or format the exception text.
            # If your Logger supports `error(msg, exc_info=True)`, prefer that. Here we include exception text.
            self.logger.error("Error performing vector search: %s", exc)
            return []

    def keyword_search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        file_types: list[str] | None = None,
    ) -> list[SearchResult]:
        """
        Perform keyword-based search using SQLite FTS or LIKE.

        Args:
            query: Search query text
            top_k: Number of top results to return
            file_types: Filter by file types

        Returns:
            List of SearchResult objects
        """
        try:
            if not query or not query.strip():
                return []

            # Simple keyword extraction (can be enhanced)
            keywords = self._extract_keywords(query)

            if not keywords:
                return []

            # Search in database
            results = self._search_by_keywords(keywords, file_types)

            # Convert to SearchResult objects
            search_results: list[SearchResult] = []
            for result in results[:top_k]:
                search_result = SearchResult(
                    chunk_id=result["chunk_id"],
                    file_id=result["file_id"],
                    file_path=result["file_path"],
                    content=result["content"],
                    score=result["relevance_score"],
                    chunk_index=result["chunk_index"],
                    start_pos=result["start_pos"],
                    end_pos=result["end_pos"],
                    file_type=result.get("file_type"),
                    metadata=result.get("chunk_metadata"),
                    match_type="keyword",
                )
                search_results.append(search_result)

            self.logger.info("Keyword search found %d results", len(search_results))
            return search_results

        except Exception as e:
            self.logger.error("Error performing keyword search: %s", str(e))
            return []

    def hybrid_search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        vector_weight: float = DEFAULT_VECTOR_WEIGHT,
        keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
        similarity_threshold: float | None = None,
        file_types: list[str] | None = None,
        rerank: bool = True,
    ) -> list[SearchResult]:
        """
        Perform hybrid search combining vector and keyword search.

        Args:
            query: Search query text
            top_k: Number of top results to return
            vector_weight: Weight for vector similarity scores
            keyword_weight: Weight for keyword match scores
            similarity_threshold: Minimum similarity for vector search
            file_types: Filter by file types
            rerank: Whether to rerank results

        Returns:
            List of SearchResult objects with combined scores
        """
        try:
            # Normalize weights
            total_weight = vector_weight + keyword_weight
            vector_weight = vector_weight / total_weight
            keyword_weight = keyword_weight / total_weight

            # Perform vector search
            vector_results = self.search(
                query,
                top_k=top_k * 2,  # Get more results for merging
                similarity_threshold=similarity_threshold,
                file_types=file_types,
            )

            # Perform keyword search
            keyword_results = self.keyword_search(query, top_k=top_k * 2, file_types=file_types)

            # Merge results
            merged_results = self._merge_search_results(
                vector_results, keyword_results, vector_weight, keyword_weight
            )

            # Rerank if requested
            if rerank and merged_results:
                merged_results = self.rerank_results(query, merged_results, top_k=top_k)
            else:
                # Just take top k
                merged_results = merged_results[:top_k]

            self.logger.info("Hybrid search returned %d results", len(merged_results))

            return merged_results

        except Exception as e:
            self.logger.error("Error performing hybrid search: %s", str(e))
            return []

    def rerank_results(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int | None = None,
        rerank_func: Callable[[str, list[SearchResult]], list[SearchResult]] | None = None,
    ) -> list[SearchResult]:
        """
        Rerank search results for better relevance.

        Args:
            query: Original search query
            results: List of search results to rerank
            top_k: Number of results to return (None for all)
            rerank_func: Custom reranking function

        Returns:
            Reranked list of SearchResult objects
        """
        try:
            if not results:
                return []

            # Use custom rerank function if provided
            if rerank_func:
                reranked = rerank_func(query, results)
                return reranked[:top_k] if top_k else reranked

            # Default reranking based on multiple factors
            query_lower = query.lower()
            query_terms = set(query_lower.split())

            for result in results:
                # Calculate additional relevance factors
                content_lower = result.content.lower()

                # Exact phrase match bonus
                exact_match_bonus = 0.2 if query_lower in content_lower else 0.0

                # Term frequency bonus
                term_matches = sum(1 for term in query_terms if term in content_lower)
                term_bonus = min(0.3, term_matches * 0.05)

                # Position bonus (prefer matches at beginning)
                position_bonus = 0.0
                if query_lower in content_lower:
                    position = content_lower.find(query_lower)
                    position_bonus = 0.1 * (1.0 - position / len(content_lower))

                # File type bonus (configurable)
                file_type_bonus = 0.0
                if result.file_type in ["pdf", "docx"]:
                    file_type_bonus = 0.05

                # Combine with original score
                boost = exact_match_bonus + term_bonus + position_bonus + file_type_bonus
                result.score = min(1.0, result.score + boost)

            # Sort by new scores
            results.sort(key=lambda x: x.score, reverse=True)

            return results[:top_k] if top_k else results

        except Exception as e:
            self.logger.error("Error reranking results: %s", str(e))
            return results

    def _retrieve_all_embeddings(self, file_types: list[str] | None = None) -> list[dict[str, Any]]:
        """
        Retrieve all embeddings from the database.

        Args:
            file_types: Optional filter by file types

        Returns:
            List of embedding data dictionaries
        """
        try:
            conn_cm = cast("Any", self.db.get_connection())
            with conn_cm as conn:
                cursor = conn.cursor()

                # Build query
                query = """
                    SELECT
                        e.id as embedding_id,
                        e.chunk_id,
                        e.embedding_vector,
                        e.model_name,
                        c.file_id,
                        c.chunk_index,
                        c.content,
                        c.start_pos,
                        c.end_pos,
                        c.metadata as chunk_metadata,
                        f.file_path,
                        f.file_type
                    FROM file_embeddings e
                    JOIN file_chunks c ON e.chunk_id = c.id
                    JOIN indexed_files f ON c.file_id = f.id
                    WHERE f.status = 'active'
                """

                params: list[Any] = []
                if file_types:
                    placeholders = ",".join(["?" for _ in file_types])
                    query += f" AND f.file_type IN ({placeholders})"
                    params.extend(file_types)

                cursor.execute(query, params)

                # Convert to list of dictionaries
                columns = [desc[0] for desc in cursor.description]
                results: list[dict[str, Any]] = []

                for row in cursor.fetchall():
                    result_dict = dict(zip(columns, row, strict=False))

                    # Parse JSON metadata if present
                    if result_dict.get("chunk_metadata"):
                        try:
                            result_dict["chunk_metadata"] = json.loads(
                                result_dict["chunk_metadata"]
                            )
                        except json.JSONDecodeError:
                            result_dict["chunk_metadata"] = None

                    results.append(result_dict)

                return results

        except Exception as e:
            self.logger.error("Error retrieving embeddings: %s", str(e))
            return []

    def _extract_keywords(self, query: str) -> list[str]:
        """
        Extract keywords from query text.
        Simple implementation - can be enhanced with NLP.
        """
        # Delegate to shared utility to avoid duplication
        return extract_keywords(query)

    def _search_by_keywords(
        self, keywords: list[str], file_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Search chunks by keywords using SQL LIKE.

        Args:
            keywords: List of keywords to search
            file_types: Optional filter by file types

        Returns:
            List of matching chunks with relevance scores
        """
        try:
            conn_cm = cast("Any", self.db.get_connection())
            with conn_cm as conn:
                cursor = conn.cursor()

                # Build query with LIKE conditions for each keyword
                query = """
                    SELECT
                        c.id as chunk_id,
                        c.file_id,
                        c.chunk_index,
                        c.content,
                        c.start_pos,
                        c.end_pos,
                        c.metadata as chunk_metadata,
                        f.file_path,
                        f.file_type,
                        (
                """

                # Add relevance scoring based on keyword matches
                like_conditions: list[str] = []
                params: list[Any] = []

                for keyword in keywords:
                    like_condition = "CASE WHEN LOWER(c.content) LIKE ? THEN 1 ELSE 0 END"
                    like_conditions.append(like_condition)
                    params.append(f"%{keyword}%")

                query += " + ".join(like_conditions)
                query += """
                        ) as match_count
                    FROM file_chunks c
                    JOIN indexed_files f ON c.file_id = f.id
                    WHERE f.status = 'active'
                    AND (
                """

                # Add WHERE conditions
                where_conditions: list[str] = []
                for keyword in keywords:
                    where_conditions.append("LOWER(c.content) LIKE ?")
                    params.append(f"%{keyword}%")

                query += " OR ".join(where_conditions)
                query += ")"

                # Add file type filter if specified
                if file_types:
                    placeholders = ",".join(["?" for _ in file_types])
                    query += f" AND f.file_type IN ({placeholders})"
                    params.extend(file_types)

                query += " ORDER BY match_count DESC, c.chunk_index ASC"

                cursor.execute(query, params)

                # Convert to list of dictionaries with relevance scores
                columns = [desc[0] for desc in cursor.description]
                results: list[dict[str, Any]] = []

                max_match_count = len(keywords)

                for row in cursor.fetchall():
                    result_dict = dict(zip(columns, row, strict=False))

                    # Calculate relevance score (0-1)
                    match_count = result_dict.pop("match_count", 0)
                    result_dict["relevance_score"] = match_count / max_match_count

                    # Parse JSON metadata if present
                    if result_dict.get("chunk_metadata"):
                        try:
                            result_dict["chunk_metadata"] = json.loads(
                                result_dict["chunk_metadata"]
                            )
                        except json.JSONDecodeError:
                            result_dict["chunk_metadata"] = None

                    results.append(result_dict)

                return results

        except Exception as e:
            self.logger.error("Error searching by keywords: %s", str(e))
            return []

    def _merge_search_results(
        self,
        vector_results: list[SearchResult],
        keyword_results: list[SearchResult],
        vector_weight: float,
        keyword_weight: float,
    ) -> list[SearchResult]:
        """
        Merge vector and keyword search results with weighted scores.

        Args:
            vector_results: Results from vector search
            keyword_results: Results from keyword search
            vector_weight: Weight for vector scores
            keyword_weight: Weight for keyword scores

        Returns:
            Merged and sorted list of SearchResult objects
        """
        # Create a dictionary to store merged results by chunk_id
        merged_dict: dict[str, SearchResult] = {}

        # Add vector results
        for result in vector_results:
            merged_dict[result.chunk_id] = SearchResult(
                chunk_id=result.chunk_id,
                file_id=result.file_id,
                file_path=result.file_path,
                content=result.content,
                score=result.score * vector_weight,
                chunk_index=result.chunk_index,
                start_pos=result.start_pos,
                end_pos=result.end_pos,
                file_type=result.file_type,
                metadata=result.metadata,
                match_type="hybrid",
            )

        # Add or update with keyword results
        for result in keyword_results:
            if result.chunk_id in merged_dict:
                # Combine scores
                merged_dict[result.chunk_id].score += result.score * keyword_weight
            else:
                # Add new result
                merged_dict[result.chunk_id] = SearchResult(
                    chunk_id=result.chunk_id,
                    file_id=result.file_id,
                    file_path=result.file_path,
                    content=result.content,
                    score=result.score * keyword_weight,
                    chunk_index=result.chunk_index,
                    start_pos=result.start_pos,
                    end_pos=result.end_pos,
                    file_type=result.file_type,
                    metadata=result.metadata,
                    match_type="hybrid",
                )

        # Convert to list and sort by score
        merged_results: list[SearchResult] = list(merged_dict.values())
        merged_results.sort(key=lambda x: x.score, reverse=True)

        return merged_results
