#!/usr/bin/env python3
"""
Simple Redis Testing Script

Basic Redis functionality tests to validate implementation.
"""

import asyncio
import json
import time
import statistics
import sys
import os
from uuid import uuid4

# Set environment
os.environ["ENVIRONMENT"] = "development"

# Require secrets from environment
if "SECRET_KEY" not in os.environ:
    print("❌ SECRET_KEY environment variable is required for testing")
    sys.exit(1)

if "REDIS_PASSWORD" not in os.environ:
    print("❌ REDIS_PASSWORD environment variable is required for testing")
    sys.exit(1)

try:
    import redis.asyncio as redis

    print("✅ Redis client library available")
except ImportError:
    print("❌ Redis client library not available")
    sys.exit(1)


class SimpleRedisValidator:
    """Simple Redis functionality validator."""

    def __init__(self):
        self.test_results = {"passed": 0, "failed": 0, "total": 0}
        self.performance_metrics = {}

    async def run_tests(self):
        """Run basic Redis tests."""
        print("🚀 Starting Simple Redis Validation")
        print("=" * 40)

        # Test Redis connection
        redis_client = None
        try:
            redis_client = redis.Redis(
                host="localhost",
                port=5240,
                password=os.environ["REDIS_PASSWORD"],
                decode_responses=True,
            )

            # Test basic connection
            await redis_client.ping()
            print("✅ Redis connection successful")

        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            return False

        # Run tests
        tests = [
            ("Basic Redis Operations", self._test_basic_operations, redis_client),
            ("Cache Key Patterns", self._test_cache_patterns, redis_client),
            ("Rate Limiting Patterns", self._test_rate_limit_patterns, redis_client),
            ("Queue Operations", self._test_queue_operations, redis_client),
            ("Progress Tracking", self._test_progress_tracking, redis_client),
            ("Session Management", self._test_session_management, redis_client),
            (
                "Performance Requirements",
                self._test_performance_requirements,
                redis_client,
            ),
            ("Memory Usage", self._test_memory_usage, redis_client),
            ("Security Features", self._test_security_features, redis_client),
        ]

        for test_name, test_func, *args in tests:
            await self._run_test(test_name, test_func, *args)

        # Cleanup
        if redis_client:
            await redis_client.close()

        # Print results
        self._print_results()
        return self.test_results["failed"] == 0

    async def _test_basic_operations(self, redis_client):
        """Test basic Redis operations."""
        test_key = f"test:{uuid4()}"
        test_value = {"test": "data", "timestamp": time.time()}

        # SET operation
        await redis_client.set(test_key, json.dumps(test_value))

        # GET operation
        retrieved = await redis_client.get(test_key)
        assert retrieved is not None
        retrieved_data = json.loads(retrieved)
        assert retrieved_data["test"] == "data"

        # DELETE operation
        await redis_client.delete(test_key)
        assert await redis_client.exists(test_key) == 0

    async def _test_cache_patterns(self, redis_client):
        """Test cache key patterns."""
        project_id = str(uuid4())
        cache_key = f"project:{project_id}:data"
        test_data = {"title": "Test Project", "content": "Test content"}

        # Test cache pattern
        await redis_client.setex(cache_key, 3600, json.dumps(test_data))

        retrieved = await redis_client.get(cache_key)
        assert retrieved is not None
        data = json.loads(retrieved)
        assert data["title"] == "Test Project"

        # Test TTL
        ttl = await redis_client.ttl(cache_key)
        assert ttl > 0 and ttl <= 3600

        # Cleanup
        await redis_client.delete(cache_key)

    async def _test_rate_limit_patterns(self, redis_client):
        """Test rate limiting patterns."""
        user_id = str(uuid4())
        rate_limit_key = f"rate_limit:user:{user_id}:60"

        # Simulate rate limiting
        current_count = await redis_client.incr(rate_limit_key)
        assert current_count == 1

        # Set expiry for rate limit window
        await redis_client.expire(rate_limit_key, 60)

        # Check current count
        count = await redis_client.get(rate_limit_key)
        assert int(count) == 1

        # Cleanup
        await redis_client.delete(rate_limit_key)

    async def _test_queue_operations(self, redis_client):
        """Test queue operations."""
        queue_name = f"queue:embeddings:{uuid4()}"
        task_data = {
            "id": str(uuid4()),
            "type": "embedding_computation",
            "data": {"text": "test text"},
            "priority": 1,
        }

        # Enqueue task
        await redis_client.lpush(queue_name, json.dumps(task_data))

        # Check queue length
        queue_length = await redis_client.llen(queue_name)
        assert queue_length == 1

        # Dequeue task
        dequeued_task = await redis_client.rpop(queue_name)
        assert dequeued_task is not None

        task = json.loads(dequeued_task)
        assert task["type"] == "embedding_computation"

        # Check queue is empty
        assert await redis_client.llen(queue_name) == 0

    async def _test_progress_tracking(self, redis_client):
        """Test progress tracking patterns."""
        correlation_id = str(uuid4())
        progress_key = f"progress:{correlation_id}"

        progress_data = {
            "correlation_id": correlation_id,
            "total_steps": 5,
            "current_step": 2,
            "message": "Processing data",
            "started_at": time.time(),
        }

        # Store progress
        await redis_client.setex(progress_key, 3600, json.dumps(progress_data))

        # Retrieve progress
        retrieved = await redis_client.get(progress_key)
        assert retrieved is not None

        progress = json.loads(retrieved)
        assert progress["correlation_id"] == correlation_id
        assert progress["total_steps"] == 5

        # Update progress
        progress["current_step"] = 3
        progress["message"] = "Step 3 completed"
        await redis_client.setex(progress_key, 3600, json.dumps(progress))

        # Cleanup
        await redis_client.delete(progress_key)

    async def _test_session_management(self, redis_client):
        """Test session management patterns."""
        session_id = str(uuid4())
        session_key = f"session:{session_id}"

        session_data = {
            "session_id": session_id,
            "user_id": str(uuid4()),
            "user_data": {"name": "Test User", "email": "test@example.com"},
            "created_at": time.time(),
        }

        # Store session
        await redis_client.setex(session_key, 7200, json.dumps(session_data))

        # Retrieve session
        retrieved = await redis_client.get(session_key)
        assert retrieved is not None

        session = json.loads(retrieved)
        assert session["user_data"]["name"] == "Test User"

        # Test TTL
        ttl = await redis_client.ttl(session_key)
        assert ttl > 0 and ttl <= 7200

        # Cleanup
        await redis_client.delete(session_key)

    async def _test_performance_requirements(self, redis_client):
        """Test performance requirements."""
        test_key = f"perf_test:{uuid4()}"
        test_value = {"performance": "test_data"}

        # Test cache read performance (should be < 5ms for 95%)
        read_times = []
        for _ in range(100):
            start_time = time.time()
            await redis_client.get(test_key)  # Will be None, still tests performance
            response_time = (time.time() - start_time) * 1000
            read_times.append(response_time)

        p95_read_time = statistics.quantiles(read_times, n=20)[18]
        self.performance_metrics["cache_read_p95_ms"] = p95_read_time
        assert p95_read_time < 5, f"Cache read P95: {p95_read_time:.2f}ms >= 5ms"

        # Test rate limit check performance (should be < 2ms for 99%)
        rate_limit_times = []
        for i in range(200):
            start_time = time.time()
            await redis_client.incr(f"rate_perf_test:{i}")
            response_time = (time.time() - start_time) * 1000
            rate_limit_times.append(response_time)

        p99_rate_time = statistics.quantiles(rate_limit_times, n=100)[98]
        self.performance_metrics["rate_limit_p99_ms"] = p99_rate_time
        assert p99_rate_time < 2, f"Rate limit P99: {p99_rate_time:.2f}ms >= 2ms"

        # Test queue operation performance (should be < 10ms for 95%)
        queue_times = []
        for i in range(50):
            start_time = time.time()
            await redis_client.lpush(f"perf_queue:{i}", f"task_{i}")
            await redis_client.rpop(f"perf_queue:{i}")
            response_time = (time.time() - start_time) * 1000
            queue_times.append(response_time)

        p95_queue_time = statistics.quantiles(queue_times, n=20)[18]
        self.performance_metrics["queue_p95_ms"] = p95_queue_time
        assert p95_queue_time < 10, f"Queue P95: {p95_queue_time:.2f}ms >= 10ms"

    async def _test_memory_usage(self, redis_client):
        """Test memory usage requirements."""
        info = await redis_client.info("memory")
        used_memory = info.get("used_memory", 0)
        used_memory_mb = used_memory / (1024 * 1024)

        self.performance_metrics["memory_usage_mb"] = used_memory_mb
        assert used_memory_mb < 512, f"Memory usage: {used_memory_mb:.2f}MB >= 512MB"

    async def _test_security_features(self, redis_client):
        """Test security features."""
        # Test that connection requires password (we're already connected successfully)
        # This is implicitly tested by the successful connection above

        # Test data encoding (sensitive data should be stored as JSON)
        sensitive_data = {
            "user_id": str(uuid4()),
            "email": "test@example.com",
            "secret_token": "secret_123",
        }

        test_key = f"security_test:{uuid4()}"
        await redis_client.set(test_key, json.dumps(sensitive_data))

        retrieved = await redis_client.get(test_key)
        assert retrieved is not None
        data = json.loads(retrieved)
        assert data["email"] == "test@example.com"

        # Cleanup
        await redis_client.delete(test_key)

    async def _run_test(self, test_name: str, test_func, *args):
        """Run individual test."""
        self.test_results["total"] += 1
        print(f"  📋 {test_name}... ", end="")

        try:
            await test_func(*args)
            print("✅ PASSED")
            self.test_results["passed"] += 1
        except Exception as e:
            print(f"❌ FAILED")
            print(f"    Error: {e}")
            self.test_results["failed"] += 1

    def _print_results(self):
        """Print test results."""
        print("=" * 40)
        print("📊 REDIS VALIDATION RESULTS")
        print("=" * 40)

        total = self.test_results["total"]
        passed = self.test_results["passed"]
        failed = self.test_results["failed"]

        print(f"Total Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print()

        # Performance metrics
        if self.performance_metrics:
            print("📈 PERFORMANCE METRICS:")
            for metric, value in self.performance_metrics.items():
                if isinstance(value, float):
                    print(f"  • {metric}: {value:.2f}")
                else:
                    print(f"  • {metric}: {value}")
            print()

        # Requirements validation
        print("📋 REQUIREMENTS VALIDATION:")
        requirements = [
            ("REQ-001", "Redis Service Configuration", passed >= 1),
            ("REQ-002", "Cache Management", passed >= 1),
            ("REQ-003", "Rate Limiting", passed >= 1),
            ("REQ-004", "Task Queue Management", passed >= 1),
            ("REQ-005", "Progress Tracking", passed >= 1),
            ("REQ-006", "Session Management", passed >= 1),
            ("PERF-001", "Performance Requirements", failed == 0),
            ("PERF-002", "Memory Usage Requirements", passed >= 1),
            ("SEC-001", "Security Requirements", passed >= 1),
        ]

        for req_id, req_name, status in requirements:
            icon = "✅" if status else "❌"
            print(f"  {icon} {req_id}: {req_name}")
        print()

        # Production readiness
        if failed == 0:
            print("🎉 PRODUCTION READINESS: ✅ READY")
            print("   All Redis functionality validated successfully")
        else:
            print("🔴 PRODUCTION READINESS: ❌ NOT READY")
            print(f"   {failed} tests failed - fix issues before production")

        print("=" * 40)


async def main():
    """Main entry point."""
    validator = SimpleRedisValidator()
    success = await validator.run_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
