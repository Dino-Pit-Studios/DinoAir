"""
Service router for DinoAir core_router.

Synchronous router that:
- validates input/output via schemas
- enforces per-service rate limits (per-minute, sliding window)
- selects services by tag using policies
- records metrics and updates health
- emits JSON-ish logs
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from typing import Any, NoReturn, cast

from .adapters import make_adapter
from .adapters.base import ServiceAdapter
from .errors import (
    NoHealthyService,
    ServiceNotFound,
    ValidationError,
    not_implemented,
)

# Import HealthState for runtime use
from .health import HealthState
from .metrics import record_error, record_success
from .registry_base import ServiceDescriptor, ServiceRegistry
from .schemas import validate_input, validate_output

# Type alias for adapter factory to keep signatures short
AdapterFactory = Callable[[ServiceDescriptor], ServiceAdapter]


def _typed_make_adapter(kind: str, cfg: dict[str, Any]) -> ServiceAdapter:
    return make_adapter(kind, cfg)


# Module-level router singleton helpers
_router_singleton: ServiceRouter | None = None
_router_singleton_lock = threading.Lock()


def create_router(services_file: str | None = None) -> ServiceRouter:
    """
    Create a ServiceRouter with a populated ServiceRegistry.

    - services_file resolution precedence:
      1) explicit argument (if provided)
      2) environment variable DINO_SERVICES_FILE
      3) default "config/services.lmstudio.yaml".
    - Imports are intentionally local to avoid import-time cycles.
    - auto_register_from_config_and_env is used for best-effort service registration
      and may include optional LM Studio reachability hints.
    """
    # Local imports to avoid cycles
    import os  # local to keep import-time surface minimal

    from .registry_base import ServiceRegistry as LocalServiceRegistry  # noqa: WPS433
    from .registry_base import (
        auto_register_from_config_and_env,
    )

    if services_file is not None:
        file_path: str = services_file
    else:
        file_path = os.getenv("DINO_SERVICES_FILE", "config/services.lmstudio.yaml")
    registry = LocalServiceRegistry()
    auto_register_from_config_and_env(registry, file_path)
    return ServiceRouter(registry=registry)


def get_router() -> ServiceRouter:
    """Lazily create and return the process-wide ServiceRouter singleton."""
    if not hasattr(get_router, "router_singleton"):
        get_router.router_singleton = None
        get_router.router_singleton_lock = threading.Lock()
    if get_router.router_singleton is None:
        with get_router.router_singleton_lock:
            if get_router.router_singleton is None:
                get_router.router_singleton = create_router()
    return get_router.router_singleton


def set_router(router: ServiceRouter | None) -> None:
    """Set or reset the process-wide ServiceRouter singleton (allow None for tests)."""
    with _router_singleton_lock:
        _router_singleton = router


__all__ = [
    "ServiceRouter",
    "create_router",
    "get_router",
    "set_router",
    "health_get",
    "version_get",
    "translate_post",
    "file_search_keyword_post",
    "file_search_vector_post",
    "file_search_hybrid_post",
    "file_index_stats_get",
    "config_dirs_get",
    "metrics_get",
    "ai_chat_post",
    "router_execute_post",
    "router_execute_by_post",
    "router_metrics_get",
]


class ServiceRouter:
    """
    Service Router.

    - Keep synchronous; thread-safe internal state via a single lock.
    - Per-service sliding-window rate limit (per-minute).
    - Policies: first_healthy, round_robin, lowest_latency.
    - JSON-ish logs with keys: service, event, duration_ms, ok.
    """

    def __init__(
        self,
        registry: ServiceRegistry,
        adapter_factory: AdapterFactory | None = None,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the router.

        Args:
            registry: ServiceRegistry instance.
            adapter_factory: Optional factory that returns a ServiceAdapter for
                a ServiceDescriptor. When provided, it is used instead of the
                default adapters.make_adapter.
            logger: Optional logger; defaults to 'core_router.router'.
        """
        self._registry: ServiceRegistry = registry
        self._adapter_factory = adapter_factory
        self._logger: logging.Logger = logger or logging.getLogger("core_router.router")

        # Thread-safety for limiter state and RR pointers
        self._lock = threading.Lock()

        # Rate limit windows: service -> deque[timestamps (monotonic)]
        self._rate_windows: dict[str, deque[float]] = {}

        # Round-robin pointers: tag -> next index
        self._rr_pointers: dict[str, int] = {}

    # -------------------------
    # Public API
    # -------------------------

    def execute(self, service_name: str, payload: Mapping[str, Any]) -> object:
        """
        Execute a service with validation, rate limiting, metrics, health,
        and logging.

        Steps:
          a) Lookup descriptor.
          b) Resolve adapter kind; else raise ValidationError.
          c) Enforce per-minute sliding-window rate limit if configured.
          d) Validate input.
          e) make_adapter(kind, config) and invoke.
          f) Validate output, update health, record metrics, log, return.
        """
        # (using module-level HealthState import)

        started = time.monotonic()
        desc = self._lookup_desc_or_log_raise(started, service_name, "execute")
        try:
            kind = self._resolve_kind_or_raise(desc)

            if (rpm := self._resolve_rpm(desc)) is not None and rpm > 0:
                self._enforce_rate_limit(desc.name, rpm)

            in_payload = validate_input(desc, dict(payload))
            adapter = self._adapter_for(desc, kind)

            result = adapter.invoke(desc, in_payload)
            validated = validate_output(desc, result)

            duration_ms = int(round((time.monotonic() - started) * 1000))

            self._registry.update_health(
                desc.name,
                HealthState.HEALTHY,
                latency_ms=duration_ms,
            )

            record_success(desc.name, duration_ms)

            self._log_event(
                service=desc.name,
                event="execute",
                duration_ms=duration_ms,
                ok=True,
            )
            return validated
        except ValidationError as exc:
            duration_ms = int(round((time.monotonic() - started) * 1000))
            record_error(desc.name, duration_ms, str(exc))
            # No health change for validation errors
            return None
        except Exception as exc:
            self._extracted_from_execute_77(started, desc, exc)

    def _extracted_from_execute_77(
        self,
        started: float,
        desc: ServiceDescriptor,
        exc: Exception,
    ) -> NoReturn:
        result = int(round((time.monotonic() - started) * 1000))
        record_error(desc.name, result, str(exc))
        self._registry.update_health(desc.name, HealthState.DOWN, latency_ms=result, error=str(exc))
        self._log_event(
            service=desc.name,
            event="execute",
            duration_ms=result,
            ok=False,
            error=str(exc),
        )
        raise exc

    # TODO: Rename method 'check_health' to 'ping_service_health' and update all references in codebase (e.g., calls in execute and monitoring logic).
    def check_health(self, service_name: str) -> dict[str, Any]:
        """
        Check health of a service by pinging its adapter and update registry.

        Returns a dict snapshot of the latest health info for the service.
        """
        from .health_utils import ping_with_timing  # Import from decoupled module

        started = time.monotonic()
        desc = self._lookup_desc_or_log_raise(started, service_name, "check_health")
        kind = self._resolve_kind_or_raise(desc)

        adapter = self._adapter_for(desc, kind)

        state_str, adapter_ms = ping_with_timing(adapter)

        # Convert string state to HealthState enum for registry update
        state = HealthState(state_str)

        # Update registry with adapter-reported state and latency
        self._registry.update_health(desc.name, state, latency_ms=adapter_ms)

        # Event duration includes lookup + construction + ping
        duration_ms = int(round((time.monotonic() - started) * 1000))
        self._log_event(
            service=desc.name,
            event="check_health",
            duration_ms=duration_ms,
            ok=(state == HealthState.HEALTHY),
        )

        # Return latest snapshot (defensive copy via dict())
        return dict(self._registry.get_by_name(service_name).health or {})

    # TODO: Rename helper '_extracted_from_check_health_19' to 'handle_check_health_error', wire up its usage in 'check_health' and update callers accordingly.
    def _extracted_from_check_health_19(
        self,
        started: float,
        service_name: str,
        event: str,
        exc: Exception,
    ) -> NoReturn:
        result = int(round((time.monotonic() - started) * 1000))
        self._log_event(
            service=service_name,
            event=event,
            duration_ms=result,
            ok=False,
            error=str(exc),
        )
        raise exc

    def execute_by(
        self,
        tag: str,
        payload: Mapping[str, Any],
        policy: str = "first_healthy",
    ) -> object:
        """
        Execute a service selected by tag and policy.

        Policies:
          - "first_healthy": first by name-sorted order.
          - "round_robin": cycle across healthy services per tag.
          - "lowest_latency": smallest health['latency_ms']; tie-break by name.
        Raises:
          - ServiceNotFound if no services are registered for the tag.
          - NoHealthyService if none of the candidates are healthy.
        """
        if not (candidates := self._registry.get_by_tag(tag)):
            raise ServiceNotFound(f"No services registered for tag '{tag}'")

        if not (healthy := [d for d in candidates if self._is_healthy(d)]):
            raise NoHealthyService(
                f"No healthy service available for tag '{tag}' with policy '{policy}'"
            )

        p = (policy or "first_healthy").strip().lower()

        if p == "first_healthy" or p not in ["round_robin", "lowest_latency"]:
            chosen = sorted(healthy, key=lambda d: d.name)[0]
        elif p == "round_robin":
            chosen = self._select_round_robin(tag, healthy)
        else:
            chosen = self._select_lowest_latency(healthy)
        self._log_event(
            service=chosen.name,
            event="route_select",
            duration_ms=0,
            ok=True,
            tag=tag,
            policy=p,
        )

        return self.execute(chosen.name, payload)

    # -------------------------
    # Internals
    # -------------------------

    @staticmethod
    def _resolve_adapter_kind(desc: ServiceDescriptor) -> str | None:
        """
        Prefer 'kind' if present, else 'adapter'.
        Return normalized lower-case string or None.
        """
        kind = getattr(desc, "kind", None)
        if isinstance(kind, str) and kind.strip():
            return kind.strip().lower()
        adapter = getattr(desc, "adapter", None)
        if isinstance(adapter, str) and adapter.strip():
            return adapter.strip().lower()
        return None

    def _lookup_desc_or_log_raise(
        self, started: float, service_name: str, event: str
    ) -> ServiceDescriptor:
        """
        Lookup a service descriptor by name; on ServiceNotFound, log and
        re-raise via _extracted_from_check_health_19.
        """
        try:
            return self._registry.get_by_name(service_name)
        except ServiceNotFound as exc:
            self._extracted_from_check_health_19(started, service_name, event, exc)
            return None

    def _resolve_kind_or_raise(self, desc: ServiceDescriptor) -> str:
        """
        Resolve adapter kind from a descriptor or raise ValidationError with a consistent message.
        """
        kind = self._resolve_adapter_kind(desc)
        if not kind:
            raise ValidationError(f"missing adapter kind for service '{desc.name}'")
        return kind

    def _adapter_for(self, desc: ServiceDescriptor, kind: str) -> ServiceAdapter:
        """
        Return an adapter instance for the given descriptor and kind using either the
        injected factory or default.
        """
        factory: AdapterFactory = self._adapter_factory or (
            lambda _d: _typed_make_adapter(kind, desc.adapter_config)
        )
        return factory(desc)

    @staticmethod
    def _get_health_state(desc: ServiceDescriptor) -> HealthState | None:
        """Return HealthState from desc.health, if available."""
        h = getattr(desc, "health", None)
        if not isinstance(h, dict):
            return None
        m = cast("dict[str, Any]", h)
        state = m.get("state")
        if isinstance(state, HealthState):
            return state
        if isinstance(state, str):
            try:
                return HealthState(state.upper())
            except Exception:
                return None
        return None

    def _resolve_rpm(self, desc: ServiceDescriptor) -> int | None:
        """
        Resolve per-minute rate limit from descriptor.

        Priority:
          - desc.rate_limit_per_minute
          - desc.rate_limits['rpm'] or ['per_minute'] (case-insensitive)
        """
        rlpm = getattr(desc, "rate_limit_per_minute", None)
        val = self._to_positive_int(rlpm)
        if val is not None:
            return val

        rl = getattr(desc, "rate_limits", None)
        if isinstance(rl, Mapping):
            mrl = cast("Mapping[str, Any]", rl)
            for key in ("rpm", "per_minute", "perMinute", "per-minute"):
                if key in mrl:
                    v = self._to_positive_int(mrl.get(key))
                    if v is not None:
                        return v
        return None

    @staticmethod
    def _to_positive_int(v: Any) -> int | None:
        try:
            if v is None:
                return None
            f = float(v)
            if f <= 0:
                return None
            return int(f) if f.is_integer() else int(round(f))
        except Exception:
            return None

    def _enforce_rate_limit(self, service_name: str, rpm: int) -> None:
        """Sliding-window limiter over the last 60 seconds."""
        now = time.monotonic()
        with self._lock:
            dq: deque[float] = self._rate_windows.setdefault(service_name, deque())

            cutoff = now - 60.0
            while dq and dq[0] <= cutoff:
                dq.popleft()

            if len(dq) >= rpm:
                raise ValidationError(f"rate limit exceeded: {rpm} rpm")

            dq.append(now)

    @staticmethod
    def _is_healthy(desc: ServiceDescriptor) -> bool:
        """
        Consider descriptor healthy when:
          - no health info is present (optimistic-by-default), or
          - health['state'] == HealthState.HEALTHY (enum or string).
        """
        state = ServiceRouter._get_health_state(desc)
        return True if state is None else state == HealthState.HEALTHY

    def _select_round_robin(
        self,
        tag: str,
        healthy: Sequence[ServiceDescriptor],
    ) -> ServiceDescriptor:
        """Round-robin among healthy services, deterministic by name."""
        sorted_healthy = sorted(healthy, key=lambda d: d.name)
        with self._lock:
            idx = self._rr_pointers.get(tag, 0)
            if idx >= len(sorted_healthy) or idx < 0:
                idx = 0
            choice = sorted_healthy[idx]
            self._rr_pointers[tag] = (idx + 1) % len(sorted_healthy)
            return choice

    @staticmethod
    def _select_lowest_latency(
        healthy: Sequence[ServiceDescriptor],
    ) -> ServiceDescriptor:
        """
        Choose the healthy service with the smallest health['latency_ms'].
        Tie-breaker: name.
        """

        def _lat(d: ServiceDescriptor) -> float:
            h = getattr(d, "health", None)
            if isinstance(h, dict):
                md = cast("dict[str, Any]", h)
                with suppress(Exception):
                    v = float(md.get("latency_ms"))  # type: ignore[arg-type]
                    if v >= 0:
                        return v
            return float("inf")

        return sorted(healthy, key=lambda d: (_lat(d), d.name))[0]

    def _log_event(
        self,
        *,
        service: str,
        event: str,
        duration_ms: int,
        ok: bool,
        tag: str | None = None,
        policy: str | None = None,
        error: str | None = None,
    ) -> None:
        """
        Emit JSON-ish single-line log with required keys and optional
        tag/policy/error.
        """
        payload: dict[str, Any] = {
            "service": service,
            "event": event,
            "duration_ms": duration_ms,
            "ok": ok,
        }
        if tag is not None:
            payload["tag"] = tag
        if policy is not None:
            payload["policy"] = policy
        if error is not None:
            payload["error"] = str(error)

        line = json.dumps(payload, ensure_ascii=False)
        if ok:
            self._logger.info(line)
        else:
            self._logger.error(line)


