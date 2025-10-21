"""
Redis Dashboard Configuration

Grafana dashboard configuration templates for Redis monitoring.
Provides comprehensive visualization of Redis metrics, health, and performance.
Implements Domain-Driven patterns with project isolation support.
"""

import json
from typing import Dict, Any, List
from uuid import UUID
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class RedisDashboardConfiguration:
    """
    Redis monitoring dashboard configuration for Grafana.

    Features:
    - Pre-configured dashboard templates
    - Memory usage visualizations
    - Performance metrics panels
    - Connection pool monitoring
    - Health status indicators
    - Alert management dashboard
    - Project-specific filtering
    - Real-time metric displays
    """

    def __init__(self):
        self.dashboard_title = "JEEX Redis Monitoring"
        self.dashboard_uid = "jeex-redis-monitoring"
        self.dashboard_tags = ["jeex", "redis", "monitoring", "performance"]

    def get_grafana_dashboard_json(self, project_id: str) -> Dict[str, Any]:
        """
        Generate complete Grafana dashboard configuration.

        Args:
            project_id: Required project ID for project-specific dashboard

        Returns:
            Grafana dashboard JSON configuration
        """
        # Validate project_id format
        try:
            UUID(project_id)
        except ValueError:
            raise ValueError(
                f"Invalid project_id format: {project_id}. Must be a valid UUID string."
            )

        dashboard = {
            "dashboard": {
                "id": None,
                "title": self.dashboard_title,
                "tags": self.dashboard_tags
                + ([f"project:{project_id}"] if project_id else []),
                "timezone": "browser",
                "panels": [],
                "time": {"from": "now-1h", "to": "now"},
                "refresh": "30s",
                "schemaVersion": 36,
                "version": 1,
                "templating": {"list": self._get_template_variables(project_id)},
                "annotations": {
                    "list": [
                        {
                            "name": "Redis Alerts",
                            "datasource": "Prometheus",
                            "enable": True,
                            "iconColor": "red",
                            "type": "tags",
                        }
                    ]
                },
            },
            "overwrite": True,
        }

        # Add panels to dashboard
        dashboard["dashboard"]["panels"] = self._get_all_dashboard_panels(project_id)

        return dashboard

    def _get_template_variables(self, project_id: str) -> List[Dict[str, Any]]:
        """Get template variables for dashboard."""
        variables = [
            {
                "name": "instance",
                "label": "Redis Instance",
                "type": "query",
                "datasource": {"type": "prometheus", "uid": "prometheus"},
                "query": {
                    "query": 'label_values(jeex_redis_memory_bytes{project_id="$project_id"}, instance)',
                    "refId": "StandardVariableQuery",
                },
                "refresh": 1,
                "sort": 1,
                "allValue": ".*",
                "includeAll": True,
                "multi": True,
            },
            {
                "name": "project_id",
                "label": "Project ID",
                "type": "constant",
                "query": project_id,
                "current": {
                    "selected": False,
                    "text": project_id,
                    "value": project_id,
                },
                "hide": True,
            },
        ]

        return variables

    def _get_all_dashboard_panels(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all dashboard panels configuration."""
        panels = []

        # Row 1: Overview and Status
        panels.extend(
            [
                self._get_status_overview_panel(project_id),
                self._get_key_metrics_panel(project_id),
                self._get_alert_summary_panel(project_id),
            ]
        )

        # Row 2: Memory Usage
        panels.extend(
            [
                self._get_memory_usage_panel(project_id),
                self._get_memory_details_panel(project_id),
                self._get_cache_performance_panel(project_id),
            ]
        )

        # Row 3: Performance Metrics
        panels.extend(
            [
                self._get_command_performance_panel(project_id),
                self._get_response_time_panel(project_id),
                self._get_throughput_panel(project_id),
            ]
        )

        # Row 4: Connection Monitoring
        panels.extend(
            [
                self._get_connection_pool_panel(project_id),
                self._get_connection_details_panel(project_id),
                self._get_error_rate_panel(project_id),
            ]
        )

        # Row 5: Health Checks
        panels.extend(
            [
                self._get_health_status_panel(project_id),
                self._get_persistence_panel(project_id),
            ]
        )

        # Row 6: Alert Management
        panels.extend(
            [
                self._get_active_alerts_panel(project_id),
                self._get_alert_history_panel(project_id),
            ]
        )

        # Assign panel positions
        for i, panel in enumerate(panels):
            row = i // 3
            col = i % 3
            panel["gridPos"] = {"h": 8, "w": 8, "x": col * 8, "y": row * 8}

        return panels

    def _get_status_overview_panel(self, project_id: str) -> Dict[str, Any]:
        """Get Redis status overview panel."""
        return {
            "id": None,
            "title": "Redis Status Overview",
            "type": "stat",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_memory_bytes{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Memory Usage",
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_connections_active{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Active Connections",
                    "refId": "B",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'rate(jeex_redis_commands_total{project_id="$project_id",instance=~"$instance"}[5m])',
                    "legendFormat": "Commands/sec",
                    "refId": "C",
                },
            ],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "custom": {"displayMode": "list", "orientation": "horizontal"},
                    "mappings": [],
                    "thresholds": {
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "red", "value": 80},
                        ]
                    },
                    "unit": "short",
                },
                "overrides": [],
            },
            "options": {
                "displayMode": "list",
                "orientation": "horizontal",
                "reduceOptions": {
                    "values": False,
                    "calcs": ["lastNotNull"],
                    "fields": "",
                },
            },
        }

    def _get_key_metrics_panel(self, project_id: str) -> Dict[str, Any]:
        """Get key metrics panel."""
        return {
            "id": None,
            "title": "Key Metrics",
            "type": "stat",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_hit_rate{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Hit Rate",
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_memory_percentage{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Memory %",
                    "refId": "B",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_connection_utilization{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Conn Util %",
                    "refId": "C",
                },
            ],
            "fieldConfig": {
                "defaults": {
                    "mappings": [],
                    "thresholds": {
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "yellow", "value": 70},
                            {"color": "red", "value": 90},
                        ]
                    },
                    "unit": "percent",
                    "max": 100,
                    "min": 0,
                },
                "overrides": [],
            },
            "options": {
                "displayMode": "list",
                "orientation": "horizontal",
                "reduceOptions": {"values": False, "calcs": ["lastNotNull"]},
            },
        }

    def _get_alert_summary_panel(self, project_id: str) -> Dict[str, Any]:
        """Get alert summary panel."""
        return {
            "id": None,
            "title": "Active Alerts",
            "type": "stat",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'sum(increase(jeex_redis_memory_alerts_total{project_id="$project_id",instance=~"$instance"}[1h]))',
                    "legendFormat": "Memory Alerts",
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'sum(increase(jeex_redis_errors_total{project_id="$project_id",instance=~"$instance"}[1h]))',
                    "legendFormat": "Errors",
                    "refId": "B",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'sum(increase(jeex_redis_slow_commands_total{project_id="$project_id",instance=~"$instance"}[1h]))',
                    "legendFormat": "Slow Commands",
                    "refId": "C",
                },
            ],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "thresholds"},
                    "thresholds": {
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "yellow", "value": 1},
                            {"color": "red", "value": 5},
                        ]
                    },
                    "unit": "short",
                },
                "overrides": [],
            },
            "options": {
                "displayMode": "list",
                "orientation": "horizontal",
                "reduceOptions": {"values": False, "calcs": ["lastNotNull"]},
            },
        }

    def _get_memory_usage_panel(self, project_id: str) -> Dict[str, Any]:
        """Get memory usage panel."""
        return {
            "id": None,
            "title": "Memory Usage",
            "type": "graph",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_memory_bytes{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Used Memory",
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_memory_bytes{project_id="$project_id",instance=~"$instance"} * 0.8',
                    "legendFormat": "80% Threshold",
                    "refId": "B",
                },
            ],
            "yAxes": [{"label": "Memory (bytes)", "min": 0}],
            "xAxes": [{"show": True}],
            "lines": True,
            "fill": 1,
            "linewidth": 2,
            "opacity": 0.8,
        }

    def _get_memory_details_panel(self, project_id: str) -> Dict[str, Any]:
        """Get memory details panel."""
        return {
            "id": None,
            "title": "Memory Details",
            "type": "graph",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_memory_percentage{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Memory %",
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_memory_fragmentation_ratio{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Fragmentation Ratio",
                    "refId": "B",
                },
            ],
            "yAxes": [{"label": "Percentage / Ratio", "min": 0}],
        }

    def _get_cache_performance_panel(self, project_id: str) -> Dict[str, Any]:
        """Get cache performance panel."""
        return {
            "id": None,
            "title": "Cache Performance",
            "type": "graph",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_hit_rate{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Hit Rate",
                    "refId": "A",
                }
            ],
            "yAxes": [
                {"label": "Hit Rate", "min": 0, "max": 1, "format": "percentunit"}
            ],
            "alert": {
                "alertRuleTags": {},
                "conditions": [
                    {
                        "evaluator": {"params": [0.8], "type": "lt"},
                        "operator": {"type": "and"},
                        "query": {"params": ["A", "5m", "now"]},
                        "reducer": {"params": [], "type": "last"},
                        "type": "query",
                    }
                ],
                "executionErrorState": "alerting",
                "for": "5m",
                "frequency": "1m",
                "handler": 1,
                "name": "Redis Cache Hit Rate Alert",
                "noDataState": "no_data",
                "notifications": [],
            },
        }

    def _get_command_performance_panel(self, project_id: str) -> Dict[str, Any]:
        """Get command performance panel."""
        return {
            "id": None,
            "title": "Command Performance",
            "type": "graph",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'rate(jeex_redis_commands_total{project_id="$project_id",instance=~"$instance"}[5m])',
                    "legendFormat": "Commands/sec",
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'rate(jeex_redis_slow_commands_total{project_id="$project_id",instance=~"$instance"}[5m])',
                    "legendFormat": "Slow Commands/sec",
                    "refId": "B",
                },
            ],
            "yAxes": [{"label": "Rate (per second)", "min": 0}],
        }

    def _get_response_time_panel(self, project_id: str) -> Dict[str, Any]:
        """Get response time panel."""
        return {
            "id": None,
            "title": "Response Time Distribution",
            "type": "heatmap",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'rate(jeex_redis_command_duration_seconds_bucket{project_id="$project_id",instance=~"$instance"}[5m])',
                    "legendFormat": "{{le}}",
                    "refId": "A",
                }
            ],
            "tooltip": {"show": True, "showHistogram": True},
            "color": {"mode": "opacity"},
            "dataFormat": "tsbuckets",
        }

    def _get_throughput_panel(self, project_id: str) -> Dict[str, Any]:
        """Get throughput panel."""
        return {
            "id": None,
            "title": "Throughput by Command Type",
            "type": "graph",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'sum by (command_type) (rate(jeex_redis_commands_total{project_id="$project_id",instance=~"$instance"}[5m]))',
                    "legendFormat": "{{command_type}}",
                    "refId": "A",
                }
            ],
            "yAxes": [{"label": "Operations/sec", "min": 0}],
        }

    def _get_connection_pool_panel(self, project_id: str) -> Dict[str, Any]:
        """Get connection pool panel."""
        return {
            "id": None,
            "title": "Connection Pool",
            "type": "graph",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_connections_active{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Active Connections",
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_connections_idle{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Idle Connections",
                    "refId": "B",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'jeex_redis_connection_utilization{project_id="$project_id",instance=~"$instance"} * 100',
                    "legendFormat": "Utilization %",
                    "refId": "C",
                },
            ],
            "yAxes": [{"label": "Connections / Percentage", "min": 0}],
        }

    def _get_connection_details_panel(self, project_id: str) -> Dict[str, Any]:
        """Get connection details panel."""
        return {
            "id": None,
            "title": "Connection Errors",
            "type": "graph",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'rate(jeex_redis_errors_total{project_id="$project_id",instance=~"$instance"}[5m])',
                    "legendFormat": "Errors/sec",
                    "refId": "A",
                }
            ],
            "yAxes": [{"label": "Error Rate", "min": 0}],
        }

    def _get_error_rate_panel(self, project_id: str) -> Dict[str, Any]:
        """Get error rate panel."""
        return {
            "id": None,
            "title": "Error Rate by Type",
            "type": "graph",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'sum by (error_type) (rate(jeex_redis_errors_total{project_id="$project_id",instance=~"$instance"}[5m]))',
                    "legendFormat": "{{error_type}}",
                    "refId": "A",
                }
            ],
            "yAxes": [{"label": "Errors/sec", "min": 0}],
        }

    def _get_health_status_panel(self, project_id: str) -> Dict[str, Any]:
        """Get health status panel."""
        return {
            "id": None,
            "title": "Health Status",
            "type": "table",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'up{job="redis",project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "{{instance}}",
                    "refId": "A",
                    "format": "table",
                }
            ],
            "transformations": [
                {
                    "id": "organize",
                    "options": {
                        "excludeByName": {"Time": True},
                        "indexByName": {},
                        "renameByName": {
                            "Value": "Status",
                            "instance": "Redis Instance",
                        },
                    },
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "thresholds"},
                    "thresholds": {
                        "steps": [
                            {"color": "red", "value": None},
                            {"color": "green", "value": 1},
                        ]
                    },
                    "custom": {"displayMode": "list", "orientation": "horizontal"},
                }
            },
        }

    def _get_persistence_panel(self, project_id: str) -> Dict[str, Any]:
        """Get persistence panel."""
        return {
            "id": None,
            "title": "Persistence Status",
            "type": "stat",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'redis_rdb_last_save_timestamp_seconds{project_id="$project_id",instance=~"$instance"}',
                    "legendFormat": "Last Save",
                    "refId": "A",
                }
            ],
            "fieldConfig": {"defaults": {"unit": "dateTimeAsIso"}},
        }

    def _get_active_alerts_panel(self, project_id: str) -> Dict[str, Any]:
        """Get active alerts panel."""
        return {
            "id": None,
            "title": "Active Alerts",
            "type": "table",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'ALERTS{alertname=~"Redis.*",project_id="$project_id"}',
                    "legendFormat": "{{alertname}}",
                    "refId": "A",
                    "format": "table",
                }
            ],
            "transformations": [
                {
                    "id": "organize",
                    "options": {
                        "excludeByName": {"Time": True},
                        "renameByName": {
                            "alertname": "Alert Name",
                            "instance": "Instance",
                            "severity": "Severity",
                            "summary": "Summary",
                        },
                    },
                }
            ],
        }

    def _get_alert_history_panel(self, project_id: str) -> Dict[str, Any]:
        """Get alert history panel."""
        return {
            "id": None,
            "title": "Alert History (24h)",
            "type": "graph",
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'increase(jeex_redis_memory_alerts_total{project_id="$project_id",instance=~"$instance"}[24h])',
                    "legendFormat": "Memory Alerts",
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": 'increase(jeex_redis_errors_total{project_id="$project_id",instance=~"$instance"}[24h])',
                    "legendFormat": "Errors",
                    "refId": "B",
                },
            ],
            "yAxes": [{"label": "Alert Count", "min": 0}],
        }

    def get_prometheus_rules_config(self) -> Dict[str, Any]:
        """Get Prometheus alerting rules configuration."""
        return {
            "groups": [
                {
                    "name": "jeex-redis-alerts",
                    "rules": [
                        {
                            "alert": "RedisHighMemoryUsage",
                            "expr": 'jeex_redis_memory_percentage{project_id!=""} > 80',
                            "for": "5m",
                            "labels": {"severity": "warning", "service": "redis"},
                            "annotations": {
                                "summary": "Redis memory usage is above 80%",
                                "description": "Redis memory usage for project {{ $labels.project_id }} is {{ $value }}% which is above the 80% threshold.",
                            },
                        },
                        {
                            "alert": "RedisCriticalMemoryUsage",
                            "expr": 'jeex_redis_memory_percentage{project_id!=""} > 90',
                            "for": "2m",
                            "labels": {"severity": "critical", "service": "redis"},
                            "annotations": {
                                "summary": "Redis memory usage is critically high",
                                "description": "Redis memory usage for project {{ $labels.project_id }} is {{ $value }}% which is above the 90% critical threshold.",
                            },
                        },
                        {
                            "alert": "RedisLowHitRate",
                            "expr": 'jeex_redis_hit_rate{project_id!=""} < 0.8',
                            "for": "10m",
                            "labels": {"severity": "warning", "service": "redis"},
                            "annotations": {
                                "summary": "Redis cache hit rate is low",
                                "description": "Redis cache hit rate for project {{ $labels.project_id }} is {{ $value | humanizePercentage }} which is below 80%.",
                            },
                        },
                        {
                            "alert": "RedisHighResponseTime",
                            "expr": 'histogram_quantile(0.95, rate(jeex_redis_command_duration_seconds_bucket{project_id!=""}[5m])) > 0.1',
                            "for": "5m",
                            "labels": {"severity": "warning", "service": "redis"},
                            "annotations": {
                                "summary": "Redis response time is high",
                                "description": "Redis 95th percentile response time for project {{ $labels.project_id }} is {{ $value }}s which is above 100ms.",
                            },
                        },
                        {
                            "alert": "RedisConnectionPoolHigh",
                            "expr": 'jeex_redis_connection_utilization{project_id!=""} > 0.8',
                            "for": "5m",
                            "labels": {"severity": "warning", "service": "redis"},
                            "annotations": {
                                "summary": "Redis connection pool usage is high",
                                "description": "Redis connection pool usage for project {{ $labels.project_id }} is {{ $value | humanizePercentage }} which is above 80%.",
                            },
                        },
                        {
                            "alert": "RedisConnectionPoolCritical",
                            "expr": 'jeex_redis_connection_utilization{project_id!=""} > 0.95',
                            "for": "2m",
                            "labels": {"severity": "critical", "service": "redis"},
                            "annotations": {
                                "summary": "Redis connection pool usage is critical",
                                "description": "Redis connection pool usage for project {{ $labels.project_id }} is {{ $value | humanizePercentage }} which is above 95%.",
                            },
                        },
                        {
                            "alert": "RedisHighErrorRate",
                            "expr": 'rate(jeex_redis_errors_total{project_id!=""}[5m]) / rate(jeex_redis_commands_total{project_id!=""}[5m]) > 0.05',
                            "for": "5m",
                            "labels": {"severity": "warning", "service": "redis"},
                            "annotations": {
                                "summary": "Redis error rate is high",
                                "description": "Redis error rate for project {{ $labels.project_id }} is {{ $value | humanizePercentage }} which is above 5%.",
                            },
                        },
                        {
                            "alert": "RedisDown",
                            "expr": 'up{job="redis",project_id!=""} == 0',
                            "for": "1m",
                            "labels": {"severity": "critical", "service": "redis"},
                            "annotations": {
                                "summary": "Redis instance is down",
                                "description": "Redis instance {{ $labels.instance }} for project {{ $labels.project_id }} has been down for more than 1 minute.",
                            },
                        },
                    ],
                }
            ]
        }

    def get_grafana_datasource_config(self) -> Dict[str, Any]:
        """Get Grafana datasource configuration."""
        return {
            "datasources": [
                {
                    "name": "Prometheus",
                    "type": "prometheus",
                    "access": "proxy",
                    "url": "http://prometheus:9090",
                    "isDefault": True,
                    "jsonData": {"timeInterval": "30s"},
                }
            ]
        }

    def export_dashboard_configs(self, project_id: str) -> Dict[str, Any]:
        """Export all dashboard configurations."""
        return {
            "grafana_dashboard": self.get_grafana_dashboard_json(project_id),
            "prometheus_rules": self.get_prometheus_rules_config(),
            "grafana_datasources": self.get_grafana_datasource_config(),
            "export_timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
        }


# Global dashboard configuration instance
redis_dashboard_configuration = RedisDashboardConfiguration()
