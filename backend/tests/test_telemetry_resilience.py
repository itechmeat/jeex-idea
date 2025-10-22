"""
JEEX Idea Telemetry Resilience Tests

Test suite for validating OpenTelemetry resilience patterns including:
- Graceful degradation when collector unavailable
- Local buffering and recovery
- Exponential backoff retry logic
- Fallback to file-based storage
- Circuit breaker functionality
"""

import asyncio
import json
import logging
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.core.telemetry import (
    OpenTelemetryManager,
    get_telemetry_health,
    get_resilience_metrics,
)

# Initialize logger before use
logger = logging.getLogger(__name__)

# Import resilience components with error handling
try:
    from app.core.resilient_exporter import (
        ResilientSpanExporter,
        LocalBuffer,
        CircuitBreaker,
        ExponentialBackoffRetry,
        CircuitState,
    )
except ImportError as e:
    logger.warning(f"Resilience components not available: {e}")
    # Create mock classes for testing
    ResilientSpanExporter = Mock
    LocalBuffer = Mock
    CircuitBreaker = Mock
    ExponentialBackoffRetry = Mock
    CircuitState = Mock
from app.core.config import get_settings
from app.main import app


class TestLocalBuffer:
    """Test suite for LocalBuffer functionality."""

    def test_buffer_initialization(self):
        """Test buffer initialization with default parameters."""
        buffer = LocalBuffer()
        assert buffer.max_size == 10000
        assert buffer.max_age == timedelta(minutes=5)
        assert buffer.size() == 0
        assert buffer.backup_dir.exists()

    def test_buffer_initialization_custom_params(self):
        """Test buffer initialization with custom parameters."""
        buffer = LocalBuffer(max_size=100, max_age_minutes=1)
        assert buffer.max_size == 100
        assert buffer.max_age == timedelta(minutes=1)

    def test_put_and_get_items(self):
        """Test putting and getting items from buffer."""
        buffer = LocalBuffer(max_size=10)

        # Put items
        test_items = [f"item_{i}" for i in range(5)]
        for item in test_items:
            result = buffer.put(item)
            assert result is True

        assert buffer.size() == 5

        # Get all items
        retrieved_items = buffer.get_all()
        assert len(retrieved_items) == 5
        assert buffer.size() == 0  # Should be empty after get_all

    def test_buffer_overflow(self):
        """Test buffer behavior when full."""
        buffer = LocalBuffer(max_size=3)

        # Add more items than buffer size
        for i in range(5):
            buffer.put(f"item_{i}")

        # Should only keep last 3 items
        assert buffer.size() == 3

        items = buffer.get_all()
        assert len(items) == 3
        # Should contain the most recent items
        assert "item_2" in items
        assert "item_3" in items
        assert "item_4" in items

    def test_expired_items_cleanup(self):
        """Test cleanup of expired items."""
        buffer = LocalBuffer(max_size=10, max_age_minutes=0.01)  # Very short expiry

        # Add items
        for i in range(5):
            buffer.put(f"item_{i}")

        # Wait for items to expire
        time.sleep(2)

        # Cleanup expired items
        removed = buffer.cleanup_expired()
        assert removed == 5
        assert buffer.size() == 0

    def test_get_items_with_age_filter(self):
        """Test getting items filtered by age."""
        buffer = LocalBuffer(max_size=10, max_age_minutes=5)

        # Add items
        for i in range(5):
            buffer.put(f"item_{i}")

        # Get items with short age filter (should return none if we wait)
        time.sleep(1)
        recent_items = buffer.get_all(max_age=timedelta(seconds=0.5))
        assert len(recent_items) == 0

    def test_clear_buffer(self):
        """Test clearing buffer."""
        buffer = LocalBuffer(max_size=10)

        # Add items
        for i in range(5):
            buffer.put(f"item_{i}")

        assert buffer.size() == 5

        # Clear buffer
        buffer.clear()
        assert buffer.size() == 0


