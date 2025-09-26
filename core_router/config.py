"""
Config loader for core_router services.

- Load list of ServiceDescriptor from YAML or JSON.
- Support top-level list or object with "services".
- Normalize field synonyms (kind <-> adapter).
- Map rate_limit_per_minute to rate_limits when needed.
- Apply DINO_SERVICE_{KEY}__ env overrides.
- Construct ServiceDescriptor via pydantic and wrap errors.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, MutableMapping
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

if TYPE_CHECKING:
    # Only for typing; import real class at runtime
    from .registry import ServiceDescriptor  # noqa: F401

__all__ = ["load_services_from_file"]


def _coerce_env_value(value: str) -> Any:
    """Parse env override value via JSON; otherwise return raw string."""
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def _service_env_prefix(name: str) -> str:
    """
    Build per-service env var prefix:
    DINO_SERVICE_{SERVICE_KEY}__ where SERVICE_KEY uppercases the name and
    replaces non-alphanumerics with underscores.
    """
    key = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return f"DINO_SERVICE_{key}__"


def _apply_env_overrides(
    entry: Mapping[str, Any],
    env: Mapping[str, str],
) -> dict[str, Any]:
    """
    Apply DINO_SERVICE_* overrides to a service dict and return a new dict.
    Path segments use double-underscores and create nested dicts as needed.
    Example:
        DINO_SERVICE_LLM_CHAT__adapter_config__base_url=http://127.0.0.1:1234/v1
    """
    name = str(entry.get("name", "")).strip()
    out: dict[str, Any] = dict(entry)
    if not name:
        return out
    prefix = _service_env_prefix(name)
    for k, v in env.items():
        if not k.startswith(prefix):
            continue
        tail = k[len(prefix) :]
        parts = [p for p in tail.split("__") if p]
        if not parts:
            continue
        cur: MutableMapping[str, Any] = out
        for seg in parts[:-1]:
            nxt = cast("dict[str, Any] | None", cur.get(seg))
            if not isinstance(nxt, dict):
                nxt = {}
                cur[seg] = nxt
            cur = cast("MutableMapping[str, Any]", nxt)
        cur[parts[-1]] = _coerce_env_value(v)
    return out


def _copy_known_fields(raw: Mapping[str, Any]) -> dict[str, Any]:
    """
    Return a shallow dict with only the known passthrough fields that should be
    carried into normalization when present.
    """
    keys = (
        "name",
        "version",
        "tags",
        "adapter_config",
        "input_schema",
        "output_schema",
        "rate_limits",
        "deps",
        "health",
        "metadata",
    )
    return {k: raw[k] for k in keys if k in raw}


def _compute_adapter_or_kind(
    raw: Mapping[str, Any],
    *,
    supports_adapter: bool,
    supports_kind: bool,
) -> dict[str, Any]:
    """
    Normalize the adapter/kind synonym into whichever field is supported by the model.
    Prefer explicit 'adapter' when provided; otherwise fall back to 'kind'.
    """
    adapter_value = raw.get("adapter", raw.get("kind"))
    if adapter_value is None:
        return {}
    if supports_adapter:
        return {"adapter": adapter_value}
    return {"kind": adapter_value} if supports_kind else {}


def _map_rate_limit_fields(
    raw: Mapping[str, Any],
    model_fields: Mapping[str, Any],
    existing_rate_limits: Any,
) -> dict[str, Any]:
    """
    Map legacy 'rate_limit_per_minute' into either the same field (if supported)
    or into 'rate_limits' with an 'rpm' value. Preserve existing rate_limits content.
    """
    if "rate_limit_per_minute" not in raw:
        return {}
    rlpm = raw.get("rate_limit_per_minute")
    if "rate_limit_per_minute" in model_fields:
        return {"rate_limit_per_minute": rlpm}
    if "rate_limits" in model_fields:
        base_rl: dict[str, Any] = (
            dict(cast("Mapping[str, Any]", existing_rate_limits))
            if isinstance(existing_rate_limits, Mapping)
            else {}
        )
        val: Any = rlpm
        with suppress(Exception):
            f = float(rlpm)  # type: ignore[arg-type]
            val = int(f) if f.is_integer() else f
        return {"rate_limits": base_rl | {"rpm": val}}
    return {}


def _apply_default_version(norm: dict[str, Any], model_fields: Mapping[str, Any]) -> None:
    """
    Provide a default 'version' only when the model exposes the field and the
    config did not provide it.
    """
    if "version" in model_fields and "version" not in norm:
        norm["version"] = "1.0.0"


def _normalize_adapter_config_inplace(norm: dict[str, Any]) -> None:
    """
    Ensure 'adapter_config' is a dict when present. Convert None to {}, and
    coerce other mapping-like values via dict(...).
    """
    if "adapter_config" in norm and not isinstance(norm["adapter_config"], dict):
        if norm["adapter_config"] is None:
            norm["adapter_config"] = {}
        else:
            norm["adapter_config"] = dict(norm["adapter_config"])


def _normalize_service_dict(
    raw: Mapping[str, Any],
    model_fields: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Normalize a service entry to align with ServiceDescriptor fields.
    - Ensure 'name' exists.
    - Map synonyms: kind <-> adapter.
    - Map rate_limit_per_minute to rate_limits.rpm
      when model uses 'rate_limits'.
    - Preserve tags, adapter_config, input_schema, output_schema,
      metadata, deps, and health.
    - Provide default 'version' when required and missing.
    """
    from .errors import ValidationError

    # Validate required 'name'
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("config missing service name")

    supports_adapter = "adapter" in model_fields
    supports_kind = "kind" in model_fields

    # Start with known passthrough fields
    norm: dict[str, Any] = _copy_known_fields(raw)

    # Adapter/kind normalization
    norm |= _compute_adapter_or_kind(
        raw,
        supports_adapter=supports_adapter,
        supports_kind=supports_kind,
    )

    # Rate limit field mapping
    norm.update(
        _map_rate_limit_fields(
            raw,
            model_fields,
            norm.get("rate_limits"),
        )
    )

    # Default version if applicable
    _apply_default_version(norm, model_fields)

    # Ensure adapter_config is a dict
    _normalize_adapter_config_inplace(norm)

    return norm