def _internal_error_response(exc: Exception, endpoint: str, operation_id: str) -> Any:
    from .errors import error_response  # local import to avoid hard dep at import time

    return error_response(
        status=500,
        code="ERR_INTERNAL",
        message=str(exc),
        error="Internal Error",
        details=None,
        endpoint=endpoint,
        operationId=operation_id,
        requestId=None,
    )


def _ni(method: str, path: str, operation_id: str) -> Any:
    return not_implemented(method, path, operation_id)


# In-file helpers to reduce duplicate endpoint wrappers
def _make_ni_noargs(method: str, path: str, operation_id: str) -> Callable[[], Any]:
    def _f() -> Any:
        return _ni(method, path, operation_id)

    return _f


def _make_ni_body(method: str, path: str, operation_id: str) -> Callable[[Any], Any]:
    def _f(_body: Any) -> Any:  # noqa: ARG001 - arg is part of public signature
        return _ni(method, path, operation_id)

    return _f


def _safe_call(endpoint: str, operation_id: str, f: Callable[[], Any]) -> Any:
    """
    Execute f() and convert unexpected exceptions into a standardized error response.
    Kept local to this module to avoid any new utilities or modules.
    """
    try:
        return f()
    except Exception as exc:
        return _internal_error_response(exc, endpoint, operation_id)


