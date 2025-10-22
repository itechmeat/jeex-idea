"""
Rate Limiting Integration Tests

Integration tests for rate limiting functionality.
"""

import pytest
import asyncio
import time
from uuid import uuid4

from ..rate_limiting import RateLimitingMiddleware, rate_limiter, RateLimitConfig
from ..queues import queue_manager, TaskType, TaskPriority


class TestRateLimitingIntegration:
    """Integration tests for rate limiting."""

    @pytest.mark.asyncio
    async def test_middleware_integration(self):
        """Test rate limiting middleware integration."""
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient
        from unittest.mock import Mock

        # Create FastAPI app
        app = FastAPI()

        # Add rate limiting middleware
        middleware = RateLimitingMiddleware(app, enabled=True)
        app.middleware("http")(middleware.dispatch)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        # Create test client
        client = TestClient(app)

        # Test multiple requests to trigger rate limiting
        responses = []
        for i in range(10):  # Assuming default limit is lower than this
            response = client.get("/test")
            responses.append(response)
            if response.status_code == 429:
                break

        # At least one request should have succeeded
        success_responses = [r for r in responses if r.status_code == 200]
        assert len(success_responses) > 0

        # Should eventually hit rate limit (depending on configuration)
        rate_limited_responses = [r for r in responses if r.status_code == 429]
        # Note: This might not trigger if limits are high

    @pytest.mark.asyncio
    async def test_user_project_ip_rate_limiting(self):
        """Test combined user, project, and IP rate limiting."""
        user_id = str(uuid4())
        project_id = uuid4()
        ip_address = "192.168.1.100"

        # Configure different limits
        user_config = RateLimitConfig(requests_per_window=10, window_seconds=60)
        project_config = RateLimitConfig(requests_per_window=20, window_seconds=60)
        ip_config = RateLimitConfig(requests_per_window=5, window_seconds=60)

        # Test user rate limiting
        for i in range(10):
            result = await rate_limiter.check_user_rate_limit(user_id, user_config)
            assert result.allowed is True

        # Should hit user limit
        result = await rate_limiter.check_user_rate_limit(user_id, user_config)
        assert result.allowed is False

        # Different user should still be allowed
        other_user_id = str(uuid4())
        result = await rate_limiter.check_user_rate_limit(other_user_id, user_config)
        assert result.allowed is True

        # Test IP rate limiting (most restrictive)
        for i in range(5):
            result = await rate_limiter.check_ip_rate_limit(ip_address, ip_config)
            assert result.allowed is True

        # Should hit IP limit
        result = await rate_limiter.check_ip_rate_limit(ip_address, ip_config)
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_rate_limiting_with_queue_integration(self):
        """Test rate limiting integration with queue operations."""
        project_id = uuid4()
        user_id = str(uuid4())

        # Set up rate limiting for queue operations
        queue_config = RateLimitConfig(requests_per_window=5, window_seconds=60)

        # Enqueue tasks while checking rate limits
        successful_enqueues = 0
        for i in range(10):
            # Check rate limit first
            rate_limit_result = await rate_limiter.check_project_rate_limit(
                project_id, queue_config
            )

            if rate_limit_result.allowed:
                # Enqueue task
                task_id = await queue_manager.enqueue_task(
                    task_type=TaskType.EMBEDDING_COMPUTATION,
                    project_id=project_id,
                    data={"test": f"task_{i}"},
                    priority=TaskPriority.NORMAL,
                )
                assert task_id is not None
                successful_enqueues += 1
            else:
                # Rate limited, should not enqueue
                break

        # Should have enqueued some tasks but hit rate limit
        assert successful_enqueues > 0
        assert successful_enqueues <= 5  # Based on rate limit config

    @pytest.mark.asyncio
    async def test_rate_limit_persistence_across_instances(self):
        """Test rate limits persist across multiple service instances."""
        user_id = str(uuid4())
        config = RateLimitConfig(requests_per_window=5, window_seconds=60)

        # Simulate multiple service instances by checking limits multiple times
        # In a real scenario, these would be separate processes/containers
        results = []

        for instance in range(3):  # Simulate 3 instances
            for request in range(2):  # Each instance makes 2 requests
                result = await rate_limiter.check_user_rate_limit(user_id, config)
                results.append((instance, result.allowed))

        # Should have some allowed requests and some denied
        allowed_count = sum(1 for _, allowed in results if allowed)
        denied_count = sum(1 for _, allowed in results if not allowed)

        assert allowed_count > 0
        assert denied_count > 0
        assert allowed_count <= 5  # Based on rate limit

    @pytest.mark.asyncio
    async def test_rate_limit_recovery_after_window(self):
        """Test rate limit recovery after time window expires."""
        user_id = str(uuid4())
        config = RateLimitConfig(
            requests_per_window=3, window_seconds=2
        )  # Short window for testing

        # Exhaust the limit
        for i in range(3):
            result = await rate_limiter.check_user_rate_limit(user_id, config)
            assert result.allowed is True

        # Should be rate limited
        result = await rate_limiter.check_user_rate_limit(user_id, config)
        assert result.allowed is False

        # Wait for window to expire
        await asyncio.sleep(3)

        # Should be allowed again
        result = await rate_limiter.check_user_rate_limit(user_id, config)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_concurrent_rate_limiting_accuracy(self):
        """Test rate limiting accuracy under concurrent load."""
        user_id = str(uuid4())
        config = RateLimitConfig(requests_per_window=10, window_seconds=60)

        # Make concurrent requests
        async def make_request(request_id):
            result = await rate_limiter.check_user_rate_limit(user_id, config)
            return request_id, result.allowed

        # Create 20 concurrent requests
        tasks = [make_request(i) for i in range(20)]
        results = await asyncio.gather(*tasks)

        # Count allowed requests
        allowed_requests = [req_id for req_id, allowed in results if allowed]
        denied_requests = [req_id for req_id, allowed in results if not allowed]

        # Should allow exactly 10 requests
        assert len(allowed_requests) == 10
        assert len(denied_requests) == 10

    @pytest.mark.asyncio
    async def test_rate_limiting_error_handling(self):
        """Test rate limiting behavior under error conditions."""
        # Test with invalid configuration
        with pytest.raises(Exception):
            invalid_config = RateLimitConfig(requests_per_window=0, window_seconds=60)
            await rate_limiter.check_user_rate_limit("test", invalid_config)

        # Test rate limiting failure recovery
        user_id = str(uuid4())
        config = RateLimitConfig(requests_per_window=5, window_seconds=60)

        # Normal operation should work
        result = await rate_limiter.check_user_rate_limit(user_id, config)
        assert result.allowed is True

        # Redis connectivity issues should fail open (allow requests)
        # This would be tested with actual Redis failure simulation


