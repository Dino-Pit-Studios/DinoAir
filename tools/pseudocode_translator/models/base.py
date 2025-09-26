"""
Base model interface for the Pseudocode Translator

This module defines the abstract base class that all language models must
implement, along with supporting data structures for model capabilities and
metadata.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from utils.shutdown_protocols import ShutdownMixin


class ModelFormat(Enum):
    """Supported model file formats"""

    GGUF = "gguf"  # llama.cpp format
    GGML = "ggml"  # Legacy llama.cpp format
    PYTORCH = "pytorch"  # PyTorch model
    ONNX = "onnx"  # ONNX format
    HF = "huggingface"  # Hugging Face format


@dataclass
class ModelCapabilities:
    """Defines what a model can do and its requirements"""

    # Language capabilities
    supported_languages: list[str] = field(default_factory=lambda: ["python"])
    max_context_length: int = 2048
    supports_code_completion: bool = True
    supports_translation: bool = True
    supports_refinement: bool = True
    supports_streaming: bool = False

    # Hardware requirements
    min_memory_gb: float = 4.0
    recommended_memory_gb: float = 8.0
    supports_gpu: bool = True
    requires_gpu: bool = False

    # Model characteristics
    model_size_gb: float = 0.0
    quantization_bits: int | None = None
    is_instruction_tuned: bool = True

    # Performance characteristics
    tokens_per_second_cpu: float | None = None
    tokens_per_second_gpu: float | None = None

    def meets_requirements(
        self, available_memory_gb: float, has_gpu: bool = False
    ) -> tuple[bool, str]:
        """
        Check if system meets model requirements

        Returns:
            Tuple of (meets_requirements, reason_if_not)
        """
        if available_memory_gb < self.min_memory_gb:
            return (
                False,
                f"Insufficient memory: {available_memory_gb}GB < {self.min_memory_gb}GB required",
            )

        if self.requires_gpu and not has_gpu:
            return False, "Model requires GPU but none available"

        return True, ""


@dataclass
class ModelMetadata:
    """Metadata about a model implementation"""

    name: str
    display_name: str
    description: str
    version: str
    author: str
    license: str
    homepage: str | None = None
    download_url: str | None = None
    sha256_checksum: str | None = None
    tags: list[str] = field(default_factory=list)

    # Model file information
    format: ModelFormat = ModelFormat.GGUF
    filename_pattern: str = "*.gguf"

    # Additional metadata
    examples: list[dict[str, str]] = field(default_factory=list)
    citation: str | None = None


class BaseModel(ABC, ShutdownMixin):
    """
    Abstract base class for all language model implementations

    All model implementations must inherit from this class and implement
    the required abstract methods.
    """

    def __init__(self, config: dict[str, Any]):
        """
        Initialize the model with configuration

        Args:
            config: Model-specific configuration dictionary
        """
        super().__init__()
        self.config = config
        self._model = None
        self._initialized = False

    @property
    @abstractmethod
    def metadata(self) -> ModelMetadata:
        """Get model metadata"""

    @property
    @abstractmethod
    def capabilities(self) -> ModelCapabilities:
        """Get model capabilities"""

    @abstractmethod
    def initialize(self, model_path: Path, **kwargs) -> None:
        """
        Initialize/load the model

        Args:
            model_path: Path to the model file
            **kwargs: Additional initialization parameters

        Raises:
            FileNotFoundError: If model file doesn't exist
            RuntimeError: If model loading fails
        """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.3,
        top_p: float = 0.9,
        top_k: int = 40,
        stop_sequences: list[str] | None = None,
        **kwargs,
    ) -> str:
        """
        Generate text from a prompt

        Args:
            prompt: The input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling parameter
            top_k: Top-k sampling parameter
            stop_sequences: List of sequences to stop generation
            **kwargs: Model-specific generation parameters

        Returns:
            Generated text

        Raises:
            RuntimeError: If model is not initialized
        """

    @abstractmethod
    def translate_instruction(self, instruction: str, context: dict[str, Any] | None = None) -> str:
        """
        Translate an English instruction to code

        Args:
            instruction: Natural language instruction
            context: Optional context (e.g., surrounding code)

        Returns:
            Generated code
        """

    def refine_code(self, code: str, error_context: str, max_attempts: int = 1) -> str:
        """
        Attempt to fix code based on error feedback

        Args:
            code: Code that needs fixing
            error_context: Error message or context
            max_attempts: Maximum refinement attempts

        Returns:
            Refined code
        """
        # Default implementation - can be overridden
        refinement_prompt = f"Fix the following Python code based on the error:\n\nCode:\n```python\n{code}\n```\n\nError:\n{error_context}\n\nFixed code:"

        return self.generate(
            refinement_prompt,
            temperature=self.config.get("refinement_temperature", 0.2),
        )

    def batch_translate(self, instructions: list[str], show_progress: bool = True) -> list[str]:
        """
        Translate multiple instructions

        Args:
            instructions: List of instructions to translate
            show_progress: Whether to show progress

        Returns:
            List of generated code snippets
        """
        results = []
        for _i, instruction in enumerate(instructions):
            try:
                code = self.translate_instruction(instruction)
                results.append(code)
            except Exception as e:
                results.append(f"# Error: {str(e)}")

        return results

    def _cleanup_resources(self) -> None:
        """
        Cleanup model resources during shutdown

        Override this method if your model needs cleanup
        """
        self._model = None
        self._initialized = False

    def get_info(self) -> dict[str, Any]:
        """
        Get information about the model instance

        Returns:
            Dictionary with model information
        """
        return {
            "name": self.metadata.name,
            "display_name": self.metadata.display_name,
            "initialized": self._initialized,
            "capabilities": {
                "max_context": self.capabilities.max_context_length,
                "languages": self.capabilities.supported_languages,
                "gpu_support": self.capabilities.supports_gpu,
            },
            "config": self.config,
        }

    def validate_config(self) -> list[str]:
        """
        Validate model configuration

        Returns:
            List of validation issues (empty if valid)
        """
        issues = []

        # Override in subclasses for specific validation
        if "temperature" in self.config:
            temp = self.config["temperature"]
            if not 0 <= temp <= 2:
                issues.append(f"Temperature {temp} out of range [0, 2]")

        return issues

    def warmup(self) -> None:
        """
        Warm up the model with a simple generation

        This can help reduce initial latency
        """
        if not self._initialized:
            raise RuntimeError("Model not initialized")

        try:
            self.generate("# Hello world", max_tokens=10)
        except Exception:
            pass  # Warmup failures are non-critical

    def supports_streaming(self) -> bool:
        """Check if model supports streaming generation"""
        return self.capabilities.supports_streaming

    def stream_generate(self, prompt: str, callback: Callable[[str], None], **kwargs) -> None:
        """
        Stream generation token by token

        Args:
            prompt: Input prompt
            callback: Function called with each generated token
            **kwargs: Generation parameters

        Raises:
            NotImplementedError: If streaming not supported
        """
        if not self.supports_streaming():
            raise NotImplementedError(f"{self.metadata.name} does not support streaming")

        # Override in subclasses that support streaming
        for char in self.generate(prompt, **kwargs):
            callback(char)

    def __repr__(self) -> str:
        """String representation of the model"""
        return f"{self.__class__.__name__}(name='{self.metadata.name}', initialized={self._initialized})"


# Helper function for model implementers
def validate_model_path(path: Path, format: ModelFormat) -> None:
    """
    Validate that a model file exists and has correct format

    Args:
        path: Path to model file
        format: Expected model format

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file has wrong extension
    """
    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")

    # Check file extension matches format
    expected_extensions = {
        ModelFormat.GGUF: [".gguf"],
        ModelFormat.GGML: [".ggml", ".bin"],
        ModelFormat.PYTORCH: [".pt", ".pth", ".bin"],
        ModelFormat.ONNX: [".onnx"],
        ModelFormat.HF: [".bin", ".safetensors"],
    }

    ext = path.suffix.lower()
    if ext not in expected_extensions.get(format, []):
        raise ValueError(
            f"Invalid file extension '{ext}' for format {format.value}. Expected one of: {expected_extensions[format]}"
        )