def _health_impl() -> Any:
    # local imports to minimize import-time surface
    from fastapi.responses import JSONResponse

    from .health import health_response

    body, status_code = health_response()
    return JSONResponse(content=body, status_code=status_code)


def _version_impl() -> Any:
    from .health import version_info

    return version_info()


def _metrics_impl() -> Any:
    from .metrics import minimal_snapshot

    return minimal_snapshot()


# -------------------------
# HTTP endpoint placeholders (per OpenAPI spec)
# -------------------------


def health_get() -> Any:
    """GET /health — operationId: health_health_get"""
    return _safe_call("GET /health", "health_health_get", _health_impl)


def version_get() -> Any:
    """GET /version — operationId: version_version_get"""
    return _safe_call("GET /version", "version_version_get", _version_impl)


translate_post = _make_ni_body("POST", "/translate", "translate_translate_post")
translate_post.__name__ = "translate_post"
translate_post.__doc__ = "POST /translate — operationId: translate_translate_post"


file_search_keyword_post = _make_ni_body(
    "POST", "/file-search/keyword", "keyword_search_file_search_keyword_post"
)
file_search_keyword_post.__name__ = "file_search_keyword_post"
file_search_keyword_post.__doc__ = (
    "POST /file-search/keyword — operationId: keyword_search_file_search_keyword_post"
)


