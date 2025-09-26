"""
Registry base module - compatibility layer.

This module provides imports from registry.py for backward compatibility.
"""

# Import the classes from the actual registry module
from .registry import ServiceDescriptor, ServiceRegistry

__all__ = ["ServiceDescriptor", "ServiceRegistry"]
