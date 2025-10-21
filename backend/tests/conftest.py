"""
Main pytest configuration for all backend tests.

Fixtures, configuration, and utilities for unit, integration, and performance tests.
"""

import os
import pytest
import asyncio
import json
import time
import statistics
from uuid import uuid4
from typing import Dict, Any, AsyncGenerator
import httpx

# Set test environment variables before importing app modules
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = (
    "postgresql://jeex_user:jeex_password@localhost:5220/jeex_idea_test"
)
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["REDIS_PASSWORD"] = "jeex_redis_secure_password_change_in_production"
os.environ["LOG_LEVEL"] = "DEBUG"

# Import test fixtures
from tests.integration.conftest import (
    PerformanceMetrics,
    assert_no_data_leakage,
    assert_isolation_boundaries,
)


# Basic test configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_config():
    """Provide basic test configuration."""
    return {
        "api_base_url": "http://localhost:5210",
        "redis_url": "redis://localhost:5240",
        "timeout": 30.0,
        "max_retries": 3,
    }


@pytest.fixture(scope="function")
async def api_client(test_config):
    """Create HTTP client for API testing."""
    client = httpx.AsyncClient(
        base_url=test_config["api_base_url"],
        timeout=test_config["timeout"],
    )

    try:
        # Test API connectivity
        response = await client.get("/health")
        if response.status_code != 200:
            pytest.skip(f"API service not available: {response.status_code}")
        yield client
    except httpx.ConnectError:
        pytest.skip("API service not reachable - ensure it's running")
    except Exception as e:
        pytest.skip(f"API service setup failed: {e}")
    finally:
        await client.aclose()


@pytest.fixture(scope="function")
async def test_project_id():
    """Generate test project ID."""
    return str(uuid4())


@pytest.fixture(scope="function")
async def test_user_id():
    """Generate test user ID."""
    return str(uuid4())


@pytest.fixture(scope="function")
async def test_session_id():
    """Generate test session ID."""
    return str(uuid4())


@pytest.fixture(scope="function")
async def test_correlation_id():
    """Generate test correlation ID."""
    return str(uuid4())


# Performance testing utilities
class RedisPerformanceTester:
    """Performance testing utilities for Redis operations."""

    def __init__(self):
        self.metrics = PerformanceMetrics()

    async def benchmark_cache_operations(self, cache_manager, iterations=100):
        """Benchmark cache operations."""
        project_id = uuid4()
        test_data = {"benchmark": "test_data"}

        # Benchmark writes
        write_times = []
        for i in range(iterations):
            start_time = time.time()
            await cache_manager.cache_project_data(
                project_id, {**test_data, "iteration": i}
            )
            write_times.append((time.time() - start_time) * 1000)

        # Benchmark reads
        read_times = []
        for i in range(iterations):
            start_time = time.time()
            await cache_manager.get_project_data(project_id)
            read_times.append((time.time() - start_time) * 1000)

        return {
            "write_times": write_times,
            "read_times": read_times,
            "write_avg": statistics.mean(write_times),
            "write_p95": statistics.quantiles(write_times, n=20)[18],
            "read_avg": statistics.mean(read_times),
            "read_p95": statistics.quantiles(read_times, n=20)[18],
        }


# Test markers and configuration
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "redis: marks tests as Redis-related")
    config.addinivalue_line("markers", "performance: marks tests as performance tests")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "security: marks tests as security tests")


def pytest_collection_modifyitems(config, items):
    """Add markers based on test file location."""
    for item in items:
        if "redis" in item.nodeid:
            item.add_marker(pytest.mark.redis)
        if "performance" in item.nodeid:
            item.add_marker(pytest.mark.performance)
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        if "security" in item.nodeid:
            item.add_marker(pytest.mark.security)