file_search_vector_post = _make_ni_body(
    "POST", "/file-search/vector", "vector_search_file_search_vector_post"
)
file_search_vector_post.__name__ = "file_search_vector_post"
file_search_vector_post.__doc__ = (
    "POST /file-search/vector — operationId: vector_search_file_search_vector_post"
)


file_search_hybrid_post = _make_ni_body(
    "POST", "/file-search/hybrid", "hybrid_search_file_search_hybrid_post"
)
file_search_hybrid_post.__name__ = "file_search_hybrid_post"
file_search_hybrid_post.__doc__ = (
    "POST /file-search/hybrid — operationId: hybrid_search_file_search_hybrid_post"
)


file_index_stats_get = _make_ni_noargs(
    "GET", "/file-index/stats", "file_index_stats_file_index_stats_get"
)
file_index_stats_get.__name__ = "file_index_stats_get"
file_index_stats_get.__doc__ = (
    "GET /file-index/stats — operationId: file_index_stats_file_index_stats_get"
)


config_dirs_get = _make_ni_noargs("GET", "/config/dirs", "get_config_dirs_config_dirs_get")
config_dirs_get.__name__ = "config_dirs_get"
config_dirs_get.__doc__ = "GET /config/dirs — operationId: get_config_dirs_config_dirs_get"


