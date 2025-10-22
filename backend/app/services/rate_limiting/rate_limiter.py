"""
Rate Limiter Service

Primary rate limiting service with sliding window algorithm.
Implements user-level, project-level, and IP-based rate limiting
with Redis backend for distributed scenarios.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Union
from uuid import UUID

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.core.config import settings
from app.infrastructure.redis.connection_factory import redis_connection_factory
from app.infrastructure.redis.exceptions import (
    RedisException,
    RedisOperationTimeoutException,
    RedisConnectionException,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class RateLimitResult(BaseModel):
    """Result of rate limit check."""

    allowed: bool = Field(..., description="Whether request is allowed")
    current_count: int = Field(..., description="Current request count")
    remaining_requests: int = Field(..., description="Remaining requests")
    reset_seconds: int = Field(..., description="Seconds until reset")
    limit: int = Field(..., description="Rate limit threshold")
    window: int = Field(..., description="Time window in seconds")
    identifier: str = Field(..., description="Rate limit identifier")
    limit_type: str = Field(..., description="Type of rate limit")
    retry_after: Optional[int] = Field(None, description="Retry-After header value")


class RateLimitConfig(BaseModel):
    """Rate limit configuration."""

    requests_per_window: int = Field(
        ..., ge=1, description="Number of allowed requests"
    )
    window_seconds: int = Field(..., ge=1, description="Time window in seconds")
    burst_size: Optional[int] = Field(None, ge=1, description="Burst capacity")


class RateLimiter:
    """
    High-performance rate limiter with sliding window algorithm.

    Implements distributed rate limiting using Redis with atomic operations
    to ensure accuracy across multiple service instances.
    """

    # Default rate limit configurations
    DEFAULT_USER_LIMIT = RateLimitConfig(
        requests_per_window=1000,
        window_seconds=3600,  # 1 hour
    )

    DEFAULT_PROJECT_LIMIT = RateLimitConfig(
        requests_per_window=5000,
        window_seconds=3600,  # 1 hour
    )

    DEFAULT_IP_LIMIT = RateLimitConfig(
        requests_per_window=100,
        window_seconds=60,  # 1 minute
    )

    # API endpoint specific limits
    API_ENDPOINT_LIMITS = {
        "/api/v1/documents": RateLimitConfig(requests_per_window=50, window_seconds=60),
        "/api/v1/agents": RateLimitConfig(requests_per_window=20, window_seconds=60),
        "/api/v1/projects": RateLimitConfig(requests_per_window=30, window_seconds=60),
    }

    def __init__(self):
        self._redis_factory = redis_connection_factory
        self._lua_scripts = {}
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize rate limiter."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            try:
                # Scripts will be loaded per project on-demand
                self._initialized = True
                logger.info("Rate limiter initialized successfully")

            except Exception as e:
                logger.error(f"Failed to initialize rate limiter: {e}")
                raise

    async def _load_lua_scripts(self, project_id: UUID) -> None:
        """Load Redis Lua scripts for atomic rate limiting operations."""

        # Sliding window Lua script
        sliding_window_script = """
        local key = KEYS[1]
        local window = tonumber(ARGV[1])
        local now = tonumber(ARGV[2])
        local request_cost = tonumber(ARGV[3])
        local limit = tonumber(ARGV[4])

        -- Remove expired entries
        redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

        -- Get current count
        local current = redis.call('ZCARD', key)

        -- Debug logging (comment out in production)
        -- redis.log(redis.LOG_DEBUG, "Rate limit check: key=" .. key .. ", current=" .. current .. ", limit=" .. limit .. ", cost=" .. request_cost)

        -- Check if request would exceed limit
        if current + request_cost > limit then
            -- Get oldest request time for retry-after calculation
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            local reset_time = oldest[2] and math.ceil(oldest[2] + window - now) or window

            return {
                0,  -- allowed = false
                current,
                math.max(0, limit - current),
                reset_time,
                limit
            }
        end

        -- Add requests according to cost (each unit of cost = 1 request)
        for i = 1, request_cost do
            local member = now .. ':' .. math.random(1000000)
            redis.call('ZADD', key, now, member)
        end
        redis.call('EXPIRE', key, math.ceil(window / 1000))

        return {
            1,  -- allowed = true
            current + request_cost,
            math.max(0, limit - current - request_cost),
            window,
            limit
        }
        """

        # Token bucket Lua script
        token_bucket_script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local tokens_per_second = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        local requested_tokens = tonumber(ARGV[4])

        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local current_tokens = tonumber(bucket[1]) or capacity
        local last_refill = tonumber(bucket[2]) or now

        -- Calculate tokens to add
        local time_passed = now - last_refill
        local tokens_to_add = time_passed * tokens_per_second
        current_tokens = math.min(capacity, current_tokens + tokens_to_add)

        -- Check if enough tokens available
        if current_tokens < requested_tokens then
            local retry_after = math.ceil((requested_tokens - current_tokens) / tokens_per_second)

            redis.call('HMSET', key, 'tokens', current_tokens, 'last_refill', now)
            redis.call('EXPIRE', key, math.ceil(capacity / tokens_per_second) + 1)

            return {
                0,  -- allowed = false
                math.floor(current_tokens),
                0,  -- remaining tokens
                retry_after,
                capacity
            }
        end

        -- Consume tokens
        current_tokens = current_tokens - requested_tokens

        redis.call('HMSET', key, 'tokens', current_tokens, 'last_refill', now)
        redis.call('EXPIRE', key, math.ceil(capacity / tokens_per_second) + 1)

        return {
            1,  -- allowed = true
            math.floor(current_tokens),
            math.floor(current_tokens),
            0,  -- no retry needed
            capacity
        }
        """

        async with self._redis_factory.get_connection(project_id) as redis_client:
            self._lua_scripts[
                f"sliding_window:{project_id}"
            ] = await redis_client.script_load(sliding_window_script)
            self._lua_scripts[
                f"token_bucket:{project_id}"
            ] = await redis_client.script_load(token_bucket_script)

    async def check_user_rate_limit(
        self,
        project_id: UUID,
        user_id: Union[str, UUID],
        config: Optional[RateLimitConfig] = None,
        cost: int = 1,
    ) -> RateLimitResult:
        """
        Check rate limit for user using sliding window algorithm.

        Args:
            project_id: Project identifier for isolation
            user_id: User identifier
            config: Rate limit configuration (uses default if not provided)
            cost: Request cost (default 1)

        Returns:
            Rate limit check result
        """
        return await self._check_rate_limit(
            project_id=project_id,
            identifier=str(user_id),
            limit_type="user",
            config=config or self.DEFAULT_USER_LIMIT,
            cost=cost,
        )

    async def check_project_rate_limit(
        self,
        project_id: UUID,
        config: Optional[RateLimitConfig] = None,
        cost: int = 1,
    ) -> RateLimitResult:
        """
        Check rate limit for project using sliding window algorithm.

        Args:
            project_id: Project identifier for isolation
            config: Rate limit configuration (uses default if not provided)
            cost: Request cost (default 1)

        Returns:
            Rate limit check result
        """
        return await self._check_rate_limit(
            project_id=project_id,
            identifier=str(project_id),
            limit_type="project",
            config=config or self.DEFAULT_PROJECT_LIMIT,
            cost=cost,
        )

    async def check_ip_rate_limit(
        self,
        project_id: UUID,
        ip_address: str,
        config: Optional[RateLimitConfig] = None,
        cost: int = 1,
    ) -> RateLimitResult:
        """
        Check rate limit for IP address using sliding window algorithm.

        Args:
            project_id: Project identifier for isolation
            ip_address: IP address
            config: Rate limit configuration (uses default if not provided)
            cost: Request cost (default 1)

        Returns:
            Rate limit check result
        """
        return await self._check_rate_limit(
            project_id=project_id,
            identifier=ip_address,
            limit_type="ip",
            config=config or self.DEFAULT_IP_LIMIT,
            cost=cost,
        )

    async def check_endpoint_rate_limit(
        self,
        project_id: UUID,
        endpoint: str,
        user_id: Optional[Union[str, UUID]] = None,
        cost: int = 1,
    ) -> RateLimitResult:
        """
        Check rate limit for specific API endpoint.

        Args:
            project_id: Project identifier for isolation
            endpoint: API endpoint path
            user_id: Optional user ID for user-specific limits
            cost: Request cost (default 1)

        Returns:
            Rate limit check result
        """
        config = self.API_ENDPOINT_LIMITS.get(endpoint)
        if not config:
            # Use default user limit if no specific endpoint limit
            config = self.DEFAULT_USER_LIMIT

        identifier = f"endpoint:{endpoint}"
        if user_id:
            identifier = f"{identifier}:user:{user_id}"

        return await self._check_rate_limit(
            project_id=project_id,
            identifier=identifier,
            limit_type="endpoint",
            config=config,
            cost=cost,
        )

    async def _check_rate_limit(
        self,
        project_id: UUID,
        identifier: str,
        limit_type: str,
        config: RateLimitConfig,
        cost: int = 1,
    ) -> RateLimitResult:
        """
        Core rate limiting check using sliding window algorithm.

        Args:
            project_id: Project identifier for isolation
            identifier: Rate limit identifier
            limit_type: Type of rate limit
            config: Rate limit configuration
            cost: Request cost

        Returns:
            Rate limit check result
        """
        # Validate cost parameter
        if cost < 1:
            raise ValueError("cost must be >= 1")

        await self.initialize()

        with tracer.start_as_current_span("rate_limiter.check") as span:
            span.set_attribute("project_id", str(project_id))
            span.set_attribute("identifier", identifier)
            span.set_attribute("limit_type", limit_type)
            span.set_attribute("limit", config.requests_per_window)
            span.set_attribute("window", config.window_seconds)
            span.set_attribute("cost", cost)

            try:
                # Load scripts for this project if not already loaded
                script_key = f"sliding_window:{project_id}"
                if script_key not in self._lua_scripts:
                    await self._load_lua_scripts(project_id)

                key = f"rate_limit:{limit_type}:{identifier}:{config.window_seconds}"
                now = int(time.time() * 1000)  # Use milliseconds for better granularity

                async with self._redis_factory.get_connection(
                    project_id
                ) as redis_client:
                    # Use sliding window algorithm with atomic Lua script
                    result = await redis_client.evalsha(
                        self._lua_scripts[script_key],
                        1,  # number of keys
                        key,
                        config.window_seconds * 1000,  # Convert window to milliseconds
                        now,
                        cost,
                        config.requests_per_window,
                    )

                    # Debug: log the Redis state after script execution
                    current_count = await redis_client.zcard(key)
                    span.set_attribute("redis_current_count", current_count)

                allowed, current_count, remaining, reset_ms, limit = result

                # Convert milliseconds to seconds using ceiling division
                reset_seconds = (reset_ms + 999) // 1000

                rate_limit_result = RateLimitResult(
                    allowed=bool(allowed),
                    current_count=current_count,
                    remaining_requests=remaining,
                    reset_seconds=reset_seconds,
                    limit=limit,
                    window=config.window_seconds,
                    identifier=identifier,
                    limit_type=limit_type,
                    retry_after=reset_seconds if not allowed else None,
                )

                span.set_attribute("allowed", allowed)
                span.set_attribute("current_count", current_count)
                span.set_attribute("remaining", remaining)

                if not allowed:
                    logger.warning(
                        f"Rate limit exceeded for {limit_type}:{identifier}",
                        extra={
                            "identifier": identifier,
                            "limit_type": limit_type,
                            "current": current_count,
                            "limit": limit,
                            "window": config.window_seconds,
                            "reset_seconds": reset_seconds,
                        },
                    )

                return rate_limit_result

            except RedisConnectionException as e:
                logger.error(f"Redis connection error during rate limit check: {e}")
                span.set_status(Status(StatusCode.ERROR, "Redis connection failed"))

                # Fail open - allow request if Redis is unavailable
                return RateLimitResult(
                    allowed=True,
                    current_count=0,
                    remaining_requests=config.requests_per_window,
                    reset_seconds=config.window_seconds,
                    limit=config.requests_per_window,
                    window=config.window_seconds,
                    identifier=identifier,
                    limit_type=limit_type,
                    retry_after=None,
                )

            except Exception as e:
                logger.error(f"Rate limit check failed for {identifier}: {e}")
                span.set_status(Status(StatusCode.ERROR, str(e)))

                # Fail open - allow request on unexpected errors
                return RateLimitResult(
                    allowed=True,
                    current_count=0,
                    remaining_requests=config.requests_per_window,
                    reset_seconds=config.window_seconds,
                    limit=config.requests_per_window,
                    window=config.window_seconds,
                    identifier=identifier,
                    limit_type=limit_type,
                    retry_after=None,
                )

    async def get_rate_limit_status(
        self,
        project_id: UUID,
        identifier: str,
        limit_type: str,
        config: RateLimitConfig,
    ) -> RateLimitResult:
        """
        Get current rate limit status without consuming tokens.

        Args:
            project_id: Project identifier for isolation
            identifier: Rate limit identifier
            limit_type: Type of rate limit
            config: Rate limit configuration

        Returns:
            Current rate limit status
        """
        await self.initialize()

        try:
            key = f"rate_limit:{limit_type}:{identifier}:{config.window_seconds}"
            now = int(time.time() * 1000)  # Use milliseconds
            window_start = now - config.window_seconds * 1000

            async with self._redis_factory.get_connection(project_id) as redis_client:
                # Count requests in current window
                current_count = await redis_client.zcount(key, window_start, now)

                # Get oldest request time for reset calculation
                oldest = await redis_client.zrange(key, 0, 0, withscores=True)
                reset_seconds = config.window_seconds

                if oldest:
                    # oldest is [(member, score)] when withscores=True
                    oldest_time = int(oldest[0][1])
                    reset_seconds = (
                        max(0, oldest_time + config.window_seconds * 1000 - now) // 1000
                    )

            return RateLimitResult(
                allowed=True,  # Status check doesn't consume
                current_count=current_count,
                remaining_requests=max(0, config.requests_per_window - current_count),
                reset_seconds=reset_seconds,
                limit=config.requests_per_window,
                window=config.window_seconds,
                identifier=identifier,
                limit_type=limit_type,
                retry_after=None,
            )

        except Exception as e:
            logger.error(f"Failed to get rate limit status for {identifier}: {e}")

            # Return default status on error
            return RateLimitResult(
                allowed=True,
                current_count=0,
                remaining_requests=config.requests_per_window,
                reset_seconds=config.window_seconds,
                limit=config.requests_per_window,
                window=config.window_seconds,
                identifier=identifier,
                limit_type=limit_type,
                retry_after=None,
            )

    async def reset_rate_limit(
        self, project_id: UUID, identifier: str, limit_type: str, window_seconds: int
    ) -> bool:
        """
        Reset rate limit for identifier.

        Args:
            project_id: Project identifier for isolation
            identifier: Rate limit identifier
            limit_type: Type of rate limit
            window_seconds: Window size in seconds

        Returns:
            True if reset successful
        """
        await self.initialize()

        try:
            key = f"rate_limit:{limit_type}:{identifier}:{window_seconds}"

            async with self._redis_factory.get_connection(project_id) as redis_client:
                await redis_client.delete(key)

            logger.info(
                f"Reset rate limit for project {project_id}:{limit_type}:{identifier}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to reset rate limit for {identifier}: {e}")
            return False

    async def get_rate_limit_metrics(self, project_id: UUID) -> Dict[str, Any]:
        """
        Get rate limiting metrics for monitoring.

        Args:
            project_id: Project identifier for project-specific metrics

        Returns:
            Rate limiting metrics and statistics
        """
        # Validate project_id
        if project_id is None:
            raise ValueError("project_id is required")

        try:
            async with self._redis_factory.get_connection(project_id) as redis_client:
                pattern = "rate_limit:*"
                keys = []

                # Use SCAN to avoid blocking Redis
                cursor = 0
                while True:
                    cursor, batch_keys = await redis_client.scan(
                        cursor=cursor, match=pattern, count=100
                    )
                    keys.extend(batch_keys)
                    if cursor == 0:
                        break

                metrics = {
                    "total_active_limits": len(keys),
                    "limits_by_type": {},
                    "memory_usage": 0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "project_id": str(project_id),
                }

                # Count limits by type
                for key in keys:
                    parts = key.split(":")
                    if len(parts) >= 3:
                        limit_type = parts[1]
                        metrics["limits_by_type"][limit_type] = (
                            metrics["limits_by_type"].get(limit_type, 0) + 1
                        )

                # Get memory usage per key using public interface
                if keys:
                    total_memory = 0
                    for key in keys:
                        try:
                            # Use public memory_usage method which handles key prefixing
                            mem = await redis_client.memory_usage(key)
                            if mem is not None:
                                total_memory += mem
                        except Exception as e:
                            logger.debug(
                                f"Failed to get memory usage for key {key}: {e}"
                            )
                            continue
                    metrics["memory_usage"] = total_memory

                return metrics

        except Exception as e:
            logger.error(f"Failed to get rate limit metrics: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }


# Global rate limiter instance
rate_limiter = RateLimiter()
