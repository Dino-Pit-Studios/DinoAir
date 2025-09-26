"""Input processing exception types used across the sanitization pipeline."""


class InputPipelineError(Exception):
    """Raised when the input processing pipeline encounters a fatal error."""


__all__ = ["InputPipelineError"]