def metrics_get() -> Any:
    """GET /metrics — operationId: metrics_metrics_get"""
    return _safe_call("GET /metrics", "metrics_metrics_get", _metrics_impl)


ai_chat_post = _make_ni_body("POST", "/ai/chat", "ai_chat_ai_chat_post")
ai_chat_post.__name__ = "ai_chat_post"
ai_chat_post.__doc__ = "POST /ai/chat — operationId: ai_chat_ai_chat_post"


router_execute_post = _make_ni_body("POST", "/router/execute", "router_execute_router_execute_post")
router_execute_post.__name__ = "router_execute_post"
router_execute_post.__doc__ = (
    "POST /router/execute — operationId: router_execute_router_execute_post"
)


router_execute_by_post = _make_ni_body(
    "POST", "/router/executeBy", "router_execute_by_router_executeBy_post"
)
router_execute_by_post.__name__ = "router_execute_by_post"
router_execute_by_post.__doc__ = (
    "POST /router/executeBy — operationId: router_execute_by_router_executeBy_post"
)


router_metrics_get = _make_ni_noargs("GET", "/router/metrics", "router_metrics_router_metrics_get")
router_metrics_get.__name__ = "router_metrics_get"
router_metrics_get.__doc__ = "GET /router/metrics — operationId: router_metrics_router_metrics_get"
