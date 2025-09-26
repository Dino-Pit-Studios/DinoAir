"""
LM Studio HTTP adapter (OpenAI-compatible /v1/chat/completions).

Configuration resolution (first match wins):
- Environment:
  - LMSTUDIO_BASE_URL (default: http://127.0.0.1:1234)
  - LMSTUDIO_API_KEY  (optional; sends Authorization: Bearer <key>)
  - LMSTUDIO_DEFAULT_MODEL (fallback if adapter_config.model missing)
  - LMSTUDIO_REQUEST_TIMEOUT_S (int seconds, default: 15)
- YAML adapter_config (e.g. config/services.lmstudio.yaml)
- Safe defaults: base_url=http://127.0.0.1:1234, timeout=15s

HTTP client:
- httpx.Client with connect/read/write timeouts
- Bounded retries (default 3) on network errors and 5xx (except 501)
- Exponential backoff with jitter between attempts
- Authorization header added when API key provided via env or adapter_config.headers

I/O expectations:
- invoke(service_desc, payload) posts to {base}/v1/chat/completions with:
  { "model": <model>, "messages": payload["messages"], "options": payload.get("options") }
- Returns upstream JSON (OpenAI-style) mapping.
- Raises AdapterError with adapter="lmstudio" and reason on failure.

This adapter is synchronous and does not mutate the provided payload.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Mapping
from contextlib import suppress
from typing import Any, cast

import httpx

from ..errors import AdapterError, RetryableError
from .base import ServiceAdapter

__all__ = ["LMStudioAdapter"]


def _normalize_base_url(base_url: str) -> str:
    """Remove a trailing '/v1' and trailing slashes to avoid double '/v1'."""
    s = str(base_url or "").strip().rstrip("/")
    return s.removesuffix("/v1")


class LMStudioAdapter(ServiceAdapter):
    """
    Production-ready adapter for LM Studio's OpenAI-compatible HTTP API.
    - Synchronous invoke with retries/backoff/timeouts and optional auth.
    """

    def __init__(self, adapter_config: Mapping[str, Any]) -> None:
        cfg = dict(adapter_config or {})

        # Resolve configuration with environment fallbacks
        raw = str(
            cfg.get("base_url") or os.getenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234")
        ).strip()
        model = str(cfg.get("model") or os.getenv("LMSTUDIO_DEFAULT_MODEL", "")).strip()
        headers = cfg.get("headers", {})
        # Timeouts (seconds)
        timeout_s = cfg.get("timeout_s", os.getenv("LMSTUDIO_REQUEST_TIMEOUT_S", 15))
        connect_timeout_s = cfg.get("connect_timeout_s")
        read_timeout_s = cfg.get("read_timeout_s")
        write_timeout_s = cfg.get("write_timeout_s")
        # Retries
        retries = cfg.get("retries", 3)

        if not raw:
            raise AdapterError(
                adapter="lmstudio",
                reason="adapter_config['base_url'] or LMSTUDIO_BASE_URL must be set",
            )
        if not model:
            raise AdapterError(
                adapter="lmstudio",
                reason="adapter_config['model'] or LMSTUDIO_DEFAULT_MODEL must be a non-empty string",
            )

        # Normalize
        self._base_raw: str = raw
        self._base: str = _normalize_base_url(self._base_raw)
        self._model: str = model.strip()

        # Headers + env auth
        self._headers: dict[str, str] = {}
        if isinstance(headers, Mapping):
            self._headers.update(
                {str(k): str(v) for k, v in cast("Mapping[str, Any]", headers).items()}
            )
        api_key = os.getenv("LMSTUDIO_API_KEY")
        if api_key and "Authorization" not in self._headers:
            self._headers["Authorization"] = f"Bearer {api_key}"

        # Timeouts
        def _safe_float(val: Any, default_: float) -> float:
            try:
                f = float(val)
                return f if f > 0 else default_
            except Exception:
                return default_

        base_timeout = _safe_float(timeout_s, 15.0)
        self._timeout = httpx.Timeout(
            connect=_safe_float(connect_timeout_s, base_timeout),
            read=_safe_float(read_timeout_s, base_timeout),
            write=_safe_float(write_timeout_s, base_timeout),
            pool=_safe_float(base_timeout, base_timeout),
        )

        # Retry policy
        try:
            self._retries: int = int(retries)
        except Exception:
            self._retries = 3
        self._retries = max(0, min(self._retries, 5))  # safety bounds
        self._backoff_base: float = 0.25  # seconds
        self._backoff_cap: float = 2.0

    def ping(self) -> bool:
        """
        Lightweight liveness probe of base_url with ~1s timeout.

        Returns True if HTTP status is 2xx. False otherwise or on error.
        """
        for method in (httpx.head, httpx.get):
            with suppress(Exception):
                resp = method(self._base_raw, timeout=1.0)
                if 200 <= resp.status_code < 300:
                    return True
        return False

    @staticmethod
    def _should_retry_status(status_code: int) -> bool:
        # Retry 5xx except 501
        return 500 <= status_code < 600 and status_code != 501

    def _sleep_backoff(self, attempt: int) -> None:
        # Exponential backoff with jitter: base * 2^(attempt-1) + random[0, base/2], capped.
        delay = min(self._backoff_cap, self._backoff_base * (2 ** max(0, attempt - 1)))
        delay += random.uniform(0, self._backoff_base / 2)
        with suppress(Exception):
            time.sleep(delay)

    @staticmethod
    def _validate_messages(items: Any) -> list[dict[str, str]]:
        """
        Validate and normalize OpenAI-style messages:
        - Must be a non-empty list
        - Each item must be a Mapping with string role and non-empty string content
        - Role is normalized to a stripped string (allow common OpenAI roles)
        """
        if not isinstance(items, list) or not items:
            raise AdapterError(
                adapter="lmstudio",
                reason="payload missing 'messages' (non-empty list required)",
            )
        seq: list[Any] = cast("list[Any]", items)

        out: list[dict[str, str]] = []
        for i, raw in enumerate(seq):
            if not isinstance(raw, Mapping):
                raise AdapterError(adapter="lmstudio", reason=f"messages[{i}] must be object")
            msg = cast("Mapping[str, Any]", raw)

            role_val = msg.get("role")
            content_val = msg.get("content")

            if (
                not isinstance(role_val, str)
                or not isinstance(content_val, str)
                or not content_val.strip()
            ):
                raise AdapterError(
                    adapter="lmstudio",
                    reason=f"messages[{i}] requires string 'role' and non-empty string 'content'",
                )

            r = role_val.strip()
            # Permit arbitrary roles but prefer common set; do not reject unknown roles
            out.append({"role": r, "content": content_val})
        return out

    def invoke(self, service_desc: Any, payload: dict[str, Any]) -> dict[str, Any]:
        """
        POST /v1/chat/completions with configured retries and timeouts.

        Accepts:
          - invoke(service_desc, payload)

        Returns:
          - Mapping parsed from upstream JSON

        Raises:
          - AdapterError on failure (after bounded retries)
        """
        body = self._prepare_request_body(payload)
        url = f"{self._base}/v1/chat/completions"
        headers = {"Content-Type": "application/json"} | self._headers

        return self._make_request_with_retries(url, body, headers)

    def _prepare_request_body(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Prepare the request body from payload.

        Args:
            payload: Input payload

        Returns:
            Prepared request body
        """
        body: dict[str, Any] = {"model": self._model}

        # Required messages validation
        body["messages"] = self._validate_messages(payload.get("messages"))

        # Optional pass-through generation controls
        if "options" in payload:
            with suppress(Exception):
                body["options"] = dict(cast("Mapping[str, Any]", payload["options"]))

        return body

    def _make_request_with_retries(
        self, url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        """Make HTTP request with retry logic.

        Args:
            url: Request URL
            body: Request body
            headers: Request headers

        Returns:
            Response data

        Raises:
            AdapterError: On request failure after retries
        """
        last_exc: Exception | None = None
        attempts = max(1, 1 + self._retries)

        for attempt in range(1, attempts + 1):
            try:
                return self._attempt_request(url, body, headers, attempt, attempts)
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt < attempts:
                    self._sleep_backoff(attempt)
                    continue
                self._raise_network_error(exc)
            except RetryableError:
                # Explicit retry signal - continue without storing as last_exc
                if attempt < attempts:
                    continue
                # If we've exhausted retries on a RetryableError, raise as AdapterError
                raise AdapterError(adapter="lmstudio", reason="max retries exceeded")
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < attempts:
                    self._sleep_backoff(attempt)
                    continue
                raise AdapterError(adapter="lmstudio", reason=str(exc)) from exc

        # Fallback (should not reach)
        self._raise_fallback_error(last_exc)
        return None

    def _attempt_request(
        self, url: str, body: dict[str, Any], headers: dict[str, str], attempt: int, attempts: int
    ) -> dict[str, Any]:
        """Attempt a single request.

        Args:
            url: Request URL
            body: Request body
            headers: Request headers
            attempt: Current attempt number
            attempts: Total attempts

        Returns:
            Response data

        Raises:
            AdapterError: On non-retryable errors
        """
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, json=body, headers=headers)

        if 200 <= resp.status_code < 300:
            return self._parse_successful_response(resp)

        return self._handle_error_response(resp, attempt, attempts)

    @staticmethod
    def _parse_successful_response(resp: httpx.Response) -> dict[str, Any]:
        """Parse successful response.

        Args:
            resp: HTTP response

        Returns:
            Parsed response data

        Raises:
            AdapterError: On parsing errors
        """
        try:
            raw = resp.json()
        except (ValueError, httpx.DecodingError) as exc:
            raise AdapterError(adapter="lmstudio", reason="invalid JSON response") from exc

        if not isinstance(raw, Mapping):
            raise AdapterError(
                adapter="lmstudio",
                reason=f"JSON root must be object, got {type(raw).__name__}",
            )

        return {str(k): v for k, v in cast("Mapping[str, Any]", raw).items()}

    def _handle_error_response(
        self, resp: httpx.Response, attempt: int, attempts: int
    ) -> dict[str, Any]:
        """Handle error response.

        Args:
            resp: HTTP response
            attempt: Current attempt number
            attempts: Total attempts

        Returns:
            Never returns, always raises

        Raises:
            AdapterError: Always
        """
        # Check if should retry
        if self._should_retry_status(resp.status_code) and attempt < attempts:
            self._sleep_backoff(attempt)
            # Will be caught and retried
            raise RetryableError("Retryable status code")

        # Non-retryable status -> raise
        text = ""
        with suppress(Exception):
            text = (resp.text or "")[:512]
        raise AdapterError(adapter="lmstudio", reason=f"HTTP {resp.status_code}: {text}")

    @staticmethod
    def _raise_network_error(exc: Exception) -> None:
        """Raise network-related AdapterError.

        Args:
            exc: Original exception

        Raises:
            AdapterError: Always
        """
        reason = "timeout" if isinstance(exc, httpx.TimeoutException) else "network error"
        raise AdapterError(adapter="lmstudio", reason=reason) from exc

    def _raise_fallback_error(self, last_exc: Exception | None) -> None:
        """Raise fallback error.

        Args:
            last_exc: Last exception that occurred

        Raises:
            AdapterError: Always
        """
        if last_exc:
            raise AdapterError(adapter="lmstudio", reason=str(last_exc)) from last_exc
        raise AdapterError(adapter="lmstudio", reason="unknown error")
