"""AI routes for chat endpoints.

Exposes POST /AI/chat and helper utilities to build payloads and parse
responses from the core router services.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any, cast

from fastapi import APIRouter, HTTPException
from starlette import status

from core_router.errors import (
    AdapterError,
    NoHealthyService,
    ServiceNotFound,
)
from core_router.errors import ValidationError as CoreValidationError

from ..schemas import ChatRequest, ChatResponse
from ..services import router_client
from ..services.tool_schema_generator import get_tool_registry

logger = logging.getLogger(__name__)

# ErrorResponse model may not exist in local test stubs; provide a safe pydantic fallback
try:
    from core_router.errors import (
        ErrorResponse as ErrorResponseModel,  # type: ignore[import-not-found,unused-ignore]
    )
except ImportError:  # pragma: no cover
    from pydantic import BaseModel

    class ErrorResponseModel(BaseModel):  # type: ignore[misc,unused-ignore]
        """Minimal error response model for FastAPI responses when core_router is unavailable."""

        detail: str | None = None
        code: str | None = None
        message: str | None = None
        error: str | None = None


router = APIRouter()


def _get_tool_schemas_from_params(extra_params: Mapping | None) -> list[dict[str, Any]]:
    """Helper to retrieve tool schemas based on extra_params."""
    enable_tools = _extract_bool_param(extra_params, "enable_tools", False)
    if not enable_tools:
        return []
    try:
        registry = get_tool_registry()
        requested_tools = _extract_list_param(extra_params, "tools")
        tool_schemas = registry.get_tool_schemas(requested_tools)
        logger.info("Function calling enabled with %d tools", len(tool_schemas))
        return tool_schemas
    except Exception as e:
        logger.warning("Failed to load tools for function calling, continuing without tools: %s", e)
        return []


@router.post(
    "/ai/chat",
    tags=["ai"],
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ErrorResponseModel,
            "description": "Validation error",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponseModel,
            "description": "Unauthorized",
        },
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {
            "model": ErrorResponseModel,
            "description": "Request too large",
        },
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
            "model": ErrorResponseModel,
            "description": "Unsupported media type",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponseModel,
            "description": "Internal server error",
        },
        status.HTTP_502_BAD_GATEWAY: {
            "model": ErrorResponseModel,
            "description": "Bad gateway",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponseModel,
            "description": "Service unavailable",
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "model": ErrorResponseModel,
            "description": "Gateway timeout",
        },
    },
)
async def ai_chat(req: ChatRequest) -> ChatResponse:
    """
    POST /ai/chat
    - Router-first chat endpoint for GUI.
    - Accepts OpenAI-style 'messages' and routes via the ServiceRouter
      for uniform health, metrics, and policy-based selection.
    - Supports OpenAI function calling when enabled via extra_params.
    - Selection:
        * Uses extra_params.router_service (exact serviceName), or
        * extra_params.router_tag (+ optional extra_params.router_policy), or
        * defaults to tag 'chat'.
    - Generation knobs: extra_params may include temperature/top_p/max_tokens,
      which are mapped to LM Studio's 'options' payload.
    - Function calling: Set extra_params.enable_tools=true to enable function calling.
    """
    mapping_params = req.extra_params if isinstance(req.extra_params, Mapping) else None

    messages: list[dict[str, str]] = [
        {"role": m.role.value, "content": m.content} for m in req.messages
    ]

    options: dict[str, Any] = _extract_options(mapping_params)
    tool_schemas = _get_tool_schemas_from_params(mapping_params)
    payload: dict[str, Any] = _build_payload(messages, options, tool_schemas)

    svc_name, tag, policy = _parse_routing_params(mapping_params)

    r = router_client.get_router()
    result_obj: Any = _execute_router_call(r, svc_name, tag, policy, payload)

    result_dict: dict[str, Any] | None = (
        cast("dict[str, Any]", result_obj) if isinstance(result_obj, dict) else None
    )

    # Handle function calls if present
    function_call_results = []
    if (
        mapping_params
        and mapping_params.get("enable_tools")
        and result_dict
        and _has_function_calls(result_dict)
    ):
        function_call_results = await _handle_function_calls(result_dict)

        # If functions were called, we might want to continue the conversation
        if function_call_results and _should_continue_conversation(req.extra_params):
            # Add function results to messages and make another call
            updated_messages = messages + _build_function_call_messages(
                result_dict, function_call_results
            )
            updated_payload = _build_payload(updated_messages, options, tool_schemas)
            result_obj = _execute_router_call(r, svc_name, tag, policy, updated_payload)
            result_dict = (
                cast("dict[str, Any]", result_obj) if isinstance(result_obj, dict) else None
            )

    text: str = _extract_first_message_text(result_dict)
    model: str | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    if result_dict is not None:
        mv = result_dict.get("model")
        model = mv if isinstance(mv, str) else None
        finish_reason = _safe_first_finish_reason(result_dict)
        usage = _extract_usage(result_dict)

    # Include function call results in metadata if present
    metadata = {}
    if function_call_results:
        metadata["function_calls"] = function_call_results

    return ChatResponse(
        success=bool(text) or bool(function_call_results),
        content=text,
        finish_reason=finish_reason,
        model=model,
        usage=usage,
        metadata=metadata,
    )


def _extract_options(extra_params: Mapping[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(extra_params, Mapping):
        for k in (
            "temperature",
            "top_p",
            "max_tokens",
            "presence_penalty",
            "frequency_penalty",
        ):
            v = extra_params.get(k)
            if v is not None:
                out[k] = v
    return out


def _build_payload(
    messages: list[dict[str, str]],
    options: Mapping[str, Any] | None,
    tool_schemas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"messages": messages}
    if options:
        payload["options"] = dict(options)
    if tool_schemas:
        payload["tools"] = tool_schemas
    return payload


def _safe_str(obj: Any) -> str | None:
    try:
        s = str(obj)
        return s or None
    except Exception:
        return None


def _pick_first_str(m: Mapping[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = m.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def _normalize_tag(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item:
                return item
            if s := _safe_str(item):
                return s
    return None


def _parse_routing_params(
    extra_params: Mapping[str, Any] | None,
) -> tuple[str | None, str | None, str | None]:
    if not isinstance(extra_params, Mapping):
        return None, None, None

    svc_name = _pick_first_str(extra_params, "router_service", "serviceName")
    tag = _normalize_tag(extra_params.get("router_tag") or extra_params.get("router_tags"))
    policy = _pick_first_str(extra_params, "router_policy")

    return svc_name, tag, policy


def _execute_router_call(
    r: Any,
    svc_name: str | None,
    tag: str | None,
    policy: str | None,
    payload: Mapping[str, Any],
) -> Any:
    try:
        if isinstance(svc_name, str) and svc_name.strip():
            return r.execute(svc_name.strip(), payload)
        rt_tag = (tag or "chat").strip().lower()
        rt_policy = (policy or "first_healthy").strip().lower()
        return r.execute_by(rt_tag, payload, rt_policy)
    except (ServiceNotFound, NoHealthyService) as exc:
        # Try fallback to mock service if available
        try:
            logger.info("Primary service failed (%s), trying mock fallback...", exc)
            return r.execute_by("mock", payload, "first_healthy")
        except (ServiceNotFound, NoHealthyService):
            # If mock also fails, re-raise original exception
            if isinstance(exc, ServiceNotFound):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
    except CoreValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except AdapterError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


def _choice_content(choices: Any) -> str:
    """Return first non-empty content/text found in choices list."""
    if not isinstance(choices, list):
        return ""
    for raw in choices:
        if not isinstance(raw, Mapping):
            continue
        msg = raw.get("message")
        if isinstance(msg, Mapping):
            content = msg.get("content")
            if isinstance(content, str) and content:
                return content
        txt = raw.get("text")
        if isinstance(txt, str) and txt:
            return txt
    return ""


def _extract_first_message_text(data: Mapping[str, Any] | None) -> str:
    if not isinstance(data, Mapping):
        return ""
    try:
        if from_choices := _choice_content(data.get("choices")):
            return from_choices
        val = data.get("content")
        return val if isinstance(val, str) else ""
    except Exception:
        return ""


def _safe_first_finish_reason(data: Mapping[str, Any] | None) -> str | None:
    try:
        if not isinstance(data, Mapping):
            return None
        choices_val = data.get("choices")
        if isinstance(choices_val, list):
            items_any: list[Any] = cast("list[Any]", choices_val)
            for raw in items_any:
                if isinstance(raw, Mapping):
                    item: Mapping[str, Any] = cast("Mapping[str, Any]", raw)
                    fr = item.get("finish_reason")
                    if isinstance(fr, str):
                        return fr
        return None
    except Exception:
        return None


def _extract_usage(data: Mapping[str, Any] | None) -> dict[str, int] | None:
    try:
        if not isinstance(data, Mapping):
            return None
        u_val = data.get("usage")
        if not isinstance(u_val, Mapping):
            return None
        u_map: Mapping[str, Any] = cast("Mapping[str, Any]", u_val)
        out: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            v_any = u_map.get(key)
            if isinstance(v_any, int):
                out[key] = v_any
        return out or None
    except Exception:
        return None


def _extract_bool_param(
    extra_params: dict[str, Any] | None, key: str, default: bool = False
) -> bool:
    """
    Extract a boolean parameter from extra_params.

    Only accepts bool or str types for the value. If the value is not a bool or str,
    returns the default value. Strings are interpreted as True if they match
    ("true", "1", "yes", "on") (case-insensitive).
    """
    if not extra_params or key not in extra_params:
        return default
    value = extra_params[key]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    # For any other type, return the default value
    return default


def _extract_list_param(extra_params: dict[str, Any] | None, key: str) -> list[str] | None:
    """Extract a list parameter from extra_params."""
    if not extra_params or key not in extra_params:
        return None
    value = extra_params[key]
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        # Support comma-separated strings
        return [item.strip() for item in value.split(",") if item.strip()]
    return None


def _has_function_calls(result_dict: dict[str, Any]) -> bool:
    """Check if the result contains function calls."""
    try:
        choices = result_dict.get("choices", [])
        if not choices:
            return False

        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls")
        return bool(tool_calls)
    except (KeyError, IndexError, AttributeError):
        return False


async def _handle_function_calls(result_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Handle function calls from the AI response."""
    function_results = []

    try:
        choices = result_dict.get("choices", [])
        if not choices:
            return function_results

        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            return function_results

        # Import here to avoid circular dependencies
        registry = get_tool_registry()

        for tool_call in tool_calls:
            try:
                function_name = tool_call.get("function", {}).get("name")
                function_args = tool_call.get("function", {}).get("arguments", "{}")
                tool_call_id = tool_call.get("id")

                if not function_name or not tool_call_id:
                    continue

                # Parse arguments if they're a JSON string
                if isinstance(function_args, str):
                    try:
                        function_args = json.loads(function_args)
                    except json.JSONDecodeError as e:
                        raise ValueError(
                            f"Malformed JSON in function arguments for '{function_name}': {e}"
                        ) from e

                # Execute the function
                result = await registry.execute_tool(function_name, function_args)

                function_results.append(
                    {"tool_call_id": tool_call_id, "function_name": function_name, "result": result}
                )

            except Exception as e:
                logger.error(
                    "Error executing function %s: %s",
                    tool_call.get("function", {}).get("name", "unknown"),
                    e,
                )
                function_results.append(
                    {
                        "tool_call_id": tool_call.get("id"),
                        "function_name": tool_call.get("function", {}).get("name"),
                        "error": str(e),
                    }
                )

    except Exception as e:
        logger.error("Error processing function calls: %s", e)

    return function_results


