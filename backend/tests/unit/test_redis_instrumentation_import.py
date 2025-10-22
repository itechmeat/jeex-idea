#!/usr/bin/env python3
"""
Redis Instrumentation Import Test

Simple test to verify that all Redis instrumentation components can be
imported and initialized correctly.
"""

import asyncio
import sys
import traceback
from pathlib import Path

# Add app directory to Python path (project root is 3 levels up from tests/unit)
app_path = Path(__file__).resolve().parents[2] / "app"
sys.path.insert(0, str(app_path))


async def test_imports():
    """Test that all Redis instrumentation components can be imported."""
    print("Testing Redis instrumentation imports...")

    try:
        # Test core instrumentation
        from app.core.redis_instrumentation import (
            redis_instrumentation,
            RedisCommandCategory,
        )

        print("✅ Core Redis instrumentation imported successfully")

        # Test integration layer
        from app.core.redis_instrumentation_integration import (
            redis_instrumentation_integration,
        )

        print("✅ Redis instrumentation integration imported successfully")

        # Test instrumented service
        from app.infrastructure.redis.instrumented_redis_service import (
            instrumented_redis_service,
            InstrumentedRedisClient,
        )

        print("✅ Instrumented Redis service imported successfully")

        # Test enhanced connection factory
        from app.infrastructure.redis.connection_factory import redis_connection_factory

        print("✅ Redis connection factory imported successfully")

        # Test API endpoints
        from app.api.endpoints.redis_instrumentation_test import (
            router as redis_test_router,
        )

        print("✅ Redis instrumentation test endpoints imported successfully")

        return True

    except Exception as e:
        print(f"❌ Import test failed: {e}")
        traceback.print_exc()
        return False


async def test_basic_functionality():
    """Test basic functionality of Redis instrumentation components."""
    print("\nTesting basic Redis instrumentation functionality...")

    try:
        from app.core.redis_instrumentation import (
            redis_instrumentation,
            RedisCommandCategory,
        )

        # Test command categorization
        test_commands = {
            "GET": RedisCommandCategory.READ,
            "SET": RedisCommandCategory.WRITE,
            "DEL": RedisCommandCategory.DELETE,
            "PING": RedisCommandCategory.ADMIN,
            "MULTI": RedisCommandCategory.TRANSACTION,
            "PUBLISH": RedisCommandCategory.PUBSUB,
            "XADD": RedisCommandCategory.STREAM,
        }

        for cmd, expected_category in test_commands.items():
            category = redis_instrumentation._categorize_command(cmd)
            if category == expected_category:
                print(f"✅ Command {cmd} correctly categorized as {category.value}")
            else:
                print(
                    f"❌ Command {cmd} categorized as {category.value}, expected {expected_category.value}"
                )
                return False

        # Test cache performance tracking
        cache_performance = redis_instrumentation.get_cache_performance_summary()
        if isinstance(cache_performance, dict):
            print("✅ Cache performance summary working")
        else:
            print("❌ Cache performance summary failed")
            return False

        # Test error rate tracking
        error_stats = redis_instrumentation.get_error_rate_stats()
        if isinstance(error_stats, dict):
            print("✅ Error rate statistics working")
        else:
            print("❌ Error rate statistics failed")
            return False

        return True

    except Exception as e:
        print(f"❌ Basic functionality test failed: {e}")
        traceback.print_exc()
        return False


async def test_instrumentation_integration():
    """Test Redis instrumentation integration initialization."""
    print("\nTesting Redis instrumentation integration...")

    try:
        from app.core.redis_instrumentation_integration import (
            redis_instrumentation_integration,
        )

        # Test status check (without full initialization)
        status = await redis_instrumentation_integration.get_instrumentation_status()
        if isinstance(status, dict):
            print("✅ Instrumentation status check working")
        else:
            print("❌ Instrumentation status check failed")
            return False

        # Test health check
        health = await redis_instrumentation_integration.health_check()
        if isinstance(health, dict) and "status" in health:
            print("✅ Health check working")
        else:
            print("❌ Health check failed")
            return False

        return True

    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        traceback.print_exc()
        return False


async def main():
    """Run all Redis instrumentation tests."""
    print("=" * 60)
    print("REDIS INSTRUMENTATION IMPORT AND FUNCTIONALITY TEST")
    print("=" * 60)

    tests = [
        ("Import Test", test_imports),
        ("Basic Functionality Test", test_basic_functionality),
        ("Integration Test", test_instrumentation_integration),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            if await test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} FAILED with exception: {e}")

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed}/{total} tests passed")
    if passed == total:
        print("🎉 All Redis instrumentation tests PASSED!")
        print("The implementation is ready for Task 2.2 validation.")
    else:
        print("⚠️  Some tests failed. Check the implementation.")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