def _parse_document(text: str, *, prefer: str | None = None) -> Any:
    """
    Parse text as YAML or JSON. If 'prefer' is 'yaml' or 'json', try it first.
    On failure, try the other format.
    """

    def try_yaml() -> Any:
        if yaml is None:
            raise RuntimeError("PyYAML required. Install 'pyyaml'.")
        return yaml.safe_load(text)

    def try_json() -> Any:
        return json.loads(text)

    if prefer == "yaml":
        order = ("yaml", "json")
    elif prefer == "json":
        order = ("json", "yaml")
    else:
        order = ("yaml", "json")

    last_err: Exception | None = None
    for fmt in order:
        try:
            return try_yaml() if fmt == "yaml" else try_json()
        except Exception as e:
            last_err = e
    if last_err is None:
        raise AssertionError("No error occurred, but no valid format found")
    raise last_err


def _resolve_config_path(path: str) -> Path:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Services file not found: {path}")
    return p


def _read_config_text(p: Path) -> tuple[str, str]:
    text = p.read_text(encoding="utf-8")
    return text, p.suffix.lower()


def _preferred_format_from_ext(ext: str) -> str | None:
    if ext in {".yaml", ".yml"}:
        return "yaml"
    return "json" if ext == ".json" else None


def _parse_services_payload(text: str, *, prefer: str | None) -> Any:
    return _parse_document(text, prefer=prefer)


def _extract_services_block(doc: Any) -> list[Any]:
    if isinstance(doc, list):
        return cast("list[Any]", doc)
    if isinstance(doc, Mapping):
        d = cast("Mapping[str, Any]", doc)
        services = d.get("services")
        if isinstance(services, list):
            return cast("list[Any]", services)
        raise ValueError("Config must be list or object with 'services' array")
    raise ValueError("Config root must be a list or an object")


def _build_descriptor_from_entry(
    raw_entry: Mapping[str, Any],
    *,
    model_fields: Mapping[str, Any],
    env: Mapping[str, str],
    apply_env: bool,
    SD: Any,
):
    from pydantic import ValidationError as PydanticValidationError

    from .errors import ValidationError

    try:
        base = _normalize_service_dict(raw_entry, model_fields)
        final_entry = _apply_env_overrides(base, env) if apply_env else dict(base)
        return SD.model_validate(final_entry)
    except PydanticValidationError as e:
        svc_name = str(raw_entry.get("name", "<unknown>"))
        raise ValidationError(
            f"config load failed for {svc_name}",
            details=cast("Any", e.errors()),
        ) from e
    except ValidationError:
        raise
    except Exception as e:
        svc_name = str(raw_entry.get("name", "<unknown>"))
        raise ValidationError(
            f"config load failed for {svc_name}",
            details=str(e),
        ) from e


def load_services_from_file(
    path: str,
    *,
    apply_env: bool = True,
) -> list[ServiceDescriptor]:
    """
    Load services from YAML/JSON and return list[ServiceDescriptor].

    - Detect format from extension; if unknown, try YAML then JSON.
    - Accept top-level list or object with "services".
    - Normalize fields and apply DINO_SERVICE_* overrides when enabled.
    - Construct ServiceDescriptor and wrap validation errors.
    """
    from .registry import ServiceDescriptor as SD

    p = _resolve_config_path(path)
    text, ext = _read_config_text(p)
    prefer = _preferred_format_from_ext(ext)
    doc = _parse_services_payload(text, prefer=prefer)
    services_raw = _extract_services_block(doc)

    env = dict(os.environ) if apply_env else {}
    model_fields = getattr(SD, "model_fields", {})

    out: list[SD] = []
    for raw_entry in services_raw:
        if not isinstance(raw_entry, Mapping):
            raise ValueError("Each service entry must be a mapping/object")
        entry_map = cast("Mapping[str, Any]", raw_entry)
        desc = _build_descriptor_from_entry(
            entry_map,
            model_fields=model_fields,
            env=env,
            apply_env=apply_env,
            SD=SD,
        )
        out.append(desc)

    return out
