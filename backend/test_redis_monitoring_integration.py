#!/usr/bin/env python3
"""
Redis Monitoring Integration Test Script

Quick integration test to verify Redis monitoring system is working.
This script can be run manually to test the implementation.
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.monitoring.redis_metrics import redis_metrics_collector
from app.monitoring.health_checker import redis_health_checker
from app.monitoring.performance_monitor import redis_performance_monitor
from app.monitoring.alert_manager import redis_alert_manager
from app.monitoring.dashboard import redis_dashboard_configuration
from app.infrastructure.redis.connection_factory import redis_connection_factory
from app.core.config import get_settings

settings = get_settings()


async def test_redis_connection():
    """Test basic Redis connection."""
    print("🔍 Testing Redis connection...")

    try:
        await redis_connection_factory.initialize()

        async with redis_connection_factory.get_connection() as redis_client:
            result = await redis_client.ping()
            if result:
                print("✅ Redis connection successful")
                return True
            else:
                print("❌ Redis ping failed")
                return False

    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False


async def test_metrics_collection():
    """Test Redis metrics collection."""
    print("📊 Testing metrics collection...")

    try:
        # Track some test commands
        await redis_metrics_collector.track_command_performance(
            "GET", redis_metrics_collector.RedisCommandType.READ, 5.0, True
        )
        await redis_metrics_collector.track_command_performance(
            "SET", redis_metrics_collector.RedisCommandType.WRITE, 10.0, True
        )

        # Collect metrics
        await redis_metrics_collector._collect_memory_metrics()
        await redis_metrics_collector._collect_connection_metrics()

        # Get summary
        summary = await redis_metrics_collector.get_metrics_summary()

        print("✅ Metrics collection successful")
        print(
            f"   Memory usage: {summary.get('memory', {}).get('used_memory_mb', 'N/A'):.2f} MB"
        )
        print(
            f"   Active connections: {summary.get('connections', {}).get('active_connections', 'N/A')}"
        )

        return True

    except Exception as e:
        print(f"❌ Metrics collection failed: {e}")
        return False


async def test_health_checks():
    """Test Redis health checks."""
    print("🏥 Testing health checks...")

    try:
        # Perform full health check
        health_status = await redis_health_checker.perform_full_health_check()

        print(f"✅ Health check completed")
        print(f"   Overall status: {health_status.status.value}")
        print(f"   Redis version: {health_status.version}")
        print(f"   Checks performed: {len(health_status.checks)}")

        # Show individual check results
        for check in health_status.checks:
            status_emoji = "✅" if check.status.value == "healthy" else "⚠️"
            print(f"   {status_emoji} {check.check_type.value}: {check.message}")

        return health_status.status.value in ["healthy", "degraded"]

    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


async def test_performance_monitoring():
    """Test performance monitoring."""
    print("⚡ Testing performance monitoring...")

    try:
        # Track some performance data
        await redis_performance_monitor.track_command_performance(
            "HGET", redis_performance_monitor.RedisCommandType.READ, 3.0, True
        )
        await redis_performance_monitor.track_command_performance(
            "LPUSH", redis_performance_monitor.RedisCommandType.WRITE, 7.0, True
        )

        # Analyze performance
        await redis_performance_monitor._analyze_command_performance()
        await redis_performance_monitor._analyze_connection_performance()
        await redis_performance_monitor._analyze_memory_performance()

        # Get dashboard
        dashboard = await redis_performance_monitor.get_performance_dashboard()

        print("✅ Performance monitoring successful")
        print(
            f"   Performance level: {dashboard.get('performance_summary', {}).get('overall_performance_level', 'N/A')}"
        )

        return True

    except Exception as e:
        print(f"❌ Performance monitoring failed: {e}")
        return False


async def test_alert_system():
    """Test alert system."""
    print("🚨 Testing alert system...")

    try:
        # Get alert summary
        summary = await redis_alert_manager.get_alert_summary()

        print("✅ Alert system functional")
        print(f"   Total alerts: {summary.get('total_alerts', 0)}")
        print(f"   Active alerts: {summary.get('active_alerts', 0)}")
        print(f"   Alert rules enabled: {summary.get('rules_enabled', 0)}")

        return True

    except Exception as e:
        print(f"❌ Alert system test failed: {e}")
        return False


async def test_dashboard_configuration():
    """Test dashboard configuration."""
    print("📈 Testing dashboard configuration...")

    try:
        # Generate Grafana dashboard
        dashboard = redis_dashboard_configuration.get_grafana_dashboard_json()

        # Generate Prometheus rules
        prometheus_rules = redis_dashboard_configuration.get_prometheus_rules_config()

        # Export configurations
        export = redis_dashboard_configuration.export_dashboard_configs()

        print("✅ Dashboard configuration successful")
        print(f"   Grafana panels: {len(dashboard['dashboard']['panels'])}")
        print(f"   Prometheus rules: {len(prometheus_rules['groups'][0]['rules'])}")

        return True

    except Exception as e:
        print(f"❌ Dashboard configuration failed: {e}")
        return False


async def test_monitoring_services():
    """Test monitoring service lifecycle."""
    print("🔄 Testing monitoring services...")

    try:
        # Start monitoring services
        await redis_metrics_collector.start_collection()
        await redis_health_checker.start_health_checks()
        await redis_performance_monitor.start_monitoring()
        await redis_alert_manager.start_alerting()

        print("✅ Monitoring services started")

        # Let them run for a few seconds
        await asyncio.sleep(3)

        # Stop monitoring services
        await redis_metrics_collector.stop_collection()
        await redis_health_checker.stop_health_checks()
        await redis_performance_monitor.stop_monitoring()
        await redis_alert_manager.stop_alerting()

        print("✅ Monitoring services stopped successfully")

        return True

    except Exception as e:
        print(f"❌ Monitoring services test failed: {e}")
        return False


async def generate_test_report():
    """Generate a test report."""
    print("\n📋 Generating Test Report")
    print("=" * 50)

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "redis_config": {
            "url": settings.REDIS_URL,
            "max_connections": settings.REDIS_MAX_CONNECTIONS,
            "timeout": settings.REDIS_CONNECTION_TIMEOUT,
        },
        "test_results": {},
        "summary": {},
    }

    # Run all tests
    tests = [
        ("Redis Connection", test_redis_connection),
        ("Metrics Collection", test_metrics_collection),
        ("Health Checks", test_health_checks),
        ("Performance Monitoring", test_performance_monitoring),
        ("Alert System", test_alert_system),
        ("Dashboard Configuration", test_dashboard_configuration),
        ("Monitoring Services", test_monitoring_services),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        start_time = time.time()

        try:
            result = await test_func()
            duration = time.time() - start_time

            report["test_results"][test_name] = {
                "passed": result,
                "duration_seconds": duration,
                "error": None,
            }

            if result:
                passed += 1

        except Exception as e:
            duration = time.time() - start_time
            report["test_results"][test_name] = {
                "passed": False,
                "duration_seconds": duration,
                "error": str(e),
            }

    # Generate summary
    report["summary"] = {
        "total_tests": total,
        "passed_tests": passed,
        "failed_tests": total - passed,
        "success_rate": passed / total if total > 0 else 0,
        "total_duration_seconds": sum(
            r["duration_seconds"] for r in report["test_results"].values()
        ),
    }

    # Print summary
    print(f"\n📊 Test Summary")
    print("=" * 50)
    print(f"Total tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success rate: {passed / total * 100:.1f}%")

    if passed == total:
        print("\n🎉 All tests passed! Redis monitoring system is working correctly.")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Please check the configuration.")

    # Save report to file
    report_file = Path("redis_monitoring_test_report.json")
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n📄 Detailed report saved to: {report_file.absolute()}")

    return report


async def main():
    """Main test function."""
    print("🚀 Redis Monitoring Integration Test")
    print("=" * 50)
    print(f"Testing Redis at: {settings.REDIS_URL}")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")

    try:
        report = await generate_test_report()
        return 0 if report["summary"]["success_rate"] == 1.0 else 1

    except KeyboardInterrupt:
        print("\n\n⏹️ Test interrupted by user")
        return 130
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    # Run the integration test
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
