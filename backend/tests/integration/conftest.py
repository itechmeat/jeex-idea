"""
Configuration and fixtures for vector database integration tests.

Shared configuration, test fixtures, and helper functions for vector isolation
and security integration testing.
"""

import pytest
import asyncio
import httpx
from uuid import uuid4
from typing import Dict, Any, List, AsyncGenerator
import structlog

# Configure logging for tests
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


# Integration Test Configuration
INTEGRATION_TEST_CONFIG = {
    "vector_service_url": "http://localhost:5210",
    "timeout": 30.0,
    "max_retries": 3,
    "test_timeout": 300.0,  # 5 minutes per test
    "cleanup_timeout": 60.0,  # 1 minute for cleanup
    "performance_test_vectors": 1000,
    "isolation_test_projects": 3,
    "vectors_per_project": 30,
}


@pytest.fixture(scope="session")
def event_loop():
    """
    Create an instance of the default event loop for the test session.

    This ensures that all async tests share the same event loop.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def integration_config():
    """
    Provide integration test configuration.

    Returns:
        Dictionary with integration test configuration
    """
    return INTEGRATION_TEST_CONFIG


@pytest.fixture(scope="function")
async def vector_client(integration_config):
    """
    Create an HTTP client for vector API testing.

    Args:
        integration_config: Test configuration fixture

    Yields:
        httpx.AsyncClient configured for vector API
    """
    client = httpx.AsyncClient(
        base_url=integration_config["vector_service_url"],
        timeout=integration_config["timeout"],
    )

    try:
        # Verify vector service is available
        response = await client.get("/api/v1/vector/health")
        if response.status_code != 200:
            pytest.skip(f"Vector service not available: {response.status_code}")

        yield client

    except httpx.ConnectError:
        pytest.skip("Vector service not reachable - ensure it's running")
    except Exception as e:
        logger.exception("Vector service setup failed", exc_info=True)
        pytest.skip(f"Vector service setup failed: {e}")
    finally:
        await client.aclose()


@pytest.fixture(scope="function")
async def test_project_context():
    """
    Create a test project context for isolation testing.

    Yields:
        Dictionary with project_id and language for testing
    """
    project_context = {"project_id": str(uuid4()), "language": "en"}

    yield project_context


@pytest.fixture(scope="function")
async def multi_project_contexts():
    """
    Create multiple test project contexts for cross-project testing.

    Yields:
        List of project contexts with different languages
    """
    contexts = [
        {"project_id": str(uuid4()), "language": "en"},
        {"project_id": str(uuid4()), "language": "ru"},
        {"project_id": str(uuid4()), "language": "es"},
    ]

    yield contexts


@pytest.fixture(scope="function")
async def performance_test_data():
    """
    Generate performance test data.

    Yields:
        Dictionary with performance test vectors and queries
    """
    from ..fixtures.vector_test_data import get_performance_test_fixtures

    perf_data = get_performance_test_fixtures()

    yield perf_data


class VectorTestHelper:
    """Helper class for vector integration testing."""

    def __init__(self, client: httpx.AsyncClient):
        """
        Initialize test helper.

        Args:
            client: HTTP client for API calls
        """
        self.client = client
        self.created_points = []

    async def create_test_vector(
        self,
        project_id: str,
        language: str,
        content: str = "Test content",
        doc_type: str = "knowledge",
    ) -> str:
        """
        Create a single test vector.

        Args:
            project_id: Project UUID
            language: Language code
            content: Vector content
            doc_type: Document type

        Returns:
            UUID of created vector
        """
        from ..fixtures.vector_test_data import create_test_vector

        vector_data = create_test_vector(
            project_id=project_id, language=language, content=content, doc_type=doc_type
        )

        response = await self.client.post(
            "/api/v1/vector/upsert",
            json={
                "points": [
                    {
                        "id": vector_data["id"],
                        "vector": vector_data["vector"],
                        "content": vector_data["content"],
                        "title": vector_data["title"],
                        "type": vector_data["type"],
                        "metadata": vector_data["metadata"],
                        "importance": vector_data["importance"],
                    }
                ]
            },
            params={"project_id": project_id, "language": language},
        )

        assert response.status_code == 200, (
            f"Failed to create test vector: {response.text}"
        )

        self.created_points.append(vector_data["id"])
        return vector_data["id"]

    async def search_vectors(
        self, project_id: str, language: str, query_vector: List[float], limit: int = 10
    ) -> Dict[str, Any]:
        """
        Search for vectors.

        Args:
            project_id: Project UUID
            language: Language code
            query_vector: Query vector
            limit: Result limit

        Returns:
            Search response data
        """
        response = await self.client.post(
            "/api/v1/vector/search",
            json={"query_vector": query_vector, "limit": limit},
            params={"project_id": project_id, "language": language},
        )

        assert response.status_code == 200, f"Search failed: {response.text}"
        return response.json()

    async def get_vector_health(self) -> Dict[str, Any]:
        """
        Get vector service health status.

        Returns:
            Health status dictionary
        """
        response = await self.client.get("/api/v1/vector/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        return response.json()

    async def cleanup_created_vectors(self, project_id: str, language: str):
        """
        Clean up vectors created during testing.

        Args:
            project_id: Project UUID
            language: Language code

        Raises:
            NotImplementedError: Cleanup not implemented due to isolation constraints
        """
        if not self.created_points:
            return

        try:
            # CRITICAL: Cleanup is not implemented due to strict isolation constraints
            # Individual tests must handle their own cleanup with proper project context
            # to ensure deletion operations respect multi-tenant boundaries
            logger.error(
                "Vector cleanup not implemented",
                points_count=len(self.created_points),
                reason="isolation_constraints",
            )
            raise NotImplementedError(
                "Vector cleanup not implemented due to isolation constraints. "
                "Tests must handle cleanup within proper project context."
            )
        except NotImplementedError:
            raise
        except Exception as e:
            logger.exception("Vector cleanup failed unexpectedly", exc_info=True)
            raise
        finally:
            self.created_points.clear()


@pytest.fixture(scope="function")
async def vector_helper(vector_client):
    """
    Create vector test helper.

    Args:
        vector_client: HTTP client fixture

    Yields:
        VectorTestHelper instance
    """
    helper = VectorTestHelper(vector_client)

    try:
        yield helper
    finally:
        # Cleanup will be handled by individual test methods
        # since they may use different project contexts
        pass


# Test markers for different test categories
pytest_plugins = []


def pytest_configure(config):
    """
    Configure custom pytest markers.
    """
    config.addinivalue_line(
        "markers", "isolation: marks tests as project/language isolation tests"
    )
    config.addinivalue_line(
        "markers", "security: marks tests as security-focused tests"
    )
    config.addinivalue_line("markers", "performance: marks tests as performance tests")
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running (may be skipped in CI)"
    )


def pytest_collection_modifyitems(config, items):
    """
    Modify test collection to add markers automatically.
    """
    for item in items:
        # Add markers based on test file location
        if "test_vector_isolation.py" in str(item.fspath):
            item.add_marker(pytest.mark.isolation)
        elif "test_vector_security.py" in str(item.fspath):
            item.add_marker(pytest.mark.security)

        # Add markers based on test function names
        if "performance" in item.name.lower():
            item.add_marker(pytest.mark.performance)
        if "slow" in item.name.lower() or "comprehensive" in item.name.lower():
            item.add_marker(pytest.mark.slow)


# Test discovery and execution helpers
def discover_vector_tests():
    """
    Discover all vector-related tests.

    Returns:
        List of test module paths
    """
    import os
    import glob

    test_dir = os.path.dirname(__file__)
    vector_test_files = glob.glob(os.path.join(test_dir, "test_vector_*.py"))

    return vector_test_files


async def run_vector_test_suite():
    """
    Run the complete vector test suite.

    Returns:
        Test results summary
    """
    import subprocess
    import sys

    test_files = discover_vector_tests()

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-v",
        "--tb=short",
        "--durations=10",
        *test_files,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "test_files": test_files,
    }


# Utility functions for test assertions
def assert_no_data_leakage(
    search_results: List[Dict[str, Any]], forbidden_content: List[str]
):
    """
    Assert that search results don't contain forbidden content.

    Args:
        search_results: List of search result dictionaries
        forbidden_content: List of content strings that should not appear
    """
    for result in search_results:
        content = result.get("content", "").lower()
        title = result.get("title", "").lower()

        for forbidden in forbidden_content:
            forbidden_lower = forbidden.lower()
            assert forbidden_lower not in content, (
                f"Forbidden content found in result: {forbidden}"
            )
            assert forbidden_lower not in title, (
                f"Forbidden content found in title: {forbidden}"
            )


def assert_isolation_boundaries(
    results_a: List[Dict[str, Any]], results_b: List[Dict[str, Any]]
):
    """
    Assert that two result sets are properly isolated.

    Args:
        results_a: First set of results
        results_b: Second set of results
    """
    ids_a = {r.get("id") for r in results_a}
    ids_b = {r.get("id") for r in results_b}

    overlap = ids_a & ids_b
    assert len(overlap) == 0, (
        f"Isolation violation: {len(overlap)} overlapping results found"
    )


# Performance testing utilities
import time
import statistics
from typing import List


class PerformanceMetrics:
    """Track and analyze performance metrics for tests."""

    def __init__(self):
        self.measurements = []

    def record_measurement(self, operation: str, duration_ms: float):
        """
        Record a performance measurement.

        Args:
            operation: Operation name
            duration_ms: Duration in milliseconds
        """
        self.measurements.append(
            {
                "operation": operation,
                "duration_ms": duration_ms,
                "timestamp": time.time(),
            }
        )

    def get_statistics(self, operation: str = None) -> Dict[str, float]:
        """
        Get performance statistics.

        Args:
            operation: Optional operation name to filter by

        Returns:
            Dictionary with performance statistics
        """
        measurements = self.measurements
        if operation:
            measurements = [m for m in measurements if m["operation"] == operation]

        if not measurements:
            return {}

        durations = [m["duration_ms"] for m in measurements]

        return {
            "count": len(durations),
            "min_ms": min(durations),
            "max_ms": max(durations),
            "mean_ms": statistics.mean(durations),
            "median_ms": statistics.median(durations),
            "p95_ms": self._percentile(durations, 95),
            "p99_ms": self._percentile(durations, 99),
        }

    def _percentile(self, data: List[float], percentile: float) -> float:
        """Calculate percentile of data."""
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        lower = int(index)
        upper = min(lower + 1, len(sorted_data) - 1)
        weight = index - lower

        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight
