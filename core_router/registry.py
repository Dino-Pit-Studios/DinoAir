"""
Service registry and descriptor model for DinoAir core_router.

Provides:
- ServiceDescriptor: pydantic model describing a service.
- ServiceRegistry: in-memory registry with CRUD and lookup utilities.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from threading import Lock
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

from .errors import ServiceNotFound
from .health import HealthState

if TYPE_CHECKING:
    import builtins


class ServiceDescriptor(BaseModel):
    """Pydantic model for a service's static config and runtime hints."""

    name: str
    version: str
    tags: list[str] = Field(default_factory=list)

    # JSON-schema-like dicts (validated elsewhere)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None

    # Adapter wiring
    adapter: str  # e.g. "local_python" | "lmstudio"
    adapter_config: dict[str, Any] = Field(default_factory=dict)

    # Optional operational knobs and metadata
    # e.g. {"qps": 5} or {"rpm": 300}
    rate_limits: dict[str, Any] | None = None
    deps: list[str] | None = None
    # health snapshot: {"state": "...", "latency_ms": number}
    health: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Pydantic v2 configuration
    model_config = ConfigDict(validate_assignment=True, frozen=False)


class ServiceRegistry:
    """
    Thread-safe in-memory registry for ServiceDescriptor objects.

    - Services are keyed by unique 'name'.
    - Registering an existing name overwrites the previous descriptor.
    """

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self._services: dict[str, ServiceDescriptor] = {}

    # -------------------------
    # CRUD / Lookup
    # -------------------------
    def register(self, desc: ServiceDescriptor | Mapping[str, Any]) -> ServiceDescriptor:
        """
        Register or replace by name.

        Accepts a ServiceDescriptor or plain dict. Returns stored descriptor.
        """
        sd = desc if isinstance(desc, ServiceDescriptor) else ServiceDescriptor(**dict(desc))
        with self._lock:
            self._services[sd.name] = sd
            return sd

    def unregister(self, name: str) -> bool:
        """Remove a service by name. True if removed, else False."""
        with self._lock:
            return self._services.pop(name, None) is not None

    def get_by_name(self, name: str) -> ServiceDescriptor:
        """
        Retrieve a descriptor by unique name.

        Raises:
            ServiceNotFound: if the service does not exist.
        """
        with self._lock:
            try:
                return self._services[name]
            except KeyError as exc:
                raise ServiceNotFound(f"Service '{name}' not found") from exc

    def get_by_tag(self, tag: str) -> builtins.list[ServiceDescriptor]:
        """Return services containing the tag (case-insensitive)."""
        t = (tag or "").lower()
        with self._lock:
            return [d for d in self._services.values() if t in {x.lower() for x in d.tags}]

    def list(self) -> builtins.list[ServiceDescriptor]:
        """Return all registered services."""
        with self._lock:
            return list(self._services.values())

    # -------------------------
    # Health
    # -------------------------
    def update_health(
        self,
        name: str,
        state_or_info: HealthState | Mapping[str, Any],
        latency_ms: int | float | None = None,
        error: str | None = None,
    ) -> ServiceDescriptor:
        """
        Update health snapshot for a service.

        Forms:
        - update_health(name, {"state": HealthState|str, "latency_ms": n, ...})
        - update_health(name, HealthState.X, latency_ms=..., error=...)

        Returns the updated ServiceDescriptor.
        """
        with self._lock:
            try:
                desc = self._services[name]
            except KeyError as exc:
                raise ServiceNotFound(f"Service '{name}' not found") from exc

            info: dict[str, Any]
            if isinstance(state_or_info, Mapping):
                # Normalize provided dict
                info = dict(state_or_info)
                s = info.get("state")
                if isinstance(s, HealthState):
                    info["state"] = s.value
                elif isinstance(s, str):
                    info["state"] = s.upper()
                # best-effort numeric coercion
                if "latency_ms" in info:
                    with suppress(Exception):
                        info["latency_ms"] = float(info["latency_ms"])
            else:
                # Build dict from discrete values
                info = {"state": state_or_info.value}
                if latency_ms is not None:
                    info["latency_ms"] = float(latency_ms)
            if error is not None:
                info["error"] = str(error)
            desc.health = info
            return desc


# -------------------------
# Auto-registration helper (soft validation)
# -------------------------


def auto_register_from_config_and_env(
    registry: ServiceRegistry,
    services_file: str = "config/services.lmstudio.yaml",
) -> ServiceRegistry:
    """
    Load services from the default YAML (and apply env overrides) and register
    them into the provided registry. Soft-validate LM Studio base URL(s) with
    a short HEAD/GET probe and update health accordingly. Never raises.

    Returns the provided registry for chaining.
    """

    import httpx

    from .config import load_services_from_file
    from .health import HealthState as _HealthState

    try:
        services = load_services_from_file(services_file)
    except Exception:
        services = []

    for s in services:
        try:
            registry.register(s)
        except Exception:
            continue

        # Minimal reachability check for LM Studio services
        adapter_kind = getattr(s, "adapter", None)
        if not isinstance(adapter_kind, str) or adapter_kind.strip().lower() != "lmstudio":
            continue

        base_url = None
        with suppress(Exception):
            cfg = getattr(s, "adapter_config", {}) or {}
            base_url = str(cfg.get("base_url") or "").strip() or None

        if not base_url:
            # Mark as DEGRADED when base URL is unknown
            with suppress(Exception):
                registry.update_health(
                    s.name, _HealthState.DEGRADED, latency_ms=0, error="missing base_url"
                )
            continue

        ok = False
        with suppress(Exception):
            r = httpx.head(base_url, timeout=0.8)
            ok = 200 <= r.status_code < 300
        if not ok:
            with suppress(Exception):
                r2 = httpx.get(base_url, timeout=0.8)
                ok = 200 <= r2.status_code < 300

        with suppress(Exception):
            registry.update_health(
                s.name,
                _HealthState.HEALTHY if ok else _HealthState.DEGRADED,
                latency_ms=0,
            )

    return registry
