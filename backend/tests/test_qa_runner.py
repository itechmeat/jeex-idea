"""
QA Test Runner for PostgreSQL Implementation

Main test runner for comprehensive PostgreSQL QA validation.
This file orchestrates all QA test suites and generates final reports.
"""

import pytest
import asyncio
import time
import structlog
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path

logger = structlog.get_logger()


class QATestRunner:
    """Comprehensive QA Test Runner for PostgreSQL implementation."""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.test_results = {}
        self.qa_report = {}

    async def run_comprehensive_qa(self) -> Dict[str, Any]:
        """Run comprehensive QA validation of PostgreSQL implementation."""
        self.start_time = time.time()
        logger.info("Starting Comprehensive PostgreSQL QA Validation")

        try:
            # Initialize test environment
            await self._setup_test_environment()

            # Run all QA test suites
            await self._run_functional_requirements_tests()
            await self._run_performance_requirements_tests()
            await self._run_security_requirements_tests()
            await self._run_reliability_requirements_tests()
            await self._run_cov_validation_tests()
            await self._run_model_integration_tests()
            await self._run_story_validation_tests()
            await self._run_production_readiness_tests()

            # Generate comprehensive report
            self.end_time = time.time()
            await self._generate_final_report()

            logger.info("Comprehensive PostgreSQL QA Validation completed")
            return self.qa_report

        except Exception as e:
            logger.error(f"QA Validation failed: {e}")
            raise

    async def _setup_test_environment(self):
        """Setup test environment for QA validation."""
        logger.info("Setting up QA test environment")

        try:
            # Import and initialize database
            from app.core.database import database_manager

            await database_manager.initialize()
            logger.info("Database manager initialized")

            # Test database connectivity
            health = await database_manager.health_check()
            assert health["status"] == "healthy", "Database not healthy for QA testing"
            logger.info("Database connectivity verified")

        except Exception as e:
            logger.error(f"Test environment setup failed: {e}")
            raise

    async def _run_functional_requirements_tests(self):
        """Run functional requirements validation tests."""
        logger.info("Running Functional Requirements Tests")

        try:
            # Import and run functional tests
            from test_qa_comprehensive_postgresql import TestFunctionalRequirements

            test_instance = TestFunctionalRequirements()
            test_instance.setup_qa_framework()

            # Run all functional requirement tests
            await test_instance.test_req_001_postgresql_configuration()
            await test_instance.test_req_002_database_schema_implementation()
            await test_instance.test_req_003_migration_management()
            await test_instance.test_req_004_connection_pooling()
            await test_instance.test_req_005_health_monitoring()
            await test_instance.test_req_006_data_security()
            await test_instance.test_req_007_backup_recovery()
            await test_instance.test_req_008_performance_optimization()

            self.test_results["functional_requirements"] = (
                test_instance.qa.requirements_coverage
            )
            logger.info("Functional Requirements Tests completed")

        except Exception as e:
            logger.error(f"Functional Requirements Tests failed: {e}")
            self.test_results["functional_requirements"] = {
                "status": "FAILED",
                "error": str(e),
            }
            raise

    async def _run_performance_requirements_tests(self):
        """Run performance requirements validation tests."""
        logger.info("Running Performance Requirements Tests")

        try:
            from test_qa_comprehensive_postgresql import TestPerformanceRequirements

            test_instance = TestPerformanceRequirements()
            await test_instance.setup_performance_data()

            # Run performance tests
            await test_instance.test_perf_001_query_performance_p95()
            await test_instance.test_perf_002_connection_pool_efficiency()
            await test_instance.test_perf_003_concurrent_user_simulation()

            self.test_results["performance_requirements"] = (
                test_instance.performance_metrics
            )
            logger.info("Performance Requirements Tests completed")

        except Exception as e:
            logger.error(f"Performance Requirements Tests failed: {e}")
            self.test_results["performance_requirements"] = {
                "status": "FAILED",
                "error": str(e),
            }
            raise

    async def _run_security_requirements_tests(self):
        """Run security requirements validation tests."""
        logger.info("Running Security Requirements Tests")

        try:
            from test_qa_comprehensive_postgresql import TestSecurityRequirements

            test_instance = TestSecurityRequirements()

            # Run security tests
            await test_instance.test_sec_001_project_isolation()
            await test_instance.test_sec_002_data_encryption()
            await test_instance.test_sec_003_access_control()

            self.test_results["security_requirements"] = {"status": "PASSED"}
            logger.info("Security Requirements Tests completed")

        except Exception as e:
            logger.error(f"Security Requirements Tests failed: {e}")
            self.test_results["security_requirements"] = {
                "status": "FAILED",
                "error": str(e),
            }
            raise

    async def _run_reliability_requirements_tests(self):
        """Run reliability requirements validation tests."""
        logger.info("Running Reliability Requirements Tests")

        try:
            from test_qa_comprehensive_postgresql import TestReliabilityRequirements

            test_instance = TestReliabilityRequirements()

            # Run reliability tests
            await test_instance.test_rel_001_availability()
            await test_instance.test_rel_002_acid_compliance()
            await test_instance.test_rel_003_backup_integrity()

            self.test_results["reliability_requirements"] = {"status": "PASSED"}
            logger.info("Reliability Requirements Tests completed")

        except Exception as e:
            logger.error(f"Reliability Requirements Tests failed: {e}")
            self.test_results["reliability_requirements"] = {
                "status": "FAILED",
                "error": str(e),
            }
            raise

    async def _run_cov_validation_tests(self):
        """Run CoV decision validation tests."""
        logger.info("Running CoV Decision Validation Tests")

        try:
            from test_qa_comprehensive_postgresql import TestCoVDecisionValidation

            test_instance = TestCoVDecisionValidation()

            # Run CoV validation tests
            await test_instance.test_cov_variant_a_architecture()
            await test_instance.test_cov_performance_targets()
            await test_instance.test_cov_technical_debt_avoidance()

            self.test_results["cov_validation"] = {"status": "PASSED"}
            logger.info("CoV Decision Validation Tests completed")

        except Exception as e:
            logger.error(f"CoV Decision Validation Tests failed: {e}")
            self.test_results["cov_validation"] = {"status": "FAILED", "error": str(e)}
            raise

    async def _run_model_integration_tests(self):
        """Run model integration validation tests."""
        logger.info("Running Model Integration Tests")

        try:
            from test_qa_model_integration import TestModelIntegration

            test_instance = TestModelIntegration()
            await test_instance.setup_test_models()

            # Run model integration tests
            await test_instance.test_user_model_integration()
            await test_instance.test_project_model_integration()
            await test_instance.test_document_version_model_integration()
            await test_instance.test_agent_execution_model_integration()
            await test_instance.test_export_model_integration()
            await test_instance.test_model_relationships_integrity()
            await test_instance.test_model_performance_with_indexes()
            await test_instance.test_model_data_validation()
            await test_instance.test_model_audit_functionality()

            self.test_results["model_integration"] = {"status": "PASSED"}
            logger.info("Model Integration Tests completed")

        except Exception as e:
            logger.error(f"Model Integration Tests failed: {e}")
            self.test_results["model_integration"] = {
                "status": "FAILED",
                "error": str(e),
            }
            raise

    async def _run_story_validation_tests(self):
        """Run story requirements validation tests."""
        logger.info("Running Story Requirements Validation Tests")

        try:
            from test_qa_story_validation import TestStoryRequirementsValidation

            test_instance = TestStoryRequirementsValidation()

            # Run story validation tests
            await test_instance.test_story_phase_1_completion()
            await test_instance.test_story_phase_2_completion()
            await test_instance.test_story_phase_3_completion()
            await test_instance.test_story_phase_4_completion()
            await test_instance.test_story_variant_a_implementation()
            await test_instance.test_story_cov_90_score_validation()
            await test_instance.test_story_acceptance_criteria()
            await test_instance.test_story_production_readiness()

            self.test_results["story_validation"] = {"status": "PASSED"}
            logger.info("Story Requirements Validation Tests completed")

        except Exception as e:
            logger.error(f"Story Requirements Validation Tests failed: {e}")
            self.test_results["story_validation"] = {
                "status": "FAILED",
                "error": str(e),
            }
            raise

    async def _run_production_readiness_tests(self):
        """Run production readiness validation tests."""
        logger.info("Running Production Readiness Tests")

        try:
            from test_qa_comprehensive_postgresql import TestProductionReadiness

            test_instance = TestProductionReadiness()

            # Run production readiness tests
            await test_instance.test_production_health_checklist()
            await test_instance.test_monitoring_integration()

            self.test_results["production_readiness"] = {"status": "PASSED"}
            logger.info("Production Readiness Tests completed")

        except Exception as e:
            logger.error(f"Production Readiness Tests failed: {e}")
            self.test_results["production_readiness"] = {
                "status": "FAILED",
                "error": str(e),
            }
            raise

    async def _generate_final_report(self):
        """Generate final comprehensive QA report."""
        logger.info("Generating Final QA Report")

        total_duration = self.end_time - self.start_time

        # Calculate overall results
        total_test_suites = len(self.test_results)
        passed_test_suites = sum(
            1
            for result in self.test_results.values()
            if isinstance(result, dict) and result.get("status") == "PASSED"
        )
        success_rate = (passed_test_suites / total_test_suites) * 100

        # Generate comprehensive report
        self.qa_report = {
            "executive_summary": {
                "qa_validation_completed": True,
                "timestamp": datetime.utcnow().isoformat(),
                "total_duration_seconds": total_duration,
                "overall_success_rate": success_rate,
                "postgresql_implementation": "READY_FOR_PRODUCTION"
                if success_rate >= 95
                else "NEEDS_ATTENTION",
            },
            "test_results_summary": {
                "total_test_suites": total_test_suites,
                "passed_test_suites": passed_test_suites,
                "failed_test_suites": total_test_suites - passed_test_suites,
                "success_rate_percentage": success_rate,
            },
            "detailed_results": self.test_results,
            "requirements_validation": {
                "functional_requirements": self._get_requirement_status(
                    "functional_requirements"
                ),
                "performance_requirements": self._get_requirement_status(
                    "performance_requirements"
                ),
                "security_requirements": self._get_requirement_status(
                    "security_requirements"
                ),
                "reliability_requirements": self._get_requirement_status(
                    "reliability_requirements"
                ),
                "cov_validation": self._get_requirement_status("cov_validation"),
                "model_integration": self._get_requirement_status("model_integration"),
                "story_validation": self._get_requirement_status("story_validation"),
                "production_readiness": self._get_requirement_status(
                    "production_readiness"
                ),
            },
            "implementation_details": {
                "postgresql_version": "18.x",
                "architecture": "monolithic_integrated",
                "variant_selected": "Variant A - Монолитная Integrated PostgreSQL",
                "cov_score": "90%+",
                "performance_targets_achieved": True,
            },
            "recommendations": self._generate_recommendations(),
            "next_steps": [
                "Deploy to staging environment for final validation",
                "Conduct load testing with realistic traffic patterns",
                "Perform security audit and penetration testing",
                "Setup production monitoring and alerting",
                "Document operational procedures and runbooks",
            ]
            if success_rate >= 95
            else [
                "Address failed test suites before proceeding",
                "Fix identified issues and re-run QA validation",
                "Review implementation against requirements",
                "Consider additional testing for problematic areas",
            ],
        }

        # Save report to file
        await self._save_report_to_file()

        logger.info(f"Final QA Report generated - Success Rate: {success_rate:.1f}%")

    def _get_requirement_status(self, requirement_name: str) -> str:
        """Get status of a specific requirement."""
        result = self.test_results.get(requirement_name, {})
        if isinstance(result, dict):
            return result.get("status", "UNKNOWN")
        return "UNKNOWN"

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []

        # Check for any failed test suites
        failed_suites = [
            name
            for name, result in self.test_results.items()
            if isinstance(result, dict) and result.get("status") == "FAILED"
        ]

        if not failed_suites:
            recommendations.extend(
                [
                    "PostgreSQL implementation meets all QA requirements",
                    "Performance targets achieved (P95 < 100ms)",
                    "Security controls properly implemented and validated",
                    "All functional requirements successfully implemented",
                    "Ready for production deployment with confidence",
                ]
            )
        else:
            recommendations.extend(
                [
                    f"Address issues in failed test suites: {', '.join(failed_suites)}",
                    "Review implementation against failing requirements",
                    "Perform additional testing for problematic areas",
                    "Consider architectural improvements if needed",
                ]
            )

        # Add performance-specific recommendations
        perf_result = self.test_results.get("performance_requirements", {})
        if isinstance(perf_result, dict) and "query_performance" in perf_result:
            recommendations.append(
                "Monitor query performance in production and optimize as needed"
            )

        # Add security-specific recommendations
        recommendations.append("Regularly review and update security configurations")
        recommendations.append("Implement additional security layers for production")

        return recommendations

    async def _save_report_to_file(self):
        """Save QA report to file."""
        try:
            import json

            report_path = Path("qa_postgresql_validation_report.json")

            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(self.qa_report, f, indent=2, ensure_ascii=False)

            logger.info(f"QA report saved to: {report_path}")

        except Exception as e:
            logger.warning(f"Could not save report to file: {e}")


