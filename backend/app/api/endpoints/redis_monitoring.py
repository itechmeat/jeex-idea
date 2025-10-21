"""
Redis Monitoring API Endpoints

Comprehensive API endpoints for Redis monitoring, health checks,
metrics collection, and alert management.
Implements Domain-Driven patterns with project isolation.
"""

import asyncio
from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

import structlog
from ...monitoring.redis_metrics import redis_metrics_collector, RedisCommandType
from ...monitoring.health_checker import redis_health_checker, HealthCheckType
from ...monitoring.performance_monitor import redis_performance_monitor
from ...monitoring.alert_manager import (
    redis_alert_manager,
    AlertStatus,
    AlertSeverity,
    AlertCategory,
)
from ...monitoring.dashboard import redis_dashboard_configuration
from ...infrastructure.redis.connection_factory import redis_connection_factory

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/monitoring/redis", tags=["redis-monitoring"])


# Pydantic models for API requests/responses
class RedisMetricsSummary(BaseModel):
    """Redis metrics summary model."""

    timestamp: str
    project_id: Optional[str] = None
    memory: Dict[str, Any]
    connections: Dict[str, Any]
    commands: Dict[str, Any]
    performance: Dict[str, Any]
    prometheus_metrics: str


class RedisHealthStatus(BaseModel):
    """Redis health status model."""

    status: str
    timestamp: str
    uptime_seconds: float
    version: str
    mode: str
    checks: List[Dict[str, Any]]
    summary: Dict[str, Any]
    alerts: List[str]


class RedisPerformanceDashboard(BaseModel):
    """Redis performance dashboard model."""

    timestamp: str
    project_id: Optional[str] = None
    performance_summary: Dict[str, Any]
    command_performance: Dict[str, Any]
    connection_performance: Dict[str, Any]
    memory_performance: Dict[str, Any]
    performance_insights: List[Dict[str, Any]]
    recommendations: List[str]


class AlertActionRequest(BaseModel):
    """Alert action request model."""

    action: str = Field(
        ..., description="Action to perform: acknowledge, resolve, suppress"
    )
    acknowledged_by: Optional[str] = Field(
        None, description="User acknowledging the alert"
    )
    hours: Optional[int] = Field(
        None, description="Hours to suppress rule (for suppress action)"
    )
    reason: Optional[str] = Field(None, description="Reason for suppression")


class ProjectFilterRequest(BaseModel):
    """Project filter request model."""

    project_id: Optional[UUID] = Field(None, description="Project ID to filter by")


# Health check endpoints
@router.get("/health", response_model=RedisHealthStatus)
async def get_redis_health(
    project_id: Optional[UUID] = Query(
        None, description="Project ID for scoped health check"
    ),
):
    """
    Get comprehensive Redis health status.

    Performs all health checks including connectivity, memory usage,
    connection pool health, performance, and persistence checks.
    """
    try:
        health_status = await redis_health_checker.perform_full_health_check(project_id)

        return RedisHealthStatus(
            status=health_status.status.value,
            timestamp=health_status.timestamp.isoformat(),
            uptime_seconds=health_status.uptime_seconds,
            version=health_status.version,
            mode=health_status.mode,
            checks=[
                {
                    "check_type": check.check_type.value,
                    "status": check.status.value,
                    "message": check.message,
                    "duration_ms": check.duration_ms,
                    "details": check.details,
                    "project_id": str(check.project_id) if check.project_id else None,
                }
                for check in health_status.checks
            ],
            summary=health_status.summary,
            alerts=health_status.alerts,
        )

    except Exception as e:
        logger.error(
            "Failed to get Redis health status", error=str(e), project_id=project_id
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get Redis health status: {str(e)}"
        )


@router.get("/health/{check_type}")
async def get_specific_health_check(
    check_type: str = Path(..., description="Type of health check to perform"),
    project_id: Optional[UUID] = Query(
        None, description="Project ID for scoped health check"
    ),
):
    """
    Get specific Redis health check.

    Supported check types: basic_connectivity, memory_usage, connection_pool,
    performance, persistence.
    """
    try:
        # Validate check type
        try:
            health_check_type = HealthCheckType(check_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid check type: {check_type}. "
                f"Supported types: {[t.value for t in HealthCheckType]}",
            )

        check_result = await redis_health_checker.check_specific_component(
            health_check_type, project_id
        )

        return {
            "check_type": check_result.check_type.value,
            "status": check_result.status.value,
            "message": check_result.message,
            "timestamp": check_result.timestamp.isoformat(),
            "duration_ms": check_result.duration_ms,
            "details": check_result.details,
            "project_id": str(check_result.project_id)
            if check_result.project_id
            else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get specific Redis health check",
            check_type=check_type,
            error=str(e),
            project_id=project_id,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to perform health check: {str(e)}"
        )


