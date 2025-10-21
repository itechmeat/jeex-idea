"""
Rate Limiter Tests

Unit tests for rate limiting functionality.
"""

import pytest
import time
import asyncio
from uuid import uuid4

from ...rate_limiter import RateLimiter, RateLimitConfig, RateLimitResult


class TestRateLimiter:
    """Test cases for RateLimiter class."""

    @pytest.fixture
    async def rate_limiter(self):
        """Create rate limiter instance for testing."""
        limiter = RateLimiter()
        await limiter.initialize()
        return limiter

    @pytest.mark.asyncio
    async def test_sliding_window_rate_limiting(self, rate_limiter):
        """Test sliding window rate limiting algorithm."""
        user_id = str(uuid4())
        config = RateLimitConfig(requests_per_window=5, window_seconds=10)

        # First 5 requests should be allowed
        for i in range(5):
            result = await rate_limiter.check_user_rate_limit(user_id, config)
            assert result.allowed is True
            assert result.remaining_requests == 4 - i
            assert result.current_count == i + 1

        # 6th request should be denied
        result = await rate_limiter.check_user_rate_limit(user_id, config)
        assert result.allowed is False
        assert result.remaining_requests == 0
        assert result.retry_after is not None

    @pytest.mark.asyncio
    async def test_project_rate_limiting(self, rate_limiter):
        """Test project-level rate limiting."""
        project_id = uuid4()
        config = RateLimitConfig(requests_per_window=10, window_seconds=60)

        # Should allow requests within limit
        result = await rate_limiter.check_project_rate_limit(project_id, config)
        assert result.allowed is True
        assert result.identifier == str(project_id)
        assert result.limit_type == "project"

    @pytest.mark.asyncio
    async def test_ip_rate_limiting(self, rate_limiter):
        """Test IP-based rate limiting."""
        ip_address = "192.168.1.1"
        config = RateLimitConfig(requests_per_window=3, window_seconds=30)

        # Should allow requests within limit
        for i in range(3):
            result = await rate_limiter.check_ip_rate_limit(ip_address, config)
            assert result.allowed is True

        # Should exceed limit
        result = await rate_limiter.check_ip_rate_limit(ip_address, config)
        assert result.allowed is False
        assert result.identifier == ip_address
        assert result.limit_type == "ip"

    @pytest.mark.asyncio
    async def test_request_cost(self, rate_limiter):
        """Test rate limiting with request cost."""
        user_id = str(uuid4())
        config = RateLimitConfig(requests_per_window=10, window_seconds=60)

        # Request with cost 5 should consume 5 tokens
        result = await rate_limiter.check_user_rate_limit(user_id, config, cost=5)
        assert result.allowed is True
        assert result.remaining_requests == 5

        # Request with cost 6 should exceed limit
        result = await rate_limiter.check_user_rate_limit(user_id, config, cost=6)
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_rate_limit_status_without_consumption(self, rate_limiter):
        """Test getting rate limit status without consuming tokens."""
        user_id = str(uuid4())
        config = RateLimitConfig(requests_per_window=5, window_seconds=60)

        # Get initial status
        status = await rate_limiter.get_rate_limit_status(user_id, "user", config)
        assert status.allowed is True
        assert status.current_count == 0

        # Make a request
        await rate_limiter.check_user_rate_limit(user_id, config)

        # Check status again
        status = await rate_limiter.get_rate_limit_status(user_id, "user", config)
        assert status.current_count == 1

    @pytest.mark.asyncio
    async def test_reset_rate_limit(self, rate_limiter):
        """Test resetting rate limit."""
        user_id = str(uuid4())
        config = RateLimitConfig(requests_per_window=5, window_seconds=60)

        # Exhaust limit
        for i in range(5):
            await rate_limiter.check_user_rate_limit(user_id, config)

        # Should be blocked
        result = await rate_limiter.check_user_rate_limit(user_id, config)
        assert result.allowed is False

        # Reset limit
        success = await rate_limiter.reset_rate_limit(user_id, "user", 60)
        assert success is True

        # Should be allowed again
        result = await rate_limiter.check_user_rate_limit(user_id, config)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_rate_limit_metrics(self, rate_limiter):
        """Test getting rate limit metrics."""
        user_id = str(uuid4())
        config = RateLimitConfig(requests_per_window=10, window_seconds=60)

        # Make some requests
        for i in range(3):
            await rate_limiter.check_user_rate_limit(user_id, config)

        # Get metrics
        metrics = await rate_limiter.get_rate_limit_metrics()
        assert "total_active_limits" in metrics
        assert "limits_by_type" in metrics
        assert metrics["total_active_limits"] >= 1

    @pytest.mark.asyncio
    async def test_concurrent_rate_limiting(self, rate_limiter):
        """Test concurrent rate limiting requests."""
        user_id = str(uuid4())
        config = RateLimitConfig(requests_per_window=10, window_seconds=60)

        # Make concurrent requests
        tasks = []
        for i in range(10):
            task = asyncio.create_task(
                rate_limiter.check_user_rate_limit(user_id, config)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All should be allowed (within limit)
        allowed_count = sum(1 for result in results if result.allowed)
        assert allowed_count == 10

        # Additional request should be blocked
        result = await rate_limiter.check_user_rate_limit(user_id, config)
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_different_identifiers_isolated(self, rate_limiter):
        """Test that different identifiers are isolated."""
        user1_id = str(uuid4())
        user2_id = str(uuid4())
        config = RateLimitConfig(requests_per_window=3, window_seconds=60)

        # User 1 exhausts limit
        for i in range(3):
            result = await rate_limiter.check_user_rate_limit(user1_id, config)
            assert result.allowed is True

        # User 1 should be blocked
        result = await rate_limiter.check_user_rate_limit(user1_id, config)
        assert result.allowed is False

        # User 2 should still be allowed (different identifier)
        result = await rate_limiter.check_user_rate_limit(user2_id, config)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_rate_limit_config_validation(self):
        """Test rate limit configuration validation."""
        # Valid configuration
        config = RateLimitConfig(requests_per_window=10, window_seconds=60)
        assert config.requests_per_window == 10
        assert config.window_seconds == 60

        # Test with burst size
        config = RateLimitConfig(
            requests_per_window=10, window_seconds=60, burst_size=15
        )
        assert config.burst_size == 15


if __name__ == "__main__":
    pytest.main([__file__])
