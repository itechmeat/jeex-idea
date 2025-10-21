"""
Vector Database Performance Testing Suite.

Comprehensive performance benchmarking framework for validating vector database
requirements and monitoring performance characteristics over time.

Components:
- VectorPerformanceBenchmark: Core benchmarking engine
- PerformanceBenchmarkRunner: Test orchestration and execution
- PerformanceReporter: Results analysis and visualization
- PerformanceMonitor: System resource tracking
- VectorDataGenerator: Realistic test data generation

Requirements Validated:
- REQ-007: Query Performance Optimization - P95 latency < 100ms
- PERF-001: Search Performance - P95 < 100ms at 100K vectors
- PERF-002: Indexing Performance - Batch upsert ≥ 200 vectors/second
- SCALE-002: Concurrent Query Capacity - ≥ 100 QPS
"""

__version__ = "1.0.0"
__author__ = "JEEX Performance Team"

from .test_vector_performance import (
    VectorPerformanceBenchmark,
    PerformanceMetrics,
    BenchmarkConfig,
    VectorDataGenerator,
    PerformanceMonitor,
    TestVectorPerformance,
)

from .benchmark_runner import PerformanceBenchmarkRunner, BenchmarkSuite
from .performance_reporter import PerformanceReporter, PerformanceTrend
from .config import (
    PerformanceTestConfig,
    PerformanceTargets,
    TestConfiguration,
    EnvironmentConfiguration,
    get_config,
    get_performance_threshold,
)

__all__ = [
    # Core benchmarking classes
    "VectorPerformanceBenchmark",
    "PerformanceMetrics",
    "BenchmarkConfig",
    "VectorDataGenerator",
    "PerformanceMonitor",
    # Test orchestration
    "PerformanceBenchmarkRunner",
    "BenchmarkSuite",
    # Reporting and analysis
    "PerformanceReporter",
    "PerformanceTrend",
    # Configuration
    "PerformanceTestConfig",
    "PerformanceTargets",
    "TestConfiguration",
    "EnvironmentConfiguration",
    "get_config",
    "get_performance_threshold",
    # Test classes
    "TestVectorPerformance",
]