# Metrics endpoints
@router.get("/metrics", response_model=RedisMetricsSummary)
async def get_redis_metrics(
    project_id: Optional[UUID] = Query(
        None, description="Project ID for scoped metrics"
    ),
):
    """
    Get comprehensive Redis metrics summary.

    Includes memory usage, connection pool statistics, command performance,
    and error rate metrics.
    """
    try:
        metrics_summary = await redis_metrics_collector.get_metrics_summary(project_id)

        return RedisMetricsSummary(**metrics_summary)

    except Exception as e:
        logger.error("Failed to get Redis metrics", error=str(e), project_id=project_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to get Redis metrics: {str(e)}"
        )


@router.get("/metrics/prometheus")
async def get_prometheus_metrics(
    project_id: Optional[UUID] = Query(
        None, description="Project ID for scoped metrics"
    ),
):
    """
    Get Redis metrics in Prometheus format.

    Returns metrics that can be scraped by Prometheus server.
    """
    try:
        metrics_summary = await redis_metrics_collector.get_metrics_summary(project_id)

        return PlainTextResponse(
            content=metrics_summary["prometheus_metrics"], media_type="text/plain"
        )

    except Exception as e:
        logger.error(
            "Failed to get Prometheus metrics", error=str(e), project_id=project_id
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get Prometheus metrics: {str(e)}"
        )


@router.get("/performance", response_model=RedisPerformanceDashboard)
async def get_performance_dashboard(
    project_id: Optional[UUID] = Query(
        None, description="Project ID for scoped performance data"
    ),
):
    """
    Get Redis performance dashboard data.

    Includes performance analysis, insights, and recommendations.
    """
    try:
        performance_data = await redis_performance_monitor.get_performance_dashboard(
            project_id
        )

        return RedisPerformanceDashboard(**performance_data)

    except Exception as e:
        logger.error(
            "Failed to get performance dashboard", error=str(e), project_id=project_id
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get performance dashboard: {str(e)}"
        )


