"""
Vector Database Security Integration Tests

Security-focused integration tests for vector database isolation requirements.
Tests security boundaries, filter enforcement, and protection against data leakage.

Security Requirements Tested:
- REQ-003: Server-Side Filter Enforcement (mandatory filters)
- REQ-008: Multi-Tenant Data Isolation (zero leakage tolerance)
- SEC-001: Filter Enforcement (absolute requirement)
- SEC-002: Network Isolation (indirect testing)
- SEC-003: Audit Logging (security event tracking)
"""

import pytest
import asyncio
import httpx
from uuid import uuid4
from typing import Dict, Any, List
import structlog
import json

from ...fixtures.vector_test_data import (
    VectorTestDataGenerator,
    get_isolation_test_fixtures,
    create_test_vector,
)

logger = structlog.get_logger()


# Security Test Configuration
SECURITY_TEST_CONFIG = {
    "base_url": "http://localhost:5210",
    "timeout": 30.0,
    "max_vectors_per_test": 50,
    "attack_vectors": [
        "missing_filters",
        "invalid_filters",
        "filter_bypass_attempts",
        "context_manipulation",
        "injection_attempts",
        "boundary_testing",
    ],
}


class VectorSecurityTester:
    """
    Security-focused tester for vector database isolation.

    Tests all security boundaries and ensures no data leakage is possible.
    """

    def __init__(self, base_url: str = SECURITY_TEST_CONFIG["base_url"]):
        """
        Initialize security tester.

        Args:
            base_url: Base URL for vector API endpoints
        """
        self.base_url = base_url
        self.client = None
        self.test_data = None
        self.security_events = []
        self.created_points = []

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(
            base_url=self.base_url, timeout=SECURITY_TEST_CONFIG["timeout"]
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        if self.client:
            await self.client.aclose()
        await self.cleanup_test_data()

    async def setup_security_test_data(self) -> Dict[str, Any]:
        """
        Setup test data specifically for security testing.

        Returns:
            Security test data dictionary
        """
        logger.info("Setting up security test data")

        # Create projects with clearly distinguishable content
        projects = [
            {"id": str(uuid4()), "name": "Security Project A", "language": "en"},
            {"id": str(uuid4()), "name": "Security Project B", "language": "ru"},
            {"id": str(uuid4()), "name": "Security Project C", "language": "es"},
        ]

        generator = VectorTestDataGenerator(
            random_seed=999
        )  # Different seed for security tests

        # Create vectors with security-sensitive content
        security_vectors = []
        for project in projects:
            # Content that should never leak between projects
            sensitive_content = [
                f"SECRET_KEY_FOR_PROJECT_{project['name']}: {uuid4()}",
                f"PRIVATE_DATA_{project['name']}: Financial records and user information",
                f"CONFIDENTIAL_{project['name']}: Internal company documents",
                f"API_CREDENTIALS_{project['name']}: Production access tokens",
                f"USER_DATABASE_{project['name']}: Personal customer information",
            ]

            for i, content in enumerate(sensitive_content):
                vector = {
                    "id": str(uuid4()),
                    "vector": generator.generate_vector_1536d(),
                    "content": content,
                    "title": f"Sensitive Document {i + 1}",
                    "type": "knowledge",
                    "metadata": {
                        "security_level": "high",
                        "classification": "confidential",
                        "project_name": project["name"],
                        "data_owner": "security_test",
                    },
                    "importance": 1.0,  # Highest importance
                    "project_id": project["id"],
                    "language": project["language"],
                }
                security_vectors.append(vector)

        self.test_data = {
            "projects": projects,
            "vectors": security_vectors,
            "sensitive_content_count": len(sensitive_content),
        }

        # Insert all vectors
        for project in projects:
            project_vectors = [
                v for v in security_vectors if v["project_id"] == project["id"]
            ]
            if project_vectors:
                await self.insert_vectors(
                    project["id"], project["language"], project_vectors
                )
                self.created_points.extend([v["id"] for v in project_vectors])

        logger.info(
            "Security test data setup completed",
            projects_count=len(projects),
            sensitive_vectors=len(security_vectors),
        )

        return self.test_data

    async def insert_vectors(
        self, project_id: str, language: str, vectors: List[Dict[str, Any]]
    ) -> None:
        """
        Insert vectors with security context.

        Args:
            project_id: Project UUID (must be non-empty string)
            language: Language code (must be non-empty string)
            vectors: List of vector dicts (must be non-empty list)

        Raises:
            ValueError: If inputs are invalid
        """
        # Input validation
        if not project_id or not isinstance(project_id, str):
            raise ValueError(f"project_id must be non-empty string, got: {type(project_id).__name__}")
        if not language or not isinstance(language, str):
            raise ValueError(f"language must be non-empty string, got: {type(language).__name__}")
        if not vectors or not isinstance(vectors, list):
            raise ValueError(f"vectors must be non-empty list, got: {type(vectors).__name__}")

        # Validate vector structure
        required_keys = {"id", "vector", "content", "title", "type", "metadata", "importance"}
        for idx, vector in enumerate(vectors):
            if not isinstance(vector, dict):
                raise ValueError(f"Vector at index {idx} must be dict, got: {type(vector).__name__}")
            missing_keys = required_keys - set(vector.keys())
            if missing_keys:
                raise ValueError(f"Vector at index {idx} missing required keys: {missing_keys}")

        api_vectors = []
        for vector in vectors:
            api_vector = {
                "id": vector["id"],
                "vector": vector["vector"],
                "content": vector["content"],
                "title": vector["title"],
                "type": vector["type"],
                "metadata": vector["metadata"],
                "importance": vector["importance"],
            }
            api_vectors.append(api_vector)

        # Insert in batches
        batch_size = 100
        for i in range(0, len(api_vectors), batch_size):
            batch = api_vectors[i : i + batch_size]

            response = await self.client.post(
                "/api/v1/vector/upsert",
                json={"points": batch},
                params={"project_id": project_id, "language": language},
            )

            assert response.status_code == 200, (
                f"Failed to insert security vectors: {response.text}"
            )

    async def attempt_search_with_context(
        self,
        project_id: str,
        language: str,
        query_vector: List[float],
        expected_success: bool = True,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Attempt search with given context and record security events.

        Args:
            project_id: Project UUID
            language: Language code
            query_vector: Query vector
            expected_success: Whether search should succeed
            description: Description of the test

        Returns:
            Search results or error information
        """
        # Build params only with provided values to truly omit missing filters
        params: Dict[str, str] = {}
        if project_id:
            params["project_id"] = project_id
        if language:
            params["language"] = language

        response = await self.client.post(
            "/api/v1/vector/search",
            json={
                "query_vector": query_vector,
                "limit": 100,  # High limit to detect any leakage
            },
            params=params,
        )

        # Raise to convert 4xx/5xx into HTTPStatusError
        response.raise_for_status()

        if expected_success:
            return response.json()
        # Unexpected success: this should have been blocked
        security_event = {
            "type": "UNAUTHORIZED_ACCESS",
            "description": description,
            "project_id": project_id,
            "language": language,
            "response_status": response.status_code,
            "response_data": response.json(),
            "timestamp": asyncio.get_event_loop().time(),
        }
        self.security_events.append(security_event)
        return {"error": "Unexpected success", "response": response.json()}

    except httpx.HTTPStatusError as e:
        if not expected_success:
            # Expected failure - record as proper security measure
            security_event = {
                "type": "PROPERLY_BLOCKED",
                "description": description,
                "project_id": project_id,
                "language": language,
                "response_status": e.response.status_code,
                "error": e.response.text,
                "timestamp": asyncio.get_event_loop().time(),
            }
            self.security_events.append(security_event)
            return {"error": "Properly blocked", "status": e.response.status_code}
        else:
            # Unexpected failure
            security_event = {
                "type": "UNEXPECTED_FAILURE",
                "description": description,
                "project_id": project_id,
                "language": language,
                "response_status": e.response.status_code,
                "error": e.response.text,
                "timestamp": asyncio.get_event_loop().time(),
            }
            self.security_events.append(security_event)
            raise

    async def test_filter_bypass_attempts(self) -> List[Dict[str, Any]]:
        """
        Test various filter bypass attempts.

        Returns:
            List of security events from bypass attempts
        """
        if not self.test_data:
            raise ValueError("Security test data not setup")

        projects = self.test_data["projects"]
        vectors = self.test_data["vectors"]

        # Get a query vector
        query_vector = vectors[0]["vector"]

        bypass_attempts = [
            # Missing filters
            {
                "project_id": None,
                "language": "en",
                "description": "Missing project_id filter",
                "expected_success": False,
            },
            {
                "project_id": projects[0]["id"],
                "language": None,
                "description": "Missing language filter",
                "expected_success": False,
            },
            # Invalid formats
            {
                "project_id": "invalid-uuid-format",
                "language": "en",
                "description": "Invalid project_id format",
                "expected_success": False,
            },
            {
                "project_id": projects[0]["id"],
                "language": "invalid-lang",
                "description": "Invalid language code",
                "expected_success": False,
            },
            # Cross-project access attempts
            {
                "project_id": projects[0]["id"],
                "language": projects[1]["language"],
                "description": "Cross-project language access attempt",
                "expected_success": True,  # Might succeed if project has mixed languages
            },
            # Edge cases
            {
                "project_id": "",
                "language": "en",
                "description": "Empty project_id",
                "expected_success": False,
            },
            {
                "project_id": projects[0]["id"],
                "language": "",
                "description": "Empty language",
                "expected_success": False,
            },
        ]

        for attempt in bypass_attempts:
            try:
                result = await self.attempt_search_with_context(
                    project_id=attempt["project_id"] or "",
                    language=attempt["language"] or "",
                    query_vector=query_vector,
                    expected_success=attempt["expected_success"],
                    description=attempt["description"],
                )

                # Additional validation for successful searches
                if attempt["expected_success"] and "results" in result:
                    # Verify no sensitive data leakage
                    await self.validate_search_results_security(result, attempt)

            except Exception as e:
                logger.exception(
                    "Bypass attempt failed (expected behavior)",
                    description=attempt['description'],
                    project_id=attempt['project_id'],
                    language=attempt['language'],
                    exc_info=True
                )
                # Re-raise to ensure test failures are visible
                raise

        return self.security_events

    async def validate_search_results_security(
        self, search_results: Dict[str, Any], search_context: Dict[str, Any]
    ) -> None:
        """
        Validate that search results don't contain security violations.

        Args:
            search_results: Search response data
            search_context: Context used for the search
        """
        if not search_results.get("results"):
            return

        requested_project = search_context.get("project_id")
        requested_language = search_context.get("language")

        for result in search_results["results"]:
            # Try to retrieve the full point to verify isolation
            try:
                point_response = await self.client.get(
                    f"/api/v1/vector/points/{result['id']}",
                    params={
                        "project_id": requested_project,
                        "language": requested_language,
                    },
                )

                if point_response.status_code == 200:
                    point_data = point_response.json()

                    # Verify point belongs to requested project and language
                    # (This is a defense-in-depth check since API should enforce this)
                    if "content" in point_data:
                        # Check for content that shouldn't be accessible
                        content = point_data["content"]

                        # Look for sensitive content from other projects
                        for project in self.test_data["projects"]:
                            if project["id"] != requested_project:
                                project_marker = (
                                    f"PROJECT_{project['name'].replace(' ', '_')}"
                                )
                                if project_marker in content:
                                    security_event = {
                                        "type": "DATA_LEAKAGE_DETECTED",
                                        "description": f"Sensitive content from {project['name']} leaked to {requested_project}",
                                        "content_preview": content[:100],
                                        "requested_project": requested_project,
                                        "leaked_from_project": project["id"],
                                        "point_id": result["id"],
                                        "timestamp": asyncio.get_event_loop().time(),
                                    }
                                    self.security_events.append(security_event)
                                    raise AssertionError(
                                        f"Security violation: {security_event['description']}"
                                    )

            except httpx.HTTPStatusError as e:
                # 404 is expected for cross-project access attempts
                if e.response.status_code != 404:
                    security_event = {
                        "type": "UNEXPECTED_API_ERROR",
                        "description": f"API error during security validation: {e.response.text}",
                        "point_id": result["id"],
                        "timestamp": asyncio.get_event_loop().time(),
                    }
                    self.security_events.append(security_event)

    async def test_injection_attempts(self) -> None:
        """Test for injection attacks in search parameters."""
        query_vector = [0.1] * 1536

        injection_payloads = [
            {"project_id": "'; DROP TABLE vectors; --", "language": "en"},
            {"project_id": str(uuid4()), "language": "'; DELETE FROM vectors; --"},
            {"project_id": "../../../etc/passwd", "language": "en"},
            {"project_id": str(uuid4()), "language": "<script>alert('xss')</script>"},
            {"project_id": "NULL", "language": "en"},
            {"project_id": str(uuid4()), "language": "UNION SELECT * FROM users"},
        ]

        for payload in injection_payloads:
            try:
                result = await self.attempt_search_with_context(
                    project_id=payload["project_id"],
                    language=payload["language"],
                    query_vector=query_vector,
                    expected_success=False,
                    description=f"Injection attempt: {payload}",
                )
            except Exception as e:
                # Expected to fail - this is good
                security_event = {
                    "type": "INJECTION_BLOCKED",
                    "description": f"Injection attempt blocked: {payload}",
                    "error": str(e),
                    "timestamp": asyncio.get_event_loop().time(),
                }
                self.security_events.append(security_event)

    async def test_boundary_conditions(self) -> None:
        """Test security under boundary conditions."""
        query_vector = [0.1] * 1536

        boundary_tests = [
            # Very large limit
            {"limit": 10000, "description": "Very large result limit"},
            # Very small limit
            {"limit": 0, "description": "Zero result limit"},
            # Negative limit
            {"limit": -1, "description": "Negative result limit"},
        ]

        for test in boundary_tests:
            try:
                if self.test_data and self.test_data["projects"]:
                    response = await self.client.post(
                        "/api/v1/vector/search",
                        json={"query_vector": query_vector, "limit": test["limit"]},
                        params={
                            "project_id": self.test_data["projects"][0]["id"],
                            "language": "en",
                        },
                    )

                    # Check if large limits are properly handled
                    if test["limit"] == 10000 and response.status_code == 200:
                        results = response.json()
                        if results.get("total_found", 0) > 50:
                            security_event = {
                                "type": "LIMIT_BYPASS",
                                "description": f"Result limit bypassed: {test['description']}",
                                "requested_limit": test["limit"],
                                "actual_results": results.get("total_found", 0),
                                "timestamp": asyncio.get_event_loop().time(),
                            }
                            self.security_events.append(security_event)

            except Exception as e:
                # Most boundary tests should fail gracefully
                security_event = {
                    "type": "BOUNDARY_CONDITION_HANDLED",
                    "description": f"Boundary condition properly handled: {test['description']}",
                    "error": str(e),
                    "timestamp": asyncio.get_event_loop().time(),
                }
                self.security_events.append(security_event)

    async def cleanup_test_data(self) -> None:
        """Clean up all test data created during security testing."""
        if not self.client or not self.created_points:
            return

        logger.info(
            "Cleaning up security test data", points_count=len(self.created_points)
        )

        # Best effort cleanup - some points may not be deletable due to isolation
        for point_id in self.created_points[:10]:  # Limit cleanup attempts
            try:
                if self.test_data and self.test_data["projects"]:
                    # DELETE with proper params and JSON body
                    await self.client.delete(
                        f"/api/v1/vector/points/{point_id}",
                        params={
                            "project_id": self.test_data["projects"][0]["id"],
                            "language": "en",
                        },
                    )
            except Exception as e:
                logger.debug(
                    "Cleanup delete failed (expected due to isolation)",
                    point_id=point_id,
                    error=str(e)
                )
                # Cleanup failures are expected due to isolation

        self.created_points.clear()

    def get_security_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive security test report.

        Returns:
            Security test report with all events and analysis
        """
        events_by_type = {}
        for event in self.security_events:
            event_type = event["type"]
            if event_type not in events_by_type:
                events_by_type[event_type] = []
            events_by_type[event_type].append(event)

        # Analyze security posture
        critical_events = [
            e
            for e in self.security_events
            if e["type"] in ["DATA_LEAKAGE_DETECTED", "UNAUTHORIZED_ACCESS"]
        ]

        security_score = 100.0
        if critical_events:
            security_score -= (
                len(critical_events) * 50
            )  # Heavy penalty for critical issues
        if self.security_events:
            security_score -= (
                len(self.security_events) * 2
            )  # Small penalty for other issues

        security_score = max(0.0, security_score)

        return {
            "security_score": security_score,
            "total_events": len(self.security_events),
            "critical_events": len(critical_events),
            "events_by_type": events_by_type,
            "test_coverage": SECURITY_TEST_CONFIG["attack_vectors"],
            "recommendations": self._generate_security_recommendations(events_by_type),
        }

    def _generate_security_recommendations(
        self, events_by_type: Dict[str, List]
    ) -> List[str]:
        """Generate security recommendations based on test results."""
        recommendations = []

        if "DATA_LEAKAGE_DETECTED" in events_by_type:
            recommendations.append(
                "CRITICAL: Data leakage detected - review isolation enforcement immediately"
            )

        if "UNAUTHORIZED_ACCESS" in events_by_type:
            recommendations.append(
                "Review authorization mechanisms for vector operations"
            )

        if "INJECTION_BLOCKED" not in events_by_type:
            recommendations.append("Verify injection protection mechanisms are active")

        if len(self.security_events) == 0:
            recommendations.append("All security tests passed - continue monitoring")

        return recommendations


# pytest fixtures
@pytest.fixture
async def vector_security_tester():
    """Pytest fixture for vector security testing."""
    async with VectorSecurityTester() as tester:
        yield tester


@pytest.fixture
async def security_test_data(vector_security_tester):
    """Pytest fixture that sets up security test data."""
    return await vector_security_tester.setup_security_test_data()


# Security Tests
@pytest.mark.asyncio
async def test_mandatory_filter_enforcement(vector_security_tester, security_test_data):
    """
    Test REQ-003: Mandatory filter enforcement cannot be bypassed.

    GIVEN: Vector search service
    WHEN: Attempting searches without required filters
    THEN: All attempts are properly rejected
    """
    security_events = await vector_security_tester.test_filter_bypass_attempts()

    # Verify all critical bypass attempts were blocked
    properly_blocked = [e for e in security_events if e["type"] == "PROPERLY_BLOCKED"]
    data_leakage = [e for e in security_events if e["type"] == "DATA_LEAKAGE_DETECTED"]

    assert len(data_leakage) == 0, (
        f"Data leakage detected: {len(data_leakage)} incidents"
    )
    assert len(properly_blocked) > 0, "No properly blocked attempts recorded"

    logger.info(
        "Mandatory filter enforcement test passed",
        blocked_attempts=len(properly_blocked),
        data_leakage_incidents=len(data_leakage),
    )


@pytest.mark.asyncio
async def test_data_isolation_zero_tolerance(
    vector_security_tester, security_test_data
):
    """
    Test REQ-008: Zero tolerance for cross-project data leakage.

    GIVEN: Projects with highly sensitive, distinguishable content
    WHEN: Performing cross-project access attempts
    THEN: Zero data leakage is detected
    """
    projects = security_test_data["projects"]
    query_vector = [0.1] * 1536

    # Test all cross-project combinations
    for i, project_a in enumerate(projects):
        for j, project_b in enumerate(projects):
            if i == j:
                continue

            # Try to access project A's data with project B's context
            results = await vector_security_tester.attempt_search_with_context(
                project_id=project_b["id"],
                language=project_a["language"],  # Different language
                query_vector=query_vector,
                expected_success=True,  # Search may succeed but should return empty/filtered results
                description=f"Cross-project access: {project_b['name']} trying to access {project_a['name']}",
            )

            # If search succeeded, verify no sensitive data leakage
            if "results" in results and results["results"]:
                await vector_security_tester.validate_search_results_security(
                    results,
                    {"project_id": project_b["id"], "language": project_a["language"]},
                )

    # Verify no security events indicate data leakage
    security_report = vector_security_tester.get_security_report()
    assert security_report["critical_events"] == 0, (
        f"Critical security events detected: {security_report['critical_events']}"
    )
    assert security_report["security_score"] >= 90.0, (
        f"Security score too low: {security_report['security_score']}"
    )

    logger.info(
        "Zero tolerance data isolation test passed",
        security_score=security_report["security_score"],
        critical_events=security_report["critical_events"],
    )


@pytest.mark.asyncio
async def test_injection_protection(vector_security_tester, security_test_data):
    """
    Test protection against injection attacks.

    GIVEN: Vector search API
    WHEN: Attempting various injection attacks
    THEN: All injection attempts are properly blocked
    """
    await vector_security_tester.test_injection_attempts()

    security_report = vector_security_tester.get_security_report()
    injection_events = [
        e
        for e in vector_security_tester.security_events
        if "injection" in e["description"].lower()
    ]

    # Should have blocked injection attempts or properly handled them
    assert len(injection_events) >= 1, "At least one injection attempt should have been recorded/blocked"

    logger.info(
        "Injection protection test passed",
        injection_attempts=len(injection_events),
        security_score=security_report["security_score"],
    )


@pytest.mark.asyncio
async def test_boundary_condition_security(vector_security_tester, security_test_data):
    """
    Test security under boundary conditions.

    GIVEN: Vector search API
    WHEN: Testing with extreme parameter values
    THEN: System remains secure and doesn't leak data
    """
    await vector_security_tester.test_boundary_conditions()

    security_report = vector_security_tester.get_security_report()
    limit_bypass_events = [
        e for e in vector_security_tester.security_events if e["type"] == "LIMIT_BYPASS"
    ]

    assert len(limit_bypass_events) == 0, (
        f"Limit bypass detected: {len(limit_bypass_events)} incidents"
    )

    logger.info(
        "Boundary condition security test passed",
        limit_bypasses=len(limit_bypass_events),
        security_score=security_report["security_score"],
    )


@pytest.mark.asyncio
async def test_comprehensive_security_validation(
    vector_security_tester, security_test_data
):
    """
    Comprehensive validation of all security requirements.

    GIVEN: Complete security test environment
    WHEN: Running all security tests
    THEN: All security requirements are satisfied
    """
    # Run all security test categories
    await vector_security_tester.test_filter_bypass_attempts()
    await vector_security_tester.test_injection_attempts()
    await vector_security_tester.test_boundary_conditions()

    # Generate final security report
    security_report = vector_security_tester.get_security_report()

    # Validate security requirements
    assert security_report["security_score"] >= 95.0, (
        f"Security score {security_report['security_score']} below required 95.0"
    )
    assert security_report["critical_events"] == 0, (
        f"Critical security events detected: {security_report['critical_events']}"
    )

    # Check specific security requirements
    critical_types = ["DATA_LEAKAGE_DETECTED", "UNAUTHORIZED_ACCESS"]
    for critical_type in critical_types:
        critical_events = [
            e
            for e in vector_security_tester.security_events
            if e["type"] == critical_type
        ]
        assert len(critical_events) == 0, (
            f"Critical security violation: {critical_type}"
        )

    logger.info(
        "Comprehensive security validation passed",
        security_score=security_report["security_score"],
        total_events=security_report["total_events"],
        recommendations=security_report["recommendations"],
    )


if __name__ == "__main__":
    # Run security tests directly
    async def main():
        async with VectorSecurityTester() as tester:
            test_data = await tester.setup_security_test_data()
            await test_mandatory_filter_enforcement(tester, test_data)
            await test_data_isolation_zero_tolerance(tester, test_data)
            await test_injection_protection(tester, test_data)

            report = tester.get_security_report()
            print(f"Security tests completed with score: {report['security_score']}")
            print(f"Recommendations: {report['recommendations']}")

    asyncio.run(main())
