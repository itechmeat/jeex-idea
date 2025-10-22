#!/usr/bin/env python3
"""
Simple validation script for telemetry resilience functionality.

This script validates the core resilience components without requiring
full application startup or external dependencies.
"""

import asyncio
import json
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# Add current directory to path
sys.path.insert(0, ".")


def test_imports():
    """Test that all resilience components can be imported."""
    print("🔍 Testing imports...")

    try:
        from app.core.resilient_exporter import (
            LocalBuffer,
            CircuitBreaker,
            ExponentialBackoffRetry,
            ResilientSpanExporter,
            FileSpanExporter,
            CircuitState,
            ExportMetrics,
        )

        print("✅ Resilience components imported successfully")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False


def test_local_buffer():
    """Test LocalBuffer functionality."""
    print("🔍 Testing LocalBuffer...")

    try:
        from app.core.resilient_exporter import LocalBuffer

        # Create buffer
        buffer = LocalBuffer(max_size=10, max_age_minutes=1)
        print("  ✅ LocalBuffer created")

        # Test basic operations
        assert buffer.put("test_item_1") is True
        assert buffer.put("test_item_2") is True
        assert buffer.size() == 2
        print("  ✅ Basic put/size operations work")

        # Test get_all
        items = buffer.get_all()
        assert len(items) == 2
        assert buffer.size() == 0
        print("  ✅ get_all works correctly")

        # Test overflow behavior
        for i in range(15):
            buffer.put(f"overflow_item_{i}")

        assert buffer.size() <= 10
        print("  ✅ Buffer overflow handling works")

        # Test cleanup
        buffer.clear()
        assert buffer.size() == 0
        print("  ✅ Buffer cleanup works")

        return True
    except Exception as e:
        print(f"  ❌ LocalBuffer test failed: {e}")
        traceback.print_exc()
        return False


def test_circuit_breaker():
    """Test CircuitBreaker functionality."""
    print("🔍 Testing CircuitBreaker...")

    try:
        from app.core.resilient_exporter import CircuitBreaker, CircuitState

        # Create circuit breaker
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
        assert breaker.state == CircuitState.CLOSED
        print("  ✅ CircuitBreaker created in CLOSED state")

        # Test normal operation
        assert breaker.allow_request() is True
        breaker.on_success()
        assert breaker.state == CircuitState.CLOSED
        print("  ✅ Normal operation works")

        # Test failure threshold
        breaker.on_failure()
        breaker.on_failure()
        assert breaker.state == CircuitState.CLOSED
        print("  ✅ Below threshold failures handled correctly")

        breaker.on_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.allow_request() is False
        print("  ✅ Circuit opens after threshold")

        # Test recovery
        time.sleep(1.1)  # Wait for recovery timeout
        assert breaker.allow_request() is True
        assert breaker.state == CircuitState.HALF_OPEN
        print("  ✅ Recovery timeout works")

        # Test success in half-open
        breaker.on_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        print("  ✅ Success in half-open closes circuit")

        return True
    except Exception as e:
        print(f"  ❌ CircuitBreaker test failed: {e}")
        traceback.print_exc()
        return False


def test_exponential_backoff():
    """Test ExponentialBackoffRetry functionality."""
    print("🔍 Testing ExponentialBackoffRetry...")

    try:
        from app.core.resilient_exporter import ExponentialBackoffRetry

        # Create retry instance
        retry = ExponentialBackoffRetry(
            max_retries=3, base_delay=0.01, max_delay=1.0, jitter=False
        )
        print("  ✅ ExponentialBackoffRetry created")

        # Test delay calculation
        assert retry._calculate_delay(0) == 0.01
        assert retry._calculate_delay(1) == 0.02
        assert retry._calculate_delay(2) == 0.04
        assert retry._calculate_delay(3) == 0.08
        print("  ✅ Delay calculation works correctly")

        # Test max delay cap
        assert retry._calculate_delay(20) == 1.0
        print("  ✅ Max delay cap works")

        # Test with jitter
        retry_with_jitter = ExponentialBackoffRetry(
            max_retries=3, base_delay=0.1, jitter=True
        )
        delay = retry_with_jitter._calculate_delay(2)  # Should be around 0.4
        assert 0.3 <= delay <= 0.5  # ±25% of 0.4
        print("  ✅ Jitter addition works")

        return True
    except Exception as e:
        print(f"  ❌ ExponentialBackoffRetry test failed: {e}")
        traceback.print_exc()
        return False


async def test_retry_execution():
    """Test retry execution with async function."""
    print("🔍 Testing retry execution...")

    try:
        from app.core.resilient_exporter import ExponentialBackoffRetry

        retry = ExponentialBackoffRetry(max_retries=3, base_delay=0.01)

        # Test successful execution
        call_count = 0

        def success_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await retry.execute_with_retry(success_function)
        assert result == "success"
        assert call_count == 1
        print("  ✅ Successful execution works")

        # Test execution with retries
        call_count = 0

        def retry_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"Attempt {call_count} failed")
            return "success_after_retries"

        result = await retry.execute_with_retry(retry_function)
        assert result == "success_after_retries"
        assert call_count == 3
        print("  ✅ Retry logic works correctly")

        # Test exhausted retries
        def always_fail_function():
            raise ValueError("Always fails")

        try:
            await retry.execute_with_retry(always_fail_function)
            assert False, "Should have raised exception"
        except ValueError:
            print("  ✅ Exhausted retries raise exception correctly")

        return True
    except Exception as e:
        print(f"  ❌ Retry execution test failed: {e}")
        traceback.print_exc()
        return False


