"""
OffloadExecutor facade centralizes offload policy and emissions for parse/validate.

Behavior/parity notes:
- Mirrors translator.py gating semantics (enabled + target includes kind).
- Submits to the existing ParseValidateExecutor via the provided ensure_pool_cb.
- Handles timeouts, BrokenProcessPool, and "exec_pool_fallback:" immediate fallback token.
- Emits EXEC_POOL_FALLBACK for the immediate-fallback RuntimeError case using the same payload
  keys and source string ("TranslationManager") as translator.py previously did.
- Does NOT raise; returns (ok, result) where:
    - ok == False  => caller should run in-process path (offload disabled/untargeted)
    - ok == True and result startswith("exec_pool_fallback:") => caller must run local fallback
    - ok == True and result otherwise => offload result to be returned as-is
- Event names/payloads must mirror translator.py; the event order remains consistent because
  emissions occur at the same logical points as before.

Import graph:
- No imports from translator.py (acyclic). Use literal source string "TranslationManager".
"""

import contextlib
from concurrent import futures
from typing import Any

# Events import (does not create cycle with translator.py)
from ..integration.events import EventType  # noqa: E402

# Best-effort BrokenProcessPool import; fall back to a local sentinel Exception subclass
try:  # pragma: no cover - platform/env specific
    from concurrent.futures.process import BrokenProcessPool as _CFBroken  # type: ignore
except Exception:  # pragma: no cover
    _CFBroken = None  # type: ignore

try:  # pragma: no cover
    from multiprocessing.pool import BrokenProcessPool as _MPBroken  # type: ignore
except Exception:  # pragma: no cover
    _MPBroken = None  # type: ignore


class _BrokenPoolSentinel(Exception):
    """Local sentinel to allow except blocks to match consistently when symbol is missing."""


# type: ignore[misc]
BrokenProcessPool = _CFBroken or _MPBroken or _BrokenPoolSentinel


class OffloadExecutor:
    """
    Facade coordinating offload checks, submission, fallbacks, and event emissions.

    Args:
        dispatcher: Event dispatcher used by translator
        recorder: Telemetry recorder (not used for new labels here; kept for parity)
        exec_cfg: Execution config used for gating (enabled/target)
        ensure_pool_cb: Callback returning a live ParseValidateExecutor instance

    Parity requirements:
    - Gating matches translator.py exactly.
    - Events: EXEC_POOL_FALLBACK emitted for immediate-fallback RuntimeError with identical
      keys (kind, reason) and source "TranslationManager", matching prior translator emission.
    - No new telemetry section names are introduced; process_pool handles existing counters.
    """

    def __init__(self, dispatcher: Any, recorder: Any, exec_cfg: Any, ensure_pool_cb: Any) -> None:
        self._dispatcher = dispatcher
        self._rec = recorder
        self._cfg = exec_cfg
        self._ensure_pool_cb = ensure_pool_cb

    def can_offload(self, kind: str) -> bool:
        """
        Return True if exec_cfg is enabled AND target includes kind ("parse" | "validate"),
        matching current gating semantics in translator.py.
        """
        cfg = self._cfg
        if not cfg or not getattr(cfg, "process_pool_enabled", False):
            return False
        target = getattr(cfg, "process_pool_target", "parse_validate")
        if kind == "parse":
            return target in {"parse_validate", "parse_only"}
        if kind == "validate":
            return target in {"parse_validate", "validate_only"}
        # Unknown kinds are not offloaded
        return False

    def submit(self, kind: str, payload: Any, timeout: float | None = None) -> tuple[bool, Any]:
        """
        Attempt to offload work of the given kind.

        Returns:
            (False, None) if offload is not permitted (caller must run local path).
            (True, result) on success from the pool (caller should return result).
            (True, "exec_pool_fallback:<reason>") instructs caller to run local fallback immediately.

        Never raises; converts exceptions to fallback sentinel to preserve translator behavior.
        """
        if not self.can_offload(kind):
            return False, None

        # Acquire executor and submit
        try:
            pool = self._ensure_pool_cb()
            if kind == "parse":
                fut = pool.submit_parse(payload)
            elif kind == "validate":
                fut = pool.submit_validate(payload)
            else:
                # Unknown kind: treat as not offloadable
                return False, None

            # Respect optional timeout parameter if provided; otherwise use pool's default
            res = fut.result(timeout=timeout) if timeout is not None else fut.result()
            return True, res

        except (futures.TimeoutError, BrokenProcessPool) as e:
            # Pool has already emitted TIMEOUT and FALLBACK; caller will run local fallback.
            reason = "timeout" if isinstance(e, futures.TimeoutError) else "broken_pool"
            return True, f"exec_pool_fallback:{reason}"

        except RuntimeError as e:
            msg = str(e)
            # Immediate fallback instruction surfaced by executor (_ImmediateFallback)
            if msg.startswith("exec_pool_fallback:"):
                reason = msg.split(":", 1)[1] if ":" in msg else "unknown"
                # Emit fallback event exactly as translator.py did previously
                with contextlib.suppress(Exception):
                    self._dispatcher.dispatch_event(
                        EventType.EXEC_POOL_FALLBACK,
                        source="TranslationManager",
                        kind=kind,
                        reason=reason,
                    )
                return True, msg
            # Any other RuntimeError: treat as broken pool fallback
            return True, "exec_pool_fallback:broken_pool"

        except Exception:
            # Unexpected failure: mirror pool wrapper's final fallback semantics
            return True, "exec_pool_fallback:broken_pool"
