"""
Enhanced health checking system for DinoAir dependencies and services.
Provides comprehensive health monitoring with retry logic and detailed reporting.
"""

import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from types import TracebackType
from typing import Any, cast

import httpx

try:
    from error_handling import circuit_breaker, retry_on_failure
except ImportError:
    # Fallback if error_handling not available
    def retry_on_failure(_config: Any = None, _exceptions: Any = None):
        def decorator(func: Any) -> Any:
            return func

        return decorator

    def circuit_breaker(_config: Any = None, _name: str = ""):
        def decorator(func: Any) -> Any:
            return func

        return decorator


try:
    # type: ignore[import]  # pylint: disable=import-error
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover - optional dependency
    aioredis = None  # type: ignore[assignment]
try:
    import asyncpg  # type: ignore[import]  # pylint: disable=import-error
except ImportError:  # pragma: no cover - optional dependency
    asyncpg = None  # type: ignore[assignment]

# Note: Using dynamic casts to Any for optional third-party clients to avoid
# strict type requirements when dependencies are not installed in the environment.


class HealthStatus(str, Enum):
    """Health status enumeration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Individual health check result."""

    name: str
    status: HealthStatus
    response_time_ms: float
    message: str
    details: dict[str, Any] | None = None
    timestamp: float | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.details is None:
            self.details = {}


@dataclass
class HealthReport:
    """Comprehensive health report."""

    overall_status: HealthStatus
    checks: list[HealthCheck]
    total_checks: int
    healthy_checks: int
    degraded_checks: int
    unhealthy_checks: int
    timestamp: float

    @classmethod
    def from_checks(cls, checks: list[HealthCheck]) -> "HealthReport":
        """Create health report from individual checks."""
        healthy = sum(1 for c in checks if c.status == HealthStatus.HEALTHY)
        degraded = sum(1 for c in checks if c.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for c in checks if c.status == HealthStatus.UNHEALTHY)

        # Determine overall status
        if unhealthy > 0:
            overall = HealthStatus.UNHEALTHY
        elif degraded > 0:
            overall = HealthStatus.DEGRADED
        elif healthy > 0:
            overall = HealthStatus.HEALTHY
        else:
            overall = HealthStatus.UNKNOWN

        return cls(
            overall_status=overall,
            checks=checks,
            total_checks=len(checks),
            healthy_checks=healthy,
            degraded_checks=degraded,
            unhealthy_checks=unhealthy,
            timestamp=time.time(),
        )


