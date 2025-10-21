"""
Rate Limiting Strategies

Different rate limiting algorithms and strategies.
Implements sliding window, token bucket, and fixed window approaches.
"""

import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from ...infrastructure.redis.connection_factory import redis_connection_factory


class RateLimitStrategy(ABC):
    """Abstract base class for rate limiting strategies."""

    @abstractmethod
    async def check_limit(
        self, identifier: str, limit: int, window: int, cost: int = 1
    ) -> Dict[str, Any]:
        """
        Check rate limit using specific strategy.

        Args:
            identifier: Unique identifier for rate limit
            limit: Maximum allowed requests
            window: Time window in seconds
            cost: Request cost

        Returns:
            Rate limit check result
        """
        pass


class SlidingWindowStrategy(RateLimitStrategy):
    """
    Sliding window rate limiting strategy.

    Uses Redis sorted sets to maintain a sliding window of requests
    with precise time-based expiration and high accuracy.
    """

    def __init__(self, redis_factory=None):
        self.redis_factory = redis_factory or redis_connection_factory

    async def check_limit(
        self, identifier: str, limit: int, window: int, cost: int = 1
    ) -> Dict[str, Any]:
        """
        Check rate limit using sliding window algorithm.

        Maintains a sorted set of request timestamps, automatically
        removing entries outside the current window.
        """
        key = f"sliding_window:{identifier}:{window}"
        now = int(time.time())

        async with self.redis_factory.get_connection() as redis_client:
            # Use pipeline for atomic operations
            pipe = redis_client.pipeline()

            # Remove expired entries
            pipe.zremrangebyscore(key, 0, now - window)

            # Get current count
            pipe.zcard(key)

            # Check if request would exceed limit
            # Add current request if within limit
            pipe.zadd(key, {str(now): now})

            # Set expiration
            pipe.expire(key, window)

            results = await pipe.execute()

            current_count = results[1]

            if current_count > limit:
                # Remove the request we just added (it exceeded limit)
                await redis_client.zrem(key, str(now))

                # Get oldest request for retry calculation
                oldest = await redis_client.zrange(key, 0, 0, withscores=True)
                reset_time = window

                if oldest:
                    oldest_time = int(oldest[0][1]) if oldest[0] else now
                    reset_time = max(0, oldest_time + window - now)

                return {
                    "allowed": False,
                    "current_count": current_count,
                    "remaining_requests": 0,
                    "reset_seconds": reset_time,
                    "limit": limit,
                }

            return {
                "allowed": True,
                "current_count": current_count,
                "remaining_requests": max(0, limit - current_count),
                "reset_seconds": window,
                "limit": limit,
            }


