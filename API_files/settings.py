"""DinoAir API settings.

LM Studio env-backed settings:

- LMSTUDIO_BASE_URL: LM Studio HTTP base URL
  default: "http://127.0.0.1:1234"
- LMSTUDIO_API_KEY: optional; when set, adds
  'Authorization: Bearer <key>' header
- LMSTUDIO_DEFAULT_MODEL: default model name
  default: "llama-3.1-8b-instruct"
- LMSTUDIO_REQUEST_TIMEOUT_S: timeout seconds (int)
  default: 30

Expose get_lmstudio_env() returning a frozen dataclass with these fields.
Stdlib-only implementation.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE from a .env-style file into os.environ if not already set."""
    with contextlib.suppress(Exception):
        if not path.exists():
            return
        with path.open(encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value


def _load_envs_for_runtime() -> None:
    """
    Load .env (base) and .env.development (when in dev) so Settings sees overrides.
    Only sets variables not already present in the environment.
    """
    try:
        root = Path(__file__).resolve().parents[1]
    except Exception:
        return
    # Base env
    _load_env_file(root / ".env")
    # Dev overrides (default env is dev)
    env = (os.environ.get("DINOAIR_ENV", "dev") or "dev").strip().lower()
    if env in {"dev", "development"}:
        _load_env_file(root / ".env.development")


# One-time load at import
_load_envs_for_runtime()


def _get_env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def _parse_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(val: str | None, default: int) -> int:
    try:
        return int(str(val)) if val is not None else default
    except Exception:
        return default


def _parse_csv(val: str | None) -> list[str]:
    if not val:
        return []
    items = [s.strip() for s in str(val).split(",")]
    return [s for s in items if s]


@dataclass(frozen=True)
class LMStudioEnv:
    """Frozen LM Studio env snapshot."""

    base_url: str
    api_key: str | None
    default_model: str
    request_timeout_s: int


def get_lmstudio_env() -> LMStudioEnv:
    """
    Load LM Studio runtime settings from environment with safe defaults.

    Returns:
        LMStudioEnv: snapshot with base_url, api_key, default_model, and
        request_timeout_s.
    """
    base_url = os.getenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234") or "http://127.0.0.1:1234"
    api_key = os.getenv("LMSTUDIO_API_KEY") or None
    default_model = (
        os.getenv("LMSTUDIO_DEFAULT_MODEL", "llama-3.1-8b-instruct") or "llama-3.1-8b-instruct"
    )
    timeout_s = _parse_int(os.getenv("LMSTUDIO_REQUEST_TIMEOUT_S"), 30)
    return LMStudioEnv(
        base_url=base_url,
        api_key=api_key,
        default_model=default_model,
        request_timeout_s=int(timeout_s),
    )


class Settings:
    """
    Runtime configuration loaded from environment variables with prefix
    DINOAIR_.

        Variables:
        - DINOAIR_ENV: "dev" or "prod" (default: dev)
        - DINOAIR_API_PORT: int (default: 24801)
        - DINOAIR_ALLOWED_ORIGINS: CSV list
            dev default if empty: [http://localhost:5173, tauri://localhost]
            prod default if empty: [tauri://localhost]
            - DINOAIR_AUTH_TOKEN: authentication token; if present,
                auth is required
        - DINOAIR_ALLOW_NO_AUTH: when true and no token set AND env=dev,
            auth can be disabled (default: false)
        - DINOAIR_LOG_LEVEL: INFO|DEBUG|WARNING|ERROR (default: INFO)
        - DINOAIR_LOG_DIR: logs directory path (default: logs)
        - DINOAIR_REQUEST_TIMEOUT_SECONDS: int seconds (default: 30)
        - DINOAIR_MAX_REQUEST_BODY_BYTES: int bytes
            (default: 10_485_760 = 10 MiB)
        - DINOAIR_EXPOSE_OPENAPI_IN_DEV: bool (default: true)
    """

    def __init__(self) -> None:
        # Environment
        self.environment: str = (_get_env("DINOAIR_ENV", "dev") or "dev").strip().lower()
        self.is_dev: bool = self.environment in {"dev", "development"}

        # Network
        self.port: int = _parse_int(_get_env("DINOAIR_API_PORT"), 24801)

        if allowed_origins_env := _get_env("DINOAIR_ALLOWED_ORIGINS"):
            self.allowed_origins: list[str] = _parse_csv(allowed_origins_env)
        else:
            self.allowed_origins = (
                [
                    "http://localhost:5175",
                    "http://localhost:5173",  # Vite default dev port
                    "tauri://localhost",
                ]
                if self.is_dev
                else [
                    "tauri://localhost",
                ]
            )

        # Auth
        self.auth_token: str | None = _get_env("DINOAIR_AUTH_TOKEN") or None
        self.allow_no_auth: bool = _parse_bool(_get_env("DINOAIR_ALLOW_NO_AUTH"), False)
        if self.auth_token:
            self.auth_required: bool = True
        else:
            self.auth_required = not (self.is_dev and self.allow_no_auth)

        # Logging
        self.log_level: str = (_get_env("DINOAIR_LOG_LEVEL", "INFO") or "INFO").upper()
        self.log_dir: str = _get_env("DINOAIR_LOG_DIR", "logs") or "logs"

        # Timeouts and limits
        self.request_timeout_seconds: int = _parse_int(
            _get_env("DINOAIR_REQUEST_TIMEOUT_SECONDS"), 30
        )
        self.max_request_body_bytes: int = _parse_int(
            _get_env("DINOAIR_MAX_REQUEST_BODY_BYTES"), 10_485_760
        )

        # Docs in dev
        self.expose_openapi_in_dev: bool = _parse_bool(
            _get_env("DINOAIR_EXPOSE_OPENAPI_IN_DEV"), True
        )
        # RAG feature toggles and runtime options
        self.rag_enabled: bool = _parse_bool(_get_env("DINOAIR_RAG_ENABLED"), True)
        self.rag_use_optimized_engine: bool = _parse_bool(
            _get_env("DINOAIR_RAG_USE_OPTIMIZED_ENGINE"), True
        )
        self.rag_cache_size: int = _parse_int(_get_env("DINOAIR_RAG_CACHE_SIZE"), 100)
        self.rag_cache_ttl_seconds: int = _parse_int(
            _get_env("DINOAIR_RAG_CACHE_TTL_SECONDS"), 3600
        )
        self.rag_embed_model: str = (
            _get_env("DINOAIR_RAG_EMBED_MODEL", "all-MiniLM-L6-v2") or "all-MiniLM-L6-v2"
        )
        self.rag_embed_max_length: int = _parse_int(_get_env("DINOAIR_RAG_EMBED_MAX_LENGTH"), 256)
        self.rag_embed_device: str = _get_env("DINOAIR_RAG_EMBED_DEVICE", "auto") or "auto"
        self.rag_chunk_size: int = _parse_int(_get_env("DINOAIR_RAG_CHUNK_SIZE"), 1000)
        self.rag_chunk_overlap: int = _parse_int(_get_env("DINOAIR_RAG_CHUNK_OVERLAP"), 200)
        self.rag_min_chunk_size: int = _parse_int(_get_env("DINOAIR_RAG_MIN_CHUNK_SIZE"), 100)
        self.rag_allowed_dirs: list[str] = _parse_csv(_get_env("DINOAIR_RAG_ALLOWED_DIRS"))
        self.rag_excluded_dirs: list[str] = _parse_csv(_get_env("DINOAIR_RAG_EXCLUDED_DIRS"))
        self.rag_file_extensions: list[str] = _parse_csv(_get_env("DINOAIR_RAG_FILE_EXTENSIONS"))
        self.rag_watchdog_enabled: bool = _parse_bool(
            _get_env("DINOAIR_RAG_WATCHDOG_ENABLED"), False
        )
        self.rag_watchdog_max_workers: int = _parse_int(
            _get_env("DINOAIR_RAG_WATCHDOG_MAX_WORKERS"), 2
        )

        # Optional override for services config path (used by ServiceRouter)
        # Env var: DINOAIR_SERVICES_FILE
        self.services_config_path: str | None = _get_env("DINOAIR_SERVICES_FILE") or None
