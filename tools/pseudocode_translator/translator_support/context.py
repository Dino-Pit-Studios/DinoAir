"""
Lightweight context container for translation operations.

TranslationContext centralizes commonly used state during streaming translation,
reducing parameter threading and keeping imports lightweight. It avoids importing
translator internals; types are intentionally broad to prevent cycles.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TranslationContext:
    """
    Central state passed within streaming translation flows.

    Fields intentionally use typing.Any to avoid heavy imports and cycles.
    Only runtime duck-typing is relied upon.
    """

    input_text: str
    target_language: Any  # Same type translator expects (e.g., OutputLanguage), kept as Any here
    start_time: float
    translation_id: int
    model: Any  # Active model instance; kept as Any to avoid tight coupling
    llm_params: dict[str, Any]  # Flat snapshot of LLM settings used by streaming path
    recorder: Any  # Telemetry recorder
    events: Any  # Event dispatcher
    exec_cfg: Any | None  # Execution/offload configuration if available
    approach: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    parse_result: Any | None = None
    processed_blocks: Any | None = None

    def to_model_config(self) -> dict[str, Any]:
        """
        Return a dict shaped like the model translation config typically built by the translator.

        Keys include the common parameters referenced in streaming code paths; the caller
        can adapt this dict into model-specific config objects if needed later.
        """
        p = self.llm_params or {}
        return {
            "temperature": p.get("temperature"),
            "top_p": p.get("top_p"),
            "top_k": p.get("top_k"),
            "max_tokens": p.get("max_tokens"),
            "n_ctx": p.get("n_ctx"),
            "n_batch": p.get("n_batch"),
            "n_threads": p.get("n_threads"),
            "n_gpu_layers": p.get("n_gpu_layers"),
        }