class TestCircuitBreaker:
    """Test suite for CircuitBreaker functionality."""

    def test_circuit_breaker_initialization(self):
        """Test circuit breaker initialization."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        assert breaker.failure_threshold == 3
        assert breaker.recovery_timeout == 60
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_circuit_breaker_closed_operation(self):
        """Test circuit breaker operation when closed."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        # Should allow requests when closed
        assert breaker.allow_request() is True

        # Success should not change state
        breaker.on_success()
        assert breaker.state == CircuitState.CLOSED

    def test_circuit_breaker_failure_threshold(self):
        """Test circuit breaker opens after failure threshold."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)

        # Fail below threshold
        breaker.on_failure()
        breaker.on_failure()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 2

        # Fail at threshold
        breaker.on_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 3

    def test_circuit_breaker_blocks_requests_when_open(self):
        """Test circuit breaker blocks requests when open."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # Trigger circuit to open
        breaker.on_failure()
        breaker.on_failure()
        assert breaker.state == CircuitState.OPEN

        # Should block requests
        assert breaker.allow_request() is False

    def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery after timeout."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        # Trigger circuit to open
        breaker.on_failure()
        breaker.on_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.2)

        # Should allow requests (half-open state)
        assert breaker.allow_request() is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_circuit_breaker_success_in_half_open(self):
        """Test circuit breaker closes on success in half-open state."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        # Trigger circuit to open
        breaker.on_failure()
        breaker.on_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.2)

        # Allow request (should be half-open)
        breaker.allow_request()

        # Success should close circuit
        breaker.on_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_circuit_breaker_failure_in_half_open(self):
        """Test circuit breaker opens again on failure in half-open state."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        # Trigger circuit to open
        breaker.on_failure()
        breaker.on_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.2)

        # Allow request (should be half-open)
        breaker.allow_request()

        # Failure should open circuit again
        breaker.on_failure()
        assert breaker.state == CircuitState.OPEN


class TestExponentialBackoffRetry:
    """Test suite for ExponentialBackoffRetry functionality."""

    def test_retry_initialization(self):
        """Test retry initialization."""
        retry = ExponentialBackoffRetry(max_retries=5, base_delay=1.0, max_delay=60.0)
        assert retry.max_retries == 5
        assert retry.base_delay == 1.0
        assert retry.max_delay == 60.0

    def test_delay_calculation(self):
        """Test exponential delay calculation."""
        retry = ExponentialBackoffRetry(
            max_retries=5, base_delay=1.0, max_delay=10.0, jitter=False
        )

        # Test exponential growth
        assert retry._calculate_delay(0) == 1.0
        assert retry._calculate_delay(1) == 2.0
        assert retry._calculate_delay(2) == 4.0
        assert retry._calculate_delay(3) == 8.0

        # Test max delay cap
        assert retry._calculate_delay(10) == 10.0

    def test_delay_with_jitter(self):
        """Test delay calculation with jitter."""
        retry = ExponentialBackoffRetry(
            max_retries=5, base_delay=1.0, max_delay=10.0, jitter=True
        )

        # With jitter, delay should be within ±25% of base
        delay = retry._calculate_delay(2)  # Should be around 4.0
        assert 3.0 <= delay <= 5.0  # ±25% of 4.0

    async def test_successful_execution(self):
        """Test successful execution without retries."""
        retry = ExponentialBackoffRetry(max_retries=3, base_delay=0.01)

        call_count = 0

        def failing_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await retry.execute_with_retry(failing_function)
        assert result == "success"
        assert call_count == 1

    async def test_execution_with_retries(self):
        """Test execution with retries."""
        retry = ExponentialBackoffRetry(max_retries=3, base_delay=0.01)

        call_count = 0

        def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"Attempt {call_count} failed")
            return "success"

        result = await retry.execute_with_retry(failing_function)
        assert result == "success"
        assert call_count == 3

    async def test_execution_exhausted_retries(self):
        """Test execution when all retries are exhausted."""
        retry = ExponentialBackoffRetry(max_retries=2, base_delay=0.01)

        def failing_function():
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            await retry.execute_with_retry(failing_function)


