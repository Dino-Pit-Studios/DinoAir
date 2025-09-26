from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Any, cast

from core_router.config import load_services_from_file
from core_router.registry import ServiceRegistry
from core_router.router import ServiceRouter

from ..settings import Settings, get_lmstudio_env

_router_singleton: ServiceRouter | None = None


def _get_adapter_value(svc: object) -> str | None:
    adapter: str | None = None
    if hasattr(svc, "adapter"):
        v = svc.adapter
        if isinstance(v, str):
            adapter = v
    elif isinstance(svc, Mapping):
        m = cast("Mapping[str, Any]", svc)
        v = m.get("adapter") or m.get("kind")
        if isinstance(v, str):
            adapter = v
    return adapter


def _is_lmstudio_adapter(adapter: str | None) -> bool:
    return isinstance(adapter, str) and adapter.strip().lower() == "lmstudio"


def _current_adapter_config(svc: object) -> dict[str, Any]:
    if hasattr(svc, "adapter_config"):
        cfg = svc.adapter_config
    elif isinstance(svc, Mapping):
        m = cast("Mapping[str, Any]", svc)
        cfg = m.get("adapter_config")
    else:
        cfg = None
    return dict(cast("Mapping[str, Any]", cfg)) if isinstance(cfg, Mapping) else {}


def _build_overridden_config(cfg_dict: dict[str, Any], env: Any) -> dict[str, Any]:
    headers = cfg_dict.get("headers")
    headers_dict: dict[str, Any] = (
        dict(cast("Mapping[str, Any]", headers)) if isinstance(headers, Mapping) else {}
    )

    # Apply env-backed overrides
    cfg_dict["base_url"] = env.base_url
    cfg_dict["model"] = env.default_model
    cfg_dict["timeout_s"] = int(env.request_timeout_s)
    if getattr(env, "api_key", None):
        headers_dict["Authorization"] = f"Bearer {env.api_key}"
    if headers_dict:
        cfg_dict["headers"] = headers_dict

    return cfg_dict


def _try_model_copy_update(svc: object, cfg_dict: dict[str, Any]) -> object | None:
    if hasattr(svc, "model_copy"):
        with suppress(Exception):
            # type: ignore[attr-defined]
            return svc.model_copy(update={"adapter_config": cfg_dict})
    return None


def _apply_config_in_place(svc: object, cfg_dict: dict[str, Any]) -> None:
    with suppress(Exception):
        if hasattr(svc, "adapter_config"):
            svc.adapter_config = cfg_dict
        elif isinstance(svc, dict):
            svc["adapter_config"] = cfg_dict
    # Best-effort only; keep original on failure


def _apply_lmstudio_env_overrides(services: Sequence[Any]) -> list[Any]:
    """
    Apply LM Studio env-backed overrides to services whose
    adapter == "lmstudio".

    - Supports pydantic models via model_copy(update=...) when available.
    - Otherwise mutates dicts in place.
    - Non-lmstudio services are left untouched.
    """
    env = get_lmstudio_env()
    out: list[Any] = []
    for svc in services or []:
        with suppress(Exception):
            if not _is_lmstudio_adapter(_get_adapter_value(svc)):
                out.append(svc)
                continue

            cfg_dict = _build_overridden_config(_current_adapter_config(svc), env)

            replaced = _try_model_copy_update(svc, cfg_dict)
            if replaced is not None:
                out.append(replaced)
                continue

            _apply_config_in_place(svc, cfg_dict)
        out.append(svc)
    return out


_router_singleton = None


@lru_cache(maxsize=1)
    def get_router() -> ServiceRouter:
        """
        Return a process-wide ServiceRouter singleton initialized
        from a services file. This keeps the API layer decoupled
        from specific adapters.

        The default file is 'config/services.lmstudio.yaml'.
        It can be overridden later via the DINO_SERVICES_FILE
        environment variable in a follow-up PR.
        """
        # Resolve services file path with layered precedence:
        # 1) Env override DINO_SERVICES_FILE
        # 2) Settings().services_config_path (DINOAIR_SERVICES_FILE)
        # 3) Default "config/services.lmstudio.yaml"
        env_file = os.getenv("DINO_SERVICES_FILE")
        if env_file and str(env_file).strip():
            services_file = env_file
        else:
            try:
                settings = Settings()
                settings_file = getattr(settings, "services_config_path", None)
            except Exception:
                settings_file = None
            services_file = settings_file or "config/services.lmstudio.yaml"

        services = load_services_from_file(services_file)
        services = _apply_lmstudio_env_overrides(services)
        registry = ServiceRegistry()
        for s in services:
            registry.register(s)
        return ServiceRouter(registry)
