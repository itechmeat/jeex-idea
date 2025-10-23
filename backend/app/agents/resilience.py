from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar
from uuid import UUID

from tenacity import retry, stop_after_attempt, wait_exponential

from ..infrastructure.redis.redis_service import redis_service

T = TypeVar("T")

logger = logging.getLogger(__name__)


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(f"Invalid integer for {name}: {raw}") from e


MAX_RETRIES = _read_int_env("AGENT_MAX_RETRIES", 3)
RETRY_DELAY_SECONDS = _read_int_env("AGENT_RETRY_DELAY_SECONDS", 1)
CIRCUIT_BREAKER_THRESHOLD = _read_int_env("AGENT_CIRCUIT_BREAKER_THRESHOLD", 5)
CIRCUIT_BREAKER_TIMEOUT_SECONDS = _read_int_env(
    "AGENT_CIRCUIT_BREAKER_TIMEOUT_SECONDS", 60
)


def with_retries() -> Callable[
    [Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]
]:
    return retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=RETRY_DELAY_SECONDS),
    )


def circuit_breaker(
    agent_key: str, project_id: UUID
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Simple Redis-based circuit breaker for agent failures.

    Opens after threshold consecutive failures and auto-closes after timeout.
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            key = f"agent:cb:{agent_key}:failures"
            open_key = f"agent:cb:{agent_key}:open"

            from redis.asyncio import Redis

            async def _get(conn: Redis, k: str) -> str | None:
                return await conn.get(k)

            # If breaker is open, reject fast
            is_open = await redis_service.execute_with_retry(
                operation="cb.get_open",
                func=_get,
                k=open_key,
                project_id=str(project_id),
            )
            if is_open:
                raise RuntimeError("Circuit breaker open for agent")

            try:
                result = await func(*args, **kwargs)

                # Reset failure counter on success
                async def _delete(conn: Redis, k: str) -> int:
                    return await conn.delete(k)

                await redis_service.execute_with_retry(
                    operation="cb.reset",
                    func=_delete,
                    k=key,
                    project_id=str(project_id),
                )
                return result
            except Exception:
                logger.exception(
                    "Circuit breaker caught exception",
                    extra={
                        "key": key,
                        "open_key": open_key,
                        "project_id": str(project_id),
                        "agent_key": agent_key,
                    },
                )

                # Increment failure counter
                async def _incr(conn: Redis, k: str) -> int:
                    return await conn.incr(k)

                failures = await redis_service.execute_with_retry(
                    operation="cb.incr",
                    func=_incr,
                    k=key,
                    project_id=str(project_id),
                )

                # Set TTL on failure counter to prevent memory leak
                async def _expire(conn: Redis, k: str, ex: int) -> bool:
                    return await conn.expire(k, ex)

                await redis_service.execute_with_retry(
                    operation="cb.set_ttl",
                    func=_expire,
                    k=key,
                    ex=CIRCUIT_BREAKER_TIMEOUT_SECONDS,
                    project_id=str(project_id),
                )

                if int(failures) >= CIRCUIT_BREAKER_THRESHOLD:
                    # Open breaker with TTL
                    async def _setex(conn: Redis, k: str, ex: int, v: str) -> bool:
                        return await conn.set(k, v, ex=ex)

                    await redis_service.execute_with_retry(
                        operation="cb.open",
                        func=_setex,
                        k=open_key,
                        ex=CIRCUIT_BREAKER_TIMEOUT_SECONDS,
                        v="1",
                        project_id=str(project_id),
                    )

                    # Reset failures counter
                    async def _del(conn: Redis, k: str) -> int:
                        return await conn.delete(k)

                    await redis_service.execute_with_retry(
                        operation="cb.clear_failures",
                        func=_del,
                        k=key,
                        project_id=str(project_id),
                    )
                    raise RuntimeError(
                        "Circuit breaker opened due to consecutive failures"
                    )
                raise

        return wrapper

    return decorator


## Legacy duplicate implementation removed (consolidated above)
