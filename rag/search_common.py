"""
Shared search utilities for RAG engines.
Centralizes common logic without changing behavior.
"""

import re
from collections.abc import Sequence

# Union of stop words from baseline and optimized engines
STOP_WORDS: set[str] = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "that",
    "the",
    "to",
    "was",
    "will",
    "with",
    "this",
    "but",
    "they",
    "have",
    "had",
    "what",
    "when",
    "where",
    "who",
    "which",
    "why",
    "how",
}


def extract_keywords(query: str) -> list[str]:
    """
    Extract keywords from query text.
    Mirrors baseline _extract_keywords behavior:
    - lowercase, strip punctuation
    - split on whitespace
    - remove STOP_WORDS
    - filter tokens with len > 2
    No bigrams are produced to avoid behavior drift.
    """
    # Remove punctuation and convert to lowercase (behavioral parity with baseline)
    cleaned = re.sub(r"[^\w\s]", " ", query.lower())
    words = cleaned.split()
    return [w for w in words if w not in STOP_WORDS and len(w) > 2]


def text_similarity(text1: str, text2: str) -> float:
    """
    Calculate simple text similarity using Jaccard index.
    Mirrors optimized _text_similarity implementation.
    """
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union) if union else 0.0


# Vectorized similarity utilities (feature-flagged)


def compute_cosine_scores(
    query: Sequence[float],
    docs: Sequence[Sequence[float]],
    mode: str = "auto",
) -> list[float]:
    """
    Compute cosine similarity scores between a query vector and many doc vectors.

    Behavior:
    - mode in {"auto","simple","vectorized"}.
    - "auto" reads env var RAG_SIM_MODE if present; allowed values {"auto","simple","vectorized"} (case-insensitive);
      default to "simple" for backward-compatible behavior if unset or invalid.
    - "simple": per-doc scalar/loop (mirrors current implementation semantics).
    - "vectorized": NumPy batch; if NumPy unavailable and mode=='vectorized', raise ImportError.
      If mode=='auto', fall back to 'simple' when NumPy is unavailable (even if env requests 'vectorized').

    Returns:
      - list[float] of cosine scores.
    """
    import os

    requested = (mode or "auto").strip().lower()
    allowed = {"auto", "simple", "vectorized"}

    if requested not in allowed:
        requested = "auto"

    if requested == "auto":
        env_mode = os.environ.get("RAG_SIM_MODE", "").strip().lower()
        if env_mode not in allowed:
            # Backward-compatible default when unset or invalid
            return _cosine_scores_simple(query, docs)

        if env_mode in {"simple", "auto"}:
            # Explicit simple or 'auto' in env -> simple for backward compatibility
            return _cosine_scores_simple(query, docs)

        # env_mode == "vectorized": attempt vectorized, fall back on failure
        try:
            from importlib import import_module as _import_module

            _ = _import_module("numpy")
        except ImportError:
            return _cosine_scores_simple(query, docs)
        return _cosine_scores_vectorized(query, docs)

    # Explicit mode handling
    if requested == "simple":
        return _cosine_scores_simple(query, docs)

    if requested == "vectorized":
        try:
            from importlib import import_module as _import_module

            _ = _import_module("numpy")
        except Exception as e:
            raise ImportError(
                "NumPy is required for 'vectorized' cosine scoring but is not available"
            ) from e
        return _cosine_scores_vectorized(query, docs)

    # Safety fallback
    return _cosine_scores_simple(query, docs)


def _cosine_scores_simple(query: Sequence[float], docs: Sequence[Sequence[float]]) -> list[float]:
    """
    Exact port of current loop-based cosine similarity semantics:
    - If either vector norm is zero, score is 0.0
    - Uses float64 precision where possible
    - Uses NumPy per-pair (to mirror current implementation) when available, with
      a pure-Python fallback to avoid new hard dependency in this utility.
    """
    # Try NumPy path to mirror existing engines' behavior as closely as possible
    try:
        import numpy as np

        q = np.asarray(list(query), dtype=np.float64)
        norm_q = float(np.linalg.norm(q))
        scores_np: list[float] = []

        for d in docs:
            dv = np.asarray(list(d), dtype=np.float64)
            norm_d = float(np.linalg.norm(dv))
            if norm_q <= 0.0 or norm_d <= 0.0:
                scores_np.append(0.0)
                continue
            dot = float(np.dot(q, dv))
            scores_np.append(dot / (norm_q * norm_d))
        return scores_np
    except (ImportError, TypeError, AttributeError):
        # Pure-Python fallback (keeps semantics; minor FP drift possible but within tolerance)
        from math import sqrt

        q_list = [float(x) for x in query]
        norm_q = sqrt(sum(x * x for x in q_list))
        scores_py: list[float] = []

        for d in docs:
            d_list = [float(x) for x in d]
            norm_d = sqrt(sum(x * x for x in d_list))
            if norm_q <= 0.0 or norm_d <= 0.0:
                scores_py.append(0.0)
                continue
            dot = sum(a * b for a, b in zip(q_list, d_list, strict=False))
            scores_py.append(dot / (norm_q * norm_d))
        return scores_py


def _cosine_scores_vectorized(
    query: Sequence[float], docs: Sequence[Sequence[float]]
) -> list[float]:
    """
    NumPy-backed vectorized cosine similarity:
    - Uses float64
    - Identical zero-norm handling (score=0.0)
    - Returns Python list[float]
    """
    try:
        import numpy as np
    except Exception as e:
        raise ImportError(
            "NumPy is required for the vectorized cosine scorer but is not available"
        ) from e

    # Handle empty docs quickly
    if not docs:
        return []

    q = np.asarray(list(query), dtype=np.float64)
    D = np.asarray([list(d) for d in docs], dtype=np.float64)

    if D.ndim != 2:
        raise ValueError("Docs must be a 2D array-like of vectors")
    if q.ndim != 1:
        raise ValueError("Query must be a 1D vector")
    if D.shape[1] != q.shape[0]:
        raise ValueError(
            f"Dimension mismatch: docs vectors have dim {D.shape[1]} but query has dim {q.shape[0]}"
        )

    qn = float(np.linalg.norm(q))
    dn = np.linalg.norm(D, axis=1).astype(np.float64)

    # Compute dot products and safe division
    dots = (D @ q).astype(np.float64)
    denom = dn * qn
    scores = np.divide(
        dots,
        denom,
        out=np.zeros_like(dots, dtype=np.float64),
        where=(denom > 0.0),
    )
    return scores.tolist()


__all__ = [
    "STOP_WORDS",
    "extract_keywords",
    "text_similarity",
    "compute_cosine_scores",
    "_cosine_scores_simple",
    "_cosine_scores_vectorized",
]
