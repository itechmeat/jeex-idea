"""
Rate Limit Repository

Redis implementation of rate limiting repository.
Provides atomic operations for distributed rate limiting.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Union
from uuid import UUID

from ...services.rate_limiting.rate_limiter import RateLimitConfig, RateLimitResult
from ...infrastructure.redis.connection_factory import redis_connection_factory
from ...infrastructure.redis.exceptions import (
    RedisException,
    RedisConnectionException,
    RedisOperationTimeoutException,
)

logger = logging.getLogger(__name__)


class RateLimitRepository:
    """
    Redis repository for rate limiting operations.

    Provides atomic rate limiting operations using Redis
    with sliding window and token bucket algorithms.
    """

    def __init__(self):
        self._redis_factory = redis_connection_factory
        self._lua_scripts = {}

    async def initialize(self) -> None:
        """Initialize repository and load Lua scripts."""
        try:
            await self._load_lua_scripts()
            logger.info("Rate limit repository initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize rate limit repository: {e}")
            raise

    async def _load_lua_scripts(self) -> None:
        """Load Redis Lua scripts for atomic rate limiting operations."""

        # Sliding window implementation
        sliding_window_script = """
        local key = KEYS[1]
        local window = tonumber(ARGV[1])
        local now = tonumber(ARGV[2])
        local cost = tonumber(ARGV[3])
        local limit = tonumber(ARGV[4])

        -- Remove expired entries
        redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

        -- Get current count
        local current = redis.call('ZCARD', key)

        -- Check if request would exceed limit
        if current + cost > limit then
            -- Get oldest request time for retry calculation
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            local reset_time = window

            if oldest[2] then
                reset_time = math.ceil(oldest[2] + window - now)
            end

            return {
                0,  -- allowed = false
                current,
                0,  -- remaining
                reset_time,
                limit
            }
        end

        -- Add current request with timestamp as score
        for i = 1, cost do
            redis.call('ZADD', key, now, now .. ':' .. i)
        end

        -- Set expiration
        redis.call('EXPIRE', key, window)

        return {
            1,  -- allowed = true
            current + cost,
            math.max(0, limit - current - cost),
            window,
            limit
        }
        """

        # Token bucket implementation
        token_bucket_script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        local requested_tokens = tonumber(ARGV[4])

        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local current_tokens = tonumber(bucket[1]) or capacity
        local last_refill = tonumber(bucket[2]) or now

        -- Calculate tokens to add
        local time_passed = now - last_refill
        local tokens_to_add = time_passed * refill_rate
        current_tokens = math.min(capacity, current_tokens + tokens_to_add)

        -- Check if enough tokens available
        if current_tokens < requested_tokens then
            local retry_after = math.ceil((requested_tokens - current_tokens) / refill_rate)

            redis.call('HMSET', key, 'tokens', current_tokens, 'last_refill', now)
            redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) + 1)

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
        redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) + 1)

        return {
            1,  -- allowed = true
            math.floor(current_tokens),
            math.floor(current_tokens),
            0,  -- no retry needed
            capacity
        }
        """

        async with self._redis_factory.get_connection() as redis_client:
            self._lua_scripts["sliding_window"] = await redis_client.script_load(
                sliding_window_script
            )
            self._lua_scripts["token_bucket"] = await redis_client.script_load(
                token_bucket_script
            )

    async def check_sliding_window_limit(
        self,
        identifier: str,
        config: RateLimitConfig,
        cost: int = 1,
        project_id: Optional[UUID] = None,
    ) -> RateLimitResult:
        """
        Check rate limit using sliding window algorithm.

        Args:
            identifier: Unique identifier for rate limiting
            config: Rate limit configuration
            cost: Request cost
            project_id: Optional project ID for isolation

        Returns:
            Rate limit check result
        """
        try:
            key = f"rate_limit:sliding:{identifier}:{config.window_seconds}"
            now = int(time.time())

            async with self._redis_factory.get_connection(
                str(project_id) if project_id else None
            ) as redis_client:
                result = await redis_client.evalsha(
                    self._lua_scripts["sliding_window"],
                    1,  # number of keys
                    key,
                    config.window_seconds,
                    now,
                    cost,
                    config.requests_per_window,
                )

            allowed, current_count, remaining, reset_seconds, limit = result

            return RateLimitResult(
                allowed=bool(allowed),
                current_count=current_count,
                remaining_requests=remaining,
                reset_seconds=reset_seconds,
                limit=limit,
                window=config.window_seconds,
                identifier=identifier,
                limit_type="sliding_window",
                retry_after=reset_seconds if not allowed else None,
            )

        except RedisConnectionException as e:
            logger.error(
                f"Redis connection error during sliding window rate limit check: {e}"
            )
            # Fail open
            return RateLimitResult(
                allowed=True,
                current_count=0,
                remaining_requests=config.requests_per_window,
                reset_seconds=config.window_seconds,
                limit=config.requests_per_window,
                window=config.window_seconds,
                identifier=identifier,
                limit_type="sliding_window",
                retry_after=None,
            )

        except Exception as e:
            logger.error(
                f"Sliding window rate limit check failed for {identifier}: {e}"
            )
            # Fail open
            return RateLimitResult(
                allowed=True,
                current_count=0,
                remaining_requests=config.requests_per_window,
                reset_seconds=config.window_seconds,
                limit=config.requests_per_window,
                window=config.window_seconds,
                identifier=identifier,
                limit_type="sliding_window",
                retry_after=None,
            )

    async def check_token_bucket_limit(
        self,
        identifier: str,
        capacity: int,
        refill_rate: float,
        cost: int = 1,
        project_id: Optional[UUID] = None,
    ) -> RateLimitResult:
        """
        Check rate limit using token bucket algorithm.

        Args:
            identifier: Unique identifier for rate limiting
            capacity: Bucket capacity
            refill_rate: Tokens per second refill rate
            cost: Request cost
            project_id: Optional project ID for isolation

        Returns:
            Rate limit check result
        """
        try:
            key = f"rate_limit:token_bucket:{identifier}"
            now = int(time.time())

            async with self._redis_factory.get_connection(
                str(project_id) if project_id else None
            ) as redis_client:
                result = await redis_client.evalsha(
                    self._lua_scripts["token_bucket"],
                    1,  # number of keys
                    key,
                    capacity,
                    refill_rate,
                    now,
                    cost,
                )

            allowed, current_tokens, remaining, retry_after, max_capacity = result

            return RateLimitResult(
                allowed=bool(allowed),
                current_count=max_capacity - current_tokens,
                remaining_requests=remaining,
                reset_seconds=retry_after if not allowed else 0,
                limit=max_capacity,
                window=int(capacity / refill_rate),  # Approximate window
                identifier=identifier,
                limit_type="token_bucket",
                retry_after=retry_after if not allowed else None,
            )

        except Exception as e:
            logger.error(f"Token bucket rate limit check failed for {identifier}: {e}")
            # Fail open
            return RateLimitResult(
                allowed=True,
                current_count=0,
                remaining_requests=capacity,
                reset_seconds=0,
                limit=capacity,
                window=int(capacity / refill_rate),
                identifier=identifier,
                limit_type="token_bucket",
                retry_after=None,
            )

    async def get_current_usage(
        self, identifier: str, window_seconds: int, project_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Get current usage statistics for identifier.

        Args:
            identifier: Unique identifier
            window_seconds: Time window in seconds
            project_id: Optional project ID for isolation

        Returns:
            Current usage statistics
        """
        try:
            key = f"rate_limit:sliding:{identifier}:{window_seconds}"
            now = int(time.time())
            window_start = now - window_seconds

            async with self._redis_factory.get_connection(
                str(project_id) if project_id else None
            ) as redis_client:
                # Count requests in current window
                current_count = await redis_client.zcount(key, window_start, now)

                # Get window boundaries
                oldest = await redis_client.zrange(key, 0, 0, withscores=True)
                newest = await redis_client.zrange(key, -1, -1, withscores=True)

                oldest_time = (
                    int(oldest[0][1]) if oldest and oldest[0] else window_start
                )
                newest_time = int(newest[0][1]) if newest and newest[0] else now

                return {
                    "current_count": current_count,
                    "window_start": window_start,
                    "window_end": now,
                    "oldest_request": oldest_time,
                    "newest_request": newest_time,
                    "window_active": oldest_time > window_start,
                }

        except Exception as e:
            logger.error(f"Failed to get current usage for {identifier}: {e}")
            return {
                "current_count": 0,
                "window_start": now - window_seconds,
                "window_end": now,
                "oldest_request": now - window_seconds,
                "newest_request": now,
                "window_active": False,
                "error": str(e),
            }

    async def reset_rate_limit(
        self, identifier: str, window_seconds: int, project_id: Optional[UUID] = None
    ) -> bool:
        """
        Reset rate limit for identifier.

        Args:
            identifier: Unique identifier
            window_seconds: Time window in seconds
            project_id: Optional project ID for isolation

        Returns:
            True if reset successful
        """
        try:
            key = f"rate_limit:sliding:{identifier}:{window_seconds}"

            async with self._redis_factory.get_connection(
                str(project_id) if project_id else None
            ) as redis_client:
                await redis_client.delete(key)

            logger.debug(f"Reset rate limit for {identifier}")
            return True

        except Exception as e:
            logger.error(f"Failed to reset rate limit for {identifier}: {e}")
            return False

    async def cleanup_expired_entries(self, max_age_hours: int = 24) -> int:
        """
        Clean up expired rate limit entries.

        Args:
            max_age_hours: Maximum age for entries

        Returns:
            Number of entries cleaned up
        """
        try:
            cutoff_time = int(time.time()) - (max_age_hours * 3600)
            cleaned_count = 0

            async with self._redis_factory.get_connection() as redis_client:
                # Get all rate limit keys
                keys = await redis_client.keys("rate_limit:*")

                for key in keys:
                    # Skip non-sliding window keys
                    if ":sliding:" not in key:
                        continue

                    # Check oldest entry in window
                    oldest = await redis_client.zrange(key, 0, 0, withscores=True)
                    if oldest and oldest[0] and int(oldest[0][1]) < cutoff_time:
                        await redis_client.delete(key)
                        cleaned_count += 1

            logger.debug(f"Cleaned up {cleaned_count} expired rate limit entries")
            return cleaned_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired rate limit entries: {e}")
            return 0

    async def get_rate_limit_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive rate limiting metrics.

        Returns:
            Rate limiting metrics
        """
        try:
            async with self._redis_factory.get_connection() as redis_client:
                # Get all rate limit keys
                keys = await redis_client.keys("rate_limit:*")

                metrics = {
                    "total_active_limits": len(keys),
                    "limits_by_algorithm": {"sliding_window": 0, "token_bucket": 0},
                    "limits_by_window": {},
                    "memory_usage": 0,
                    "timestamp": datetime.utcnow().isoformat(),
                }

                # Analyze keys
                for key in keys:
                    if ":sliding:" in key:
                        metrics["limits_by_algorithm"]["sliding_window"] += 1
                        # Extract window size
                        parts = key.split(":")
                        if len(parts) >= 4:
                            window = parts[-1]
                            metrics["limits_by_window"][window] = (
                                metrics["limits_by_window"].get(window, 0) + 1
                            )
                    elif ":token_bucket:" in key:
                        metrics["limits_by_algorithm"]["token_bucket"] += 1

                # Get memory usage (approximate)
                if keys:
                    for key in keys[:100]:  # Sample first 100 keys to avoid blocking
                        try:
                            memory = await redis_client.memory_usage(key)
                            metrics["memory_usage"] += memory
                        except:
                            pass

                return metrics

        except Exception as e:
            logger.error(f"Failed to get rate limit metrics: {e}")
            return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}


# Global rate limit repository instance
rate_limit_repository = RateLimitRepository()
