#!/usr/bin/env python3
"""
Vector Database Isolation Test Runner

Comprehensive test runner for vector database isolation and security tests.
Provides detailed reporting and validation of REQ-003 and REQ-008 requirements.

Usage:
    python run_vector_isolation_tests.py [--category=all|isolation|security] [--verbose]
    python run_vector_isolation_tests.py --help
"""

import argparse
import asyncio
import sys
import time
import json
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

import pytest
import httpx
import structlog

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.fixtures.vector_test_data import get_isolation_test_fixtures
from tests.integration.conftest import INTEGRATION_TEST_CONFIG, PerformanceMetrics

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@dataclass
class TestResults:
    """Container for test execution results."""

    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    errors: List[str] = None
    performance_metrics: PerformanceMetrics = None
    security_issues: List[Dict[str, Any]] = None
    requirements_coverage: Dict[str, bool] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.performance_metrics is None:
            self.performance_metrics = PerformanceMetrics()
        if self.security_issues is None:
            self.security_issues = []
        if self.requirements_coverage is None:
            self.requirements_coverage = {}


class VectorIsolationTestRunner:
    """
    Comprehensive test runner for vector database isolation.

    Executes isolation and security tests with detailed reporting and validation.
    """

    def __init__(self, base_url: str = INTEGRATION_TEST_CONFIG["vector_service_url"]):
        """
        Initialize test runner.

        Args:
            base_url: Base URL for vector service

        Raises:
            ValueError: If base_url is invalid
        """
        # Input validation: fail fast on invalid URL
        if not base_url or not isinstance(base_url, str):
            raise ValueError(
                f"base_url must be non-empty string, got: {type(base_url).__name__}"
            )

        from urllib.parse import urlparse

        try:
            parsed = urlparse(base_url)
            if parsed.scheme not in ["http", "https"]:
                raise ValueError(
                    f"base_url must have http or https scheme, got: {parsed.scheme}"
                )
            if not parsed.netloc:
                raise ValueError(
                    f"base_url must have network location (host), got: {base_url}"
                )
        except Exception as e:
            raise ValueError(f"Invalid base_url format: {base_url}") from e

        self.base_url = base_url
        self.results = TestResults()
        self.start_time = None
        self.test_categories = {
            "isolation": [
                "tests/integration/test_vector_isolation.py::test_project_isolation_strict_separation",
                "tests/integration/test_vector_isolation.py::test_project_isolation_cross_language_search",
                "tests/integration/test_vector_isolation.py::test_project_isolation_no_bypass_possible",
                "tests/integration/test_vector_isolation.py::test_language_isolation_strict_separation",
                "tests/integration/test_vector_isolation.py::test_language_isolation_same_project_different_languages",
                "tests/integration/test_vector_isolation.py::test_server_side_filter_enforcement_mandatory",
                "tests/integration/test_vector_isolation.py::test_data_integrity_upsert_tagging",
                "tests/integration/test_vector_isolation.py::test_isolation_comprehensive_verification",
            ],
            "security": [
                "tests/integration/test_vector_security.py::test_mandatory_filter_enforcement",
                "tests/integration/test_vector_security.py::test_data_isolation_zero_tolerance",
                "tests/integration/test_vector_security.py::test_injection_protection",
                "tests/integration/test_vector_security.py::test_boundary_condition_security",
                "tests/integration/test_vector_security.py::test_comprehensive_security_validation",
            ],
        }

    async def run_pre_flight_checks(self) -> bool:
        """
        Perform pre-flight checks before running tests.

        Returns:
            True if all checks pass, False otherwise
        """
        logger.info("Performing pre-flight checks")

        try:
            # Check vector service availability
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/v1/vector/health")
                if response.status_code != 200:
                    logger.error(
                        f"Vector service health check failed: {response.status_code}"
                    )
                    return False

                health_data = response.json()
                logger.info("Vector service is healthy", **health_data)

        except httpx.ConnectError:
            logger.error("Cannot connect to vector service - ensure it's running")
            return False
        except Exception as e:
            logger.error("Pre-flight check failed", error=str(e))
            return False

        logger.info("Pre-flight checks passed")
        return True

    async def run_test_category(self, category: str) -> Dict[str, Any]:
        """
        Run tests for a specific category.

        Args:
            category: Test category to run

        Returns:
            Test execution results
        """
        if category not in self.test_categories:
            raise ValueError(f"Unknown test category: {category}")

        logger.info(f"Running {category} tests")

        test_files = self.test_categories[category]
        if not test_files:
            logger.warning(f"No tests found for category: {category}")
            return {"category": category, "tests_run": 0, "passed": 0, "failed": 0}

        # Prepare pytest arguments
        pytest_args = [
            "-v",
            "--tb=short",
            "--json-report",
            "--json-report-file=/tmp/pytest_report.json",
            *test_files,
        ]

        # Run pytest
        start_time = time.time()
        exit_code = pytest.main(pytest_args)
        duration = time.time() - start_time

        # Parse pytest JSON report if available
        test_results = self._parse_pytest_report("/tmp/pytest_report.json")

        category_results = {
            "category": category,
            "exit_code": exit_code,
            "duration_seconds": duration,
            **test_results,
        }

        # Update overall results
        self.results.total_tests += test_results.get("total", 0)
        self.results.passed_tests += test_results.get("passed", 0)
        self.results.failed_tests += test_results.get("failed", 0)
        self.results.skipped_tests += test_results.get("skipped", 0)

        logger.info(
            f"{category.capitalize()} tests completed",
            duration=duration,
            exit_code=exit_code,
            **test_results,
        )

        return category_results

    def _parse_pytest_report(self, report_path: str) -> Dict[str, Any]:
        """
        Parse pytest JSON report.

        Args:
            report_path: Path to pytest JSON report

        Returns:
            Parsed test results
        """
        try:
            with open(report_path, "r") as f:
                report = json.load(f)

            summary = report.get("summary", {})
            tests = report.get("tests", [])

            # Extract performance metrics from test durations
            for test in tests:
                if "duration" in test:
                    self.results.performance_metrics.record_measurement(
                        operation=test.get("nodeid", "unknown"),
                        duration_ms=test["duration"] * 1000,
                    )

            # Extract security issues from test metadata
            for test in tests:
                if "metadata" in test and "security_issues" in test["metadata"]:
                    self.results.security_issues.extend(
                        test["metadata"]["security_issues"]
                    )

            return {
                "total": summary.get("total", 0),
                "passed": summary.get("passed", 0),
                "failed": summary.get("failed", 0),
                "skipped": summary.get("skipped", 0),
                "error": summary.get("error", 0),
                "duration": summary.get("duration", 0),
            }

        except Exception as e:
            logger.error("Failed to parse pytest report", error=str(e), exc_info=True)
            # Re-raise to preserve error context instead of silently returning empty dict
            raise

    async def validate_requirements_coverage(self) -> Dict[str, bool]:
        """
        Validate that critical requirements are covered by tests.

        TODO(JEEX): Implement proper requirements-to-test coverage mapping
        Current implementation is a placeholder that assumes coverage if any tests exist.
        Real implementation should:
        1. Map test functions to requirement IDs via decorators/metadata
        2. Parse pytest report for per-test requirement tags
        3. Validate each requirement has >=1 passing test
        4. Track which specific tests cover which requirements
        5. Generate detailed coverage report

        Returns:
            Dictionary mapping requirement IDs to coverage status
        """
        requirements = {
            "REQ-003": "Server-Side Filter Enforcement",
            "REQ-008": "Multi-Tenant Data Isolation",
            "SEC-001": "Filter Enforcement",
            "PERF-001": "Search Performance",
            "PERF-002": "Indexing Performance",
        }

        # FIXME: This is a stub implementation - raise NotImplementedError until proper tracking is added
        raise NotImplementedError(
            "TODO(JEEX): Implement proper requirements-to-test coverage mapping. "
            "Current placeholder logic (assume coverage if tests exist) is insufficient for production use. "
            "Real implementation should map test functions to requirement IDs via decorators/metadata."
        )

    async def generate_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive test report.

        Returns:
            Detailed test report
        """
        duration = (time.time() - self.start_time) if self.start_time is not None else 0

        # Get performance statistics
        perf_stats = self.results.performance_metrics.get_statistics()

        # Generate security assessment
        security_score = 100.0
        if self.results.security_issues:
            critical_issues = [
                i
                for i in self.results.security_issues
                if i.get("severity") == "critical"
            ]
            if critical_issues:
                security_score -= len(critical_issues) * 25
            security_score -= len(self.results.security_issues) * 5
        security_score = max(0.0, security_score)

        report = {
            "test_execution": {
                "start_time": datetime.fromtimestamp(self.start_time).isoformat()
                if self.start_time
                else None,
                "duration_seconds": duration,
                "total_tests": self.results.total_tests,
                "passed_tests": self.results.passed_tests,
                "failed_tests": self.results.failed_tests,
                "skipped_tests": self.results.skipped_tests,
                "success_rate": (
                    self.results.passed_tests / max(self.results.total_tests, 1)
                )
                * 100,
            },
            "performance_metrics": perf_stats,
            "security_assessment": {
                "security_score": security_score,
                "security_issues_count": len(self.results.security_issues),
                "security_issues": self.results.security_issues,
            },
            "requirements_coverage": self.results.requirements_coverage,
            "vector_service": {
                "base_url": self.base_url,
                "test_categories": list(self.test_categories.keys()),
            },
        }

        return report

    async def run_all_tests(self) -> Dict[str, Any]:
        """
        Run all test categories.

        Returns:
            Comprehensive test results
        """
        self.start_time = time.time()
        logger.info("Starting comprehensive vector isolation tests")

        # Pre-flight checks
        if not await self.run_pre_flight_checks():
            error_msg = "Pre-flight checks failed - aborting tests"
            logger.error(error_msg)
            self.results.errors.append(error_msg)
            return await self.generate_report()

        # Run all test categories
        categories = list(self.test_categories.keys())
        category_results = {}

        for category in categories:
            try:
                result = await self.run_test_category(category)
                category_results[category] = result
            except Exception as e:
                error_msg = f"Failed to run {category} tests: {e}"
                logger.exception(error_msg, exc_info=True)
                self.results.errors.append(error_msg)
                category_results[category] = {"error": str(e)}
                # Continue with other categories but track error

        # Validate requirements coverage
        await self.validate_requirements_coverage()

        # Generate final report
        report = await self.generate_report()
        report["category_results"] = category_results

        logger.info(
            "Vector isolation tests completed",
            total_tests=self.results.total_tests,
            passed=self.results.passed_tests,
            failed=self.results.failed_tests,
            duration=report["test_execution"]["duration_seconds"],
        )

        return report

    def print_summary(self, report: Dict[str, Any]) -> int:
        """
        Print human-readable test summary and return exit code.

        Args:
            report: Test report to summarize

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        print("\n" + "=" * 80)
        print("VECTOR DATABASE ISOLATION TEST RESULTS")
        print("=" * 80)

        execution = report["test_execution"]
        print(f"\n📊 Test Execution Summary:")
        print(f"   Total Tests: {execution['total_tests']}")
        print(f"   Passed: {execution['passed_tests']}")
        print(f"   Failed: {execution['failed_tests']}")
        print(f"   Skipped: {execution['skipped_tests']}")
        print(f"   Success Rate: {execution['success_rate']:.1f}%")
        print(f"   Duration: {execution['duration_seconds']:.2f}s")

        security = report["security_assessment"]
        print(f"\n🔒 Security Assessment:")
        print(f"   Security Score: {security['security_score']:.1f}/100")
        print(f"   Security Issues: {security['security_issues_count']}")

        if security["security_issues_count"] > 0:
            print("   Issues:")
            for issue in security["security_issues"][:5]:  # Show first 5
                print(
                    f"     - {issue.get('type', 'Unknown')}: {issue.get('description', 'No description')}"
                )
            if len(security["security_issues"]) > 5:
                print(f"     ... and {len(security['security_issues']) - 5} more")

        requirements = report["requirements_coverage"]
        print(f"\n✅ Requirements Coverage:")
        for req_id, covered in requirements.items():
            status = "✅ COVERED" if covered else "❌ MISSING"
            print(f"   {req_id}: {status}")

        performance = report["performance_metrics"]
        if performance:
            print(f"\n⚡ Performance Metrics:")
            print(f"   Mean Response Time: {performance.get('mean_ms', 0):.2f}ms")
            print(f"   P95 Response Time: {performance.get('p95_ms', 0):.2f}ms")
            print(f"   P99 Response Time: {performance.get('p99_ms', 0):.2f}ms")

        # Overall status
        success = execution["failed_tests"] == 0 and security["security_score"] >= 90.0
        status_emoji = "✅ SUCCESS" if success else "❌ FAILURE"
        print(f"\n🎯 Overall Status: {status_emoji}")

        if not success:
            print("\n⚠️  Issues detected - review detailed report above")
            return 1
        else:
            print("\n🎉 All tests passed - isolation requirements satisfied!")
            return 0


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Vector Database Isolation Test Runner"
    )
    parser.add_argument(
        "--category",
        choices=["all", "isolation", "security"],
        default="all",
        help="Test category to run (default: all)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "--base-url",
        default=INTEGRATION_TEST_CONFIG["vector_service_url"],
        help=f"Base URL for vector service (default: {INTEGRATION_TEST_CONFIG['vector_service_url']})",
    )
    parser.add_argument("--output", "-o", help="Output JSON report to file")

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

    # Create and run test runner
    runner = VectorIsolationTestRunner(base_url=args.base_url)

    try:
        if args.category == "all":
            report = await runner.run_all_tests()
        else:
            # Run specific category
            if not await runner.run_pre_flight_checks():
                print("❌ Pre-flight checks failed")
                return 1

            category_result = await runner.run_test_category(args.category)
            report = await runner.generate_report()
            report["category_results"] = {args.category: category_result}

        # Save JSON report if requested
        if args.output:
            with open(args.output, "w") as f:
                json.dump(report, f, indent=2)
            print(f"\n📄 Detailed report saved to: {args.output}")

        # Print summary and return exit code
        return runner.print_summary(report)

    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        return 130
    except Exception as e:
        print(f"\n💥 Test runner failed: {e}")
        if args.verbose:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