class TestResilientSpanExporter:
    """Test suite for ResilientSpanExporter functionality."""

    @pytest.fixture
    def mock_primary_exporter(self):
        """Create mock primary exporter."""
        exporter = Mock()
        exporter.export.return_value = Mock()
        exporter.shutdown.return_value = None
        exporter.force_flush.return_value = None
        return exporter

    @pytest.fixture
    def resilient_exporter(self, mock_primary_exporter):
        """Create resilient exporter with mock primary."""
        return ResilientSpanExporter(
            primary_exporter=mock_primary_exporter,
            fallback_enabled=True,
            buffer_size=100,
            buffer_max_age_minutes=5,
            circuit_breaker_threshold=3,
            circuit_breaker_timeout=1,
        )

    def test_resilient_exporter_initialization(self, resilient_exporter):
        """Test resilient exporter initialization."""
        assert resilient_exporter.primary_exporter is not None
        assert resilient_exporter.fallback_enabled is True
        assert resilient_exporter.buffer.max_size == 100
        assert resilient_exporter.circuit_breaker.failure_threshold == 3

    def test_successful_export(self, resilient_exporter, mock_primary_exporter):
        """Test successful export through primary exporter."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_primary_exporter.export.return_value = SpanExportResult.SUCCESS

        # Create mock spans
        mock_spans = [Mock() for _ in range(3)]

        result = resilient_exporter.export(mock_spans)
        assert result == SpanExportResult.SUCCESS
        assert resilient_exporter.metrics.successful_exports == 1
        assert resilient_exporter.metrics.failed_exports == 0

    def test_failed_export_with_buffering(
        self, resilient_exporter, mock_primary_exporter
    ):
        """Test export failure with buffering fallback."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_primary_exporter.export.side_effect = Exception("Connection failed")

        # Create mock spans
        mock_spans = [Mock() for _ in range(3)]

        result = resilient_exporter.export(mock_spans)
        assert result == SpanExportResult.FAILURE
        assert resilient_exporter.metrics.failed_exports == 1
        assert resilient_exporter.buffer.size() == 3  # Should be buffered

    def test_circuit_breaker_activation(
        self, resilient_exporter, mock_primary_exporter
    ):
        """Test circuit breaker activation after repeated failures."""
        mock_primary_exporter.export.side_effect = Exception("Connection failed")

        # Create mock spans
        mock_spans = [Mock()]

        # Fail multiple times to trigger circuit breaker
        for i in range(3):
            resilient_exporter.export(mock_spans)

        # Circuit breaker should be open
        assert resilient_exporter.circuit_breaker.state == CircuitState.OPEN
        assert resilient_exporter.metrics.circuit_breaker_trips >= 1

    def test_metrics_tracking(self, resilient_exporter, mock_primary_exporter):
        """Test metrics tracking functionality."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_primary_exporter.export.return_value = SpanExportResult.SUCCESS

        # Create mock spans
        mock_spans = [Mock() for _ in range(3)]

        # Export spans
        resilient_exporter.export(mock_spans)
        resilient_exporter.export(mock_spans)

        metrics = resilient_exporter.get_metrics()
        assert metrics.total_exports == 2
        assert metrics.successful_exports == 2
        assert metrics.failed_exports == 0

    def test_shutdown_cleanup(self, resilient_exporter, mock_primary_exporter):
        """Test shutdown cleanup."""
        # Add some spans to buffer
        resilient_exporter.buffer.put("test_span")

        # Shutdown exporter
        resilient_exporter.shutdown()

        # Should shutdown primary exporter
        mock_primary_exporter.shutdown.assert_called_once()

        # Should be marked as shutdown
        assert resilient_exporter._shutdown is True


class TestTelemetryResilienceAPI:
    """Test suite for telemetry resilience API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_health_endpoint(self, client):
        """Test telemetry health endpoint."""
        response = client.get("/telemetry-test/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "healthy" in data
        assert "initialized" in data
        assert "collector_endpoint" in data
        assert "service_name" in data

    def test_metrics_endpoint(self, client):
        """Test resilience metrics endpoint."""
        response = client.get("/telemetry-test/metrics")
        assert response.status_code == 200

        data = response.json()
        # May contain metrics or message about initialization
        assert isinstance(data, (dict, str))

    def test_generate_load_endpoint(self, client):
        """Test telemetry load generation endpoint."""
        payload = {"span_count": 5, "delay_ms": 10, "include_errors": False}

        response = client.post("/telemetry-test/generate-loads", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "generated_spans" in data
        assert "error_spans" in data
        assert data["generated_spans"] <= payload["span_count"]

    def test_simulate_collector_failure(self, client):
        """Test collector failure simulation endpoint."""
        payload = {"duration_seconds": 30}

        response = client.post(
            "/telemetry-test/simulate/collector-failure", json=payload
        )
        assert response.status_code == 200

        data = response.json()
        assert "message" in data
        assert "duration_seconds" in data

    def test_start_resilience_test(self, client):
        """Test starting a resilience test."""
        payload = {
            "test_type": "continuous_load",
            "duration_seconds": 10,
            "span_rate": 5,
            "severity": "moderate",
        }

        response = client.post("/telemetry-test/test/start", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "test_id" in data
        assert "test_type" in data
        assert "status" in data
        assert data["status"] == "started"

    def test_list_active_tests(self, client):
        """Test listing active tests."""
        response = client.get("/telemetry-test/tests")
        assert response.status_code == 200

        data = response.json()
        assert "active_tests" in data
        assert isinstance(data["active_tests"], list)


class TestOpenTelemetryManagerResilience:
    """Test suite for OpenTelemetry manager resilience features."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock()
        settings.OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4317"
        settings.OTEL_SERVICE_NAME = "test-service"
        settings.OTEL_SERVICE_VERSION = "0.1.0"
        settings.ENVIRONMENT = "test"
        settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
        settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60
        return settings

    @pytest.fixture
    def otel_manager(self, mock_settings):
        """Create OpenTelemetry manager with mock settings."""
        with patch("app.core.telemetry.get_settings", return_value=mock_settings):
            manager = OpenTelemetryManager()
            return manager

    def test_get_resilience_metrics_not_initialized(self, otel_manager):
        """Test getting resilience metrics when not initialized."""
        metrics = otel_manager.get_resilience_metrics()
        assert metrics is None

    def test_get_telemetry_health_not_initialized(self, otel_manager):
        """Test getting telemetry health when not initialized."""
        health = otel_manager.get_telemetry_health()
        assert health["initialized"] is False
        assert health["status"] == "healthy"
        assert health["healthy"] is True

    async def test_initialization_failure_handling(self, otel_manager):
        """Test handling of initialization failures."""
        # Mock initialization to fail
        with patch.object(
            otel_manager, "_initialize_tracing", side_effect=Exception("Init failed")
        ):
            result = await otel_manager.initialize()
            assert result is False
            assert otel_manager._initialized is False

    def test_resilient_span_exporter_creation(self, otel_manager):
        """Test creation of resilient span exporter."""
        exporter = otel_manager._create_span_exporter()
        assert isinstance(exporter, ResilientSpanExporter)
        assert exporter.fallback_enabled is True


# Integration Tests
class TestTelemetryResilienceIntegration:
    """Integration tests for telemetry resilience."""

    @pytest.mark.skip(
        reason="TODO: Implement end-to-end resilience flow test - requires complex OpenTelemetry setup"
    )
    async def test_end_to_end_resilience_flow(self):
        """Test end-to-end resilience flow."""
        # TODO: This would require a more complex setup with actual OpenTelemetry components
        # For now, we'll test the integration points
        pass

    @pytest.mark.skip(
        reason="TODO: Implement collector recovery scenario test - requires collector mocking"
    )
    async def test_collector_recovery_scenario(self):
        """Test scenario where collector recovers after failure."""
        # TODO: This would require mocking collector behavior
        pass

    @pytest.mark.skip(
        reason="TODO: Implement buffer recovery test - requires backup/restore functionality"
    )
    async def test_buffer_recovery_after_restart(self):
        """Test buffer recovery after application restart."""
        # TODO: This would involve testing backup/restore functionality
        pass


if __name__ == "__main__":
    # Run specific test suite
    pytest.main([__file__, "-v", "--tb=short"])
