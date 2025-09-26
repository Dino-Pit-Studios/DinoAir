"""
Adapter protocol and utilities for core_router.

Adapters encapsulate transport/execution details for services.
They must be synchronous and SHOULD NOT mutate the provided payload.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..errors import AdapterError

__all__ = ["ServiceAdapter", "ensure_protocol"]


@runtime_checkable
class ServiceAdapter(Protocol):
    """
    Protocol for service adapters used by the router.

    Requirements:
      - invoke(service_desc, payload: dict) -> object
        Perform the operation synchronously. Implementations should not
        mutate the provided payload.
      - ping() -> bool
        Return True if the adapter is healthy. Implementations should
        avoid raising for normal health checks.
    """

    def invoke(
        self,
        service_desc: Any,
        payload: dict[str, Any],
    ) -> object:  # pragma: no cover - protocol signature
        ...

    def ping(self) -> bool:  # pragma: no cover - protocol signature
        ...


def ensure_protocol(obj: Any) -> None:
    """
    Ensure the given object satisfies the ServiceAdapter protocol at runtime.

    Raises:
        AdapterError: if the object does not appear to implement the protocol.
    """
    if not isinstance(obj, ServiceAdapter):
        raise AdapterError(
            adapter="protocol",
            reason="Object does not implement ServiceAdapter",
        )
