"""
Support package for translator helpers used to reduce complexity in translator.py.

Exports:
- TranslationContext: Lightweight context holder for streaming translations.
- StreamEmitter: Helper to emit translator events with consistent payloads.
- DependencyResolver: AST dependency analysis helper for dependency handling.
- attempt_fixes: Behavior-parity fix/refinement helper for code validation errors.
"""

from .context import TranslationContext  # noqa: F401
from .dependency_resolver import DependencyResolver  # noqa: F401
from .fix_refiner import attempt_fixes  # noqa: F401
from .offload_executor import OffloadExecutor  # noqa: F401
from .stream_emitter import StreamEmitter  # noqa: F401