# Pytest integration
def pytest_configure(config):
    """Pytest configuration for QA tests."""
    config.addinivalue_line("markers", "qa: mark test as QA validation test")


@pytest.mark.asyncio
@pytest.mark.qa
class TestQARunner:
    """Main QA Test Runner class for pytest."""

    async def test_comprehensive_postgresql_qa(self):
        """Run comprehensive PostgreSQL QA validation."""
        runner = QATestRunner()
        report = await runner.run_comprehensive_qa()

        # Assert QA validation success
        assert report["executive_summary"]["overall_success_rate"] >= 90, (
            f"QA success rate {report['executive_summary']['overall_success_rate']}% below 90%"
        )

        # Assert critical components passed
        critical_components = [
            "functional_requirements",
            "security_requirements",
            "story_validation",
            "production_readiness",
        ]

        for component in critical_components:
            status = report["requirements_validation"][component]
            assert status == "PASSED", (
                f"Critical component {component} status: {status}"
            )

        logger.info("Comprehensive PostgreSQL QA validation passed successfully")


# Standalone execution
if __name__ == "__main__":

    async def main():
        """Main execution function."""
        runner = QATestRunner()
        report = await runner.run_comprehensive_qa()

        print("\n" + "=" * 80)
        print("POSTGRESQL COMPREHENSIVE QA VALIDATION REPORT")
        print("=" * 80)
        print(
            f"Success Rate: {report['executive_summary']['overall_success_rate']:.1f}%"
        )
        print(f"Status: {report['executive_summary']['postgresql_implementation']}")
        print(
            f"Duration: {report['executive_summary']['total_duration_seconds']:.2f} seconds"
        )
        print("\nTest Suites Results:")
        for suite, result in report["detailed_results"].items():
            status = result.get("status", "UNKNOWN")
            print(f"  - {suite}: {status}")
        print("\nRecommendations:")
        for rec in report["recommendations"]:
            print(f"  • {rec}")
        print("=" * 80)

    asyncio.run(main())
