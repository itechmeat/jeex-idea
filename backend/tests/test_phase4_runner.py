"""
Phase 4 Test Runner - Complete Integration and Testing Suite

Comprehensive test runner for Phase 4 integration that validates:
1. All functional requirements (REQ-001 through REQ-008)
2. All non-functional requirements (PERF-001, PERF-002, SEC-001, SEC-002, SEC-003, REL-001, REL-002, REL-003)
3. Complete integration between database and application
4. Production readiness validation
"""

import pytest
import asyncio
import sys
import os
import time
import logging
from typing import Dict, List, Any
from datetime import datetime

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("phase4_test_results.log")],
)

logger = logging.getLogger(__name__)


class Phase4TestRunner:
    """Comprehensive test runner for Phase 4 integration."""

    def __init__(self):
        self.test_results = {
            "start_time": datetime.utcnow(),
            "end_time": None,
            "total_duration_seconds": 0,
            "test_categories": {},
            "functional_requirements": {},
            "non_functional_requirements": {},
            "production_readiness": {},
            "overall_status": "pending",
        }

    async def run_all_tests(self):
        """Run complete Phase 4 test suite."""
        logger.info("=" * 80)
        logger.info("STARTING PHASE 4 INTEGRATION AND TESTING SUITE")
        logger.info("=" * 80)

        start_time = time.time()

        try:
            # Test 4.1: Database Integration with FastAPI
            await self._run_database_integration_tests()

            # Test 4.2: Database Operations and Transactions
            await self._run_crud_operations_tests()

            # Test 4.3: Migration Rollback Procedures
            await self._run_migration_rollback_tests()

            # Test 4.4: Failover and Recovery Scenarios
            await self._run_failover_recovery_tests()

            # Test 4.5: Performance Testing and Optimization
            await self._run_performance_tests()

            # Validate functional requirements
            await self._validate_functional_requirements()

            # Validate non-functional requirements
            await self._validate_non_functional_requirements()

            # Production readiness validation
            await self._validate_production_readiness()

            # Generate final report
            self._generate_final_report()

        except Exception as e:
            logger.exception("Test runner failed")
            self.test_results["overall_status"] = "failed"
            raise

        finally:
            self.test_results["end_time"] = datetime.utcnow()
            self.test_results["total_duration_seconds"] = time.time() - start_time

        logger.info("=" * 80)
        logger.info("PHASE 4 INTEGRATION AND TESTING SUITE COMPLETED")
        logger.info("=" * 80)

    async def _run_database_integration_tests(self):
        """Run database integration tests (Task 4.1)."""
        logger.info("Running Database Integration Tests (Task 4.1)...")

        test_category = "database_integration"
        self.test_results["test_categories"][test_category] = {}

        # Test database connection on startup
        try:
            # This would be implemented by running the actual integration tests
            # For now, we'll simulate the test execution
            test_results = await self._run_pytest_tests(
                ["test_phase4_integration.py::TestDatabaseIntegration"]
            )

            self.test_results["test_categories"][test_category] = {
                "status": "passed" if test_results["passed"] else "failed",
                "tests_run": test_results["total"],
                "tests_passed": test_results["passed"],
                "tests_failed": test_results["failed"],
                "duration_seconds": test_results["duration"],
                "details": test_results,
            }

            logger.info(
                f"Database Integration Tests: {test_results['passed']}/{test_results['total']} passed"
            )

        except Exception as e:
            logger.exception("Database integration tests failed")
            self.test_results["test_categories"][test_category] = {
                "status": "failed",
                "error": str(e),
            }
            raise

    async def _run_crud_operations_tests(self):
        """Run CRUD operations and transactions tests (Task 4.2)."""
        logger.info("Running CRUD Operations and Transactions Tests (Task 4.2)...")

        test_category = "crud_operations"
        self.test_results["test_categories"][test_category] = {}

        try:
            test_results = await self._run_pytest_tests(
                ["test_phase4_integration.py::TestCRUDOperations"]
            )

            self.test_results["test_categories"][test_category] = {
                "status": "passed" if test_results["passed"] else "failed",
                "tests_run": test_results["total"],
                "tests_passed": test_results["passed"],
                "tests_failed": test_results["failed"],
                "duration_seconds": test_results["duration"],
                "details": test_results,
            }

            logger.info(
                f"CRUD Operations Tests: {test_results['passed']}/{test_results['total']} passed"
            )

        except Exception as e:
            logger.exception("CRUD operations tests failed")
            self.test_results["test_categories"][test_category] = {
                "status": "failed",
                "error": str(e),
            }
            raise

    async def _run_migration_rollback_tests(self):
        """Run migration rollback procedure tests (Task 4.3)."""
        logger.info("Running Migration Rollback Procedure Tests (Task 4.3)...")

        test_category = "migration_rollback"
        self.test_results["test_categories"][test_category] = {}

        try:
            # Run both integration and specific rollback tests
            test_results = await self._run_pytest_tests(
                [
                    "test_phase4_integration.py::TestMigrationRollback",
                    "test_migration_rollback.py::TestMigrationRollback",
                ]
            )

            self.test_results["test_categories"][test_category] = {
                "status": "passed" if test_results["passed"] else "failed",
                "tests_run": test_results["total"],
                "tests_passed": test_results["passed"],
                "tests_failed": test_results["failed"],
                "duration_seconds": test_results["duration"],
                "details": test_results,
            }

            logger.info(
                f"Migration Rollback Tests: {test_results['passed']}/{test_results['total']} passed"
            )

        except Exception as e:
            logger.exception("Migration rollback tests failed")
            self.test_results["test_categories"][test_category] = {
                "status": "failed",
                "error": str(e),
            }
            raise

    async def _run_failover_recovery_tests(self):
        """Run failover and recovery scenario tests (Task 4.4)."""
        logger.info("Running Failover and Recovery Tests (Task 4.4)...")

        test_category = "failover_recovery"
        self.test_results["test_categories"][test_category] = {}

        try:
            test_results = await self._run_pytest_tests(
                ["test_phase4_integration.py::TestFailoverRecovery"]
            )

            self.test_results["test_categories"][test_category] = {
                "status": "passed" if test_results["passed"] else "failed",
                "tests_run": test_results["total"],
                "tests_passed": test_results["passed"],
                "tests_failed": test_results["failed"],
                "duration_seconds": test_results["duration"],
                "details": test_results,
            }

            logger.info(
                f"Failover and Recovery Tests: {test_results['passed']}/{test_results['total']} passed"
            )

        except Exception as e:
            logger.exception("Failover and recovery tests failed")
            self.test_results["test_categories"][test_category] = {
                "status": "failed",
                "error": str(e),
            }
            raise

    async def _run_performance_tests(self):
        """Run performance testing and optimization validation (Task 4.5)."""
        logger.info(
            "Running Performance Testing and Optimization Validation (Task 4.5)..."
        )

        test_category = "performance_testing"
        self.test_results["test_categories"][test_category] = {}

        try:
            # Run both performance validation and load tests
            test_results = await self._run_pytest_tests(
                [
                    "test_phase4_integration.py::TestPerformanceValidation",
                    "test_performance_load.py::TestPerformanceRequirements",
                    "test_performance_load.py::TestLoadTestingScenarios",
                ]
            )

            self.test_results["test_categories"][test_category] = {
                "status": "passed" if test_results["passed"] else "failed",
                "tests_run": test_results["total"],
                "tests_passed": test_results["passed"],
                "tests_failed": test_results["failed"],
                "duration_seconds": test_results["duration"],
                "details": test_results,
            }

            logger.info(
                f"Performance Testing: {test_results['passed']}/{test_results['total']} passed"
            )

        except Exception as e:
            logger.exception("Performance testing failed")
            self.test_results["test_categories"][test_category] = {
                "status": "failed",
                "error": str(e),
            }
            raise

    async def _validate_functional_requirements(self):
        """Validate all functional requirements (REQ-001 through REQ-008)."""
        logger.info("Validating Functional Requirements...")

        functional_requirements = {
            "REQ-001": {
                "name": "PostgreSQL 18 Database Setup",
                "description": "PostgreSQL 18 database configured with proper users and permissions",
                "status": "validated" if self._check_postgresql_setup() else "failed",
                "validation_method": "Database connection and version check",
            },
            "REQ-002": {
                "name": "Database Schema Implementation",
                "description": "Complete database schema with all required tables and relationships",
                "status": "validated"
                if await self._check_database_schema()
                else "failed",
                "validation_method": "Schema validation against ER diagram",
            },
            "REQ-003": {
                "name": "Alembic Migration System",
                "description": "Alembic migrations implemented with rollback capability",
                "status": "validated"
                if await self._check_migration_system()
                else "failed",
                "validation_method": "Migration file and rollback test validation",
            },
            "REQ-004": {
                "name": "Connection Pool Management",
                "description": "Optimized connection pooling with proper configuration",
                "status": "validated"
                if await self._check_connection_pooling()
                else "failed",
                "validation_method": "Connection pool metrics and performance testing",
            },
            "REQ-005": {
                "name": "Database Health Monitoring",
                "description": "Comprehensive health monitoring and alerting system",
                "status": "validated"
                if await self._check_health_monitoring()
                else "failed",
                "validation_method": "Health endpoint and monitoring dashboard validation",
            },
            "REQ-006": {
                "name": "Project Isolation Enforcement",
                "description": "Strict project isolation with proper data scoping",
                "status": "validated"
                if await self._check_project_isolation()
                else "failed",
                "validation_method": "Cross-project data access testing",
            },
            "REQ-007": {
                "name": "Backup and Recovery",
                "description": "Automated backup system with recovery procedures",
                "status": "validated"
                if await self._check_backup_recovery()
                else "failed",
                "validation_method": "Backup system status and recovery testing",
            },
            "REQ-008": {
                "name": "Performance Optimization",
                "description": "Database performance optimization with proper indexing",
                "status": "validated"
                if await self._check_performance_optimization()
                else "failed",
                "validation_method": "Query performance and index usage analysis",
            },
        }

        self.test_results["functional_requirements"] = functional_requirements

        # Count validation results
        validated_count = sum(
            1
            for req in functional_requirements.values()
            if req["status"] == "validated"
        )
        total_count = len(functional_requirements)

        logger.info(
            f"Functional Requirements Validation: {validated_count}/{total_count} validated"
        )

        # Log any failed requirements
        for req_id, req_data in functional_requirements.items():
            if req_data["status"] == "failed":
                logger.error(
                    f"Functional requirement {req_id} ({req_data['name']}) failed validation"
                )

    async def _validate_non_functional_requirements(self):
        """Validate all non-functional requirements."""
        logger.info("Validating Non-Functional Requirements...")

        non_functional_requirements = {
            "PERF-001": {
                "name": "Query Response Time < 100ms P95",
                "description": "95th percentile query response time under 100ms",
                "status": "validated"
                if await self._check_p95_response_time()
                else "failed",
                "measured_value": await self._measure_p95_response_time(),
                "target_value": "100ms",
            },
            "PERF-002": {
                "name": "Concurrent User Support",
                "description": "Support for 10+ concurrent users with <2s response time",
                "status": "validated"
                if await self._check_concurrent_users()
                else "failed",
                "measured_value": await self._measure_concurrent_performance(),
                "target_value": "10 users, <2s response",
            },
            "SEC-001": {
                "name": "Project Data Isolation",
                "description": "Strict data isolation between projects",
                "status": "validated"
                if await self._check_data_isolation()
                else "failed",
                "validation_method": "Cross-project access prevention testing",
            },
            "SEC-002": {
                "name": "Input Validation and Sanitization",
                "description": "Proper input validation and SQL injection prevention",
                "status": "validated"
                if await self._check_input_validation()
                else "failed",
                "validation_method": "Input validation and security testing",
            },
            "SEC-003": {
                "name": "Connection Security",
                "description": "Secure database connections with proper authentication",
                "status": "validated"
                if await self._check_connection_security()
                else "failed",
                "validation_method": "Connection security and authentication validation",
            },
            "REL-001": {
                "name": "99.9% Database Availability",
                "description": "High database availability with failover support",
                "status": "validated" if await self._check_availability() else "failed",
                "measured_value": await self._measure_availability(),
                "target_value": "99.9%",
            },
            "REL-002": {
                "name": "Data Backup Reliability",
                "description": "Reliable backup system with regular testing",
                "status": "validated"
                if await self._check_backup_reliability()
                else "failed",
                "validation_method": "Backup system testing and validation",
            },
            "REL-003": {
                "name": "Error Recovery",
                "description": "Graceful error handling and recovery procedures",
                "status": "validated"
                if await self._check_error_recovery()
                else "failed",
                "validation_method": "Error scenario and recovery testing",
            },
        }

        self.test_results["non_functional_requirements"] = non_functional_requirements

        # Count validation results
        validated_count = sum(
            1
            for req in non_functional_requirements.values()
            if req["status"] == "validated"
        )
        total_count = len(non_functional_requirements)

        logger.info(
            f"Non-Functional Requirements Validation: {validated_count}/{total_count} validated"
        )

        # Log any failed requirements
        for req_id, req_data in non_functional_requirements.items():
            if req_data["status"] == "failed":
                logger.error(
                    f"Non-functional requirement {req_id} ({req_data['name']}) failed validation"
                )

    async def _validate_production_readiness(self):
        """Validate production readiness checklist."""
        logger.info("Validating Production Readiness...")

        production_readiness_items = {
            "api_endpoints": {
                "name": "All API Endpoints Operational",
                "status": await self._check_api_endpoints(),
                "description": "All CRUD endpoints functional and documented",
            },
            "database_connectivity": {
                "name": "Database Connectivity",
                "status": await self._check_database_connectivity(),
                "description": "Reliable database connection with proper error handling",
            },
            "performance_monitoring": {
                "name": "Performance Monitoring",
                "status": await self._check_monitoring_systems(),
                "description": "Active monitoring and alerting systems",
            },
            "backup_systems": {
                "name": "Backup Systems",
                "status": await self._check_backup_systems(),
                "description": "Automated backup systems with tested recovery",
            },
            "documentation": {
                "name": "API Documentation",
                "status": await self._check_api_documentation(),
                "description": "Complete OpenAPI documentation and deployment guides",
            },
            "error_handling": {
                "name": "Error Handling",
                "status": await self._check_error_handling(),
                "description": "Comprehensive error handling and logging",
            },
            "security_measures": {
                "name": "Security Measures",
                "status": await self._check_security_measures(),
                "description": "Input validation, authentication, and data protection",
            },
            "deployment_procedures": {
                "name": "Deployment Procedures",
                "status": await self._check_deployment_procedures(),
                "description": "Documented deployment and rollback procedures",
            },
        }

        self.test_results["production_readiness"] = production_readiness_items

        # Count readiness items
        ready_count = sum(
            1 for item in production_readiness_items.values() if item["status"]
        )
        total_count = len(production_readiness_items)

        logger.info(f"Production Readiness: {ready_count}/{total_count} items ready")

        for item_name, item_data in production_readiness_items.items():
            status_text = "✓" if item_data["status"] else "✗"
            logger.info(
                f"  {status_text} {item_data['name']}: {item_data['description']}"
            )

    def _generate_final_report(self):
        """Generate final Phase 4 completion report."""
        logger.info("=" * 80)
        logger.info("PHASE 4 INTEGRATION AND TESTING - FINAL REPORT")
        logger.info("=" * 80)

        # Overall status
        test_categories = self.test_results["test_categories"]
        all_passed = all(
            cat.get("status") == "passed" for cat in test_categories.values()
        )

        self.test_results["overall_status"] = (
            "completed" if all_passed else "completed_with_issues"
        )

        logger.info(f"Overall Status: {self.test_results['overall_status'].upper()}")
        logger.info(
            f"Total Duration: {self.test_results['total_duration_seconds']:.2f} seconds"
        )
        logger.info(f"Start Time: {self.test_results['start_time']}")
        logger.info(f"End Time: {self.test_results['end_time']}")

        # Test category results
        logger.info("\nTEST CATEGORIES:")
        for category, results in test_categories.items():
            status_icon = "✓" if results.get("status") == "passed" else "✗"
            logger.info(
                f"  {status_icon} {category.replace('_', ' ').title()}: {results.get('status', 'unknown')}"
            )
            if "tests_run" in results:
                logger.info(
                    f"    Tests: {results['tests_passed']}/{results['tests_run']} passed"
                )

        # Functional requirements summary
        func_reqs = self.test_results["functional_requirements"]
        func_validated = sum(
            1 for req in func_reqs.values() if req["status"] == "validated"
        )
        logger.info(
            f"\nFUNCTIONAL REQUIREMENTS: {func_validated}/{len(func_reqs)} validated"
        )

        # Non-functional requirements summary
        non_func_reqs = self.test_results["non_functional_requirements"]
        non_func_validated = sum(
            1 for req in non_func_reqs.values() if req["status"] == "validated"
        )
        logger.info(
            f"NON-FUNCTIONAL REQUIREMENTS: {non_func_validated}/{len(non_func_reqs)} validated"
        )

        # Production readiness summary
        prod_ready = self.test_results["production_readiness"]
        prod_ready_count = sum(1 for item in prod_ready.values() if item["status"])
        logger.info(
            f"PRODUCTION READINESS: {prod_ready_count}/{len(prod_ready)} items ready"
        )

        # Final determination
        logger.info("\n" + "=" * 80)
        if (
            all_passed
            and func_validated == len(func_reqs)
            and non_func_validated == len(non_func_reqs)
        ):
            logger.info("🎉 PHASE 4 INTEGRATION AND TESTING - SUCCESSFULLY COMPLETED")
            logger.info("✅ All requirements validated")
            logger.info("✅ System ready for production deployment")
        else:
            logger.info("⚠️  PHASE 4 INTEGRATION AND TESTING - COMPLETED WITH ISSUES")
            logger.info(
                "❌ Some requirements need attention before production deployment"
            )

        logger.info("=" * 80)

    # Helper methods for requirement validation
    def _check_postgresql_setup(self) -> bool:
        """Check PostgreSQL 18 setup."""
        # TODO: Implement PostgreSQL 18 version and configuration validation
        raise NotImplementedError("_check_postgresql_setup not implemented")

    async def _check_database_schema(self) -> bool:
        """Check database schema implementation."""
        # TODO: Implement ER diagram vs live schema validation
        raise NotImplementedError("_check_database_schema not implemented")

    async def _check_migration_system(self) -> bool:
        """Check Alembic migration system."""
        # TODO: Implement Alembic migration files and rollback capability validation
        raise NotImplementedError("_check_migration_system not implemented")

    async def _check_connection_pooling(self) -> bool:
        """Check connection pool management."""
        # TODO: Implement database connection pool validation
        raise NotImplementedError("_check_connection_pooling not implemented")

    async def _check_health_monitoring(self) -> bool:
        """Check database health monitoring."""
        # TODO: Implement health endpoints and monitoring dashboard validation
        raise NotImplementedError("_check_health_monitoring not implemented")

    async def _check_project_isolation(self) -> bool:
        """Check project isolation enforcement."""
        # TODO: Implement cross-project data access prevention testing
        raise NotImplementedError("_check_project_isolation not implemented")

    async def _check_backup_recovery(self) -> bool:
        """Check backup and recovery systems."""
        # TODO: Implement backup system and recovery procedures validation
        raise NotImplementedError("_check_backup_recovery not implemented")

    async def _check_performance_optimization(self) -> bool:
        """Check performance optimization."""
        # TODO: Implement query performance and indexing validation
        raise NotImplementedError("_check_performance_optimization not implemented")

    async def _check_p95_response_time(self) -> bool:
        """Check P95 response time requirement."""
        # TODO: Implement P95 response time measurement and validation
        raise NotImplementedError("_check_p95_response_time not implemented")

    async def _measure_p95_response_time(self) -> str:
        """Measure actual P95 response time."""
        # TODO: Implement actual P95 response time measurement
        raise NotImplementedError("_measure_p95_response_time not implemented")

    async def _check_concurrent_users(self) -> bool:
        """Check concurrent user support."""
        # TODO: Implement concurrent user support testing
        raise NotImplementedError("_check_concurrent_users not implemented")

    async def _measure_concurrent_performance(self) -> str:
        """Measure concurrent user performance."""
        # TODO: Implement concurrent user performance measurement
        raise NotImplementedError("_measure_concurrent_performance not implemented")

    async def _check_data_isolation(self) -> bool:
        """Check data isolation security."""
        # TODO: Implement data isolation security testing
        raise NotImplementedError("_check_data_isolation not implemented")

    async def _check_input_validation(self) -> bool:
        """Check input validation."""
        # TODO: Implement input validation and sanitization testing
        raise NotImplementedError("_check_input_validation not implemented")

    async def _check_connection_security(self) -> bool:
        """Check connection security."""
        # TODO: Implement secure database connection validation
        raise NotImplementedError("_check_connection_security not implemented")

    async def _check_availability(self) -> bool:
        """Check availability requirements."""
        # TODO: Implement database availability measurement
        raise NotImplementedError("_check_availability not implemented")

    async def _measure_availability(self) -> str:
        """Measure actual availability."""
        # TODO: Implement actual database availability measurement
        raise NotImplementedError("_measure_availability not implemented")

    async def _check_backup_reliability(self) -> bool:
        """Check backup reliability."""
        # TODO: Implement backup reliability testing
        raise NotImplementedError("_check_backup_reliability not implemented")

    async def _check_error_recovery(self) -> bool:
        """Check error recovery procedures."""
        # TODO: Implement error recovery procedures testing
        raise NotImplementedError("_check_error_recovery not implemented")

    async def _check_api_endpoints(self) -> bool:
        """Check all API endpoints."""
        # TODO: Implement API endpoints functionality testing
        raise NotImplementedError("_check_api_endpoints not implemented")

    async def _check_database_connectivity(self) -> bool:
        """Check database connectivity."""
        # TODO: Implement database connectivity testing
        raise NotImplementedError("_check_database_connectivity not implemented")

    async def _check_monitoring_systems(self) -> bool:
        """Check monitoring systems."""
        # TODO: Implement monitoring systems validation
        raise NotImplementedError("_check_monitoring_systems not implemented")

    async def _check_backup_systems(self) -> bool:
        """Check backup systems."""
        # TODO: Implement backup systems validation
        raise NotImplementedError("_check_backup_systems not implemented")

    async def _check_api_documentation(self) -> bool:
        """Check API documentation."""
        # TODO: Implement OpenAPI documentation validation
        raise NotImplementedError("_check_api_documentation not implemented")

    async def _check_error_handling(self) -> bool:
        """Check error handling."""
        # TODO: Implement error handling testing
        raise NotImplementedError("_check_error_handling not implemented")

    async def _check_security_measures(self) -> bool:
        """Check security measures."""
        # TODO: Implement security measures validation
        raise NotImplementedError("_check_security_measures not implemented")

    async def _check_deployment_procedures(self) -> bool:
        """Check deployment procedures."""
        # TODO: Implement deployment procedures validation
        raise NotImplementedError("_check_deployment_procedures not implemented")

    async def _run_pytest_tests(self, test_files: List[str]) -> Dict[str, Any]:
        """Run pytest tests and return real results."""
        import time
        import asyncio

        # Prepare pytest command
        pytest_cmd = [
            "python3",
            "-m",
            "pytest",
            "-q",
            "--maxfail=1",
            "--tb=short",
        ] + test_files

        try:
            start_time = time.time()

            # Run pytest asynchronously using asyncio.create_subprocess_exec
            process = await asyncio.create_subprocess_exec(
                *pytest_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_root,
            )

            stdout, stderr = await process.communicate()
            duration = time.time() - start_time

            # Parse pytest output to extract results
            stdout_str = stdout.decode("utf-8") if stdout else ""
            stderr_str = stderr.decode("utf-8") if stderr else ""

            # Parse pytest summary from output
            total_tests = 0
            failed_tests = 0
            passed_tests = 0

            # Look for pytest summary in output
            lines = stdout_str.split("\n")
            for line in lines:
                if "=" in line and ("passed" in line or "failed" in line):
                    # Parse line like: "5 passed, 2 failed in 10.5s"
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.isdigit():
                            count = int(part)
                            if i + 1 < len(parts):
                                next_part = parts[i + 1]
                                if "passed" in next_part:
                                    passed_tests += count
                                elif "failed" in next_part:
                                    failed_tests += count
                            total_tests += count

            # Fallback if parsing failed
            if total_tests == 0:
                if process.returncode == 0:
                    total_tests = passed_tests = 1  # Assume at least one test passed
                else:
                    total_tests = failed_tests = 1  # Assume at least one test failed

            return {
                "total": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "duration": duration,
                "exit_code": process.returncode,
                "details": {
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                    "summary": f"{passed_tests} passed, {failed_tests} failed in {duration:.2f}s",
                },
            }

        except Exception as e:
            # Return error information if pytest execution fails
            return {
                "total": 0,
                "passed": 0,
                "failed": 1,
                "duration": 0,
                "exit_code": -1,
                "details": {
                    "error": str(e),
                    "summary": f"Failed to run pytest: {str(e)}",
                },
            }


async def main():
    """Main entry point for Phase 4 test runner."""
    runner = Phase4TestRunner()
    await runner.run_all_tests()

    # Save test results to file
    import json

    with open("phase4_test_results.json", "w") as f:
        # Convert datetime objects to strings for JSON serialization
        results = runner.test_results.copy()
        results["start_time"] = results["start_time"].isoformat()
        results["end_time"] = (
            results["end_time"].isoformat() if results["end_time"] else None
        )
        json.dump(results, f, indent=2, default=str)

    logger.info("Phase 4 test results saved to phase4_test_results.json")


if __name__ == "__main__":
    asyncio.run(main())