def test_file_span_exporter():
    """Test FileSpanExporter functionality."""
    print("🔍 Testing FileSpanExporter...")

    try:
        from app.core.resilient_exporter import FileSpanExporter
        from opentelemetry.sdk.trace.export import SpanExportResult

        # Create temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            exporter = FileSpanExporter(output_dir=Path(temp_dir))
            print("  ✅ FileSpanExporter created")

            # Create mock spans
            mock_spans = []
            for i in range(3):
                span = type(
                    "MockSpan",
                    (),
                    {
                        "name": f"test-span-{i}",
                        "trace_id": i,
                        "span_id": i,
                        "parent_span_id": None,
                        "start_time": 1000 + i,
                        "end_time": 2000 + i,
                        "status": type(
                            "Status",
                            (),
                            {
                                "status_code": type("StatusCode", (), {"name": "OK"})(),
                                "description": None,
                            },
                        )(),
                        "attributes": {"test_attr": f"value_{i}"},
                        "events": [],
                        "resource": type(
                            "Resource",
                            (),
                            {"attributes": {"service.name": "test-service"}},
                        )(),
                    },
                )()
                mock_spans.append(span)

            # Test export
            result = exporter.export(mock_spans)
            assert result == SpanExportResult.SUCCESS
            print("  ✅ Export to file works")

            # Test force flush
            result = exporter.force_flush()
            assert result == SpanExportResult.SUCCESS
            print("  ✅ Force flush works")

            # Check that files were created
            files = list(Path(temp_dir).glob("spans_*.json"))
            assert len(files) > 0
            print("  ✅ Files created successfully")

            # Test file content
            with open(files[0], "r") as f:
                data = json.load(f)
                assert "spans" in data
                assert len(data["spans"]) == 3
                assert data["spans"][0]["name"] == "test-span-0"
            print("  ✅ File content is correct")

            # Test shutdown
            exporter.shutdown()
            print("  ✅ Shutdown works")

        return True
    except Exception as e:
        print(f"  ❌ FileSpanExporter test failed: {e}")
        traceback.print_exc()
        return False


def test_resilience_integration():
    """Test integration of resilience components."""
    print("🔍 Testing resilience integration...")

    try:
        from app.core.resilient_exporter import (
            ResilientSpanExporter,
            LocalBuffer,
            CircuitBreaker,
            FileSpanExporter,
        )
        from opentelemetry.sdk.trace.export import SpanExportResult

        # Create mock primary exporter that fails
        def mock_export(spans, timeout_millis=30000):
            raise Exception("Connection failed")

        mock_primary = type(
            "MockExporter",
            (),
            {
                "export": mock_export,
                "shutdown": lambda: None,
                "force_flush": lambda timeout_millis=30000: SpanExportResult.SUCCESS,
            },
        )()

        # Create resilient exporter
        resilient_exporter = ResilientSpanExporter(
            primary_exporter=mock_primary,
            fallback_enabled=True,
            buffer_size=100,
            buffer_max_age_minutes=5,
            circuit_breaker_threshold=3,
            circuit_breaker_timeout=1,
        )
        print("  ✅ ResilientSpanExporter created with mock primary")

        # Test export with failure
        mock_spans = [type("MockSpan", (), {"name": "test-span"})()]
        result = resilient_exporter.export(mock_spans)
        assert result == SpanExportResult.FAILURE
        print("  ✅ Export failure handled correctly")

        # Check that spans were buffered
        assert resilient_exporter.buffer.size() == 1
        print("  ✅ Spans buffered on primary failure")

        # Test metrics
        metrics = resilient_exporter.get_metrics()
        assert metrics.total_exports == 1
        assert metrics.failed_exports == 1
        assert metrics.buffer_size == 1
        print("  ✅ Metrics tracking works")

        # Test shutdown
        resilient_exporter.shutdown()
        print("  ✅ Resilient exporter shutdown works")

        return True
    except Exception as e:
        print(f"  ❌ Resilience integration test failed: {e}")
        traceback.print_exc()
        return False


async def main():
    """Run all validation tests."""
    print("🚀 Starting telemetry resilience validation\n")

    tests = [
        ("Import Test", test_imports),
        ("LocalBuffer Test", test_local_buffer),
        ("CircuitBreaker Test", test_circuit_breaker),
        ("ExponentialBackoff Test", test_exponential_backoff),
        ("Retry Execution Test", test_retry_execution),
        ("FileSpanExporter Test", test_file_span_exporter),
        ("Resilience Integration Test", test_resilience_integration),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()

            if result:
                print(f"✅ {test_name} PASSED")
                passed += 1
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")

    print(f"\n{'=' * 50}")
    print(f"📊 Validation Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All resilience components validated successfully!")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
