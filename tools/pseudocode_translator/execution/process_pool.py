from __future__ import annotations

import contextlib
import multiprocessing as mp
import os
import time
from concurrent.futures import Future, ProcessPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pseudocode_translator.config import ExecutionConfig, TranslatorConfig
from pseudocode_translator.integration.events import EventDispatcher, EventType
from pseudocode_translator.parser import ParserModule
from pseudocode_translator.telemetry import get_recorder
from pseudocode_translator.validator import ValidationResult, Validator

if TYPE_CHECKING:
    from collections.abc import Callable


try:
    from concurrent.futures.process import BrokenProcessPool  # type: ignore
except Exception:  # pragma: no cover
    # fallback for environments without symbol export
    class BrokenProcessPool(Exception):
        """Custom exception indicating the process pool is broken or unavailable."""


# Top-level worker functions for picklability


def worker_parse(text: str):
    """Parse text using ParserModule in a fresh process."""
    parser = ParserModule()
    return parser.get_parse_result(text)


def worker_validate(ast_obj) -> ValidationResult:
    """
    Validate syntax of provided code (ast_obj treated as code string).
    Creates a fresh Validator with default config to keep isolation.
    """
    code = ast_obj if isinstance(ast_obj, str) else str(ast_obj)
    cfg = TranslatorConfig()  # use defaults; validation semantics match in-process defaults
    validator = Validator(cfg)
    return validator.validate_syntax(code)


@dataclass
class _TaskSpec:
    """Specifies the type, function, and arguments for a processing task."""

    kind: str  # "parse" | "validate"
    func: Callable[..., Any]
    args: tuple


class _ImmediateFallback:
    """Small Future-like object to represent an immediate fallback instruction."""

    def __init__(self, reason: str):
        self.reason = reason

    def result(self, timeout: float | None = None):
        raise RuntimeError(f"exec_pool_fallback:{self.reason}")


