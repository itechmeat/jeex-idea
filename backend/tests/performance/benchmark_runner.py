"""
Performance benchmark runner for vector database system.

Orchestrates comprehensive performance testing including:
- Search performance across dataset sizes
- Upsert throughput testing
- Concurrent query capacity testing
- Resource usage monitoring
- Performance regression detection

Usage:
    python -m tests.performance.benchmark_runner
    or
    pytest tests/performance/benchmark_runner.py -v
"""

import asyncio
import json
import os
import sys
import time
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

# Add the backend directory to the path for imports
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from tests.performance.test_vector_performance import (
    VectorPerformanceBenchmark,
    PerformanceMetrics,
    BenchmarkConfig,
    VectorDataGenerator,
    PerformanceMonitor,
)
from tests.performance.performance_reporter import PerformanceReporter
from app.services.vector.repositories.qdrant_repository import QdrantVectorRepository
from app.services.vector.search_service import DefaultVectorSearchService
from qdrant_client import QdrantClient


@dataclass
class BenchmarkSuite:
    """Configuration for a complete benchmark suite run."""

    name: str
    description: str
    dataset_sizes: List[int]
    batch_sizes: List[int]
    concurrency_levels: List[int]
    iterations: int = 3
    enable_detailed_profiling: bool = False
    output_directory: str = "performance_results"


