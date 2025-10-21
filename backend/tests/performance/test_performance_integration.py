"""
Integration tests for performance testing framework.

Validates that the performance testing suite components work together
correctly and can successfully execute benchmarks.
"""

import pytest
import asyncio
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from tests.performance.test_vector_performance import (
    VectorPerformanceBenchmark,
    PerformanceMetrics,
    VectorDataGenerator,
    PerformanceMonitor,
)
from tests.performance.benchmark_runner import PerformanceBenchmarkRunner
from tests.performance.performance_reporter import PerformanceReporter
from tests.performance.config import PerformanceTestConfig, get_config


@pytest.mark.asyncio
@pytest.mark.performance
class TestPerformanceFrameworkIntegration:
    """Integration tests for the complete performance testing framework."""

    async def test_data_generator_integration(self):
        """Test that VectorDataGenerator produces valid test data."""
        generator = VectorDataGenerator()

        # Test vector generation
        vector = generator.generate_vector()
        assert len(vector) == 1536
        assert all(isinstance(x, float) for x in vector)
        assert all(-1.0 <= x <= 1.0 for x in vector)

        # Test VectorData generation
        vector_data = generator.generate_query_vector()
        assert len(vector_data) == 1536

        # Test VectorPoint generation
        project_id = str(uuid4())
        point = generator.generate_vector_point(project_id=project_id)

        assert point.project_id.value == project_id
        assert len(point.vector) == 1536
        assert point.content is not None
        assert point.importance >= 0.3 and point.importance <= 1.0

    async def test_performance_monitor_integration(self):
        """Test that PerformanceMonitor correctly tracks resources."""
        monitor = PerformanceMonitor()

        # Start monitoring
        monitor.start_monitoring()

        # Simulate some work
        await asyncio.sleep(0.1)

        # Take measurements
        measurement = monitor.take_measurement()
        assert "memory_mb" in measurement
        assert "cpu_percent" in measurement
        assert "timestamp" in measurement

        # Stop monitoring
        metrics = monitor.stop_monitoring()
        assert "memory_mb" in metrics
        assert "cpu_percent" in metrics

    def test_performance_metrics_structure(self):
        """Test that PerformanceMetrics data structure is correct."""
        metrics = PerformanceMetrics(
            operation="test",
            dataset_size=1000,
            duration_ms=100.0,
            throughput=10.0,
            latency_p50=50.0,
            latency_p95=95.0,
            latency_p99=99.0,
            error_count=0,
            memory_usage_mb=100.0,
            cpu_usage_percent=50.0,
        )

        # Test conversion to dictionary
        metrics_dict = metrics.to_dict()
        assert metrics_dict["operation"] == "test"
        assert metrics_dict["dataset_size"] == 1000
        assert metrics_dict["throughput"] == 10.0
        assert metrics_dict["latency_p95"] == 95.0

    def test_configuration_management(self):
        """Test that configuration management works correctly."""
        # Test default configuration
        config = get_config()
        assert config.environment == "development"
        assert config.targets.search_p95_latency_ms == 100.0
        assert config.test_config.vector_dimension == 1536

        # Test environment-specific configuration
        ci_config = get_config("ci")
        assert ci_config.environment == "ci"
        assert ci_config.test_config.quick_mode is True
        assert ci_config.test_config.benchmark_iterations == 3

        # Test configuration validation
        try:
            # This should raise a validation error
            invalid_config = PerformanceTestConfig()
            invalid_config.targets.search_p95_latency_ms = 200.0
            invalid_config.targets.search_p99_latency_ms = 150.0  # P99 < P95 is invalid
            invalid_config._validate_configuration()
            assert False, "Should have raised validation error"
        except ValueError:
            pass  # Expected

    async def test_performance_reporter_integration(self):
        """Test that PerformanceReporter can generate reports."""
        output_dir = Path("/tmp/test_performance_reports")
        output_dir.mkdir(exist_ok=True)

        reporter = PerformanceReporter(output_dir)

        # Create sample results
        sample_results = {
            "summary": {
                "total_benchmarks": 5,
                "successful_benchmarks": 5,
                "performance_highlights": {
                    "best_search_p95": 85.2,
                    "best_upsert_throughput": 245.0,
                    "best_qps": 120.0,
                },
            },
            "results": {
                "search_performance": [
                    {
                        "dataset_size": 1000,
                        "latency_p95": 85.2,
                        "latency_p50": 65.1,
                        "latency_p99": 120.5,
                        "throughput": 15.2,
                        "error_count": 0,
                        "memory_usage_mb": 100.0,
                        "cpu_usage_percent": 25.0,
                    }
                ],
                "upsert_performance": [
                    {
                        "dataset_size": 1000,
                        "batch_size": 50,
                        "latency_p95": 150.0,
                        "throughput": 245.0,
                        "error_count": 0,
                        "memory_usage_mb": 120.0,
                        "cpu_usage_percent": 40.0,
                    }
                ],
            },
            "requirements_validation": {
                "req_007_query_performance": {"passed": True, "details": []},
                "perf_002_indexing_performance": {"passed": True, "details": []},
                "scale_002_concurrent_capacity": {"passed": True, "details": []},
            },
        }

        # Test CSV export
        csv_file = await reporter.generate_csv_report(sample_results)
        assert Path(csv_file).exists()

        # Test trend analysis
        trend_file = await reporter.generate_trend_analysis(sample_results)
        assert Path(trend_file).exists()

        # Clean up
        import shutil

        shutil.rmtree(output_dir, ignore_errors=True)

    @pytest.mark.slow
    async def test_benchmark_runner_setup(self):
        """Test that benchmark runner can setup test environment."""
        # Skip if Qdrant is not available
        try:
            from qdrant_client import QdrantClient
        except ImportError:
            pytest.skip("qdrant_client not installed")

        try:
            client = QdrantClient(host="localhost", port=5230)
            await asyncio.to_thread(client.get_collections)
        except Exception as e:
            pytest.skip(f"Qdrant not available for integration testing: {e}")

        # Test benchmark runner initialization
        runner = PerformanceBenchmarkRunner("/tmp/test_runner_output")

        # Test environment setup
        repository, search_service = await runner._setup_test_environment()

        # Verify repository is configured
        assert repository is not None
        assert search_service is not None
        assert repository.COLLECTION_NAME.startswith("jeex_benchmark_")

        # Cleanup
        await runner._cleanup_test_environment()

        # Clean up output directory
        import shutil

        shutil.rmtree("/tmp/test_runner_output", ignore_errors=True)


