"""
Pydantic-backed JSON-schema-like validation helpers for core_router.

Scope:
- Dynamic BaseModel construction from a lightweight JSON-Schema-like dict
- Root type "object" with:
  - properties: types among string, integer, number, boolean, array, object
  - required: presence enforcement
  - arrays: items.type mapped when present; default Any
- Additional properties allowed; side-effect free.

Exports:
- validate_input(desc, payload)
- validate_output(desc, payload)
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from pydantic import (
    BaseModel,
)
from pydantic import Field as PydField
from pydantic import ValidationError as PydanticValidationError
from pydantic import (
    create_model,
)
from pydantic.config import ConfigDict

from .errors import ValidationError

if TYPE_CHECKING:
    from .registry import ServiceDescriptor

__all__ = ["validate_input", "validate_output"]


class _DynamicBaseModel(BaseModel):
    """Base config for dynamic models: allow extras, validate assignments."""

    model_config = ConfigDict(
        extra="allow",
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )


def _get_schema(desc: Any, key: str) -> dict[str, Any] | None:
    """Extract schema ('input' or 'output') from a descriptor or Mapping."""
    attr = f"{key}_schema"
    if hasattr(desc, attr):
        return getattr(desc, attr)
    if isinstance(desc, Mapping):
        val = desc.get(attr)  # type: ignore[index]
        return cast("dict[str, Any] | None", val)
    return None


def _to_service_name(desc: Any) -> str:
    """Best-effort service name for error messages."""
    with contextlib.suppress(Exception):
        if hasattr(desc, "name"):
            n = desc.name
            if isinstance(n, str) and n:
                return n
        if isinstance(desc, Mapping):
            n = desc.get("name")  # type: ignore[index]
            if isinstance(n, str) and n:
                return n
    return "<service>"


def _map_json_type(
    jtype: str | None,
    items: Mapping[str, Any] | None = None,
) -> Any:
    """Map minimal JSON Schema types to Python typing for pydantic."""
    if not isinstance(jtype, str):
        return dict[str, Any]
    t = jtype.lower()
    if t == "string":
        return str
    if t == "integer":
        return int
    if t == "number":
        return float
    if t == "boolean":
        return bool
    if t == "array":
        item_type: Any = Any
        if isinstance(items, Mapping):
            it = items.get("type")
            if isinstance(it, str):
                inner_items = (
                    items.get("items") if isinstance(items.get("items"), Mapping) else None
                )
                item_type = _map_json_type(it, inner_items)
        return list[item_type]  # PEP 585
    return dict[str, Any]


def _is_required(required: list[str] | None, key: str) -> bool:
    return isinstance(required, list) and key in required


def _coerce_nonneg_int(raw: Any) -> int | None:
    """Best-effort coerce to non-negative int; None on failure."""
    val: int | None = None
    try:
        if isinstance(raw, int | float | str) and (
            isinstance(raw, float) and raw.is_integer() or not isinstance(raw, float)
        ):
            val = int(raw)
    except Exception:
        val = None
    return val if isinstance(val, int) and val >= 0 else None


def _array_type_from_prop(prop: Mapping[str, Any]) -> Any:
    items = prop.get("items") if isinstance(prop.get("items"), Mapping) else None
    return _map_json_type("array", items)


def _string_field_def(
    key: str, prop: Mapping[str, Any], required: list[str] | None
) -> tuple[Any, Any]:
    min_len = _coerce_nonneg_int(prop.get("minLength"))
    if min_len is not None:
        if _is_required(required, key):
            return (str, PydField(..., min_length=min_len))
        return (str | None, PydField(None, min_length=min_len))
    # Fallback: no constraint
    return (str, ...) if _is_required(required, key) else (str | None, None)


def _array_field_def(
    key: str, prop: Mapping[str, Any], required: list[str] | None
) -> tuple[Any, Any]:
    array_type = _array_type_from_prop(prop)
    min_items = _coerce_nonneg_int(prop.get("minItems"))
    if min_items is not None:
        if _is_required(required, key):
            return (array_type, PydField(..., min_length=min_items))
        return (array_type | None, PydField(None, min_length=min_items))
    # Fallback: no constraint
    if _is_required(required, key):
        return (array_type, ...)
    return (array_type | None, None)


def _generic_field_def(ptype: Any, required: list[str] | None, key: str) -> tuple[Any, Any]:
    py_type = _map_json_type(ptype if isinstance(ptype, str) else None)
    if _is_required(required, key):
        return (py_type, ...)
    return (py_type | None, None)


def _build_field_def(key: str, prop: Any, required: list[str] | None) -> tuple[Any, Any]:
    if isinstance(prop, Mapping):
        typed_prop = cast("Mapping[str, Any]", prop)
        ptype = typed_prop.get("type")
        if ptype == "array":
            return _array_field_def(key, typed_prop, required)
        if ptype == "string":
            return _string_field_def(key, typed_prop, required)
        return _generic_field_def(ptype, required, key)
    # Non-mapping property -> Any
    return (Any, ...) if _is_required(required, key) else (Any | None, None)


def _build_model_from_schema(
    schema: Mapping[str, Any],
    model_name: str,
) -> type[BaseModel]:
    """
    Construct a dynamic pydantic model from a minimal object schema.
    - Unknown/additional properties are allowed.
    - Optional fields are Optional[T] with default None.
    - Required keys missing in 'properties' become required Any.
    """
    stype = schema.get("type") or "object"

    if stype != "object":
        # Non-object roots are out of scope; wrap as single-field 'value'
        py_type = _map_json_type(
            stype,
            schema.get("items") if isinstance(schema.get("items"), Mapping) else None,
        )
        cm = cast("Any", create_model)
        return cm(
            model_name,
            __base__=_DynamicBaseModel,
            value=(py_type, ...),
        )

    props_raw = schema.get("properties")
    if isinstance(props_raw, Mapping):
        props: Mapping[str, Any] | None = cast("Mapping[str, Any]", props_raw)
    else:
        props = None
    req_raw = schema.get("required")
    required_list: list[str] = cast("list[str]", req_raw) if isinstance(req_raw, list) else []

    field_defs: dict[str, tuple[Any, Any]] = {}

    if props is not None:
        for key, prop in props.items():
            field_defs[key] = _build_field_def(key, prop, required_list)

    # Any required fields not described in properties -> required Any
    for key in required_list:
        if key not in field_defs:
            field_defs[key] = (Any, ...)

    fields_kw: dict[str, Any] = cast("dict[str, Any]", field_defs)
    cm = cast("Any", create_model)
    return cm(
        model_name,
        __base__=_DynamicBaseModel,
        **fields_kw,
    )


def validate_input(
    desc: ServiceDescriptor | Mapping[str, Any] | Any,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Validate input payload using descriptor's input_schema.
    - If no schema: return a shallow copy of payload unchanged.
    - On success: return validated dict (exclude None).
    - On failure: raise core_router.errors.ValidationError with details.
    """
    schema = _get_schema(desc, "input")
    if schema is None:
        return dict(payload)

    name = _to_service_name(desc)
    model_name = f"{name.replace(' ', '_').replace('-', '_')}_Input"
    try:
        Model = _build_model_from_schema(schema, model_name)
        inst = Model.model_validate(dict(payload))
        return inst.model_dump(by_alias=False, exclude_none=True)
    except PydanticValidationError as e:
        raise ValidationError(
            f"input validation failed for '{name}'",
            details=cast("Any", e.errors()),
        ) from e
    except Exception as e:
        raise ValidationError(
            f"input validation failed for '{name}'",
            details=str(e),
        ) from e


