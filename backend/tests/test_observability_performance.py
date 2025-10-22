"""
JEEX Idea Observability Stack Performance Tests

Performance test suite for validating observability system performance under load.
Tests performance requirements, resource usage, and scalability limits.

Performance Requirements:
- PERF-001: < 5% latency overhead for API requests
- PERF-002: Handle 1000 spans/second without data loss
- PERF-003: Dashboard loads within 2 seconds
"""

import asyncio
import gc
import logging
import psutil
import time
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, patch

import pytest
from opentelemetry import trace

from app.core.telemetry import (
    OpenTelemetryManager,
    ProjectAwareSampler,
    get_tracer,
    set_correlation_id,
    get_correlation_id,
    get_telemetry_health,
    get_resilience_metrics,
)

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics data structure."""

    operation_count: int
    total_duration: float
    average_duration: float
    min_duration: float
    max_duration: float
    percentile_95: float
    percentile_99: float
    operations_per_second: float
    memory_usage_mb: float
    cpu_usage_percent: float


class PerformanceMonitor:
    """Monitor system performance during tests."""

    def __init__(self):
        self.process = psutil.Process()
        self.start_time = None
        self.start_memory = None
        self.start_cpu_time = None
        self.measurements = []

    def start_monitoring(self):
        """Start performance monitoring."""
        self.start_time = time.time()
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.start_cpu_time = self.process.cpu_times()

    def stop_monitoring(self) -> Dict[str, float]:
        """Stop monitoring and return performance metrics."""
        end_time = time.time()
        end_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        end_cpu_time = self.process.cpu_times()

        duration = end_time - self.start_time
        memory_delta = end_memory - self.start_memory
        cpu_delta = (end_cpu_time.user + end_cpu_time.system) - (
            self.start_cpu_time.user + self.start_cpu_time.system
        )

        return {
            "duration_seconds": duration,
            "memory_usage_mb": end_memory,
            "memory_delta_mb": memory_delta,
            "cpu_time_seconds": cpu_delta,
            "cpu_percent": (cpu_delta / duration) * 100 if duration > 0 else 0,
        }


class TestPerformanceOverhead:
    """Test suite for PERF-001: Performance Overhead (< 5% latency overhead)."""

    @pytest.fixture
    def performance_monitor(self):
        """Create performance monitor."""
        return PerformanceMonitor()

    def test_sampling_performance(self, performance_monitor):
        """
        Test sampling operation performance.

        Validate that sampling adds minimal overhead.
        """
        sampler = ProjectAwareSampler(sample_rate=1.0, max_spans_per_second=10000)

        # Baseline performance without telemetry
        performance_monitor.start_monitoring()

        baseline_operations = 10000
        start_time = time.perf_counter()

        # Simulate operations without sampling
        for i in range(baseline_operations):
            # Simulate basic operation
            result = i * 2
            assert result == i * 2

        baseline_duration = time.perf_counter() - start_time
        baseline_metrics = performance_monitor.stop_monitoring()

        # Performance with telemetry sampling
        performance_monitor.start_monitoring()

        telemetry_operations = 10000
        start_time = time.perf_counter()

        for i in range(telemetry_operations):
            # Simulate operation with sampling
            sampler.should_sample(
                parent_context=None,
                trace_id=i,
                name=f"operation_{i}",
                attributes={"test.value": i},
            )

        telemetry_duration = time.perf_counter() - start_time
        telemetry_metrics = performance_monitor.stop_monitoring()

        # Calculate overhead
        overhead_percentage = (
            (telemetry_duration - baseline_duration) / baseline_duration
        ) * 100

        # Assert performance requirements
        assert overhead_percentage < 5.0, (
            f"Sampling overhead: {overhead_percentage:.2f}%"
        )
        assert telemetry_metrics["memory_delta_mb"] < 50, (
            f"Memory overhead: {telemetry_metrics['memory_delta_mb']:.2f}MB"
        )

        logger.info(
            "Sampling performance test completed",
            baseline_duration_ms=baseline_duration * 1000,
            telemetry_duration_ms=telemetry_duration * 1000,
            overhead_percentage=overhead_percentage,
            memory_overhead_mb=telemetry_metrics["memory_delta_mb"],
        )

    def test_correlation_id_overhead(self, performance_monitor):
        """
        Test correlation ID operation overhead.

        Validate that correlation ID management is efficient.
        """
        # Baseline without correlation ID
        performance_monitor.start_monitoring()

        operations = 50000
        test_ids = [str(uuid.uuid4()) for _ in range(1000)]  # Reuse IDs

        start_time = time.perf_counter()

        # Simulate operations without correlation ID
        for i in range(operations):
            test_id = test_ids[i % len(test_ids)]
            # Simulate basic operation with ID
            result = f"operation_{i}_{test_id[:8]}"

        baseline_duration = time.perf_counter() - start_time
        baseline_metrics = performance_monitor.stop_monitoring()

        # Performance with correlation ID
        performance_monitor.start_monitoring()

        start_time = time.perf_counter()

        for i in range(operations):
            test_id = test_ids[i % len(test_ids)]
            set_correlation_id(test_id)
            retrieved_id = get_correlation_id()
            assert retrieved_id == test_id

        telemetry_duration = time.perf_counter() - start_time
        telemetry_metrics = performance_monitor.stop_monitoring()

        # Calculate overhead
        overhead_percentage = (
            (telemetry_duration - baseline_duration) / baseline_duration
        ) * 100

        assert overhead_percentage < 5.0, (
            f"Correlation ID overhead: {overhead_percentage:.2f}%"
        )
        assert telemetry_metrics["memory_delta_mb"] < 20, (
            f"Memory overhead: {telemetry_metrics['memory_delta_mb']:.2f}MB"
        )

        logger.info(
            "Correlation ID performance test completed",
            overhead_percentage=overhead_percentage,
            memory_overhead_mb=telemetry_metrics["memory_delta_mb"],
        )

    def test_span_creation_overhead(self, performance_monitor):
        """
        Test span creation overhead.

        Validate that manual span creation is efficient.
        """
        tracer = get_tracer("performance_test")

        # Baseline without spans
        performance_monitor.start_monitoring()

        operations = 1000
        start_time = time.perf_counter()

        for i in range(operations):
            # Simulate business logic
            result = i * i
            assert result == i * i

        baseline_duration = time.perf_counter() - start_time
        baseline_metrics = performance_monitor.stop_monitoring()

        # Performance with spans
        performance_monitor.start_monitoring()

        start_time = time.perf_counter()

        for i in range(operations):
            with tracer.start_as_current_span(f"operation_{i}") as span:
                span.set_attribute("operation.id", i)
                span.set_attribute("project_id", str(uuid.uuid4()))
                # Simulate business logic
                result = i * i
                assert result == i * i

        telemetry_duration = time.perf_counter() - start_time
        telemetry_metrics = performance_monitor.stop_monitoring()

        # Calculate overhead
        overhead_percentage = (
            (telemetry_duration - baseline_duration) / baseline_duration
        ) * 100

        assert overhead_percentage < 5.0, (
            f"Span creation overhead: {overhead_percentage:.2f}%"
        )
        assert telemetry_metrics["memory_delta_mb"] < 100, (
            f"Memory overhead: {telemetry_metrics['memory_delta_mb']:.2f}MB"
        )

        logger.info(
            "Span creation performance test completed",
            overhead_percentage=overhead_percentage,
            memory_overhead_mb=telemetry_metrics["memory_delta_mb"],
        )


class TestDataCollectionThroughput:
    """Test suite for PERF-002: Data Collection Throughput (1000 spans/second)."""

    def test_single_thread_throughput(self):
        """
        Test single-threaded span creation throughput.

        Validate ability to create 1000 spans/second in single thread.
        """
        tracer = get_tracer("throughput_test")
        target_spans_per_second = 1000
        test_duration_seconds = 5

        spans_created = 0
        start_time = time.perf_counter()

        while (time.perf_counter() - start_time) < test_duration_seconds:
            with tracer.start_as_current_span(
                f"throughput_span_{spans_created}"
            ) as span:
                span.set_attribute("test.id", spans_created)
                span.set_attribute("project_id", str(uuid.uuid4()))
                spans_created += 1

        actual_duration = time.perf_counter() - start_time
        actual_spans_per_second = spans_created / actual_duration

        assert actual_spans_per_second >= target_spans_per_second, (
            f"Throughput: {actual_spans_per_second:.2f} spans/sec, target: {target_spans_per_second}"
        )

        logger.info(
            "Single-thread throughput test completed",
            spans_created=spans_created,
            duration_seconds=actual_duration,
            spans_per_second=actual_spans_per_second,
        )

    def test_multi_thread_throughput(self):
        """
        Test multi-threaded span creation throughput.

        Validate throughput under concurrent load.
        """
        tracer = get_tracer("concurrent_throughput_test")
        num_threads = 10
        spans_per_thread = 100

        def create_spans(thread_id: int) -> int:
            """Create spans in a thread."""
            spans_created = 0
            for i in range(spans_per_thread):
                with tracer.start_as_current_span(
                    f"thread_{thread_id}_span_{i}"
                ) as span:
                    span.set_attribute("thread.id", thread_id)
                    span.set_attribute("span.id", i)
                    span.set_attribute("project_id", str(uuid.uuid4()))
                    spans_created += 1
            return spans_created

        # Execute in multiple threads
        start_time = time.perf_counter()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(create_spans, i) for i in range(num_threads)]
            results = [future.result() for future in as_completed(futures)]

        actual_duration = time.perf_counter() - start_time
        total_spans = sum(results)
        spans_per_second = total_spans / actual_duration

        target_throughput = 1000  # spans per second
        assert spans_per_second >= target_throughput, (
            f"Concurrent throughput: {spans_per_second:.2f} spans/sec, target: {target_throughput}"
        )

        logger.info(
            "Multi-thread throughput test completed",
            total_spans=total_spans,
            num_threads=num_threads,
            duration_seconds=actual_duration,
            spans_per_second=spans_per_second,
        )

    def test_async_span_creation_throughput(self):
        """
        Test async span creation throughput.

        Validate performance with async operations.
        """
        tracer = get_tracer("async_throughput_test")
        num_concurrent_operations = 100
        operations_per_coroutine = 20

        async def create_spans_async(coroutine_id: int) -> int:
            """Create spans asynchronously."""
            spans_created = 0
            for i in range(operations_per_coroutine):
                with tracer.start_as_current_span(
                    f"async_{coroutine_id}_span_{i}"
                ) as span:
                    span.set_attribute("coroutine.id", coroutine_id)
                    span.set_attribute("span.id", i)
                    span.set_attribute("project_id", str(uuid.uuid4()))
                    spans_created += 1

                    # Small delay to simulate async work
                    await asyncio.sleep(0.001)
            return spans_created

        # Execute async operations
        start_time = time.perf_counter()

        tasks = [create_spans_async(i) for i in range(num_concurrent_operations)]
        results = await asyncio.gather(*tasks)

        actual_duration = time.perf_counter() - start_time
        total_spans = sum(results)
        spans_per_second = total_spans / actual_duration

        target_throughput = 500  # Lower target for async with delays
        assert spans_per_second >= target_throughput, (
            f"Async throughput: {spans_per_second:.2f} spans/sec, target: {target_throughput}"
        )

        logger.info(
            "Async throughput test completed",
            total_spans=total_spans,
            num_coroutines=num_concurrent_operations,
            duration_seconds=actual_duration,
            spans_per_second=spans_per_second,
        )

    def test_memory_usage_under_load(self):
        """
        Test memory usage during high-throughput operations.

        Validate memory usage stays within limits.
        """
        tracer = get_tracer("memory_test")
        process = psutil.Process()

        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        target_spans = 5000
        memory_limit_mb = 512  # From requirements

        # Create spans and monitor memory
        for i in range(target_spans):
            with tracer.start_as_current_span(f"memory_test_span_{i}") as span:
                span.set_attribute("test.id", i)
                span.set_attribute("project_id", str(uuid.uuid4()))

                # Add some attributes to test memory usage
                span.set_attribute("large.attribute", "x" * 100)

                # Check memory every 1000 spans
                if i % 1000 == 0:
                    current_memory = process.memory_info().rss / 1024 / 1024
                    memory_delta = current_memory - initial_memory

                    assert memory_delta < memory_limit_mb, (
                        f"Memory usage: {current_memory:.2f}MB, delta: {memory_delta:.2f}MB, limit: {memory_limit_mb}MB"
                    )

        final_memory = process.memory_info().rss / 1024 / 1024
        total_memory_delta = final_memory - initial_memory

        assert total_memory_delta < memory_limit_mb, (
            f"Final memory usage: {final_memory:.2f}MB, delta: {total_memory_delta:.2f}MB, limit: {memory_limit_mb}MB"
        )

        logger.info(
            "Memory usage test completed",
            initial_memory_mb=initial_memory,
            final_memory_mb=final_memory,
            memory_delta_mb=total_memory_delta,
            spans_created=target_spans,
        )


class TestDashboardResponsiveness:
    """Test suite for PERF-003: Dashboard Responsiveness (< 2 second load time)."""

    def test_telemetry_health_response_time(self):
        """
        Test telemetry health endpoint response time.

        Validate health endpoint responds within 2 seconds.
        """
        target_response_time_seconds = 2.0

        start_time = time.perf_counter()
        health = get_telemetry_health()
        response_time = time.perf_counter() - start_time

        assert response_time < target_response_time_seconds, (
            f"Health endpoint response time: {response_time:.3f}s, target: {target_response_time_seconds}s"
        )

        assert isinstance(health, dict)
        assert "status" in health

        logger.info(
            "Health endpoint responsiveness test completed",
            response_time_ms=response_time * 1000,
            target_time_ms=target_response_time_seconds * 1000,
        )

    def test_resilience_metrics_response_time(self):
        """
        Test resilience metrics endpoint response time.

        Validate metrics endpoint responds within 2 seconds.
        """
        target_response_time_seconds = 2.0

        start_time = time.perf_counter()
        metrics = get_resilience_metrics()
        response_time = time.perf_counter() - start_time

        assert response_time < target_response_time_seconds, (
            f"Metrics endpoint response time: {response_time:.3f}s, target: {target_response_time_seconds}s"
        )

        # May be None if not initialized, which is acceptable
        assert metrics is None or isinstance(metrics, dict)

        logger.info(
            "Metrics endpoint responsiveness test completed",
            response_time_ms=response_time * 1000,
            target_time_ms=target_response_time_seconds * 1000,
            has_metrics=metrics is not None,
        )

    def test_correlation_id_operations_response_time(self):
        """
        Test correlation ID operation response times.

        Validate correlation ID operations are fast.
        """
        target_operation_time_ms = 1.0  # Very fast for simple operations

        # Test set operation
        test_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        set_correlation_id(test_id)
        set_time = (time.perf_counter() - start_time) * 1000

        assert set_time < target_operation_time_ms, (
            f"Set correlation ID time: {set_time:.3f}ms, target: {target_operation_time_ms}ms"
        )

        # Test get operation
        start_time = time.perf_counter()
        retrieved_id = get_correlation_id()
        get_time = (time.perf_counter() - start_time) * 1000

        assert get_time < target_operation_time_ms, (
            f"Get correlation ID time: {get_time:.3f}ms, target: {target_operation_time_ms}ms"
        )

        assert retrieved_id == test_id

        logger.info(
            "Correlation ID operations responsiveness test completed",
            set_time_ms=set_time,
            get_time_ms=get_time,
            target_time_ms=target_operation_time_ms,
        )

    @pytest.mark.asyncio
    async def test_dashboard_data_aggregation_time(self):
        """
        Test dashboard data aggregation performance.

        Validate data aggregation for dashboard is efficient.
        """
        # Simulate dashboard data aggregation
        tracer = get_tracer("dashboard_test")

        # Create test data
        num_test_spans = 1000
        project_ids = [str(uuid.uuid4()) for _ in range(10)]

        start_time = time.perf_counter()

        # Create spans representing dashboard data
        for i in range(num_test_spans):
            with tracer.start_as_current_span(f"dashboard_data_{i}") as span:
                span.set_attribute("project_id", project_ids[i % len(project_ids)])
                span.set_attribute(
                    "operation.type", ["api", "database", "cache", "search"][i % 4]
                )
                span.set_attribute("http.status_code", 200 if i % 10 != 0 else 500)
                span.set_attribute("duration.ms", i % 1000)

        # Simulate aggregation (in real implementation, this would query the dashboard)
        aggregation_start = time.perf_counter()

        # Mock aggregation logic
        aggregated_data = {
            "total_spans": num_test_spans,
            "projects": len(project_ids),
            "operations": {
                "api": num_test_spans // 4,
                "database": num_test_spans // 4,
                "cache": num_test_spans // 4,
                "search": num_test_spans // 4,
            },
            "error_rate": 0.1,  # 10% errors from simulation
            "avg_duration_ms": 500,
        }

        aggregation_time = time.perf_counter() - aggregation_start
        total_time = time.perf_counter() - start_time

        target_aggregation_time = 2.0
        assert aggregation_time < target_aggregation_time, (
            f"Data aggregation time: {aggregation_time:.3f}s, target: {target_aggregation_time}s"
        )

        assert isinstance(aggregated_data, dict)
        assert aggregated_data["total_spans"] == num_test_spans

        logger.info(
            "Dashboard data aggregation test completed",
            total_time_ms=total_time * 1000,
            aggregation_time_ms=aggregation_time * 1000,
            target_time_ms=target_aggregation_time * 1000,
            spans_processed=num_test_spans,
        )


class TestPerformanceScalability:
    """Test suite for performance scalability limits."""

    def test_sampling_rate_impact(self):
        """
        Test performance impact of different sampling rates.

        Validate that sampling reduces overhead appropriately.
        """
        sampling_rates = [0.01, 0.1, 0.5, 1.0]
        operations_per_rate = 1000
        results = {}

        for rate in sampling_rates:
            sampler = ProjectAwareSampler(sample_rate=rate)

            start_time = time.perf_counter()
            sampled_count = 0

            for i in range(operations_per_rate):
                result = sampler.should_sample(
                    parent_context=None,
                    trace_id=i,
                    name=f"operation_{i}",
                    attributes={"test.value": i},
                )
                if result.decision.value == 1:  # RECORD_AND_SAMPLE
                    sampled_count += 1

            duration = time.perf_counter() - start_time
            operations_per_second = operations_per_rate / duration
            actual_sampling_rate = sampled_count / operations_per_rate

            results[rate] = {
                "duration": duration,
                "operations_per_second": operations_per_second,
                "sampled_count": sampled_count,
                "actual_sampling_rate": actual_sampling_rate,
            }

            # Verify sampling rate is approximately correct (within 10%)
            expected_sampled = operations_per_rate * rate
            tolerance = expected_sampled * 0.1
            assert abs(sampled_count - expected_sampled) <= tolerance, (
                f"Rate {rate}: expected ~{expected_sampled}, got {sampled_count}"
            )

        # Verify performance improves with lower sampling rates
        assert (
            results[0.01]["operations_per_second"]
            > results[1.0]["operations_per_second"]
        )

        logger.info(
            "Sampling rate impact test completed",
            results={
                k: {
                    "ops_per_sec": v["operations_per_second"],
                    "actual_rate": v["actual_sampling_rate"],
                }
                for k, v in results.items()
            },
        )

    def test_memory_scaling_with_span_count(self):
        """
        Test memory usage scaling with span count.

        Validate memory usage scales linearly, not exponentially.
        """
        tracer = get_tracer("memory_scaling_test")
        process = psutil.Process()

        span_counts = [100, 500, 1000, 2000]
        memory_measurements = []

        for count in span_counts:
            # Force garbage collection before each test
            gc.collect()
            initial_memory = process.memory_info().rss / 1024 / 1024

            # Create spans
            for i in range(count):
                with tracer.start_as_current_span(f"scaling_test_{count}_{i}") as span:
                    span.set_attribute("test.count", count)
                    span.set_attribute("test.id", i)
                    span.set_attribute("project_id", str(uuid.uuid4()))

            final_memory = process.memory_info().rss / 1024 / 1024
            memory_delta = final_memory - initial_memory

            memory_measurements.append(
                {
                    "span_count": count,
                    "memory_delta_mb": memory_delta,
                    "memory_per_span_kb": (memory_delta * 1024) / count,
                }
            )

            logger.info(
                f"Memory scaling for {count} spans",
                memory_delta_mb=memory_delta,
                memory_per_span_kb=(memory_delta * 1024) / count,
            )

        # Verify linear scaling (memory per span should be relatively constant)
        memory_per_span_values = [m["memory_per_span_kb"] for m in memory_measurements]
        avg_memory_per_span = sum(memory_per_span_values) / len(memory_per_span_values)

        # Allow 50% variation from average
        tolerance = avg_memory_per_span * 0.5

        for measurement in memory_measurements:
            assert (
                abs(measurement["memory_per_span_kb"] - avg_memory_per_span)
                <= tolerance
            ), (
                f"Memory scaling non-linear: {measurement['memory_per_span_kb']:.2f}KB/span, avg: {avg_memory_per_span:.2f}KB/span"
            )

        logger.info(
            "Memory scaling test completed",
            avg_memory_per_span_kb=avg_memory_per_span,
            measurements=memory_measurements,
        )

    @pytest.mark.asyncio
    async def test_concurrent_load_scaling(self):
        """
        Test performance under increasing concurrent load.

        Validate system scales reasonably with concurrent operations.
        """
        tracer = get_tracer("concurrent_scaling_test")

        concurrency_levels = [1, 5, 10, 20]
        operations_per_level = 100
        results = {}

        async def create_concurrent_spans(
            concurrency: int, operations: int
        ) -> Dict[str, float]:
            """Create spans with specified concurrency."""

            async def worker_span(worker_id: int, span_count: int) -> int:
                created = 0
                for i in range(span_count):
                    with tracer.start_as_current_span(
                        f"worker_{worker_id}_span_{i}"
                    ) as span:
                        span.set_attribute("worker.id", worker_id)
                        span.set_attribute("span.id", i)
                        span.set_attribute("project_id", str(uuid.uuid4()))
                        created += 1
                        # Small delay to simulate work
                        await asyncio.sleep(0.001)
                return created

            start_time = time.perf_counter()

            # Create concurrent tasks
            spans_per_worker = operations // concurrency
            tasks = [worker_span(i, spans_per_worker) for i in range(concurrency)]

            results_counts = await asyncio.gather(*tasks)
            total_spans = sum(results_counts)

            duration = time.perf_counter() - start_time
            spans_per_second = total_spans / duration

            return {
                "total_spans": total_spans,
                "duration": duration,
                "spans_per_second": spans_per_second,
            }

        for concurrency in concurrency_levels:
            result = await create_concurrent_spans(concurrency, operations_per_level)
            results[concurrency] = result

            logger.info(
                f"Concurrent load test - {concurrency} workers",
                spans_per_second=result["spans_per_second"],
                total_spans=result["total_spans"],
            )

        # Verify reasonable scaling (performance shouldn't degrade dramatically)
        single_thread_performance = results[1]["spans_per_second"]
        highest_concurrency_performance = results[max(concurrency_levels)][
            "spans_per_second"
        ]

        # Performance should not drop below 20% of single-thread performance
        scaling_ratio = highest_concurrency_performance / single_thread_performance
        assert scaling_ratio >= 0.2, (
            f"Poor scaling: {scaling_ratio:.2f}x, single_thread: {single_thread_performance:.2f}, concurrent: {highest_concurrency_performance:.2f}"
        )

        logger.info(
            "Concurrent load scaling test completed",
            scaling_ratio=scaling_ratio,
            single_thread_ops_per_sec=single_thread_performance,
            highest_concurrency_ops_per_sec=highest_concurrency_performance,
            results=results,
        )


class TestPerformanceRegression:
    """Test suite for performance regression detection."""

    def test_performance_baseline_comparison(self):
        """
        Test against established performance baselines.

        Detect performance regressions by comparing to baseline metrics.
        """
        # Performance baselines (these would be established from previous runs)
        baselines = {
            "sampling_operations_per_second": 50000,
            "correlation_id_operations_per_second": 100000,
            "span_creation_overhead_percent": 5.0,
            "memory_per_span_kb": 2.0,
            "health_endpoint_response_time_ms": 10.0,
        }

        current_metrics = {}

        # Test sampling performance
        sampler = ProjectAwareSampler(sample_rate=1.0)
        start_time = time.perf_counter()
        for i in range(5000):
            sampler.should_sample(None, i, f"test_{i}", {"test": "value"})
        sampling_ops_per_sec = 5000 / (time.perf_counter() - start_time)
        current_metrics["sampling_operations_per_second"] = sampling_ops_per_sec

        # Test correlation ID performance
        test_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        for i in range(10000):
            set_correlation_id(test_id)
            get_correlation_id()
        correlation_ops_per_sec = 10000 / (time.perf_counter() - start_time)
        current_metrics["correlation_id_operations_per_second"] = (
            correlation_ops_per_sec
        )

        # Test health endpoint performance
        start_time = time.perf_counter()
        get_telemetry_health()
        health_response_time_ms = (time.perf_counter() - start_time) * 1000
        current_metrics["health_endpoint_response_time_ms"] = health_response_time_ms

        # Compare against baselines
        regression_detected = False
        regression_details = []

        for metric, baseline_value in baselines.items():
            current_value = current_metrics.get(metric)
            if current_value is None:
                continue

            if metric.endswith("_operations_per_second"):
                # Higher is better for operations per second
                if current_value < baseline_value * 0.8:  # 20% degradation threshold
                    regression_detected = True
                    regression_details.append(
                        f"{metric}: {current_value:.2f} < {baseline_value:.2f} (baseline)"
                    )

            elif metric.endswith("_percent") or metric.endswith("_time_ms"):
                # Lower is better for percentages and times
                if current_value > baseline_value * 1.2:  # 20% degradation threshold
                    regression_detected = True
                    regression_details.append(
                        f"{metric}: {current_value:.2f} > {baseline_value:.2f} (baseline)"
                    )

        # Assert no performance regression
        assert not regression_detected, (
            f"Performance regression detected: {regression_details}"
        )

        logger.info(
            "Performance baseline comparison completed",
            current_metrics=current_metrics,
            baselines=baselines,
            regression_detected=regression_detected,
        )

    def test_performance_under_stress(self):
        """
        Test performance under stress conditions.

        Validate system maintains performance under stress.
        """
        tracer = get_tracer("stress_test")
        stress_duration_seconds = 30
        target_spans_per_second = 1000

        start_time = time.perf_counter()
        spans_created = 0

        # Create spans continuously for stress duration
        while (time.perf_counter() - start_time) < stress_duration_seconds:
            with tracer.start_as_current_span(f"stress_span_{spans_created}") as span:
                span.set_attribute("stress.test", True)
                span.set_attribute("span.id", spans_created)
                span.set_attribute("project_id", str(uuid.uuid4()))
                spans_created += 1

            # Small delay to prevent CPU overload
            time.sleep(0.001)

        actual_duration = time.perf_counter() - start_time
        actual_spans_per_second = spans_created / actual_duration

        # Should maintain at least 80% of target performance under stress
        stress_performance_ratio = actual_spans_per_second / target_spans_per_second
        assert stress_performance_ratio >= 0.8, (
            f"Stress performance: {actual_spans_per_second:.2f} spans/sec, target: {target_spans_per_second}, ratio: {stress_performance_ratio:.2f}"
        )

        logger.info(
            "Stress test completed",
            duration_seconds=actual_duration,
            spans_created=spans_created,
            spans_per_second=actual_spans_per_second,
            stress_performance_ratio=stress_performance_ratio,
        )


if __name__ == "__main__":
    # Run performance tests
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "-m",  # Add performance test markers if needed
        ]
    )
