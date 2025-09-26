"""
Controllers package for pseudocode_translator.

Exports controller classes to avoid deep import paths and ensure package recognition.
"""

from .llm_first import LlmFirstController  # noqa: F401
from .structured_flow import StructuredParsingController  # noqa: F401

__all__ = ["LlmFirstController", "StructuredParsingController"]