# Alert management endpoints
@router.get("/alerts")
async def get_redis_alerts(
    status: Optional[str] = Query(None, description="Filter by alert status"),
    severity: Optional[str] = Query(None, description="Filter by alert severity"),
    category: Optional[str] = Query(None, description="Filter by alert category"),
    project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of alerts to return"
    ),
):
    """
    Get Redis alerts with optional filtering.

    Supports filtering by status, severity, category, and project ID.
    """
    try:
        # Parse filter parameters
        alert_status = None
        if status:
            try:
                alert_status = AlertStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. "
                    f"Supported statuses: {[s.value for s in AlertStatus]}",
                )

        alert_severity = None
        if severity:
            try:
                alert_severity = AlertSeverity(severity)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid severity: {severity}. "
                    f"Supported severities: {[s.value for s in AlertSeverity]}",
                )

        alert_category = None
        if category:
            try:
                alert_category = AlertCategory(category)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid category: {category}. "
                    f"Supported categories: {[c.value for c in AlertCategory]}",
                )

        alerts = await redis_alert_manager.get_alerts(
            status=alert_status,
            severity=alert_severity,
            category=alert_category,
            project_id=project_id,
            limit=limit,
        )

        return {
            "alerts": [
                {
                    "id": str(alert.id),
                    "rule_id": alert.rule_id,
                    "category": alert.category.value,
                    "severity": alert.severity.value,
                    "status": alert.status.value,
                    "title": alert.title,
                    "message": alert.message,
                    "current_value": alert.current_value,
                    "threshold": alert.threshold,
                    "project_id": str(alert.project_id) if alert.project_id else None,
                    "created_at": alert.created_at.isoformat(),
                    "updated_at": alert.updated_at.isoformat(),
                    "acknowledged_at": alert.acknowledged_at.isoformat()
                    if alert.acknowledged_at
                    else None,
                    "acknowledged_by": alert.acknowledged_by,
                    "resolved_at": alert.resolved_at.isoformat()
                    if alert.resolved_at
                    else None,
                    "tags": alert.tags,
                }
                for alert in alerts
            ],
            "total_count": len(alerts),
            "filters": {
                "status": status,
                "severity": severity,
                "category": category,
                "project_id": str(project_id) if project_id else None,
                "limit": limit,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get Redis alerts", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get Redis alerts: {str(e)}"
        )


@router.get("/alerts/summary")
async def get_alerts_summary():
    """
    Get Redis alerts summary statistics.

    Provides counts of active, acknowledged, and resolved alerts
    broken down by severity and category.
    """
    try:
        summary = await redis_alert_manager.get_alert_summary()

        return summary

    except Exception as e:
        logger.error("Failed to get alerts summary", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get alerts summary: {str(e)}"
        )


@router.post("/alerts/{alert_id}/action")
async def manage_alert(
    alert_id: UUID = Path(..., description="Alert ID"),
    action_request: AlertActionRequest = ...,
):
    """
    Manage Redis alerts (acknowledge, resolve, suppress).

    Actions:
    - acknowledge: Acknowledge an alert with user information
    - resolve: Manually resolve an alert
    - suppress: Suppress alerts from a rule for specified hours
    """
    try:
        if action_request.action == "acknowledge":
            if not action_request.acknowledged_by:
                raise HTTPException(
                    status_code=400,
                    detail="acknowledged_by is required for acknowledge action",
                )

            success = await redis_alert_manager.acknowledge_alert(
                alert_id, action_request.acknowledged_by
            )

            if not success:
                raise HTTPException(
                    status_code=404,
                    detail=f"Alert {alert_id} not found or not in active state",
                )

            return {
                "message": "Alert acknowledged successfully",
                "alert_id": str(alert_id),
            }

        elif action_request.action == "resolve":
            success = await redis_alert_manager.resolve_alert(alert_id)

            if not success:
                raise HTTPException(
                    status_code=404,
                    detail=f"Alert {alert_id} not found or already resolved",
                )

            return {"message": "Alert resolved successfully", "alert_id": str(alert_id)}

        elif action_request.action == "suppress":
            # This would require extending the alert manager to suppress by alert
            # For now, we'll raise an error indicating this functionality needs to be implemented
            raise HTTPException(
                status_code=501,
                detail="Suppress action for individual alerts not yet implemented. "
                "Use rule suppression endpoint instead.",
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action: {action_request.action}. "
                f"Supported actions: acknowledge, resolve",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to manage alert",
            alert_id=alert_id,
            action=action_request.action,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Failed to manage alert: {str(e)}")


# Dashboard configuration endpoints
@router.get("/dashboard/grafana")
async def get_grafana_dashboard(
    project_id: Optional[UUID] = Query(
        None, description="Project ID for project-specific dashboard"
    ),
):
    """
    Get Grafana dashboard configuration for Redis monitoring.

    Returns JSON configuration that can be imported into Grafana.
    """
    try:
        dashboard_config = redis_dashboard_configuration.get_grafana_dashboard_json(
            str(project_id) if project_id else None
        )

        return dashboard_config

    except Exception as e:
        logger.error(
            "Failed to get Grafana dashboard", error=str(e), project_id=project_id
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get Grafana dashboard: {str(e)}"
        )


@router.get("/dashboard/prometheus-rules")
async def get_prometheus_rules():
    """
    Get Prometheus alerting rules for Redis monitoring.

    Returns YAML configuration for Prometheus alerting rules.
    """
    try:
        rules_config = redis_dashboard_configuration.get_prometheus_rules_config()

        return JSONResponse(content=rules_config, media_type="application/x-yaml")

    except Exception as e:
        logger.error("Failed to get Prometheus rules", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get Prometheus rules: {str(e)}"
        )


@router.get("/dashboard/export")
async def export_dashboard_configurations(
    project_id: Optional[UUID] = Query(
        None, description="Project ID for project-specific configurations"
    ),
):
    """
    Export all dashboard configurations.

    Returns comprehensive configuration package including Grafana dashboard,
    Prometheus rules, and datasource configurations.
    """
    try:
        export_config = redis_dashboard_configuration.export_dashboard_configs()

        # Add project-specific information if provided
        if project_id:
            export_config["project_id"] = str(project_id)
            export_config["grafana_dashboard"] = (
                redis_dashboard_configuration.get_grafana_dashboard_json(
                    str(project_id)
                )
            )

        return export_config

    except Exception as e:
        logger.error(
            "Failed to export dashboard configurations",
            error=str(e),
            project_id=project_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export dashboard configurations: {str(e)}",
        )


# Connection factory monitoring endpoints
@router.get("/connections/status")
async def get_connection_factory_status():
    """
    Get Redis connection factory status and metrics.

    Provides information about connection pools, circuit breaker status,
    and connection health.
    """
    try:
        # Get connection factory metrics
        factory_metrics = redis_connection_factory.get_metrics()

        # Get health check
        health_status = await redis_connection_factory.health_check()

        return {
            "connection_factory": {
                "initialized": factory_metrics["initialized"],
                "pools_count": factory_metrics["pools_count"],
                "circuit_breaker": factory_metrics["circuit_breaker"],
                "pools": factory_metrics["pools"],
            },
            "health_status": health_status,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Failed to get connection factory status", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get connection factory status: {str(e)}"
        )


# Monitoring control endpoints
@router.post("/monitoring/start")
async def start_monitoring():
    """
    Start all Redis monitoring services.

    Starts metrics collection, health checking, performance monitoring,
    and alert management services.
    """
    try:
        # Start all monitoring services
        await redis_metrics_collector.start_collection()
        await redis_health_checker.start_health_checks()
        await redis_performance_monitor.start_monitoring()
        await redis_alert_manager.start_alerting()

        logger.info("All Redis monitoring services started")

        return {
            "message": "Redis monitoring services started successfully",
            "services": [
                "metrics_collection",
                "health_checking",
                "performance_monitoring",
                "alert_management",
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Failed to start monitoring services", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to start monitoring services: {str(e)}"
        )


@router.post("/monitoring/stop")
async def stop_monitoring():
    """
    Stop all Redis monitoring services.

    Stops metrics collection, health checking, performance monitoring,
    and alert management services.
    """
    try:
        # Stop all monitoring services
        await redis_metrics_collector.stop_collection()
        await redis_health_checker.stop_health_checks()
        await redis_performance_monitor.stop_monitoring()
        await redis_alert_manager.stop_alerting()

        logger.info("All Redis monitoring services stopped")

        return {
            "message": "Redis monitoring services stopped successfully",
            "services": [
                "metrics_collection",
                "health_checking",
                "performance_monitoring",
                "alert_management",
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Failed to stop monitoring services", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to stop monitoring services: {str(e)}"
        )


@router.get("/monitoring/status")
async def get_monitoring_status():
    """
    Get status of all Redis monitoring services.

    Returns the current status of metrics collection, health checking,
    performance monitoring, and alert management services.
    """
    try:
        # Check service status
        metrics_running = redis_metrics_collector._collection_task is not None
        health_running = redis_health_checker._health_check_task is not None
        performance_running = redis_performance_monitor._analysis_task is not None
        alerts_running = redis_alert_manager._evaluation_task is not None

        # Get service-specific status
        latest_health = await redis_health_checker.get_latest_health_status()
        alert_summary = await redis_alert_manager.get_alert_summary()

        return {
            "services": {
                "metrics_collection": {
                    "running": metrics_running,
                    "task_id": str(id(redis_metrics_collector._collection_task))
                    if metrics_running
                    else None,
                },
                "health_checking": {
                    "running": health_running,
                    "task_id": str(id(redis_health_checker._health_check_task))
                    if health_running
                    else None,
                    "latest_status": latest_health.status.value
                    if latest_health
                    else "unknown",
                },
                "performance_monitoring": {
                    "running": performance_running,
                    "task_id": str(id(redis_performance_monitor._analysis_task))
                    if performance_running
                    else None,
                },
                "alert_management": {
                    "running": alerts_running,
                    "task_id": str(id(redis_alert_manager._evaluation_task))
                    if alerts_running
                    else None,
                    "active_alerts": alert_summary["active_alerts"],
                    "suppressed_rules": alert_summary["suppressed_rules"],
                },
            },
            "overall_status": "running"
            if all(
                [metrics_running, health_running, performance_running, alerts_running]
            )
            else "partial",
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Failed to get monitoring status", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get monitoring status: {str(e)}"
        )
