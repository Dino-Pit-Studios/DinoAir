"""
Pseudocode Translator Package

A local-only tool that parses mixed English/Python pseudocode
and translates it into functional Python code using a local language model.

Main Components:
- TranslationManager: Central orchestrator for the translation process
- ParserModule: Parses mixed English/Python pseudocode
- LLMInterface: Manages interaction with local language models
- CodeAssembler: Combines code segments into cohesive scripts
- Validator: Validates generated Python code

Usage:
    from pseudocode_translator import TranslationManager, TranslatorConfig

    config = TranslatorConfig()
    translator = TranslationManager(config)
    result = translator.translate_pseudocode("print hello world")

    if result.success:
        print(result.code)
"""

# Core components
from .assembler import CodeAssembler

# Configuration
from .config import ConfigManager, LLMConfig

# Models
from .models import BlockType, CodeBlock, ParseError, ParseResult
from .parser import ParserModule

# Prompts
from .prompts import PromptLibrary, PromptStyle, PromptTemplate
from .translator import TranslationManager, TranslationResult
from .validator import ValidationResult, Validator

__version__ = "0.1.0"
__author__ = "Pseudocode Translator Team"

__all__ = [
    # Core components
    "TranslationManager",
    "TranslationResult",
    "ParserModule",
    "CodeAssembler",
    "Validator",
    "ValidationResult",
    # Models
    "CodeBlock",
    "BlockType",
    "ParseError",
    "ParseResult",
    # Configuration
    "LLMConfig",
    "ConfigManager",
    # Prompts
    "PromptStyle",
    "PromptLibrary",
    "PromptTemplate",
]