def validate_output(
    desc: ServiceDescriptor | Mapping[str, Any] | Any,
    payload: dict[str, Any] | Any,
) -> dict[str, Any] | Any:
    """
    Validate output payload using descriptor's output_schema.
    - If no schema: return payload unchanged.
    - Accept Mapping or objects convertible to dict via model_dump()/dict().
    - On success: return validated dict (exclude None).
    - On failure: raise core_router.errors.ValidationError with details.
    """
    schema = _get_schema(desc, "output")
    if schema is None:
        return payload

    name = _to_service_name(desc)
    model_name = f"{name.replace(' ', '_').replace('-', '_')}_Output"

    # Best-effort normalization for non-dict payloads
    candidate: Any
    if isinstance(payload, Mapping):
        candidate = dict(cast("Mapping[str, Any]", payload))
    elif hasattr(payload, "model_dump"):
        method = getattr(payload, "model_dump", None)
        candidate = method() if callable(method) else payload
    elif hasattr(payload, "dict") and callable(payload.dict):
        candidate = payload.dict()
    else:
        # Let pydantic attempt attribute-based validation; may error.
        candidate = payload

    try:
        Model = _build_model_from_schema(schema, model_name)
        inst = Model.model_validate(candidate)
        return inst.model_dump(by_alias=False, exclude_none=True)
    except PydanticValidationError as e:
        raise ValidationError(
            f"output validation failed for '{name}'",
            details=cast("Any", e.errors()),
        ) from e
    except Exception as e:
        raise ValidationError(
            f"output validation failed for '{name}'",
            details=str(e),
        ) from e