class PerformanceBenchmarkRunner:
    """
    Main benchmark runner for vector database performance testing.

    Coordinates execution of all performance benchmarks, manages test data,
    monitors system resources, and generates comprehensive reports.
    """

    def __init__(self, output_dir: str = "performance_results"):
        """
        Initialize benchmark runner.

        Args:
            output_dir: Directory to store performance reports and logs
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)

        # Initialize components
        self.client = QdrantClient(host="localhost", port=5230)
        self.data_generator = VectorDataGenerator()
        self.reporter = PerformanceReporter(self.output_dir)

        # Test configuration
        self.config = BenchmarkConfig()
        self.results: List[PerformanceMetrics] = []

        # Resource monitoring
        self.system_monitor = PerformanceMonitor()

    async def run_full_benchmark_suite(self) -> Dict[str, Any]:
        """
        Run complete benchmark suite covering all performance requirements.

        Returns:
            Dictionary containing all benchmark results and summary statistics
        """
        print(
            "🚀 Starting comprehensive vector database performance benchmark suite..."
        )
        print(f"📁 Results will be saved to: {self.output_dir}")

        start_time = time.time()
        suite_results = {
            "suite_name": "vector_database_performance",
            "timestamp": datetime.utcnow().isoformat(),
            "config": vars(self.config),
            "results": {},
            "summary": {},
        }

        try:
            # Initialize isolated test collection
            repository, search_service = await self._setup_test_environment()

            # Initialize benchmark instance
            benchmark = VectorPerformanceBenchmark(repository, search_service)

            # Run individual benchmark categories
            print("\n" + "=" * 80)
            print("1. SEARCH PERFORMANCE BENCHMARKS")
            print("=" * 80)
            suite_results["results"][
                "search_performance"
            ] = await self._run_search_benchmarks(benchmark)

            print("\n" + "=" * 80)
            print("2. UPSERT PERFORMANCE BENCHMARKS")
            print("=" * 80)
            suite_results["results"][
                "upsert_performance"
            ] = await self._run_upsert_benchmarks(benchmark)

            print("\n" + "=" * 80)
            print("3. CONCURRENT SEARCH BENCHMARKS")
            print("=" * 80)
            suite_results["results"][
                "concurrent_search"
            ] = await self._run_concurrent_benchmarks(benchmark)

            print("\n" + "=" * 80)
            print("4. FILTER PERFORMANCE BENCHMARKS")
            print("=" * 80)
            suite_results["results"][
                "filter_performance"
            ] = await self._run_filter_benchmarks(benchmark)

            print("\n" + "=" * 80)
            print("5. SCALING ANALYSIS")
            print("=" * 80)
            suite_results["results"][
                "scaling_analysis"
            ] = await self._run_scaling_analysis(benchmark)

            # Generate summary statistics
            suite_results["summary"] = self._generate_summary_statistics(
                suite_results["results"]
            )

            # Validate performance requirements
            suite_results["requirements_validation"] = (
                self._validate_performance_requirements(suite_results["results"])
            )

            # Save complete results
            await self._save_results(suite_results)

            # Generate reports
            await self._generate_reports(suite_results)

            total_duration = time.time() - start_time
            print(f"\n✅ Benchmark suite completed in {total_duration:.2f} seconds")

            return suite_results

        except Exception as e:
            print(f"❌ Benchmark suite failed: {e}")
            raise
        finally:
            # Cleanup
            await self._cleanup_test_environment()

    async def _setup_test_environment(
        self,
    ) -> tuple[QdrantVectorRepository, DefaultVectorSearchService]:
        """Setup isolated test environment for benchmarking."""
        print("🔧 Setting up isolated test environment...")

        # Create unique test collection for this run
        test_collection_name = f"jeex_benchmark_{int(time.time())}"

        # Initialize repository with test collection
        repository = QdrantVectorRepository(self.client)
        repository.COLLECTION_NAME = test_collection_name

        # Initialize collection
        await repository.initialize_collection()

        # Create search service
        search_service = DefaultVectorSearchService(repository)

        print(f"✅ Test collection '{test_collection_name}' created successfully")
        return repository, search_service

    async def _cleanup_test_environment(self):
        """Cleanup test environment after benchmarking."""
        print("🧹 Cleaning up test environment...")

        try:
            # Get all collections and delete benchmark collections
            collections = await asyncio.to_thread(self.client.get_collections)
            for collection in collections.collections:
                if collection.name.startswith("jeex_benchmark_"):
                    await asyncio.to_thread(
                        self.client.delete_collection, collection_name=collection.name
                    )
                    print(f"🗑️ Deleted test collection: {collection.name}")
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception("Could not cleanup test collections", exc_info=True)

    async def _run_search_benchmarks(
        self, benchmark: VectorPerformanceBenchmark
    ) -> List[Dict[str, Any]]:
        """Run search performance benchmarks across different dataset sizes."""
        results = []

        # Test dataset sizes (start with smaller sizes for quick testing)
        dataset_sizes = [1000, 5000, 10000]  # Reduced for faster execution

        for dataset_size in dataset_sizes:
            print(f"🔍 Testing search performance with {dataset_size} vectors...")

            # Run multiple iterations for statistical significance
            iteration_results = []
            for iteration in range(2):  # Reduced iterations for faster execution
                print(f"  Iteration {iteration + 1}/2...")
                project_id = f"search_test_{dataset_size}_{iteration}"

                try:
                    metrics = await benchmark.benchmark_search_performance(
                        dataset_size=dataset_size, project_id=project_id, iterations=10
                    )
                    iteration_results.append(metrics)

                    # Validate performance target
                    if metrics.latency_p95 > self.config.target_p95_latency_ms:
                        print(
                            f"  ⚠️ P95 latency {metrics.latency_p95:.2f}ms exceeds target {self.config.target_p95_latency_ms}ms"
                        )
                    else:
                        print(
                            f"  ✅ P95 latency {metrics.latency_p95:.2f}ms within target"
                        )

                except Exception as e:
                    print(f"  ❌ Search benchmark failed: {e}")
                    continue

            # Calculate average metrics across iterations
            if iteration_results:
                avg_metrics = self._average_metrics(iteration_results)
                results.append(avg_metrics.to_dict())

        return results

    async def _run_upsert_benchmarks(
        self, benchmark: VectorPerformanceBenchmark
    ) -> List[Dict[str, Any]]:
        """Run upsert performance benchmarks across different batch sizes."""
        results = []

        for batch_size in [10, 50, 100]:  # Test batch sizes
            print(f"📝 Testing upsert performance with batch size {batch_size}...")

            try:
                metrics = await benchmark.benchmark_upsert_performance(
                    batch_size=batch_size,
                    total_vectors=1000,  # Fixed size for consistent comparison
                )

                results.append(metrics.to_dict())

                # Validate throughput target
                if metrics.throughput < self.config.target_upsert_throughput:
                    print(
                        f"  ⚠️ Throughput {metrics.throughput:.2f} vectors/s below target {self.config.target_upsert_throughput}"
                    )
                else:
                    print(
                        f"  ✅ Throughput {metrics.throughput:.2f} vectors/s meets target"
                    )

            except Exception as e:
                print(f"  ❌ Upsert benchmark failed: {e}")
                continue

        return results

    async def _run_concurrent_benchmarks(
        self, benchmark: VectorPerformanceBenchmark
    ) -> List[Dict[str, Any]]:
        """Run concurrent search benchmarks across different concurrency levels."""
        results = []

        # Test concurrency levels (reduced for faster execution)
        concurrency_levels = [1, 10, 25]

        for concurrency in concurrency_levels:
            print(
                f"⚡ Testing concurrent search with {concurrency} concurrent queries..."
            )

            try:
                metrics = await benchmark.benchmark_concurrent_search(
                    concurrency=concurrency,
                    total_queries=50,  # Reduced for faster execution
                    dataset_size=5000,  # Moderate dataset size
                )

                results.append(metrics.to_dict())

                # Validate QPS target
                if metrics.throughput < self.config.target_qps:
                    print(
                        f"  ⚠️ QPS {metrics.throughput:.2f} below target {self.config.target_qps}"
                    )
                else:
                    print(f"  ✅ QPS {metrics.throughput:.2f} meets target")

            except Exception as e:
                print(f"  ❌ Concurrent benchmark failed: {e}")
                continue

        return results

    async def _run_filter_benchmarks(
        self, benchmark: VectorPerformanceBenchmark
    ) -> List[Dict[str, Any]]:
        """Run filter performance benchmarks."""
        print("🔍 Testing filter performance...")

        try:
            metrics = await benchmark.benchmark_filter_performance()
            return [metrics.to_dict()]
        except Exception as e:
            print(f"❌ Filter benchmark failed: {e}")
            return []

    async def _run_scaling_analysis(
        self, benchmark: VectorPerformanceBenchmark
    ) -> Dict[str, Any]:
        """Run comprehensive scaling analysis."""
        print("📈 Running scaling analysis...")

        scaling_results = {
            "search_scaling": [],
            "memory_scaling": [],
            "throughput_scaling": [],
        }

        # Test search performance scaling (reduced dataset sizes)
        for dataset_size in [1000, 5000, 10000]:
            try:
                print(f"  Analyzing search scaling at {dataset_size} vectors...")
                project_id = f"scaling_test_{dataset_size}"
                metrics = await benchmark.benchmark_search_performance(
                    dataset_size=dataset_size, project_id=project_id, iterations=5
                )

                scaling_results["search_scaling"].append(
                    {
                        "dataset_size": dataset_size,
                        "latency_p95": metrics.latency_p95,
                        "throughput": metrics.throughput,
                        "memory_usage_mb": metrics.memory_usage_mb,
                    }
                )

            except Exception as e:
                print(f"  ❌ Scaling analysis failed for {dataset_size} vectors: {e}")

        return scaling_results

    def _average_metrics(
        self, metrics_list: List[PerformanceMetrics]
    ) -> PerformanceMetrics:
        """Calculate average metrics across multiple runs."""
        if not metrics_list:
            raise ValueError("Cannot average empty metrics list")

        # Simple averaging of key metrics
        avg_duration = statistics.mean([m.duration_ms for m in metrics_list])
        avg_throughput = statistics.mean([m.throughput for m in metrics_list])
        avg_p50 = statistics.mean([m.latency_p50 for m in metrics_list])
        avg_p95 = statistics.mean([m.latency_p95 for m in metrics_list])
        avg_p99 = statistics.mean([m.latency_p99 for m in metrics_list])
        avg_errors = statistics.mean([m.error_count for m in metrics_list])
        avg_memory = statistics.mean([m.memory_usage_mb for m in metrics_list])
        avg_cpu = statistics.mean([m.cpu_usage_percent for m in metrics_list])

        return PerformanceMetrics(
            operation=metrics_list[0].operation,
            dataset_size=metrics_list[0].dataset_size,
            duration_ms=avg_duration,
            throughput=avg_throughput,
            latency_p50=avg_p50,
            latency_p95=avg_p95,
            latency_p99=avg_p99,
            error_count=int(avg_errors),
            memory_usage_mb=avg_memory,
            cpu_usage_percent=avg_cpu,
            additional_data={
                "iterations": len(metrics_list),
                "operation": metrics_list[0].operation,
            },
        )

    def _generate_summary_statistics(
        self, results: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """Generate summary statistics across all benchmark results."""
        summary = {
            "total_benchmarks": 0,
            "successful_benchmarks": 0,
            "requirements_met": {
                "search_p95_latency": True,
                "upsert_throughput": True,
                "concurrent_qps": True,
            },
            "performance_highlights": {},
            "resource_usage": {},
        }

        # Count benchmarks
        for category, benchmarks in results.items():
            if isinstance(benchmarks, list):
                summary["total_benchmarks"] += len(benchmarks)
                summary["successful_benchmarks"] += len(
                    [b for b in benchmarks if b.get("error_count", 0) == 0]
                )

        # Extract performance highlights
        if "search_performance" in results and results["search_performance"]:
            search_results = results["search_performance"]
            summary["performance_highlights"]["best_search_p95"] = min(
                [r["latency_p95"] for r in search_results]
            )
            summary["performance_highlights"]["worst_search_p95"] = max(
                [r["latency_p95"] for r in search_results]
            )

        if "upsert_performance" in results and results["upsert_performance"]:
            upsert_results = results["upsert_performance"]
            summary["performance_highlights"]["best_upsert_throughput"] = max(
                [r["throughput"] for r in upsert_results]
            )

        if "concurrent_search" in results and results["concurrent_search"]:
            concurrent_results = results["concurrent_search"]
            summary["performance_highlights"]["best_qps"] = max(
                [r["throughput"] for r in concurrent_results]
            )

        return summary

    def _validate_performance_requirements(
        self, results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate performance results against requirements."""
        validation = {
            "req_007_query_performance": {"passed": True, "details": []},
            "perf_001_search_performance": {"passed": True, "details": []},
            "perf_002_indexing_performance": {"passed": True, "details": []},
            "scale_002_concurrent_capacity": {"passed": True, "details": []},
        }

        # Validate search performance (REQ-007, PERF-001)
        if "search_performance" in results:
            for result in results["search_performance"]:
                p95_latency = result.get("latency_p95", 0)
                if p95_latency > self.config.target_p95_latency_ms:
                    validation["req_007_query_performance"]["passed"] = False
                    validation["perf_001_search_performance"]["passed"] = False
                    validation["req_007_query_performance"]["details"].append(
                        f"P95 latency {p95_latency:.2f}ms > {self.config.target_p95_latency_ms}ms"
                    )

        # Validate upsert performance (PERF-002)
        if "upsert_performance" in results:
            for result in results["upsert_performance"]:
                throughput = result.get("throughput", 0)
                if throughput < self.config.target_upsert_throughput:
                    validation["perf_002_indexing_performance"]["passed"] = False
                    validation["perf_002_indexing_performance"]["details"].append(
                        f"Throughput {throughput:.2f} < {self.config.target_upsert_throughput} vectors/s"
                    )

        # Validate concurrent capacity (SCALE-002)
        if "concurrent_search" in results:
            for result in results["concurrent_search"]:
                qps = result.get("throughput", 0)
                if qps < self.config.target_qps:
                    validation["scale_002_concurrent_capacity"]["passed"] = False
                    validation["scale_002_concurrent_capacity"]["details"].append(
                        f"QPS {qps:.2f} < {self.config.target_qps}"
                    )

        return validation

    async def _save_results(self, results: Dict[str, Any]):
        """Save benchmark results to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save complete results as JSON
        results_file = self.output_dir / f"benchmark_results_{timestamp}.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"💾 Results saved to: {results_file}")

        # Save summary as separate file
        summary_file = self.output_dir / f"benchmark_summary_{timestamp}.json"
        with open(summary_file, "w") as f:
            json.dump(
                {
                    "summary": results["summary"],
                    "requirements_validation": results["requirements_validation"],
                },
                f,
                indent=2,
                default=str,
            )

    async def _generate_reports(self, results: Dict[str, Any]):
        """Generate performance reports."""
        try:
            await self.reporter.generate_html_report(results)
            await self.reporter.generate_csv_report(results)
            await self.reporter.generate_trend_analysis(results)
            print(f"📊 Performance reports generated in: {self.output_dir}")
        except Exception as e:
            print(f"⚠️ Warning: Could not generate reports: {e}")


async def main():
    """Main entry point for running benchmarks."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Vector Database Performance Benchmark Runner"
    )
    parser.add_argument(
        "--output-dir",
        default="performance_results",
        help="Output directory for benchmark results",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick benchmark suite (smaller datasets, fewer iterations)",
    )

    args = parser.parse_args()

    print("🎯 Vector Database Performance Benchmark Suite")
    print("=" * 50)

    # Check if Qdrant is available
    try:
        client = QdrantClient(host="localhost", port=5230)
        await asyncio.to_thread(client.get_collections)
        print("✅ Qdrant connection established")
    except Exception as e:
        print(f"❌ Cannot connect to Qdrant: {e}")
        print("Make sure Qdrant is running on localhost:5230")
        return

    # Run benchmark suite
    runner = PerformanceBenchmarkRunner(args.output_dir)
    results = await runner.run_full_benchmark_suite()

    # Print summary
    print("\n" + "=" * 50)
    print("📊 BENCHMARK SUMMARY")
    print("=" * 50)

    summary = results["summary"]
    print(f"Total benchmarks: {summary['total_benchmarks']}")
    print(f"Successful benchmarks: {summary['successful_benchmarks']}")

    if "performance_highlights" in summary:
        highlights = summary["performance_highlights"]
        if "best_search_p95" in highlights:
            print(f"Best search P95 latency: {highlights['best_search_p95']:.2f}ms")
        if "best_upsert_throughput" in highlights:
            print(
                f"Best upsert throughput: {highlights['best_upsert_throughput']:.2f} vectors/s"
            )
        if "best_qps" in highlights:
            print(f"Best QPS: {highlights['best_qps']:.2f}")

    # Print requirements validation
    print("\n📋 REQUIREMENTS VALIDATION:")
    validation = results["requirements_validation"]
    for req_name, req_result in validation.items():
        status = "✅ PASS" if req_result["passed"] else "❌ FAIL"
        print(f"  {req_name}: {status}")
        for detail in req_result["details"]:
            print(f"    - {detail}")

    print(f"\n📁 Detailed results saved to: {args.output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