@pytest.mark.asyncio
@pytest.mark.performance
class TestPerformanceFrameworkValidation:
    """Validation tests for performance framework components."""

    async def test_percentile_calculations(self):
        """Test that percentile calculations are correct."""
        benchmark = VectorPerformanceBenchmark(None, None)

        # Test with known data
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        p50 = benchmark._percentile(data, 50)
        p95 = benchmark._percentile(data, 95)
        p99 = benchmark._percentile(data, 99)

        assert p50 == 5.5  # Median
        assert p95 == 9.55
        assert p99 == 9.91

        # Test with empty data
        empty_p95 = benchmark._percentile([], 95)
        assert empty_p95 == 0.0

    def test_config_dataset_sizes(self):
        """Test that dataset sizes are correctly configured."""
        config = get_config()

        # Test normal mode
        normal_sizes = config.get_dataset_sizes()
        assert 1000 in normal_sizes
        assert 100000 in normal_sizes

        # Test quick mode
        config.test_config.quick_mode = True
        quick_sizes = config.get_dataset_sizes()
        assert len(quick_sizes) <= len(normal_sizes)
        assert all(size in normal_sizes for size in quick_sizes)

    def test_performance_targets_consistency(self):
        """Test that performance targets are internally consistent."""
        config = get_config()

        # P50 should be <= P95 <= P99
        assert (
            config.targets.search_p50_latency_ms <= config.targets.search_p95_latency_ms
        )
        assert (
            config.targets.search_p95_latency_ms <= config.targets.search_p99_latency_ms
        )

        # All targets should be positive
        assert config.targets.search_p95_latency_ms > 0
        assert config.targets.upsert_throughput_vectors_per_second > 0
        assert config.targets.concurrent_qps > 0
        assert config.targets.max_memory_usage_mb > 0

    def test_hnsw_configuration_validation(self):
        """Test HNSW configuration validation."""
        config = get_config()

        # HNSW parameters should be within reasonable ranges
        assert config.hnsw_config.m >= 0
        assert config.hnsw_config.payload_m > 0
        assert config.hnsw_config.ef_construct > 0
        assert config.hnsw_config.full_scan_threshold > 0
        assert config.hnsw_config.indexing_threshold > 0

        # Configuration should match story requirements
        assert config.hnsw_config.m == 0
        assert config.hnsw_config.payload_m == 16
        assert config.hnsw_config.ef_construct == 100


if __name__ == "__main__":
    # Run integration tests directly
    pytest.main([__file__, "-v", "--tb=short", "-m", "performance"])