def _should_continue_conversation(extra_params: dict[str, Any] | None) -> bool:
    """Check if we should continue the conversation after function calls."""
    return _extract_bool_param(extra_params, "auto_continue", True)


def _build_function_call_messages(
    result_dict: dict[str, Any], function_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build messages to add function call results back to the conversation."""
    messages = []

    try:
        if choices := result_dict.get("choices", []):
            if assistant_message := choices[0].get("message", {}):
                messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_message.get("content"),
                        "tool_calls": assistant_message.get("tool_calls"),
                    }
                )

        # Add function results as tool messages
        for func_result in function_results:
            tool_message = {
                "role": "tool",
                "tool_call_id": func_result["tool_call_id"],
                "name": func_result["function_name"],
            }

            if "error" in func_result:
                tool_message["content"] = f"Error: {func_result['error']}"
            else:
                # Convert result to JSON string if it's not already a string
                result = func_result["result"]
                if isinstance(result, str):
                    tool_message["content"] = result
                else:
                    try:
                        tool_message["content"] = json.dumps(result)
                    except (TypeError, ValueError) as e:
                        logger.warning(
                            "Failed to serialize result to JSON: %s. Using str(result) as fallback.",
                            e,
                        )
                        tool_message["content"] = str(result)

            messages.append(tool_message)

    except Exception as e:
        logger.error("Error building function call messages: %s", e)

    return messages


@router.get("/v1/models", tags=["ai"])
async def list_models():
    """
    GET /v1/models
    - Returns available models from LM Studio via direct proxy
    """
    import httpx

    try:
        # Direct proxy to LM Studio
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:1234/v1/models")
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LM Studio is not available"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to get models: {str(exc)}",
        ) from exc
