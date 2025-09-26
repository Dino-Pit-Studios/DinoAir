from __future__ import annotations

from enum import Enum
from typing import Any, cast

from pydantic import BaseModel, Field, field_validator

# Shared validation messages
QUERY_EMPTY_ERROR = "query must not be empty"

# -----------------------
# Enums (align with spec)
# -----------------------


class TargetLanguageEnum(str, Enum):
    """Enumeration of supported target programming languages."""

    python = "python"
    javascript = "javascript"
    typescript = "typescript"
    rust = "rust"
    go = "go"
    java = "java"
    csharp = "csharp"
    cpp = "cpp"
    ruby = "ruby"
    swift = "swift"
    kotlin = "kotlin"
    scala = "scala"
    php = "php"
    r = "r"


class DistanceMetricEnum(str, Enum):
    """Enumeration of available distance metrics for vector search."""

    cosine = "cosine"
    euclidean = "euclidean"


# -----------------------
# Common types
# -----------------------


class ValidationFieldError(BaseModel):
    """Represents a validation error for a specific field."""

    field: str = Field(..., description="Field name that failed validation")
    message: str = Field(..., description="Human-readable message")
    code: str = Field(..., description="Machine-friendly code")


class ValidationErrors(BaseModel):
    """Container for validation field errors."""

    field_errors: list[ValidationFieldError] = Field(
        default_factory=lambda: cast("list[ValidationFieldError]", [])
    )


# -----------------------
# Translate DTOs
# -----------------------


class TranslateRequest(BaseModel):
    """Request model for translating pseudocode into target programming language."""

    pseudocode: str = Field(..., min_length=1, max_length=100_000)
    target_language: TargetLanguageEnum | None = Field(default=TargetLanguageEnum.python)

    @field_validator("pseudocode")
    @classmethod
    def _trim_and_check(cls, v: str) -> str:
        if v := v.strip():
            return v
        raise ValueError("pseudocode must not be empty")


class TranslateResponse(BaseModel):
    """Response model for the result of a pseudocode translation request."""

    success: bool
    language: str
    code: str | None
    errors: list[str] = Field(
        default_factory=lambda: cast("list[str]", []),
        description=("List of error messages (bounded to 50 elements; each up to 500 chars)"),
    )
    warnings: list[str] = Field(
        default_factory=lambda: cast("list[str]", []),
        description=("List of warning messages (bounded to 50 elements; each up to 500 chars)"),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def _validate_str_list(values: list[Any], field_name: str) -> list[str]:
        if len(values) > 50:
            raise ValueError(f"{field_name} length must be <= 50")
        for s in values:
            if not isinstance(s, str):
                raise ValueError(f"All {field_name} entries must be strings")
            if len(s) > 500:
                raise ValueError(f"{field_name} entries must be <= 500 characters")
        return cast("list[str]", values)

    @field_validator("errors")
    @classmethod
    def _validate_errors(cls, v: list[str]) -> list[str]:
        return cls._validate_str_list(v, "errors")

    @field_validator("warnings")
    @classmethod
    def _validate_warnings(cls, v: list[str]) -> list[str]:
        return cls._validate_str_list(v, "warnings")


# -----------------------
# Search DTOs
# -----------------------


# Hit used by vector, keyword, and hybrid responses (spec uses unified shape)
class VectorSearchHit(BaseModel):
    """Represents a single search hit in vector search results."""

    file_path: str
    content: str = Field(
        ...,
        description="Snippet/chunk; server may truncate to 500 chars",
    )
    score: float
    chunk_index: int
    start_pos: int
    end_pos: int
    file_type: str | None = None
    metadata: dict[str, Any] | None = None


class VectorSearchRequest(BaseModel):
    """Request model for performing a vector-based search."""

    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=50)
    similarity_threshold: float | None = Field(default=0.5, ge=0.0, le=1.0)
    file_types: list[str] | None = Field(default=None)
    distance_metric: DistanceMetricEnum = Field(default=DistanceMetricEnum.cosine)

    @field_validator("query")
    @classmethod
    def _trim_query(cls, v: str) -> str:
        if v := v.strip():
            return v
        raise ValueError(QUERY_EMPTY_ERROR)


class VectorSearchResponse(BaseModel):
    """Response model containing hits from vector search."""

    hits: list[VectorSearchHit] = Field(default_factory=lambda: cast("list[VectorSearchHit]", []))


class KeywordSearchRequest(BaseModel):
    """Request model for performing a keyword-based search."""

    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=50)
    file_types: list[str] | None = Field(default=None)

    @field_validator("query")
    @classmethod
    def _trim_query(cls, v: str) -> str:
        if v := v.strip():
            return v
        raise ValueError(QUERY_EMPTY_ERROR)