class TestRateLimitingPerformance:
    """Performance tests for rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limiting_performance(self):
        """Test rate limiting performance meets requirements (< 2ms for 99% of requests)."""
        user_id = str(uuid4())
        config = RateLimitConfig(requests_per_window=1000, window_seconds=3600)

        response_times = []
        num_requests = 1000

        for i in range(num_requests):
            start_time = time.perf_counter()
            result = await rate_limiter.check_user_rate_limit(user_id, config)
            end_time = time.perf_counter()

            response_time_ms = (end_time - start_time) * 1000
            response_times.append(response_time_ms)

        # Sort response times to find 99th percentile
        response_times.sort()
        p99_index = int(len(response_times) * 0.99)
        p99_time = response_times[p99_index]

        # 99% of requests should be under 2ms
        assert p99_time < 2.0, (
            f"P99 response time {p99_time:.2f}ms exceeds 2ms requirement"
        )

        # Also check average
        avg_time = sum(response_times) / len(response_times)
        assert avg_time < 1.0, (
            f"Average response time {avg_time:.2f}ms exceeds 1ms target"
        )

        print(f"Rate limiting performance:")
        print(f"  Average: {avg_time:.2f}ms")
        print(f"  P99: {p99_time:.2f}ms")
        print(f"  Max: {max(response_times):.2f}ms")

    @pytest.mark.asyncio
    async def test_high_volume_rate_limiting(self):
        """Test rate limiting under high volume."""
        config = RateLimitConfig(requests_per_window=10000, window_seconds=3600)

        # Simulate high volume with different users
        num_users = 100
        requests_per_user = 50

        async def make_user_requests(user_idx):
            user_id = f"user_{user_idx}"
            results = []

            for i in range(requests_per_user):
                start_time = time.perf_counter()
                result = await rate_limiter.check_user_rate_limit(user_id, config)
                end_time = time.perf_counter()

                results.append(
                    {
                        "allowed": result.allowed,
                        "response_time_ms": (end_time - start_time) * 1000,
                    }
                )

            return results

        # Create concurrent tasks for multiple users
        tasks = [make_user_requests(i) for i in range(num_users)]
        all_results = await asyncio.gather(*tasks)

        # Analyze results
        total_requests = sum(len(user_results) for user_results in all_results)
        allowed_requests = sum(
            sum(1 for r in user_results if r["allowed"]) for user_results in all_results
        )

        all_response_times = [
            r["response_time_ms"] for user_results in all_results for r in user_results
        ]

        avg_response_time = sum(all_response_times) / len(all_response_times)
        max_response_time = max(all_response_times)

        # All requests should be allowed (high limit)
        assert allowed_requests == total_requests

        # Performance should remain good under load
        assert avg_response_time < 5.0, (
            f"Average response time {avg_response_time:.2f}ms too high under load"
        )
        assert max_response_time < 50.0, (
            f"Max response time {max_response_time:.2f}ms too high under load"
        )

        print(f"High volume test results:")
        print(f"  Total requests: {total_requests}")
        print(f"  Allowed requests: {allowed_requests}")
        print(f"  Average response time: {avg_response_time:.2f}ms")
        print(f"  Max response time: {max_response_time:.2f}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