class TokenBucketStrategy(RateLimitStrategy):
    """
    Token bucket rate limiting strategy.

    Uses Redis hash to maintain token count with automatic refill
    based on time elapsed. Good for burst handling.
    """

    def __init__(self, redis_factory=None):
        self.redis_factory = redis_factory or redis_connection_factory

    async def check_limit(
        self,
        identifier: str,
        capacity: int,
        refill_rate: int,  # tokens per second
        cost: int = 1,
    ) -> Dict[str, Any]:
        """
        Check rate limit using token bucket algorithm.

        Tokens are refilled based on elapsed time since last request.
        Allows for burst handling within capacity limits.
        """
        key = f"token_bucket:{identifier}"
        now = int(time.time())

        async with self.redis_factory.get_connection() as redis_client:
            # Use atomic script for token bucket operations
            script = """
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

            result = await redis_client.eval(
                script,
                1,  # number of keys
                key,
                capacity,
                refill_rate,
                now,
                cost,
            )

            allowed, current_tokens, remaining, retry_after, max_capacity = result

            return {
                "allowed": bool(allowed),
                "current_count": max_capacity - current_tokens,
                "remaining_requests": remaining,
                "reset_seconds": retry_after if not allowed else 0,
                "limit": max_capacity,
                "tokens": current_tokens,
            }


class FixedWindowStrategy(RateLimitStrategy):
    """
    Fixed window rate limiting strategy.

    Uses simple counters with fixed time windows.
    Less accurate than sliding window but very fast.
    """

    def __init__(self, redis_factory=None):
        self.redis_factory = redis_factory or redis_connection_factory

    async def check_limit(
        self, identifier: str, limit: int, window: int, cost: int = 1
    ) -> Dict[str, Any]:
        """
        Check rate limit using fixed window algorithm.

        Uses Redis INCR with EXPIRE for simple, fast rate limiting.
        Less accurate at window boundaries but very performant.
        """
        # Calculate current window key
        current_time = int(time.time())
        window_start = (current_time // window) * window
        key = f"fixed_window:{identifier}:{window_start}"

        async with self.redis_factory.get_connection() as redis_client:
            # Use atomic increment with expiration
            pipe = redis_client.pipeline()
            pipe.incrby(key, cost)
            pipe.expire(key, window)

            results = await pipe.execute()
            current_count = results[0]

            if current_count > limit:
                # Calculate time until next window
                next_window = window_start + window
                reset_seconds = max(0, next_window - current_time)

                return {
                    "allowed": False,
                    "current_count": current_count,
                    "remaining_requests": 0,
                    "reset_seconds": reset_seconds,
                    "limit": limit,
                }

            return {
                "allowed": True,
                "current_count": current_count,
                "remaining_requests": max(0, limit - current_count),
                "reset_seconds": window,
                "limit": limit,
            }


class AdaptiveRateLimitStrategy(RateLimitStrategy):
    """
    Adaptive rate limiting strategy.

    Adjusts limits based on system load, user behavior patterns,
    and other contextual factors.
    """

    def __init__(self, redis_factory=None):
        self.redis_factory = redis_factory or redis_connection_factory
        self.base_strategy = SlidingWindowStrategy(redis_factory)

    async def check_limit(
        self, identifier: str, base_limit: int, window: int, cost: int = 1
    ) -> Dict[str, Any]:
        """
        Check rate limit with adaptive adjustment.

        Adjusts the limit based on various factors like:
        - System load
        - Historical user behavior
        - Time of day
        - Geographic location (if available)
        """
        # Calculate adaptive limit multiplier
        multiplier = await self._calculate_adaptive_multiplier(identifier)

        # Apply multiplier to base limit
        adjusted_limit = int(base_limit * multiplier)

        # Use base strategy with adjusted limit
        result = await self.base_strategy.check_limit(
            identifier, adjusted_limit, window, cost
        )

        # Add adaptive information to result
        result["adaptive_multiplier"] = multiplier
        result["base_limit"] = base_limit
        result["adjusted_limit"] = adjusted_limit

        return result

    async def _calculate_adaptive_multiplier(self, identifier: str) -> float:
        """Calculate adaptive multiplier for rate limit adjustment."""
        # Default multiplier
        multiplier = 1.0

        try:
            # Check system load (would integrate with monitoring system)
            system_load_key = "system:load:average"
            async with self.redis_factory.get_connection() as redis_client:
                system_load = await redis_client.get(system_load_key)

                if system_load and float(system_load) > 0.8:
                    # Reduce limits under high load
                    multiplier *= 0.7

            # Check user's historical behavior
            user_history_key = f"user_history:{identifier}"
            async with self.redis_factory.get_connection() as redis_client:
                history = await redis_client.hgetall(user_history_key)

                if history:
                    # Reward good behavior with higher limits
                    if float(history.get("success_rate", 0)) > 0.95:
                        multiplier *= 1.2

                    # Penalize abusive behavior
                    if int(history.get("violation_count", 0)) > 5:
                        multiplier *= 0.5

        except Exception as e:
            # Fallback to default multiplier on errors
            pass

        # Ensure multiplier is within reasonable bounds
        return max(0.1, min(2.0, multiplier))


class DistributedRateLimitStrategy(RateLimitStrategy):
    """
    Distributed rate limiting strategy for multi-instance deployments.

    Uses Redis for centralized rate limiting state with consistency
    guarantees across multiple service instances.
    """

    def __init__(self, redis_factory=None):
        self.redis_factory = redis_factory or redis_connection_factory

    async def check_limit(
        self, identifier: str, limit: int, window: int, cost: int = 1
    ) -> Dict[str, Any]:
        """
        Check rate limit with distributed consistency.

        Uses Redis Lua scripts for atomic operations across
        multiple service instances.
        """
        script = """
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

        key = f"distributed:{identifier}:{window}"
        now = int(time.time())

        async with self.redis_factory.get_connection() as redis_client:
            result = await redis_client.eval(
                script,
                1,  # number of keys
                key,
                window,
                now,
                cost,
                limit,
            )

            allowed, current_count, remaining, reset_seconds, limit = result

            return {
                "allowed": bool(allowed),
                "current_count": current_count,
                "remaining_requests": remaining,
                "reset_seconds": reset_seconds,
                "limit": limit,
            }