class KeywordSearchResponse(BaseModel):
    """Response model containing hits from keyword search."""

    hits: list[VectorSearchHit] = Field(default_factory=lambda: cast("list[VectorSearchHit]", []))


class HybridSearchRequest(BaseModel):
    """Request model for performing a hybrid (vector + keyword) search."""

    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=50)
    vector_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    keyword_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    similarity_threshold: float | None = Field(default=0.5, ge=0.0, le=1.0)
    file_types: list[str] | None = Field(default=None)
    rerank: bool = Field(default=True)

    @field_validator("query")
    @classmethod
    def _trim_query(cls, v: str) -> str:
        if v := v.strip():
            return v
        raise ValueError(QUERY_EMPTY_ERROR)

    @field_validator("keyword_weight")
    @classmethod
    def _validate_weights(cls, kw: float) -> float:
        # Per-field bounds are enforced via Field; cross-field checks are handled at the model level.
        return kw


class HybridSearchResponse(BaseModel):
    """Response model containing hits from hybrid search."""

    hits: list[VectorSearchHit] = Field(default_factory=lambda: cast("list[VectorSearchHit]", []))


# -----------------------
# Index/config DTOs
# -----------------------


class FileIndexStatsResponse(BaseModel):
    """Statistics about files indexed in the system."""

    total_files: int
    files_by_type: dict[str, int]
    total_size_bytes: int
    total_size_mb: float
    total_chunks: int
    total_embeddings: int
    last_indexed_date: str | None = Field(
        default=None,
        description="ISO timestamp or null",
    )


class DirectorySettingsResponse(BaseModel):
    """Response model for directory indexing settings."""

    allowed_directories: list[str] = Field(default_factory=list)
    excluded_directories: list[str] = Field(default_factory=list)
    total_allowed: int = 0
    total_excluded: int = 0


# -----------------------
# AI Chat DTOs
# -----------------------


class ChatRoleEnum(str, Enum):
    """Enumeration of possible roles in chat messages."""

    system = "system"
    user = "user"
    assistant = "assistant"


class ChatMessage(BaseModel):
    """Represents a single chat message with role and content."""

    role: ChatRoleEnum = Field(
        ...,
        description="Chat role: system|user|assistant",
    )
    content: str = Field(..., min_length=1, max_length=100_000)

    @field_validator("content")
    @classmethod
    def _trim_content(cls, v: str) -> str:
        if s := v.strip():
            return s
        raise ValueError("content must not be empty")


class ChatRequest(BaseModel):
    """Request model for initiating a chat conversation."""

    messages: list[ChatMessage] = Field(..., min_length=1)
    provider: str | None = Field(
        default="lmstudio",
        description=("Provider alias; 'lmstudio' or 'local' will use router-first path."),
    )
    model: str | None = Field(
        default=None,
        description=("Optional model name (LM Studio may use env default)."),
    )
    extra_params: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Adapter extra params (e.g., {'router_tags':['chat','lmstudio'], 'prepend_router_metadata': true, 'temperature': 0.3})."
        ),
    )

    @field_validator("messages")
    @classmethod
    def _non_empty_messages(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        if not v:
            raise ValueError("messages must be a non-empty list")
        return v


class ChatResponse(BaseModel):
    """Response model for a chat conversation result."""

    success: bool
    content: str
    finish_reason: str | None = None
    model: str | None = None
    usage: dict[str, int] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# -----------------------
# RAG minimal request models
# -----------------------


class IngestDirectoryRequest(BaseModel):
    """Request model to ingest all files in a directory."""

    directory: str = Field(..., min_length=1, max_length=10_000)
    recursive: bool = Field(default=True)
    file_types: list[str] | None = Field(default=None)
    force_reprocess: bool = Field(default=False)


class IngestFilesRequest(BaseModel):
    """Request model to ingest specific file paths."""

    paths: list[str] = Field(..., min_length=1)
    force_reprocess: bool = Field(default=False)


class GenerateMissingEmbeddingsRequest(BaseModel):
    """Request model to generate embeddings for unprocessed file chunks."""

    batch_size: int = Field(default=32, ge=1, le=4096)


class ContextRequest(BaseModel):
    """Request model to retrieve contextual snippets based on a query."""

    query: str = Field(..., min_length=1, max_length=1000)
    file_types: list[str] | None = Field(default=None)
    top_k: int = Field(default=10, ge=1, le=50)
    include_suggestions: bool = Field(default=True)

    @field_validator("query")
    @classmethod
    def _trim_query(cls, v: str) -> str:
        if s := v.strip():
            return s
        raise ValueError(QUERY_EMPTY_ERROR)


class MonitorStartRequest(BaseModel):
    """Request model to start monitoring specified directories."""

    directories: list[str] = Field(..., min_length=1)
    file_extensions: list[str] | None = Field(default=None)
