#!/usr/bin/env python3
"""
Realistic Redis Performance Testing

Tests Redis under realistic workloads with proper optimization.
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
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-change-in-production"
os.environ["REDIS_PASSWORD"] = "jeex_redis_secure_password_change_in_production"

try:
    import redis.asyncio as redis

    print("✅ Redis client library available")
except ImportError:
    print("❌ Redis client library not available")
    sys.exit(1)


class RealisticRedisValidator:
    """Realistic Redis performance validator."""

    def __init__(self):
        self.test_results = {"passed": 0, "failed": 0, "total": 0}
        self.performance_metrics = {}

    async def run_tests(self):
        """Run realistic Redis tests."""
        print("🚀 Starting Realistic Redis Performance Testing")
        print("=" * 50)

        # Test Redis connection with pipeline optimization
        redis_client = None
        try:
            redis_client = redis.Redis(
                host="localhost",
                port=5240,
                password="jeex_redis_secure_password_change_in_production",
                decode_responses=True,
                # Connection pooling for better performance
                max_connections=20,
                retry_on_timeout=True,
            )

            # Test basic connection
            await redis_client.ping()
            print("✅ Redis connection successful with optimized settings")

        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            return False

        # Warm up Redis
        print("🔥 Warming up Redis...")
        await self._warmup_redis(redis_client)

        # Run realistic tests
        tests = [
            (
                "Optimized Cache Read Performance",
                self._test_optimized_cache_reads,
                redis_client,
            ),
            (
                "Optimized Rate Limit Performance",
                self._test_optimized_rate_limits,
                redis_client,
            ),
            (
                "Optimized Queue Performance",
                self._test_optimized_queue_operations,
                redis_client,
            ),
            (
                "Progress Update Performance",
                self._test_progress_performance,
                redis_client,
            ),
            ("Pipeline Performance", self._test_pipeline_performance, redis_client),
            ("Concurrent Operations", self._test_concurrent_operations, redis_client),
            ("Memory Efficiency", self._test_memory_efficiency, redis_client),
        ]

        for test_name, test_func, *args in tests:
            await self._run_test(test_name, test_func, *args)

        # Cleanup
        if redis_client:
            await redis_client.aclose()

        # Print results
        self._print_results()
        return self.test_results["failed"] == 0

    async def _warmup_redis(self, redis_client):
        """Warm up Redis for realistic performance."""
        # Create some test data
        for i in range(50):
            key = f"warmup:{i}"
            await redis_client.setex(key, 60, f"warmup_data_{i}")
            await redis_client.get(key)  # Cache the data
            await redis_client.delete(key)

    async def _test_optimized_cache_reads(self, redis_client):
        """Test optimized cache read performance."""
        print("    🔧 Setting up cache data...")
        project_id = str(uuid4())

        # Pre-populate cache with realistic data
        cache_keys = []
        for i in range(100):
            key = f"project:{project_id}:data:{i}"
            cache_data = {
                "id": i,
                "title": f"Document {i}",
                "content": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                * 10,
                "metadata": {"type": "document", "size": 1024},
            }
            await redis_client.setex(key, 3600, json.dumps(cache_data))
            cache_keys.append(key)

        print("    ⚡ Measuring cache read performance...")
        read_times = []

        # Perform realistic cache reads
        for i in range(1000):
            key = cache_keys[i % len(cache_keys)]
            start_time = time.perf_counter()
            result = await redis_client.get(key)
            end_time = time.perf_counter()

            response_time = (end_time - start_time) * 1000
            read_times.append(response_time)

            # Verify data integrity for 10% of reads
            if i % 100 == 0 and result:
                data = json.loads(result)
                assert data["id"] is not None

        # Calculate statistics
        avg_time = statistics.mean(read_times)
        p95_time = statistics.quantiles(read_times, n=20)[18]
        p99_time = statistics.quantiles(read_times, n=100)[98]

        self.performance_metrics["cache_read_avg_ms"] = avg_time
        self.performance_metrics["cache_read_p95_ms"] = p95_time
        self.performance_metrics["cache_read_p99_ms"] = p99_time

        print(
            f"    📊 Cache Read - Avg: {avg_time:.2f}ms, P95: {p95_time:.2f}ms, P99: {p99_time:.2f}ms"
        )

        # Requirements: 95% under 5ms
        assert p95_time < 5, f"Cache read P95: {p95_time:.2f}ms >= 5ms"

        # Cleanup
        for key in cache_keys:
            await redis_client.delete(key)

    async def _test_optimized_rate_limits(self, redis_client):
        """Test optimized rate limit performance."""
        print("    🔧 Setting up rate limit data...")

        # Use different rate limit patterns
        rate_patterns = [
            ("user", f"rate_limit:user:{{user_id}}:60"),
            ("project", f"rate_limit:project:{{project_id}}:3600"),
            ("ip", f"rate_limit:ip:{{ip}}:300"),
        ]

        print("    ⚡ Measuring rate limit performance...")
        rate_times = []

        for pattern_type, pattern_template in rate_patterns:
            for i in range(300):  # 300 iterations per pattern
                identifier = (
                    f"test_{pattern_type}_{i % 10}"  # Simulate 10 different identifiers
                )
                key = pattern_template.format(
                    user_id=identifier, project_id=identifier, ip=identifier
                )

                start_time = time.perf_counter()

                # Simulate rate limit check using optimized operations
                pipe = redis_client.pipeline()
                pipe.incr(key)
                pipe.expire(key, 60)  # Set expiry in same pipeline
                results = await pipe.execute()

                end_time = time.perf_counter()
                response_time = (end_time - start_time) * 1000
                rate_times.append(response_time)

                # Verify operation success
                assert results[0] > 0  # INCR result should be positive

        # Calculate statistics
        avg_time = statistics.mean(rate_times)
        p95_time = statistics.quantiles(rate_times, n=20)[18]
        p99_time = statistics.quantiles(rate_times, n=100)[98]

        self.performance_metrics["rate_limit_avg_ms"] = avg_time
        self.performance_metrics["rate_limit_p95_ms"] = p95_time
        self.performance_metrics["rate_limit_p99_ms"] = p99_time

        print(
            f"    📊 Rate Limit - Avg: {avg_time:.2f}ms, P95: {p95_time:.2f}ms, P99: {p99_time:.2f}ms"
        )

        # Requirements: 99% under 2ms
        assert p99_time < 2, f"Rate limit P99: {p99_time:.2f}ms >= 2ms"

        # Cleanup rate limit keys
        for pattern_type, pattern_template in rate_patterns:
            for i in range(10):
                identifier = f"test_{pattern_type}_{i}"
                key = pattern_template.format(
                    user_id=identifier, project_id=identifier, ip=identifier
                )
                await redis_client.delete(key)

    async def _test_optimized_queue_operations(self, redis_client):
        """Test optimized queue operations."""
        print("    🔧 Setting up queue data...")
        queue_name = f"queue:test:{uuid4()}"

        # Pre-create some tasks
        tasks = []
        for i in range(50):
            task = {
                "id": str(uuid4()),
                "type": "test_task",
                "data": {"payload": f"test_data_{i}", "size": 1024},
                "priority": i % 3,
                "created_at": time.time(),
            }
            tasks.append(task)

        print("    ⚡ Measuring queue performance...")
        queue_times = []

        # Test enqueue/dequeue performance
        for i in range(200):
            task = tasks[i % len(tasks)]

            start_time = time.perf_counter()

            # Use pipeline for atomic enqueue
            pipe = redis_client.pipeline()
            pipe.lpush(queue_name, json.dumps(task))
            pipe.llen(queue_name)  # Check queue length
            enqueue_results = await pipe.execute()

            # Dequeue if queue has items
            if enqueue_results[1] > 0:
                dequeued_task = await redis_client.rpop(queue_name)
                assert dequeued_task is not None

            end_time = time.perf_counter()
            response_time = (end_time - start_time) * 1000
            queue_times.append(response_time)

        # Calculate statistics
        avg_time = statistics.mean(queue_times)
        p95_time = statistics.quantiles(queue_times, n=20)[18]
        p99_time = statistics.quantiles(queue_times, n=100)[98]

        self.performance_metrics["queue_avg_ms"] = avg_time
        self.performance_metrics["queue_p95_ms"] = p95_time
        self.performance_metrics["queue_p99_ms"] = p99_time

        print(
            f"    📊 Queue Ops - Avg: {avg_time:.2f}ms, P95: {p95_time:.2f}ms, P99: {p99_time:.2f}ms"
        )

        # Requirements: 95% under 10ms
        assert p95_time < 10, f"Queue P95: {p95_time:.2f}ms >= 10ms"

        # Cleanup
        await redis_client.delete(queue_name)

    async def _test_progress_performance(self, redis_client):
        """Test progress update performance."""
        print("    🔧 Setting up progress tracking...")
        correlation_id = str(uuid4())
        progress_key = f"progress:{correlation_id}"

        # Initialize progress
        initial_progress = {
            "correlation_id": correlation_id,
            "total_steps": 10,
            "current_step": 0,
            "message": "Starting operation",
            "started_at": time.time(),
        }
        await redis_client.setex(progress_key, 3600, json.dumps(initial_progress))

        print("    ⚡ Measuring progress update performance...")
        progress_times = []

        # Test progress update performance
        for i in range(100):
            start_time = time.perf_counter()

            # Update progress efficiently
            progress_data = {
                "correlation_id": correlation_id,
                "total_steps": 10,
                "current_step": i % 10 + 1,
                "message": f"Step {i % 10 + 1} completed",
                "updated_at": time.time(),
            }

            await redis_client.setex(progress_key, 3600, json.dumps(progress_data))

            end_time = time.perf_counter()
            response_time = (end_time - start_time) * 1000
            progress_times.append(response_time)

        # Calculate statistics
        avg_time = statistics.mean(progress_times)
        p95_time = statistics.quantiles(progress_times, n=20)[18]
        p99_time = statistics.quantiles(progress_times, n=100)[98]

        self.performance_metrics["progress_avg_ms"] = avg_time
        self.performance_metrics["progress_p95_ms"] = p95_time
        self.performance_metrics["progress_p99_ms"] = p99_time

        print(
            f"    📊 Progress Updates - Avg: {avg_time:.2f}ms, P95: {p95_time:.2f}ms, P99: {p99_time:.2f}ms"
        )

        # Requirements: 95% under 3ms
        assert p95_time < 3, f"Progress P95: {p95_time:.2f}ms >= 3ms"

        # Cleanup
        await redis_client.delete(progress_key)

    async def _test_pipeline_performance(self, redis_client):
        """Test Redis pipeline performance."""
        print("    ⚡ Measuring pipeline performance...")

        pipeline_times = []

        # Test batch operations with pipeline
        for i in range(50):
            start_time = time.perf_counter()

            # Use pipeline for multiple operations
            pipe = redis_client.pipeline()
            for j in range(10):
                key = f"pipeline_test:{i}_{j}"
                pipe.setex(key, 60, f"data_{i}_{j}")
                pipe.get(key)

            results = await pipe.execute()

            end_time = time.perf_counter()
            response_time = (end_time - start_time) * 1000
            pipeline_times.append(response_time)

            # Verify results
            assert len(results) == 20  # 10 SET + 10 GET operations

            # Cleanup
            for j in range(10):
                key = f"pipeline_test:{i}_{j}"
                await redis_client.delete(key)

        avg_pipeline_time = statistics.mean(pipeline_times)
        self.performance_metrics["pipeline_avg_ms"] = avg_pipeline_time

        print(f"    📊 Pipeline (20 ops) - Avg: {avg_pipeline_time:.2f}ms")

        # Pipeline should be significantly faster than individual operations
        assert avg_pipeline_time < 50, f"Pipeline too slow: {avg_pipeline_time:.2f}ms"

    async def _test_concurrent_operations(self, redis_client):
        """Test concurrent Redis operations."""
        print("    🔄 Testing concurrent operations...")

        async def worker(worker_id: int):
            """Worker function for concurrent testing."""
            worker_times = []
            for i in range(20):
                key = f"concurrent:{worker_id}:{i}"

                start_time = time.perf_counter()
                await redis_client.setex(key, 60, f"worker_{worker_id}_data_{i}")
                result = await redis_client.get(key)
                await redis_client.delete(key)
                end_time = time.perf_counter()

                worker_times.append((end_time - start_time) * 1000)

                assert result is not None

            return worker_times

        # Run 5 concurrent workers
        tasks = [worker(i) for i in range(5)]
        worker_results = await asyncio.gather(*tasks)

        # Flatten all timing results
        all_times = []
        for worker_times in worker_results:
            all_times.extend(worker_times)

        avg_time = statistics.mean(all_times)
        p95_time = statistics.quantiles(all_times, n=20)[18]

        self.performance_metrics["concurrent_avg_ms"] = avg_time
        self.performance_metrics["concurrent_p95_ms"] = p95_time

        print(f"    📊 Concurrent Ops - Avg: {avg_time:.2f}ms, P95: {p95_time:.2f}ms")

        # Concurrent operations should still be reasonably fast
        assert p95_time < 20, f"Concurrent P95 too slow: {p95_time:.2f}ms"

    async def _test_memory_efficiency(self, redis_client):
        """Test Redis memory efficiency."""
        print("    🧠 Analyzing memory usage...")

        # Get initial memory usage
        initial_info = await redis_client.info("memory")
        initial_memory = initial_info.get("used_memory", 0)

        # Create test data
        test_data = []
        for i in range(100):
            key = f"memory_test:{i}"
            data = {
                "id": i,
                "title": f"Document {i}",
                "content": "Test content " * 50,  # Larger content
                "metadata": {"tags": [f"tag_{j}" for j in range(5)], "size": 2048},
            }
            await redis_client.setex(key, 3600, json.dumps(data))
            test_data.append(key)

        # Get memory usage after data creation
        final_info = await redis_client.info("memory")
        final_memory = final_info.get("used_memory", 0)

        memory_increase = (final_memory - initial_memory) / (1024 * 1024)  # MB
        memory_per_item = memory_increase / len(test_data) * 1024  # KB per item

        self.performance_metrics["memory_increase_mb"] = memory_increase
        self.performance_metrics["memory_per_item_kb"] = memory_per_item

        print(
            f"    📊 Memory - Increase: {memory_increase:.2f}MB, Per item: {memory_per_item:.2f}KB"
        )

        # Memory usage should be reasonable
        assert memory_increase < 50, (
            f"Memory increase too high: {memory_increase:.2f}MB"
        )
        assert memory_per_item < 10, (
            f"Memory per item too high: {memory_per_item:.2f}KB"
        )

        # Cleanup
        for key in test_data:
            await redis_client.delete(key)

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
        """Print comprehensive test results."""
        print("=" * 50)
        print("📊 REALISTIC REDIS PERFORMANCE RESULTS")
        print("=" * 50)

        total = self.test_results["total"]
        passed = self.test_results["passed"]
        failed = self.test_results["failed"]

        print(f"Total Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print()

        # Performance metrics
        if self.performance_metrics:
            print("📈 DETAILED PERFORMANCE METRICS:")
            print("  🔄 Cache Operations:")
            print(
                f"    • Average: {self.performance_metrics.get('cache_read_avg_ms', 0):.2f}ms"
            )
            print(
                f"    • P95: {self.performance_metrics.get('cache_read_p95_ms', 0):.2f}ms (requirement: <5ms)"
            )
            print(
                f"    • P99: {self.performance_metrics.get('cache_read_p99_ms', 0):.2f}ms"
            )

            print("  ⚡ Rate Limiting:")
            print(
                f"    • Average: {self.performance_metrics.get('rate_limit_avg_ms', 0):.2f}ms"
            )
            print(
                f"    • P95: {self.performance_metrics.get('rate_limit_p95_ms', 0):.2f}ms"
            )
            print(
                f"    • P99: {self.performance_metrics.get('rate_limit_p99_ms', 0):.2f}ms (requirement: <2ms)"
            )

            print("  📋 Queue Operations:")
            print(
                f"    • Average: {self.performance_metrics.get('queue_avg_ms', 0):.2f}ms"
            )
            print(
                f"    • P95: {self.performance_metrics.get('queue_p95_ms', 0):.2f}ms (requirement: <10ms)"
            )
            print(f"    • P99: {self.performance_metrics.get('queue_p99_ms', 0):.2f}ms")

            print("  📊 Progress Updates:")
            print(
                f"    • Average: {self.performance_metrics.get('progress_avg_ms', 0):.2f}ms"
            )
            print(
                f"    • P95: {self.performance_metrics.get('progress_p95_ms', 0):.2f}ms (requirement: <3ms)"
            )
            print(
                f"    • P99: {self.performance_metrics.get('progress_p99_ms', 0):.2f}ms"
            )

            print("  🚀 Advanced Metrics:")
            print(
                f"    • Pipeline (20 ops): {self.performance_metrics.get('pipeline_avg_ms', 0):.2f}ms"
            )
            print(
                f"    • Concurrent P95: {self.performance_metrics.get('concurrent_p95_ms', 0):.2f}ms"
            )
            print(
                f"    • Memory increase: {self.performance_metrics.get('memory_increase_mb', 0):.2f}MB"
            )
            print(
                f"    • Memory per item: {self.performance_metrics.get('memory_per_item_kb', 0):.2f}KB"
            )
            print()

        # Requirements validation
        print("📋 REQUIREMENTS VALIDATION:")

        cache_p95 = self.performance_metrics.get("cache_read_p95_ms", float("inf"))
        rate_p99 = self.performance_metrics.get("rate_limit_p99_ms", float("inf"))
        queue_p95 = self.performance_metrics.get("queue_p95_ms", float("inf"))
        progress_p95 = self.performance_metrics.get("progress_p95_ms", float("inf"))

        requirements = [
            ("Cache Reads < 5ms (95%)", cache_p95 < 5, f"{cache_p95:.2f}ms"),
            ("Rate Limits < 2ms (99%)", rate_p99 < 2, f"{rate_p99:.2f}ms"),
            ("Queue Ops < 10ms (95%)", queue_p95 < 10, f"{queue_p95:.2f}ms"),
            ("Progress < 3ms (95%)", progress_p95 < 3, f"{progress_p95:.2f}ms"),
        ]

        all_passed = True
        for req_name, passed, actual in requirements:
            icon = "✅" if passed else "❌"
            print(f"  {icon} {req_name}: {actual}")
            if not passed:
                all_passed = False
        print()

        # Production readiness
        if failed == 0 and all_passed:
            print("🎉 PRODUCTION READINESS: ✅ READY")
            print("   All performance requirements met!")
            print("   Redis implementation is production-ready")
        else:
            print("🔴 PRODUCTION READINESS: ❌ NOT READY")
            if failed > 0:
                print(f"   {failed} tests failed")
            if not all_passed:
                print("   Performance requirements not met")
            print("   Address issues before production deployment")

        print("=" * 50)


async def main():
    """Main entry point."""
    validator = RealisticRedisValidator()
    success = await validator.run_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
