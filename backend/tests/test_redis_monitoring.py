"""
Redis Monitoring System Tests

Comprehensive test suite for Redis monitoring components including
metrics collection, health checks, performance monitoring, and alerting.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timedelta

from app.monitoring.redis_metrics import RedisMetricsCollector, RedisCommandType
from app.monitoring.health_checker import (
    RedisHealthChecker,
    HealthStatus,
    HealthCheckType,
)
from app.monitoring.performance_monitor import RedisPerformanceMonitor, PerformanceLevel
from app.monitoring.alert_manager import (
    RedisAlertManager,
    AlertSeverity,
    AlertCategory,
    AlertStatus,
)
from app.monitoring.dashboard import RedisDashboardConfiguration


class TestRedisMetricsCollector:
    """Test Redis metrics collector functionality."""

    @pytest.fixture
    def metrics_collector(self):
        """Create metrics collector instance."""
        return RedisMetricsCollector()

    @pytest.fixture
    def mock_redis_client(self):
        """Create mock Redis client."""
        client = AsyncMock()
        client.ping.return_value = True
        client.info.return_value = {
            "memory": {
                "used_memory": 1073741824,  # 1GB
                "maxmemory": 2147483648,  # 2GB
                "used_memory_rss": 1342177280,  # 1.25GB
            },
            "stats": {
                "keyspace_hits": 8000,
                "keyspace_misses": 2000,
                "total_commands_processed": 10000,
                "instantaneous_ops_per_sec": 50,
                "evicted_keys": 10,
                "expired_keys": 5,
            },
        }
        return client

    @pytest.mark.asyncio
    async def test_command_metrics_tracking(self, metrics_collector):
        """Test command performance tracking."""
        command = "GET"
        command_type = RedisCommandType.READ
        duration_ms = 25.5
        project_id = uuid4()

        # Track command performance
        await metrics_collector.track_command_performance(
            command=command,
            command_type=command_type,
            duration_ms=duration_ms,
            success=True,
            project_id=project_id,
        )

        # Verify metrics were recorded
        assert len(metrics_collector._command_metrics) == 1
        metric = metrics_collector._command_metrics[0]
        assert metric.command == command
        assert metric.command_type == command_type
        assert metric.duration_ms == duration_ms
        assert metric.success is True
        assert metric.project_id == project_id

    @pytest.mark.asyncio
    async def test_memory_metrics_collection(
        self, metrics_collector, mock_redis_client
    ):
        """Test memory metrics collection."""
        with patch(
            "app.monitoring.redis_metrics.redis_connection_factory"
        ) as mock_factory:
            mock_factory.get_connection.return_value.__aenter__.return_value = (
                mock_redis_client
            )

            # Collect memory metrics
            await metrics_collector._collect_memory_metrics()

            # Verify metrics were collected
            assert len(metrics_collector._memory_metrics) == 1
            memory_metric = metrics_collector._memory_metrics[0]
            assert memory_metric.used_memory_bytes == 1073741824
            assert memory_metric.max_memory_bytes == 2147483648
            assert memory_metric.memory_percentage == 50.0  # 1GB / 2GB * 100
            assert memory_metric.hit_rate == 0.8  # 8000 / (8000 + 2000)

    @pytest.mark.asyncio
    async def test_metrics_summary_generation(self, metrics_collector):
        """Test metrics summary generation."""
        project_id = uuid4()

        # Add some test metrics
        await metrics_collector.track_command_performance(
            "GET", RedisCommandType.READ, 10.0, True, project_id
        )
        await metrics_collector.track_command_performance(
            "SET", RedisCommandType.WRITE, 15.0, True, project_id
        )

        # Generate summary
        summary = await metrics_collector.get_metrics_summary(project_id)

        # Verify summary structure
        assert "timestamp" in summary
        assert "project_id" in summary
        assert summary["project_id"] == str(project_id)
        assert "memory" in summary
        assert "connections" in summary
        assert "commands" in summary
        assert "performance" in summary
        assert "prometheus_metrics" in summary

    def test_opentelemetry_integration(self, metrics_collector):
        """Test OpenTelemetry metrics integration."""
        # Verify OpenTelemetry metrics are created
        assert hasattr(metrics_collector, "meter")
        assert hasattr(metrics_collector, "redis_memory_usage")
        assert hasattr(metrics_collector, "redis_commands_total")
        assert hasattr(metrics_collector, "redis_command_duration")

    def test_prometheus_metrics(self, metrics_collector):
        """Test Prometheus metrics configuration."""
        # Verify Prometheus metrics are created
        assert hasattr(metrics_collector, "registry")
        assert hasattr(metrics_collector, "prom_redis_memory_bytes")
        assert hasattr(metrics_collector, "prom_redis_commands_total")
        assert hasattr(metrics_collector, "prom_redis_command_duration_seconds")


class TestRedisHealthChecker:
    """Test Redis health checker functionality."""

    @pytest.fixture
    def health_checker(self):
        """Create health checker instance."""
        return RedisHealthChecker()

    @pytest.fixture
    def mock_redis_client(self):
        """Create mock Redis client."""
        client = AsyncMock()
        client.ping.return_value = True
        client.set.return_value = True
        client.get.return_value = "test_value"
        client.delete.return_value = 1
        client.info.return_value = {
            "server": {
                "redis_version": "6.4.0",
                "redis_mode": "standalone",
                "uptime_in_seconds": 3600,
            },
            "memory": {
                "used_memory": 1073741824,
                "maxmemory": 2147483648,
            },
            "clients": {
                "connected_clients": 5,
            },
            "stats": {
                "keyspace_hits": 8000,
                "keyspace_misses": 2000,
            },
            "persistence": {
                "loading": 0,
                "rdb_bgsave_in_progress": 0,
                "aof_rewrite_in_progress": 0,
            },
        }
        return client

    @pytest.mark.asyncio
    async def test_basic_connectivity_check(self, health_checker, mock_redis_client):
        """Test basic connectivity health check."""
        with patch(
            "app.monitoring.health_checker.redis_connection_factory"
        ) as mock_factory:
            mock_factory.get_connection.return_value.__aenter__.return_value = (
                mock_redis_client
            )

            # Perform connectivity check
            result = await health_checker._check_basic_connectivity()

            # Verify check result
            assert result.check_type == HealthCheckType.BASIC_CONNECTIVITY
            assert result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
            assert result.duration_ms >= 0
            assert "response_time" in result.message.lower()

    @pytest.mark.asyncio
    async def test_memory_usage_check(self, health_checker, mock_redis_client):
        """Test memory usage health check."""
        with patch(
            "app.monitoring.health_checker.redis_connection_factory"
        ) as mock_factory:
            mock_factory.get_connection.return_value.__aenter__.return_value = (
                mock_redis_client
            )

            # Perform memory check
            result = await health_checker._check_memory_usage()

            # Verify check result
            assert result.check_type == HealthCheckType.MEMORY_USAGE
            assert result.status == HealthStatus.HEALTHY  # 50% usage should be healthy
            assert "50.1%" in result.message

            # Test high memory usage
            mock_redis_client.info.return_value["memory"]["used_memory"] = (
                1932735283  # ~90%
            )
            result = await health_checker._check_memory_usage()
            assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_full_health_check(self, health_checker, mock_redis_client):
        """Test comprehensive health check."""
        with patch(
            "app.monitoring.health_checker.redis_connection_factory"
        ) as mock_factory:
            mock_factory.get_connection.return_value.__aenter__.return_value = (
                mock_redis_client
            )
            mock_factory.get_metrics.return_value = {
                "pools": {
                    "default": {
                        "max_connections": 10,
                        "created_connections": 5,
                    }
                }
            }

            # Perform full health check
            health_status = await health_checker.perform_full_health_check()

            # Verify health status
            assert health_status.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
            assert len(health_status.checks) >= 5  # At least 5 types of checks
            assert health_status.version == "6.4.0"
            assert health_status.mode == "standalone"
            assert isinstance(health_status.summary, dict)
            assert isinstance(health_status.alerts, list)

    @pytest.mark.asyncio
    async def test_specific_component_check(self, health_checker, mock_redis_client):
        """Test specific component health check."""
        with patch(
            "app.monitoring.health_checker.redis_connection_factory"
        ) as mock_factory:
            mock_factory.get_connection.return_value.__aenter__.return_value = (
                mock_redis_client
            )

            # Check specific component
            result = await health_checker.check_specific_component(
                HealthCheckType.MEMORY_USAGE
            )

            # Verify result
            assert result.check_type == HealthCheckType.MEMORY_USAGE
            assert result.status in [
                HealthStatus.HEALTHY,
                HealthStatus.DEGRADED,
                HealthStatus.UNHEALTHY,
            ]


class TestRedisPerformanceMonitor:
    """Test Redis performance monitor functionality."""

    @pytest.fixture
    def performance_monitor(self):
        """Create performance monitor instance."""
        return RedisPerformanceMonitor()

    @pytest.mark.asyncio
    async def test_command_performance_tracking(self, performance_monitor):
        """Test command performance tracking."""
        command = "GET"
        command_type = RedisCommandType.READ
        duration_ms = 25.5
        project_id = uuid4()

        # Track performance
        await performance_monitor.track_command_performance(
            command=command,
            command_type=command_type,
            duration_ms=duration_ms,
            success=True,
            project_id=project_id,
        )

        # Verify tracking
        command_key = f"{command_type.value}:{command}"
        assert command_key in performance_monitor._command_history
        assert len(performance_monitor._command_history[command_key]) == 1

        execution = performance_monitor._command_history[command_key][0]
        assert execution["duration_ms"] == duration_ms
        assert execution["success"] is True
        assert execution["project_id"] == project_id

    @pytest.mark.asyncio
    async def test_performance_analysis(self, performance_monitor):
        """Test performance analysis."""
        # Add some test data
        for i in range(10):
            await performance_monitor.track_command_performance(
                "GET", RedisCommandType.READ, 20 + i, True
            )

        # Analyze performance
        await performance_monitor._analyze_command_performance()

        # Verify analysis was performed (would need more detailed assertions based on implementation)
        assert len(performance_monitor._command_history) > 0

    @pytest.mark.asyncio
    async def test_performance_dashboard(self, performance_monitor):
        """Test performance dashboard generation."""
        # Add some test data
        await performance_monitor.track_command_performance(
            "GET", RedisCommandType.READ, 25.0, True
        )

        # Generate dashboard
        dashboard = await performance_monitor.get_performance_dashboard()

        # Verify dashboard structure
        assert "timestamp" in dashboard
        assert "performance_summary" in dashboard
        assert "command_performance" in dashboard
        assert "connection_performance" in dashboard
        assert "memory_performance" in dashboard
        assert "performance_insights" in dashboard
        assert "recommendations" in dashboard

    def test_performance_level_calculation(self, performance_monitor):
        """Test performance level calculation."""
        # Test different performance levels
        assert (
            performance_monitor._get_performance_level(10, [25, 50, 100])
            == PerformanceLevel.EXCELLENT
        )
        assert (
            performance_monitor._get_performance_level(30, [25, 50, 100])
            == PerformanceLevel.GOOD
        )
        assert (
            performance_monitor._get_performance_level(60, [25, 50, 100])
            == PerformanceLevel.FAIR
        )
        assert (
            performance_monitor._get_performance_level(80, [25, 50, 100])
            == PerformanceLevel.POOR
        )
        assert (
            performance_monitor._get_performance_level(120, [25, 50, 100])
            == PerformanceLevel.CRITICAL
        )


class TestRedisAlertManager:
    """Test Redis alert manager functionality."""

    @pytest.fixture
    def alert_manager(self):
        """Create alert manager instance."""
        return RedisAlertManager()

    def test_default_alert_rules(self, alert_manager):
        """Test default alert rules are initialized."""
        assert len(alert_manager._alert_rules) > 0

        # Check for specific alert rules
        assert "redis_memory_usage_warning" in alert_manager._alert_rules
        assert "redis_memory_usage_critical" in alert_manager._alert_rules
        assert "redis_hit_rate_low" in alert_manager._alert_rules

        memory_rule = alert_manager._alert_rules["redis_memory_usage_warning"]
        assert memory_rule.category == AlertCategory.MEMORY
        assert memory_rule.severity == AlertSeverity.WARNING
        assert memory_rule.threshold == 80.0
        assert memory_rule.operator == ">="

    @pytest.mark.asyncio
    async def test_alert_rule_evaluation(self, alert_manager):
        """Test alert rule evaluation."""
        rule = alert_manager._alert_rules["redis_memory_usage_warning"]

        # Test data that should trigger alert
        data = {
            "memory": {
                "percentage": 85.0  # Above 80% threshold
            }
        }

        # Evaluate rule
        await alert_manager._evaluate_rule(rule, data)

        # Verify alert was triggered
        active_alerts = await alert_manager.get_alerts(status=AlertStatus.ACTIVE)
        memory_alerts = [a for a in active_alerts if a.rule_id == rule.id]
        assert len(memory_alerts) > 0

        alert = memory_alerts[0]
        assert alert.category == AlertCategory.MEMORY
        assert alert.severity == AlertSeverity.WARNING
        assert alert.current_value == 85.0
        assert alert.threshold == 80.0

    @pytest.mark.asyncio
    async def test_alert_acknowledgement(self, alert_manager):
        """Test alert acknowledgement."""
        # Create a test alert
        rule = alert_manager._alert_rules["redis_memory_usage_warning"]
        data = {"memory": {"percentage": 85.0}}
        await alert_manager._evaluate_rule(rule, data)

        # Get active alert
        active_alerts = await alert_manager.get_alerts(status=AlertStatus.ACTIVE)
        assert len(active_alerts) > 0
        alert = active_alerts[0]

        # Acknowledge alert
        success = await alert_manager.acknowledge_alert(alert.id, "test_user")
        assert success is True

        # Verify alert is acknowledged
        acknowledged_alerts = await alert_manager.get_alerts(
            status=AlertStatus.ACKNOWLEDGED
        )
        acknowledged = [a for a in acknowledged_alerts if a.id == alert.id]
        assert len(acknowledged) == 1
        assert acknowledged[0].acknowledged_by == "test_user"

    @pytest.mark.asyncio
    async def test_alert_resolution(self, alert_manager):
        """Test alert resolution."""
        # Create a test alert
        rule = alert_manager._alert_rules["redis_memory_usage_warning"]
        data = {"memory": {"percentage": 85.0}}
        await alert_manager._evaluate_rule(rule, data)

        # Get active alert
        active_alerts = await alert_manager.get_alerts(status=AlertStatus.ACTIVE)
        assert len(active_alerts) > 0
        alert = active_alerts[0]

        # Resolve alert
        success = await alert_manager.resolve_alert(alert.id)
        assert success is True

        # Verify alert is resolved
        resolved_alerts = await alert_manager.get_alerts(status=AlertStatus.RESOLVED)
        resolved = [a for a in resolved_alerts if a.id == alert.id]
        assert len(resolved) == 1
        assert resolved[0].resolved_at is not None

    def test_alert_summary(self, alert_manager):
        """Test alert summary generation."""
        # Add some test alerts
        # (This would require creating alerts directly for testing)

        # Generate summary
        summary = asyncio.run(alert_manager.get_alert_summary())

        # Verify summary structure
        assert "total_alerts" in summary
        assert "active_alerts" in summary
        assert "acknowledged_alerts" in summary
        assert "resolved_alerts" in summary
        assert "severity_breakdown" in summary
        assert "category_breakdown" in summary
        assert "rules_enabled" in summary
        assert "rules_disabled" in summary


class TestRedisDashboardConfiguration:
    """Test Redis dashboard configuration functionality."""

    @pytest.fixture
    def dashboard_config(self):
        """Create dashboard configuration instance."""
        return RedisDashboardConfiguration()

    def test_grafana_dashboard_generation(self, dashboard_config):
        """Test Grafana dashboard configuration generation."""
        dashboard = dashboard_config.get_grafana_dashboard_json()

        # Verify dashboard structure
        assert "dashboard" in dashboard
        assert dashboard["dashboard"]["title"] == "JEEX Redis Monitoring"
        assert "panels" in dashboard["dashboard"]
        assert "templating" in dashboard["dashboard"]
        assert len(dashboard["dashboard"]["panels"]) > 0

        # Verify panels
        panels = dashboard["dashboard"]["panels"]
        panel_titles = [panel["title"] for panel in panels]
        assert "Redis Status Overview" in panel_titles
        assert "Key Metrics" in panel_titles
        assert "Active Alerts" in panel_titles
        assert "Memory Usage" in panel_titles

    def test_prometheus_rules_generation(self, dashboard_config):
        """Test Prometheus alerting rules configuration."""
        rules = dashboard_config.get_prometheus_rules_config()

        # Verify rules structure
        assert "groups" in rules
        assert len(rules["groups"]) > 0

        group = rules["groups"][0]
        assert "name" in group
        assert "rules" in group
        assert len(group["rules"]) > 0

        # Verify specific rules
        rule_names = [rule["alert"] for rule in group["rules"]]
        assert "RedisHighMemoryUsage" in rule_names
        assert "RedisLowHitRate" in rule_names
        assert "RedisHighResponseTime" in rule_names

    def test_dashboard_export(self, dashboard_config):
        """Test dashboard configuration export."""
        export = dashboard_config.export_dashboard_configs()

        # Verify export structure
        assert "grafana_dashboard" in export
        assert "prometheus_rules" in export
        assert "grafana_datasources" in export
        assert "export_timestamp" in export
        assert "version" in export

        # Verify all configurations are present
        assert (
            export["grafana_dashboard"]["dashboard"]["title"] == "JEEX Redis Monitoring"
        )
        assert len(export["prometheus_rules"]["groups"]) > 0
        assert len(export["grafana_datasources"]["datasources"]) > 0

    def test_project_specific_dashboard(self, dashboard_config):
        """Test project-specific dashboard generation."""
        project_id = str(uuid4())
        dashboard = dashboard_config.get_grafana_dashboard_json(project_id)

        # Verify project-specific configuration
        assert f"project:{project_id}" in dashboard["dashboard"]["tags"]

        # Verify template variable for project
        variables = dashboard["dashboard"]["templating"]["list"]
        project_var = next(
            (v for v in variables if v.get("name") == "project_id"), None
        )
        assert project_var is not None
        assert project_var["query"] == project_id


class TestIntegration:
    """Integration tests for Redis monitoring system."""

    @pytest.mark.asyncio
    async def test_end_to_end_monitoring_flow(self):
        """Test end-to-end monitoring flow."""
        # This would test the complete flow from metrics collection
        # through health checking to alert generation

        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {
            "memory": {"used_memory": 1073741824, "maxmemory": 2147483648},
            "stats": {"keyspace_hits": 8000, "keyspace_misses": 2000},
            "clients": {"connected_clients": 5},
            "server": {"redis_version": "6.4.0", "redis_mode": "standalone"},
        }

        with patch(
            "app.monitoring.redis_metrics.redis_connection_factory"
        ) as mock_factory:
            mock_factory.get_connection.return_value.__aenter__.return_value = (
                mock_redis
            )

            # Initialize components
            metrics_collector = RedisMetricsCollector()
            health_checker = RedisHealthChecker()
            alert_manager = RedisAlertManager()

            # Collect metrics
            await metrics_collector._collect_memory_metrics()

            # Perform health check
            health_status = await health_checker.perform_full_health_check()

            # Verify health status is healthy
            assert health_status.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]

            # Generate metrics summary
            summary = await metrics_collector.get_metrics_summary()
            assert "memory" in summary
            assert "connections" in summary

    @pytest.mark.asyncio
    async def test_alert_triggering_scenario(self):
        """Test alert triggering scenario."""
        # Mock Redis with high memory usage
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {
            "memory": {"used_memory": 1932735283, "maxmemory": 2147483648},  # ~90%
            "stats": {"keyspace_hits": 4000, "keyspace_misses": 6000},  # 40% hit rate
            "clients": {"connected_clients": 12},
            "server": {"redis_version": "6.4.0", "redis_mode": "standalone"},
        }

        with patch(
            "app.monitoring.redis_metrics.redis_connection_factory"
        ) as mock_factory:
            mock_factory.get_connection.return_value.__aenter__.return_value = (
                mock_redis
            )
            mock_factory.get_metrics.return_value = {
                "pools": {"default": {"max_connections": 10, "created_connections": 10}}
            }

            # Initialize alert manager
            alert_manager = RedisAlertManager()

            # Simulate metrics that should trigger alerts
            metrics_summary = {
                "memory": {"percentage": 90.0, "hit_rate": 0.4},
                "connections": {"connection_utilization": 0.8},
                "performance": {"error_rate_5m": 0.1},
            }

            # Create data structure for evaluation
            evaluation_data = {
                "memory": metrics_summary["memory"],
                "connections": metrics_summary["connections"],
                "performance": metrics_summary["performance"],
            }

            # Evaluate alert rules
            for rule in alert_manager._alert_rules.values():
                if not rule.enabled:
                    continue
                await alert_manager._evaluate_rule(rule, evaluation_data)

            # Check that alerts were triggered
            active_alerts = await alert_manager.get_alerts(status=AlertStatus.ACTIVE)
            assert len(active_alerts) > 0

            # Verify specific alerts
            memory_alerts = [a for a in active_alerts if "memory" in a.rule_id]
            assert len(memory_alerts) > 0

            hit_rate_alerts = [a for a in active_alerts if "hit_rate" in a.rule_id]
            assert len(hit_rate_alerts) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