class ParseValidateExecutor:
    """
    Optional process pool executor for CPU-heavy parse/validate.
    Lazy initialization; Windows prefers 'spawn'.
    """

    def __init__(
        self,
        config: ExecutionConfig,
        recorder=None,
        dispatcher: EventDispatcher | None = None,
        start_method: str | None = None,
        # test-only seams for determinism (must be top-level functions to be picklable)
        parse_fn: Callable[[str], Any] | None = None,
        validate_fn: Callable[[Any], Any] | None = None,
    ) -> None:
        self._config = config
        self._pool: ProcessPoolExecutor | None = None
        self._dispatcher = dispatcher
        self._rec = recorder if recorder is not None else get_recorder()
        self._start_method = start_method
        # picklable submission targets (top-level functions)
        self._parse_fn = parse_fn or worker_parse
        self._validate_fn = validate_fn or worker_validate

        # resolved runtime concurrency (lazy)
        self._resolved_workers: int | None = None
        self._resolved_start_method: str | None = None

    # ----- lifecycle -----

    def _resolve_workers(self) -> int:
        if self._config.process_pool_max_workers is None:
            cpu = os.cpu_count() or 2
            return max(2, cpu)
        return max(1, int(self._config.process_pool_max_workers))

    def _resolve_start_method(self) -> str | None:
        method = (
            self._start_method
            if self._start_method is not None
            else self._config.process_pool_start_method
        )
        if method:
            return method
        # Prefer spawn on Windows by default
        if os.name == "nt":
            return "spawn"
        return None  # platform default

    def _emit(self, et: EventType, **data) -> None:
        if self._dispatcher:
            with contextlib.suppress(Exception):
                self._dispatcher.dispatch_event(et, source=self.__class__.__name__, **data)

    def _ensure_pool(self) -> None:
        if self._pool is not None:
            return

        t0 = time.perf_counter()
        max_workers = self._resolve_workers()
        start_method = self._resolve_start_method()
        self._resolved_workers = max_workers
        self._resolved_start_method = start_method

        if start_method:
            ctx = mp.get_context(start_method)
            self._pool = ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx)
        else:
            self._pool = ProcessPoolExecutor(max_workers=max_workers)

        # telemetry and events
        init_ms = (time.perf_counter() - t0) * 1000.0
        self._rec.record_event(
            "exec_pool.started",
            duration_ms=None,
            extra=None,
            counters={"exec_pool.started": 1},
        )
        self._rec.record_event("exec_pool.init_ms", duration_ms=init_ms)
        self._emit(
            EventType.EXEC_POOL_STARTED,
            max_workers=max_workers,
            start_method=start_method,
        )

    def _restart_pool(self) -> None:
        try:
            if self._pool:
                self._pool.shutdown(cancel_futures=True)
        except Exception:
            pass
        self._pool = None
        self._ensure_pool()

    def shutdown(self, wait: bool = True) -> None:
        if self._pool:
            with contextlib.suppress(Exception):
                self._pool.shutdown(wait=wait, cancel_futures=True)
            self._pool = None

    # ----- submission -----

    def submit_parse(self, text: str):
        # job size guardrail
        cap = int(self._config.process_pool_job_max_chars)
        if cap > 0 and len(text) > cap:
            self._emit(EventType.EXEC_POOL_FALLBACK, kind="parse", reason="job_too_large")
            self._rec.record_event("exec_pool.fallback", counters={"exec_pool.fallback": 1})
            return _ImmediateFallback("job_too_large")

        # respect target
        if self._config.process_pool_target not in {"parse_validate", "parse_only"}:
            return _ImmediateFallback("target_disabled")

        self._ensure_pool()
        # submit
        self._emit(EventType.EXEC_POOL_TASK_SUBMITTED, kind="parse", size_chars=len(text))
        self._rec.record_event("exec_pool.submit", counters={"exec_pool.submit": 1})
        spec = _TaskSpec(kind="parse", func=self._parse_fn, args=(text,))
        # type: ignore[arg-type]
        fut = self._pool.submit(spec.func, *spec.args)
        return self._TaskHandle(self, spec, fut)

    def submit_validate(self, ast_obj):
        # respect target
        if self._config.process_pool_target not in {"parse_validate", "validate_only"}:
            return _ImmediateFallback("target_disabled")

        self._ensure_pool()
        self._emit(
            EventType.EXEC_POOL_TASK_SUBMITTED,
            kind="validate",
            size_chars=(len(ast_obj) if isinstance(ast_obj, str) else 0),
        )
        self._rec.record_event("exec_pool.submit", counters={"exec_pool.submit": 1})
        spec = _TaskSpec(kind="validate", func=self._validate_fn, args=(ast_obj,))
        # type: ignore[arg-type]
        fut = self._pool.submit(spec.func, *spec.args)
        return self._TaskHandle(self, spec, fut)

    # ----- internal Future-like wrapper with retry/timeout -----

    class _TaskHandle:
        """Internal Future-like wrapper for managing process pool tasks with retry, timeout, and metrics."""

        def __init__(self, parent: ParseValidateExecutor, spec: _TaskSpec, fut: Future):
            self._p = parent
            self._spec = spec
            self._fut = fut
            self._attempt = 0
            self._t0 = time.perf_counter()

        def _timeout_seconds(self) -> float:
            ms = max(1, int(self._p.config.process_pool_task_timeout_ms))
            return ms / 1000.0

        def result(self, timeout: float | None = None):
            timeout_sec = timeout if timeout is not None else self._timeout_seconds()
            while True:
                try:
                    res = self._fut.result(timeout=timeout_sec)
                    dur_ms = (time.perf_counter() - self._t0) * 1000.0
                    self._p.emit(
                        EventType.EXEC_POOL_TASK_COMPLETED,
                        kind=self._spec.kind,
                        duration_ms=dur_ms,
                    )
                    self._p.record_event("exec_pool.complete", counters={"exec_pool.complete": 1})
                    self._p.record_event("exec_pool.task_ms", duration_ms=dur_ms)
                    return res
                except (TimeoutError, BrokenProcessPool) as e:
                    # telemetry
                    self._p.emit(
                        EventType.EXEC_POOL_TIMEOUT,
                        kind=self._spec.kind,
                        timeout_ms=int(timeout_sec * 1000.0),
                        attempt=self._attempt,
                    )
                    self._p.record_event("exec_pool.timeout", counters={"exec_pool.timeout": 1})
                    # retry semantics
                    do_retry = bool(self._p.config.process_pool_retry_on_timeout)
                    limit = int(self._p.config.process_pool_retry_limit)
                    if do_retry and self._attempt < limit:
                        self._attempt += 1
                        # restart pool and resubmit
                        try:
                            self._p.restart_pool()
                            self._fut = self._p.pool.submit(self._spec.func, *self._spec.args)  # type: ignore
                            self._t0 = time.perf_counter()
                            continue
                        except Exception:
                            # if resubmission fails, break to fallback
                            pass
                    # give up -> fallback
                    self._p.emit(
                        EventType.EXEC_POOL_FALLBACK,
                        kind=self._spec.kind,
                        reason=("timeout" if isinstance(e, TimeoutError) else "broken_pool"),
                    )
                    self._p.record_event("exec_pool.fallback", counters={"exec_pool.fallback": 1})
                    raise
                except Exception:
                    # unexpected failure: treat as broken pool and fallback
                    self._p.emit(
                        EventType.EXEC_POOL_FALLBACK,
                        kind=self._spec.kind,
                        reason="broken_pool",
                    )
                    self._p.record_event("exec_pool.fallback", counters={"exec_pool.fallback": 1})
                    raise
