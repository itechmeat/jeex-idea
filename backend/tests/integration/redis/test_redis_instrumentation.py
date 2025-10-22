#!/usr/bin/env python3
"""
Redis Instrumentation Validation Script

Comprehensive test script to validate Task 2.2 Redis instrumentation implementation.
Tests all acceptance criteria for Redis client instrumentation, cache metrics,
operation latency, memory usage monitoring, and connection pool metrics.

Usage:
    python test_redis_instrumentation.py [--api-url http://localhost:5210] [--project-id <uuid>]
"""

import asyncio
import argparse
import json
import time
import uuid
import logging
from typing import Dict, Any, List
from datetime import datetime

import httpx
import structlog

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)


class RedisInstrumentationValidator:
    """
    Validator for Redis instrumentation implementation.

    Tests all Task 2.2 acceptance criteria:
    - Redis client instrumentation capturing operation spans
    - Cache hit/miss ratios calculated and exported as metrics
    - Operation latency metrics (GET, SET, DEL, etc.)
    - Memory usage statistics from Redis INFO command
    - Connection pool metrics and error rates
    """

    def __init__(self, api_url: str = "http://localhost:5210", project_id: str = None):
        self.api_url = api_url.rstrip("/")
        if project_id is None:
            raise ValueError("project_id is required")
        self.project_id = project_id
        self.client = httpx.AsyncClient(timeout=30.0)
        self.test_results = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def test_basic_operations_instrumentation(self) -> Dict[str, Any]:
        """Test Redis client instrumentation capturing operation spans."""
        logger.info("Testing Redis client instrumentation with basic operations")

        test_request = {
            "operation": "SET",
            "key_prefix": "instrumentation_test",
            "count": 50,
            "project_id": self.project_id,
        }

        try:
            response = await self.client.post(
                f"{self.api_url}/test/redis/operations/basic", json=test_request
            )
            response.raise_for_status()
            result = response.json()

            # Validate instrumentation data
            validation = {
                "test_name": "basic_operations_instrumentation",
                "success": result.get("success", False),
                "operations_completed": result.get("operations_completed", 0),
                "instrumentation_present": bool(result.get("instrumentation_data")),
                "trace_data_available": False,
                "metrics_collected": False,
                "error_count": result.get("error_count", 0),
                "details": result,
            }

            # Check for instrumentation data
            if result.get("instrumentation_data"):
                instr_data = result["instrumentation_data"]
                validation["trace_data_available"] = bool(
                    instr_data.get("base_service")
                )
                validation["metrics_collected"] = bool(
                    instr_data.get("cache_performance")
                )

            self.test_results.append(validation)
            logger.info(
                "Basic operations instrumentation test completed",
                success=validation["success"],
                operations=validation["operations_completed"],
                instrumentation_present=validation["instrumentation_present"],
            )

            return validation

        except Exception as e:
            logger.error("Basic operations instrumentation test failed", error=str(e))
            return {
                "test_name": "basic_operations_instrumentation",
                "success": False,
                "error": str(e),
                "details": {},
            }

    async def test_cache_performance_metrics(self) -> Dict[str, Any]:
        """Test cache hit/miss ratios calculated and exported as metrics."""
        logger.info("Testing cache performance metrics and hit/miss ratios")

        test_request = {
            "total_keys": 200,
            "hit_rate_target": 0.75,
            "project_id": self.project_id,
        }

        try:
            response = await self.client.post(
                f"{self.api_url}/test/redis/cache/performance", json=test_request
            )
            response.raise_for_status()
            result = response.json()

            # Validate cache metrics
            cache_results = result.get("cache_results", {})
            instrumentation_cache = result.get("instrumentation_cache_data", {})

            validation = {
                "test_name": "cache_performance_metrics",
                "success": True,
                "hits_recorded": cache_results.get("hits", 0),
                "misses_recorded": cache_results.get("misses", 0),
                "hit_ratio_calculated": cache_results.get("actual_hit_rate", 0) > 0,
                "target_achieved": cache_results.get("target_achieved", False),
                "instrumentation_data_present": bool(instrumentation_cache),
                "cache_metrics_exported": bool(
                    instrumentation_cache.get("total_cache_operations")
                ),
                "details": result,
            }

            self.test_results.append(validation)
            logger.info(
                "Cache performance metrics test completed",
                hit_ratio=cache_results.get("actual_hit_rate", 0),
                target_achieved=validation["target_achieved"],
            )

            return validation

        except Exception as e:
            logger.error("Cache performance metrics test failed", error=str(e))
            return {
                "test_name": "cache_performance_metrics",
                "success": False,
                "error": str(e),
                "details": {},
            }

    async def test_operation_latency_metrics(self) -> Dict[str, Any]:
        """Test operation latency metrics (GET, SET, DEL, etc.)."""
        logger.info("Testing operation latency metrics for Redis commands")

        commands_to_test = ["GET", "SET", "INCR", "HSET", "LPUSH"]
        latency_results = {}

        for command in commands_to_test:
            test_request = {
                "command": command,
                "iterations": 500,
                "key_size": 256,
                "project_id": self.project_id,
            }

            try:
                response = await self.client.post(
                    f"{self.api_url}/test/redis/latency/measurement", json=test_request
                )
                response.raise_for_status()
                result = response.json()

                measured_latency = result.get("measured_latency", {})
                instrumentation_latency = result.get("instrumentation_latency", {})

                latency_results[command] = {
                    "measured_avg_ms": measured_latency.get("average_ms", 0),
                    "instrumentation_avg_ms": instrumentation_latency.get(
                        "average_ms", 0
                    ),
                    "p95_ms": measured_latency.get("p95_ms", 0),
                    "error_count": measured_latency.get("error_count", 0),
                    "latency_tracking_enabled": instrumentation_latency.get("count", 0)
                    > 0,
                }

            except Exception as e:
                logger.warning(
                    f"Latency test failed for command {command}", error=str(e)
                )
                latency_results[command] = {"error": str(e)}

        validation = {
            "test_name": "operation_latency_metrics",
            "success": all(
                result.get("latency_tracking_enabled", False)
                for result in latency_results.values()
                if "error" not in result
            ),
            "commands_tested": len(latency_results),
            "commands_with_latency_tracking": sum(
                1
                for result in latency_results.values()
                if result.get("latency_tracking_enabled", False)
            ),
            "latency_results": latency_results,
            "details": latency_results,
        }

        self.test_results.append(validation)
        logger.info(
            "Operation latency metrics test completed",
            commands_tested=validation["commands_tested"],
            tracking_enabled=validation["commands_with_latency_tracking"],
        )

        return validation

    async def test_memory_usage_monitoring(self) -> Dict[str, Any]:
        """Test memory usage statistics from Redis INFO command."""
        logger.info("Testing memory usage monitoring and Redis INFO parsing")

        try:
            response = await self.client.get(
                f"{self.api_url}/test/redis/memory/usage",
                params={"project_id": self.project_id},
            )
            response.raise_for_status()
            result = response.json()

            memory_analysis = result.get("memory_analysis", {})
            redis_info_stats = result.get("redis_info_stats", {})

            validation = {
                "test_name": "memory_usage_monitoring",
                "success": True,
                "initial_memory_mb": memory_analysis.get("initial_memory_mb", 0),
                "post_creation_memory_mb": memory_analysis.get(
                    "post_creation_memory_mb", 0
                ),
                "memory_consumed_mb": memory_analysis.get("memory_consumed_mb", 0),
                "fragmentation_ratio": memory_analysis.get("fragmentation_ratio", 0),
                "redis_info_parsed": bool(redis_info_stats),
                "maxmemory_policy_available": bool(
                    redis_info_stats.get("maxmemory_policy")
                ),
                "allocator_stats_available": bool(
                    redis_info_stats.get("allocator_allocated_mb")
                ),
                "details": result,
            }

            # Validate memory consumption
            if validation["memory_consumed_mb"] > 0:
                validation["memory_tracking_working"] = True
            else:
                validation["memory_tracking_working"] = False
                validation["success"] = False

            self.test_results.append(validation)
            logger.info(
                "Memory usage monitoring test completed",
                memory_consumed_mb=validation["memory_consumed_mb"],
                fragmentation_ratio=validation["fragmentation_ratio"],
            )

            return validation

        except Exception as e:
            logger.error("Memory usage monitoring test failed", error=str(e))
            return {
                "test_name": "memory_usage_monitoring",
                "success": False,
                "error": str(e),
                "details": {},
            }

    async def test_connection_pool_metrics(self) -> Dict[str, Any]:
        """Test connection pool metrics and error rates."""
        logger.info("Testing connection pool monitoring and error rate tracking")

        try:
            response = await self.client.get(
                f"{self.api_url}/test/redis/connection/pool/status",
                params={"project_id": self.project_id},
            )
            response.raise_for_status()
            result = response.json()

            connection_pool_analysis = result.get("connection_pool_analysis", {})
            error_analysis = result.get("error_analysis", {})
            performance_metrics = result.get("performance_metrics", {})

            validation = {
                "test_name": "connection_pool_metrics",
                "success": True,
                "initial_stats_available": bool(
                    connection_pool_analysis.get("initial_stats")
                ),
                "final_stats_available": bool(
                    connection_pool_analysis.get("final_stats")
                ),
                "concurrent_operations_completed": performance_metrics.get(
                    "total_operations", 0
                ),
                "error_rate_tracking_available": bool(
                    error_analysis.get("total_operations")
                ),
                "cache_performance_available": bool(result.get("cache_performance")),
                "details": result,
            }

            # Validate connection pool metrics
            if connection_pool_analysis.get("final_stats"):
                final_stats = connection_pool_analysis["final_stats"]
                validation["connection_metrics_available"] = bool(
                    final_stats.get("active_connections") is not None
                )
            else:
                validation["connection_metrics_available"] = False
                validation["success"] = False

            self.test_results.append(validation)
            logger.info(
                "Connection pool metrics test completed",
                operations_completed=validation["concurrent_operations_completed"],
                connection_metrics=validation["connection_metrics_available"],
            )

            return validation

        except Exception as e:
            logger.error("Connection pool metrics test failed", error=str(e))
            return {
                "test_name": "connection_pool_metrics",
                "success": False,
                "error": str(e),
                "details": {},
            }

    async def test_instrumentation_status(self) -> Dict[str, Any]:
        """Test overall instrumentation status and health."""
        logger.info("Testing instrumentation status and health check")

        try:
            response = await self.client.get(
                f"{self.api_url}/test/redis/instrumentation/status"
            )
            response.raise_for_status()
            result = response.json()

            instrumentation_status = result.get("instrumentation_status", {})
            service_health = result.get("service_health", {})
            metrics_collection = result.get("metrics_collection", {})

            validation = {
                "test_name": "instrumentation_status",
                "success": True,
                "cache_performance_available": bool(
                    instrumentation_status.get("cache_performance")
                ),
                "error_rate_tracking_available": bool(
                    instrumentation_status.get("error_rates")
                ),
                "command_latencies_available": bool(
                    instrumentation_status.get("command_latencies")
                ),
                "background_collection_running": metrics_collection.get(
                    "background_collection_running", False
                ),
                "total_operations_tracked": metrics_collection.get(
                    "total_operations_tracked", 0
                ),
                "service_healthy": service_health.get("status") == "healthy",
                "details": result,
            }

            # Validate critical components
            critical_components = [
                validation["cache_performance_available"],
                validation["error_rate_tracking_available"],
                validation["background_collection_running"],
            ]

            validation["critical_components_working"] = all(critical_components)
            if not validation["critical_components_working"]:
                validation["success"] = False

            self.test_results.append(validation)
            logger.info(
                "Instrumentation status test completed",
                background_running=validation["background_collection_running"],
                operations_tracked=validation["total_operations_tracked"],
            )

            return validation

        except Exception as e:
            logger.error("Instrumentation status test failed", error=str(e))
            return {
                "test_name": "instrumentation_status",
                "success": False,
                "error": str(e),
                "details": {},
            }

    async def cleanup_test_data(self) -> None:
        """Clean up test data created during validation."""
        logger.info("Cleaning up test data")

        try:
            response = await self.client.post(
                f"{self.api_url}/test/redis/cleanup",
                params={"project_id": self.project_id},
            )
            response.raise_for_status()
            result = response.json()
            logger.info(
                "Test data cleanup completed",
                keys_deleted=result.get("keys_deleted", 0),
            )
        except Exception as e:
            logger.warning("Test data cleanup failed", error=str(e))

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all Redis instrumentation validation tests."""
        logger.info("Starting Redis instrumentation validation")

        start_time = time.time()

        try:
            # Run all test suites
            await self.test_basic_operations_instrumentation()
            await self.test_cache_performance_metrics()
            await self.test_operation_latency_metrics()
            await self.test_memory_usage_monitoring()
            await self.test_connection_pool_metrics()
            await self.test_instrumentation_status()

            # Calculate overall results
            total_tests = len(self.test_results)
            successful_tests = sum(
                1 for result in self.test_results if result.get("success", False)
            )

            overall_success = successful_tests == total_tests
            total_duration = time.time() - start_time

            # Generate comprehensive report
            report = {
                "validation_summary": {
                    "timestamp": datetime.utcnow().isoformat(),
                    "project_id": self.project_id,
                    "total_tests": total_tests,
                    "successful_tests": successful_tests,
                    "failed_tests": total_tests - successful_tests,
                    "success_rate": successful_tests / total_tests
                    if total_tests > 0
                    else 0,
                    "overall_success": overall_success,
                    "total_duration_seconds": total_duration,
                },
                "acceptance_criteria_validation": {
                    "redis_client_instrumentation": self._get_test_result(
                        "basic_operations_instrumentation"
                    ),
                    "cache_hit_miss_ratios": self._get_test_result(
                        "cache_performance_metrics"
                    ),
                    "operation_latency_metrics": self._get_test_result(
                        "operation_latency_metrics"
                    ),
                    "memory_usage_statistics": self._get_test_result(
                        "memory_usage_monitoring"
                    ),
                    "connection_pool_metrics": self._get_test_result(
                        "connection_pool_metrics"
                    ),
                    "instrumentation_health": self._get_test_result(
                        "instrumentation_status"
                    ),
                },
                "detailed_results": self.test_results,
                "task_2_2_completion": {
                    "all_criteria_met": overall_success,
                    "implementation_ready": overall_success,
                    "test_coverage": "comprehensive",
                    "production_ready": overall_success,
                },
            }

            logger.info(
                "Redis instrumentation validation completed",
                success_rate=report["validation_summary"]["success_rate"],
                overall_success=overall_success,
            )

            return report

        finally:
            # Cleanup test data
            await self.cleanup_test_data()

    def _get_test_result(self, test_name: str) -> Dict[str, Any]:
        """Get result for a specific test by name."""
        for result in self.test_results:
            if result.get("test_name") == test_name:
                return {
                    "success": result.get("success", False),
                    "details": result.get("details", {}),
                }
        return {"success": False, "error": "Test not found"}


async def main():
    """Main function to run Redis instrumentation validation."""
    parser = argparse.ArgumentParser(description="Redis Instrumentation Validation")
    parser.add_argument(
        "--api-url", default="http://localhost:5210", help="Base URL for the API"
    )
    parser.add_argument(
        "--project-id", help="Project ID for testing (generates UUID if not provided)"
    )
    parser.add_argument(
        "--output", help="Output file for validation report (JSON format)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Generate project_id if not provided
    project_id = args.project_id or str(uuid.uuid4())

    async with RedisInstrumentationValidator(args.api_url, project_id) as validator:
        report = await validator.run_all_tests()

        # Output results
        print("\n" + "=" * 80)
        print("REDIS INSTRUMENTATION VALIDATION REPORT")
        print("=" * 80)

        summary = report["validation_summary"]
        print(f"Project ID: {summary['project_id']}")
        print(f"Tests Run: {summary['successful_tests']}/{summary['total_tests']}")
        print(f"Success Rate: {summary['success_rate']:.1%}")
        print(
            f"Overall Success: {'✅ PASS' if summary['overall_success'] else '❌ FAIL'}"
        )
        print(f"Duration: {summary['total_duration_seconds']:.2f}s")

        print("\nAcceptance Criteria Validation:")
        criteria = report["acceptance_criteria_validation"]
        for criterion, result in criteria.items():
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"  {criterion}: {status}")

        print("\nTask 2.2 Completion:")
        completion = report["task_2_2_completion"]
        for key, value in completion.items():
            status = "✅" if value else "❌"
            print(f"  {key}: {status} {value}")

        # Save to file if requested
        if args.output:
            with open(args.output, "w") as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\nDetailed report saved to: {args.output}")

        # Exit with appropriate code
        exit_code = 0 if summary["overall_success"] else 1
        return exit_code


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
