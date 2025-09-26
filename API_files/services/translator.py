"""
Pseudocode translation service.

This module provides a safe wrapper around the pseudocode translator API,
ensuring deterministic, non-streaming translation with conservative defaults.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any, Protocol, cast

from pydantic import ValidationError

from ..schemas import TargetLanguageEnum, TranslateRequest, TranslateResponse

# Prefer the high-level API but force non-streaming behavior
try:
    # type: ignore[import-untyped]
    from pseudocode_translator.integration.api import TranslatorAPI

    # Type alias for when the dependency is available
    TranslatorAPIType = type[TranslatorAPI]
except ImportError:
    # Handle missing dependency gracefully
    TranslatorAPI = None  # type: ignore[misc,assignment]
    TranslatorAPIType = None  # type: ignore[misc,assignment]


class TranslatorAPIProtocol(Protocol):
    """Protocol for translator API to provide type hints."""

    def translate(
        self, pseudocode: str, *, language: str, use_streaming: bool = False
    ) -> dict[str, Any]:
        """Translate pseudocode to target language."""
        return {}


log = logging.getLogger("api.services.translator")


class TranslatorService:
    """
    Safe wrapper around the pseudocode translator.

    Requirements:
    - Deterministic, non-streaming translation (v0 disallows streaming).
    - No dynamic eval/exec.
    - Conservative defaults.
    """

    def __init__(self) -> None:
        # Initialize the high-level API and ensure streaming is disabled
        if TranslatorAPI is None:
            raise ImportError(
                "pseudocode_translator package not available. "
                "Install it to use translation features."
            )
        self._api: Any = TranslatorAPI()  # type: ignore[misc]
        # Prevent auto streaming by setting a huge threshold
        # TranslatorAPI auto-enables streaming when input length exceeds _streaming_threshold.
        # Force an extremely large threshold to keep non-streaming behavior for all requests.
        with suppress(Exception):
            self._api._streaming_threshold = (  # type: ignore[attr-defined]
                10**12
            )  # internal but safe to adjust for v0 needs

    @staticmethod
    def _create_error_response(error: Exception, target_lang: str) -> TranslateResponse:
        """Create an error response from an exception."""
        return TranslateResponse(
            success=False,
            language=target_lang,
            code=None,
            errors=[str(error)][:50],
            warnings=[],
            metadata={"error_type": type(error).__name__},
        )

    @staticmethod
    def _normalize_list(items: object) -> list[str]:
        """Normalize and truncate a list of items to strings."""
        if not isinstance(items, list):
            return []
        out: list[str] = []
        for x in cast("list[object]", items)[:50]:
            s = x if isinstance(x, str) else str(x)
            out.append(s[:500])
        return out

    @staticmethod
    def _extract_metadata(metadata_raw: object) -> dict[str, Any]:
        """Extract and normalize metadata from raw result."""
        if isinstance(metadata_raw, dict):
            md_typed: dict[Any, Any] = cast("dict[Any, Any]", metadata_raw)
            return {str(k): v for k, v in md_typed.items()}
        return {}

    @staticmethod
    def _create_validation_error_response(
        language: str, validation_error: ValidationError
    ) -> TranslateResponse:
        """Create a response for validation errors."""
        log.warning(
            "TranslateResponse validation failed; coercing to error",
            extra={"errors": validation_error.errors()},
        )
        return TranslateResponse(
            success=False,
            language=language,
            code=None,
            errors=["Translator returned invalid response"],
            warnings=[],
            metadata={"validation_error": True},
        )

    def translate(self, req: TranslateRequest) -> TranslateResponse:
        """Translate pseudocode to the target language with non-streaming behavior."""
        # Map TargetLanguageEnum to raw string expected by TranslatorAPI
        target_lang: str = (req.target_language or TargetLanguageEnum.python).value

        # TranslatorAPI returns a dictionary with keys:
        #   success: bool, code: Optional[str], language: str
        #   errors: List[str], warnings: List[str], metadata: Dict[str, Any]
        # We must conform to TranslateResponse schema and enforce constraints
        # (truncate long fields).
        try:
            # Explicitly set use_streaming to False (though API may auto-enable;
            # we raised the threshold above)
            result: dict[str, Any] = self._api.translate(
                req.pseudocode,
                language=target_lang,
                use_streaming=False,
            )
        except (ImportError, AttributeError, RuntimeError, ValueError) as e:
            log.exception("TranslatorAPI.translate failed")
            # Surface a structured but typed response (error envelope handled
            # by global handlers when raising)
            return self._create_error_response(e, target_lang)

        # Conformance adjustments
        success = bool(result.get("success", False))
        code = result.get("code")
        language = str(result.get("language") or target_lang)

        # Normalize lists and enforce bounds
        errors = self._normalize_list(result.get("errors", []))
        warnings = self._normalize_list(result.get("warnings", []))
        metadata = self._extract_metadata(result.get("metadata"))

        # Build typed response
        try:
            return TranslateResponse(
                success=success,
                language=language,
                code=code,
                errors=errors,
                warnings=warnings,
                metadata=metadata,
            )
        except ValidationError as ve:
            # If the upstream result violates our DTO constraints, coerce to a safe failure
            return self._create_validation_error_response(language, ve)


# Module-level facade
class _TranslatorServiceSingleton:
    """Singleton holder for translator service."""

    def __init__(self) -> None:
        self._instance: TranslatorService | None = None

    def get_instance(self) -> TranslatorService:
        """Get or create the translator service instance."""
        if self._instance is None:
            self._instance = TranslatorService()
        return self._instance


_singleton = _TranslatorServiceSingleton()


def get_translator_service() -> TranslatorService:
    """Get or create a singleton translator service instance."""
    return _singleton.get_instance()


def translate(req: TranslateRequest) -> TranslateResponse:
    """Translate pseudocode using the singleton translator service."""
    return get_translator_service().translate(req)


def router_translate(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Adapter entry point for core_router.adapters.local_python.

    Input:
        input_data: dict with keys:
          - 'pseudocode': str (required)
          - 'target_language': Optional[str]

    Behavior:
        Wraps translate() by building TranslateRequest.
        Returns a simple dict matching TranslateResponse.
    """
    req = TranslateRequest(
        pseudocode=input_data["pseudocode"],
        target_language=input_data.get("target_language"),
    )
    resp = translate(req)
    return resp.model_dump(by_alias=False, exclude_none=True)