class HealthChecker:
    """Comprehensive health checker for DinoAir services and dependencies."""

    def __init__(self, timeout: float = 10.0, retries: int = 3):
        self.timeout = timeout
        self.retries = retries
        self.logger = logging.getLogger(__name__)
        self._http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "HealthChecker":
        """Async context manager entry."""
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout), follow_redirects=True
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        if self._http_client:
            await self._http_client.aclose()

    @retry_on_failure()
    async def check_http_endpoint(
        self, name: str, url: str, expected_status: int = 200
    ) -> HealthCheck:
        """Check HTTP endpoint health."""
        start_time = time.perf_counter()

        try:
            if self._http_client is None:
                raise AssertionError("HTTP client is None")
            self.logger.debug("Attempting HTTP GET request to %s", url)
            response = await self._http_client.get(url)
            response_time_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code == expected_status:
                return HealthCheck(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    response_time_ms=response_time_ms,
                    message=f"HTTP {response.status_code}",
                    details={
                        "status_code": response.status_code,
                        "url": url,
                        "response_headers": dict(response.headers),
                    },
                )
            return HealthCheck(
                name=name,
                status=HealthStatus.DEGRADED,
                response_time_ms=response_time_ms,
                message=f"HTTP {response.status_code}, expected {expected_status}",
                details={"status_code": response.status_code, "url": url},
            )

        except (RuntimeError, httpx.RequestError) as e:
            response_time_ms = (time.perf_counter() - start_time) * 1000
            return HealthCheck(
                name=name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time_ms,
                message=f"Connection failed: {str(e)}",
                details={"url": url, "error": str(e)},
            )

    @retry_on_failure()
    async def check_redis(
        self,
        name: str = "redis",
        host: str = "localhost",
        port: int = 6379,
        password: str | None = None,
    ) -> HealthCheck:
        """Check Redis health."""
        start_time = time.perf_counter()

        if aioredis is None:
            return HealthCheck(
                name=name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=0,
                message="redis client not installed",
            )
        try:
            redis_client: Any = aioredis.from_url(  # type: ignore[union-attr]
                (f"redis://:{password}@{host}:{port}" if password else f"redis://{host}:{port}"),
                decode_responses=True,
            )

            # Test basic operations
            rc = redis_client
            await rc.ping()
            test_key = f"health_check_{int(time.time())}"
            await rc.set(test_key, "test", ex=10)
            value = await rc.get(test_key)
            await rc.delete(test_key)

            response_time_ms = (time.perf_counter() - start_time) * 1000

            if value == "test":
                info: dict[str, Any] = await rc.info()
                await rc.close()

                return HealthCheck(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    response_time_ms=response_time_ms,
                    message="Redis ping and operations successful",
                    details={
                        "version": info.get("redis_version"),
                        "memory_usage": info.get("used_memory_human"),
                        "connected_clients": info.get("connected_clients"),
                    },
                )
            await rc.close()
            return HealthCheck(
                name=name,
                status=HealthStatus.DEGRADED,
                response_time_ms=response_time_ms,
                message="Redis operations failed",
            )

        except RuntimeError as e:
            response_time_ms = (time.perf_counter() - start_time) * 1000
            return HealthCheck(
                name=name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time_ms,
                message=f"Redis connection failed: {str(e)}",
                details={"error": str(e)},
            )

    @retry_on_failure()
    async def check_postgres(self, name: str = "postgres", dsn: str | None = None) -> HealthCheck:
        """Check PostgreSQL health."""
        start_time = time.perf_counter()

        if not dsn:
            # Configure PostgreSQL credentials via environment variables
            # Set POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB
            user = os.getenv("POSTGRES_USER", "user")
            password = os.getenv("POSTGRES_PASSWORD", "password")
            host = os.getenv("POSTGRES_HOST", "localhost")
            port = os.getenv("POSTGRES_PORT", "5432")
            database = os.getenv("POSTGRES_DB", "database")
            dsn = f"postgresql://{user}:{password}@{host}:{port}/{database}"

        if asyncpg is None:
            return HealthCheck(
                name=name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=0,
                message="asyncpg not installed",
            )
        try:
            # type: ignore[union-attr]
            conn = cast("Any", await asyncpg.connect(dsn))

            # Test basic query
            result: Any = await conn.fetchval("SELECT 1")

            # Get database stats
            stats: Any = await conn.fetchrow(
                """
                SELECT
                    count(*) as table_count,
                    pg_size_pretty(pg_database_size(current_database())) as database_size,
                    version() as version
            """
            )

            await conn.close()
            response_time_ms = (time.perf_counter() - start_time) * 1000

            if result == 1:
                version_str = str(stats["version"])
                version_parts = version_str.split()
                version_fmt = " ".join(version_parts[:2]) if version_parts else version_str
                return HealthCheck(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    response_time_ms=response_time_ms,
                    message="PostgreSQL query successful",
                    details={
                        "table_count": stats["table_count"],
                        "database_size": stats["database_size"],
                        "version": version_fmt,
                    },
                )
            return HealthCheck(
                name=name,
                status=HealthStatus.DEGRADED,
                response_time_ms=response_time_ms,
                message="PostgreSQL query returned unexpected result",
            )

        except RuntimeError as e:
            response_time_ms = (time.perf_counter() - start_time) * 1000
            return HealthCheck(
                name=name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time_ms,
                message=f"PostgreSQL connection failed: {str(e)}",
                details={"error": str(e)},
            )

    @circuit_breaker(_name="lmstudio")
    async def check_lmstudio(
        self, name: str = "lmstudio", base_url: str = "http://localhost:1234"
    ) -> HealthCheck:
        """Check LM Studio health."""
        models_url = f"{base_url}/v1/models"
        return await self.check_http_endpoint(name, models_url)

    async def check_all(self, config: dict[str, Any] | None = None) -> HealthReport:
        """Run all health checks and return comprehensive report."""
        if config is None:
            config = {
                "http_endpoints": [
                    {"name": "dinoair-api", "url": "http://localhost:24801/health"},
                ],
                "redis": {"host": "localhost", "port": 6379},
                "postgres": {"dsn": None},
                "lmstudio": {"base_url": "http://localhost:1234"},
            }

        checks: list[HealthCheck] = []

        # HTTP endpoints
        for endpoint in config.get("http_endpoints", []):
            check = await self.check_http_endpoint(
                name=endpoint["name"],
                url=endpoint["url"],
                expected_status=endpoint.get("expected_status", 200),
            )
            checks.append(check)

        # Redis
        if "redis" in config:
            redis_config = config["redis"]
            check = await self.check_redis(name="redis", **redis_config)
            checks.append(check)

        # PostgreSQL
        if "postgres" in config:
            postgres_config = config["postgres"]
            check = await self.check_postgres(name="postgres", **postgres_config)
            checks.append(check)

        # LM Studio
        if "lmstudio" in config:
            lmstudio_config = config["lmstudio"]
            check = await self.check_lmstudio(name="lmstudio", **lmstudio_config)
            checks.append(check)

        return HealthReport.from_checks(checks)


# Convenience function for simple health checks
async def quick_health_check() -> dict[str, Any]:
    """Perform a quick health check and return JSON-serializable result."""
    async with HealthChecker() as checker:
        report = await checker.check_all()

        return {
            "status": report.overall_status.value,
            "timestamp": report.timestamp,
            "summary": {
                "total": report.total_checks,
                "healthy": report.healthy_checks,
                "degraded": report.degraded_checks,
                "unhealthy": report.unhealthy_checks,
            },
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "response_time_ms": round(check.response_time_ms, 2),
                    "message": check.message,
                    "details": check.details,
                }
                for check in report.checks
            ],
        }
