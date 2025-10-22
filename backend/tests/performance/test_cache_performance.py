"""
Performance tests for Cache operations.

Validates that cache operations meet performance requirements:
- Cache read operations: 95% under 5ms
- Rate limit checks: 99% under 2ms
- Progress updates: 95% under 3ms
"""

import asyncio
import statistics
import time
from datetime import datetime
from typing import List, Dict, Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.cache.cache_manager import CacheManager
from app.domain.cache.value_objects import TTL, RateLimitWindow, RateLimitConfig


class TestCachePerformance:
    """Performance tests for cache operations."""

    @pytest.fixture
    def cache_manager(self):
        """Create cache manager instance."""
        manager = CacheManager()
        # Mock repository operations to isolate performance testing
        manager.repository = AsyncMock()
        manager.repository.project_cache.find_by_project_id = AsyncMock()
        manager.repository.project_cache.save = AsyncMock()
        manager.repository.progress.update_progress = AsyncMock()
        return manager

    @pytest.fixture
    def sample_project_data(self):
        """Sample project data for testing."""
        return {
            "id": str(uuid4()),
            "name": "Test Project",
            "description": "Test Description",
            "documents": [f"doc_{i}" for i in range(10)],
            "metadata": {"created_by": "test_user", "tags": ["test", "performance"]},
        }

    def _measure_execution_time(self, func, *args, **kwargs) -> float:
        """Measure execution time of a function in milliseconds."""
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            # For async functions, we need to handle differently
            raise ValueError("Use _measure_async_execution_time for async functions")
        end_time = time.perf_counter()
        return (end_time - start_time) * 1000

    async def _measure_async_execution_time(self, coro) -> tuple:
        """Measure execution time of async function in milliseconds."""
        start_time = time.perf_counter()
        result = await coro
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000
        return result, execution_time_ms

    async def _run_performance_test(
        self,
        operation,
        iterations: int = 1000,
        p95_threshold_ms: float = 5.0,
        p99_threshold_ms: float = 10.0,
    ) -> Dict[str, Any]:
        """
        Run performance test for an operation.

        Args:
            operation: Async operation to test
            iterations: Number of iterations to run
            p95_threshold_ms: 95th percentile threshold in milliseconds
            p99_threshold_ms: 99th percentile threshold in milliseconds

        Returns:
            Performance test results
        """
        execution_times = []
        errors = []

        print(f"Running {iterations} iterations...")

        for i in range(iterations):
            try:
                _, execution_time = await self._measure_async_execution_time(
                    operation()
                )
                execution_times.append(execution_time)

                if (i + 1) % 100 == 0:
                    print(f"  Completed {i + 1}/{iterations} iterations")

            except Exception as e:
                errors.append(str(e))

        # Calculate statistics
        if execution_times:
            avg_time = statistics.mean(execution_times)
            median_time = statistics.median(execution_times)
            p95_time = (
                statistics.quantiles(execution_times, n=20)[18]
                if len(execution_times) >= 20
                else max(execution_times)
            )
            p99_time = (
                statistics.quantiles(execution_times, n=100)[98]
                if len(execution_times) >= 100
                else max(execution_times)
            )
            min_time = min(execution_times)
            max_time = max(execution_times)

            results = {
                "iterations": iterations,
                "successful_runs": len(execution_times),
                "errors": len(errors),
                "avg_time_ms": round(avg_time, 3),
                "median_time_ms": round(median_time, 3),
                "p95_time_ms": round(p95_time, 3),
                "p99_time_ms": round(p99_time, 3),
                "min_time_ms": round(min_time, 3),
                "max_time_ms": round(max_time, 3),
                "p95_threshold_ms": p95_threshold_ms,
                "p99_threshold_ms": p99_threshold_ms,
                "p95_passed": p95_time <= p95_threshold_ms,
                "p99_passed": p99_time <= p99_threshold_ms,
                "all_passed": p95_time <= p95_threshold_ms
                and p99_time <= p99_threshold_ms,
            }

            # Sample execution times for debugging
            results["sample_times"] = execution_times[:10]

            return results
        else:
            return {
                "iterations": iterations,
                "successful_runs": 0,
                "errors": len(errors),
                "error_details": errors[:5],  # First 5 errors
            }

    @pytest.mark.asyncio
    async def test_cache_read_performance(self, cache_manager, sample_project_data):
        """Test cache read performance - 95% under 5ms."""
        project_id = uuid4()

        # Mock cache hit
        mock_cache = AsyncMock()
        mock_cache.data = sample_project_data
        mock_cache.version.value = 1

        cache_manager.repository.project_cache.find_by_project_id.return_value = (
            mock_cache
        )

        async def cache_read_operation():
            return await cache_manager.get_project_data(project_id)

        print("\n=== Cache Read Performance Test ===")
        print("Requirement: 95% of cache read operations under 5ms")
        print(f"Testing with {len(sample_project_data)} items in project data")

        results = await self._run_performance_test(
            cache_read_operation,
            iterations=1000,
            p95_threshold_ms=5.0,
            p99_threshold_ms=10.0,
        )

        print(f"\nCache Read Performance Results:")
        print(f"  Iterations: {results['iterations']}")
        print(f"  Successful runs: {results['successful_runs']}")
        print(f"  Errors: {results['errors']}")
        print(f"  Average time: {results['avg_time_ms']}ms")
        print(f"  Median time: {results['median_time_ms']}ms")
        print(
            f"  P95 time: {results['p95_time_ms']}ms (threshold: {results['p95_threshold_ms']}ms)"
        )
        print(
            f"  P99 time: {results['p99_time_ms']}ms (threshold: {results['p99_threshold_ms']}ms)"
        )
        print(f"  Min time: {results['min_time_ms']}ms")
        print(f"  Max time: {results['max_time_ms']}ms")
        print(f"  P95 passed: {results['p95_passed']}")
        print(f"  P99 passed: {results['p99_passed']}")
        print(f"  All passed: {results['all_passed']}")

        # Assertions
        assert results["successful_runs"] >= 950, (
            f"Too few successful runs: {results['successful_runs']}"
        )
        assert results["p95_passed"], (
            f"P95 time {results['p95_time_ms']}ms exceeds threshold {results['p95_threshold_ms']}ms"
        )
        assert results["p99_passed"], (
            f"P99 time {results['p99_time_ms']}ms exceeds threshold {results['p99_threshold_ms']}ms"
        )
        assert results["errors"] == 0, (
            f"Unexpected errors: {results.get('error_details', [])}"
        )

    @pytest.mark.asyncio
    async def test_rate_limit_check_performance(self, cache_manager):
        """Test rate limit check performance - 99% under 2ms."""
        identifier = "user123"
        config = RateLimitConfig(requests_per_window=100, window_seconds=3600)

        # Mock rate limit service response
        mock_result = {
            "allowed": True,
            "current_count": 5,
            "remaining_requests": 95,
            "reset_seconds": 1800,
            "limit": 100,
            "window": 3600,
        }

        with patch.object(
            cache_manager.rate_limit_service,
            "check_rate_limit",
            return_value=mock_result,
        ):

            async def rate_limit_operation():
                return await cache_manager.check_rate_limit("user", identifier, config)

            print("\n=== Rate Limit Check Performance Test ===")
            print("Requirement: 99% of rate limit checks under 2ms")
            print(f"Testing with user identifier: {identifier}")

            results = await self._run_performance_test(
                rate_limit_operation,
                iterations=1000,
                p95_threshold_ms=1.5,  # Stricter for 99% requirement
                p99_threshold_ms=2.0,
            )

            print(f"\nRate Limit Check Performance Results:")
            print(f"  Iterations: {results['iterations']}")
            print(f"  Successful runs: {results['successful_runs']}")
            print(f"  Errors: {results['errors']}")
            print(f"  Average time: {results['avg_time_ms']}ms")
            print(f"  Median time: {results['median_time_ms']}ms")
            print(
                f"  P95 time: {results['p95_time_ms']}ms (threshold: {results['p95_threshold_ms']}ms)"
            )
            print(
                f"  P99 time: {results['p99_time_ms']}ms (threshold: {results['p99_threshold_ms']}ms)"
            )
            print(f"  Min time: {results['min_time_ms']}ms")
            print(f"  Max time: {results['max_time_ms']}ms")
            print(f"  P95 passed: {results['p95_passed']}")
            print(f"  P99 passed: {results['p99_passed']}")
            print(f"  All passed: {results['all_passed']}")

            # Assertions for 99% requirement (use P99 as threshold)
            assert results["successful_runs"] >= 990, (
                f"Too few successful runs: {results['successful_runs']}"
            )
            assert results["p99_passed"], (
                f"P99 time {results['p99_time_ms']}ms exceeds threshold {results['p99_threshold_ms']}ms"
            )
            assert results["errors"] == 0, (
                f"Unexpected errors: {results.get('error_details', [])}"
            )

    @pytest.mark.asyncio
    async def test_progress_update_performance(self, cache_manager):
        """Test progress update performance - 95% under 3ms."""
        correlation_id = uuid4()
        step = 2
        message = "Processing business analyst response"

        # Mock progress update
        cache_manager.repository.progress.update_progress.return_value = True

        async def progress_update_operation():
            return await cache_manager.update_progress(correlation_id, step, message)

        print("\n=== Progress Update Performance Test ===")
        print("Requirement: 95% of progress updates under 3ms")
        print(f"Testing with correlation_id: {correlation_id}")

        results = await self._run_performance_test(
            progress_update_operation,
            iterations=1000,
            p95_threshold_ms=3.0,
            p99_threshold_ms=5.0,
        )

        print(f"\nProgress Update Performance Results:")
        print(f"  Iterations: {results['iterations']}")
        print(f"  Successful runs: {results['successful_runs']}")
        print(f"  Errors: {results['errors']}")
        print(f"  Average time: {results['avg_time_ms']}ms")
        print(f"  Median time: {results['median_time_ms']}ms")
        print(
            f"  P95 time: {results['p95_time_ms']}ms (threshold: {results['p95_threshold_ms']}ms)"
        )
        print(
            f"  P99 time: {results['p99_time_ms']}ms (threshold: {results['p99_threshold_ms']}ms)"
        )
        print(f"  Min time: {results['min_time_ms']}ms")
        print(f"  Max time: {results['max_time_ms']}ms")
        print(f"  P95 passed: {results['p95_passed']}")
        print(f"  P99 passed: {results['p99_passed']}")
        print(f"  All passed: {results['all_passed']}")

        # Assertions
        assert results["successful_runs"] >= 950, (
            f"Too few successful runs: {results['successful_runs']}"
        )
        assert results["p95_passed"], (
            f"P95 time {results['p95_time_ms']}ms exceeds threshold {results['p95_threshold_ms']}ms"
        )
        assert results["errors"] == 0, (
            f"Unexpected errors: {results.get('error_details', [])}"
        )

    @pytest.mark.asyncio
    async def test_cache_write_performance(self, cache_manager, sample_project_data):
        """Test cache write performance."""
        project_id = uuid4()
        ttl = TTL.hours(1)

        # Mock cache save
        cache_manager.repository.project_cache.save.return_value = None

        async def cache_write_operation():
            return await cache_manager.cache_project_data(
                project_id, sample_project_data, ttl
            )

        print("\n=== Cache Write Performance Test ===")
        print("Testing cache write operations")
        print(f"Project data size: {len(str(sample_project_data))} characters")

        results = await self._run_performance_test(
            cache_write_operation,
            iterations=500,  # Fewer iterations for write operations
            p95_threshold_ms=10.0,  # More lenient for writes
            p99_threshold_ms=20.0,
        )

        print(f"\nCache Write Performance Results:")
        print(f"  Iterations: {results['iterations']}")
        print(f"  Successful runs: {results['successful_runs']}")
        print(f"  Errors: {results['errors']}")
        print(f"  Average time: {results['avg_time_ms']}ms")
        print(f"  Median time: {results['median_time_ms']}ms")
        print(
            f"  P95 time: {results['p95_time_ms']}ms (threshold: {results['p95_threshold_ms']}ms)"
        )
        print(
            f"  P99 time: {results['p99_time_ms']}ms (threshold: {results['p99_threshold_ms']}ms)"
        )
        print(f"  Min time: {results['min_time_ms']}ms")
        print(f"  Max time: {results['max_time_ms']}ms")
        print(f"  P95 passed: {results['p95_passed']}")
        print(f"  P99 passed: {results['p99_passed']}")
        print(f"  All passed: {results['all_passed']}")

        # Assertions
        assert results["successful_runs"] >= 475, (
            f"Too few successful runs: {results['successful_runs']}"
        )
        assert results["p95_passed"], (
            f"P95 time {results['p95_time_ms']}ms exceeds threshold {results['p95_threshold_ms']}ms"
        )
        assert results["errors"] == 0, (
            f"Unexpected errors: {results.get('error_details', [])}"
        )

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(
        self, cache_manager, sample_project_data
    ):
        """Test concurrent cache operations performance."""
        project_id = uuid4()
        concurrent_requests = 100

        # Mock cache operations
        mock_cache = AsyncMock()
        mock_cache.data = sample_project_data
        mock_cache.version.value = 1
        cache_manager.repository.project_cache.find_by_project_id.return_value = (
            mock_cache
        )

        async def concurrent_cache_read():
            return await cache_manager.get_project_data(project_id)

        print(f"\n=== Concurrent Cache Operations Test ===")
        print(f"Testing {concurrent_requests} concurrent cache reads")

        # Measure concurrent performance
        start_time = time.perf_counter()
        tasks = [concurrent_cache_read() for _ in range(concurrent_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.perf_counter()

        total_time_ms = (end_time - start_time) * 1000
        successful_operations = sum(1 for r in results if not isinstance(r, Exception))
        errors = [r for r in results if isinstance(r, Exception)]

        avg_time_per_operation = total_time_ms / concurrent_requests

        print(f"\nConcurrent Operations Results:")
        print(f"  Concurrent requests: {concurrent_requests}")
        print(f"  Total time: {total_time_ms:.2f}ms")
        print(f"  Average time per operation: {avg_time_per_operation:.2f}ms")
        print(f"  Successful operations: {successful_operations}")
        print(f"  Errors: {len(errors)}")

        # Assertions
        assert successful_operations >= 95, (
            f"Too few successful operations: {successful_operations}"
        )
        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert avg_time_per_operation < 10.0, (
            f"Average time per operation too high: {avg_time_per_operation}ms"
        )

    @pytest.mark.asyncio
    async def test_memory_usage_pattern(self, cache_manager):
        """Test memory usage patterns during cache operations."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        print(f"\n=== Memory Usage Pattern Test ===")
        print(f"Initial memory usage: {initial_memory:.2f}MB")

        # Perform many cache operations
        for i in range(100):
            project_id = uuid4()
            data = {"iteration": i, "data": "x" * 1000}  # 1KB per iteration

            # Mock cache save
            cache_manager.repository.project_cache.save.return_value = None
            await cache_manager.cache_project_data(project_id, data)

            if (i + 1) % 20 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_increase = current_memory - initial_memory
                print(
                    f"  Iteration {i + 1}: {current_memory:.2f}MB (+{memory_increase:.2f}MB)"
                )

        final_memory = process.memory_info().rss / 1024 / 1024
        total_memory_increase = final_memory - initial_memory

        print(f"\nMemory Usage Results:")
        print(f"  Initial memory: {initial_memory:.2f}MB")
        print(f"  Final memory: {final_memory:.2f}MB")
        print(f"  Total increase: {total_memory_increase:.2f}MB")
        print(f"  Average per operation: {total_memory_increase / 100:.2f}MB")

        # Memory increase should be reasonable (less than 50MB for 100 operations)
        assert total_memory_increase < 50.0, (
            f"Memory increase too high: {total_memory_increase:.2f}MB"
        )

    @pytest.mark.asyncio
    async def test_ttl_expiration_performance(self, cache_manager):
        """Test performance impact of TTL operations."""
        project_id = uuid4()
        data = {"test": "data"}
        ttl_values = [TTL.seconds(1), TTL.minutes(1), TTL.hours(1), TTL.days(1)]

        print(f"\n=== TTL Expiration Performance Test ===")
        print("Testing performance impact of different TTL values")

        for ttl in ttl_values:
            # Mock cache save
            cache_manager.repository.project_cache.save.return_value = None

            async def ttl_operation():
                return await cache_manager.cache_project_data(project_id, data, ttl)

            results = await self._run_performance_test(
                ttl_operation,
                iterations=100,
                p95_threshold_ms=10.0,
                p99_threshold_ms=20.0,
            )

            print(f"\nTTL {ttl} Results:")
            print(f"  Average time: {results['avg_time_ms']}ms")
            print(f"  P95 time: {results['p95_time_ms']}ms")
            print(f"  P95 passed: {results['p95_passed']}")

            assert results["p95_passed"], (
                f"P95 time {results['p95_time_ms']}ms exceeds threshold for TTL {ttl}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
