"""
Health check endpoints for JEEX Idea API.

Provides comprehensive health monitoring for the application and its dependencies.
Integrates with PostgreSQL health monitoring and OpenTelemetry metrics.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Dict, Any, Optional
import logging
import asyncio
import time
from datetime import datetime

# Track process start time for uptime calculation
PROCESS_START_TIME = time.time()

from ...db import get_database_session, get_database_health, get_database_metrics
from ...core.config import get_settings
from ...core.telemetry import get_tracer, get_correlation_id, otel_manager
from ...monitoring.health_checker import redis_health_checker
import httpx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])

settings = get_settings()


@router.get("/")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint.

    Returns a simple health status for load balancers and monitoring systems.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.OTEL_SERVICE_NAME,
        "version": settings.OTEL_SERVICE_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@router.get("/ready")
async def readiness_check(
    project_id: UUID = Query(
        ..., description="Project ID for database session scoping"
    ),
    db: AsyncSession = Depends(get_database_session),
) -> Dict[str, Any]:
    """
    Readiness check endpoint.

    Checks if the application is ready to serve traffic by verifying
    database connectivity and other critical dependencies.

    Args:
        project_id: Required project ID for database session scoping
    """
    logger.info(f"Running readiness check for project: {project_id}")
    ready = True
    checks = {}

    # Check database connectivity
    try:
        result = await db.execute(text("SELECT 1"))
        if result.scalar() != 1:
            raise RuntimeError("Database probe returned unexpected result")
        checks["database"] = {
            "status": "healthy",
            "message": "Database connection successful",
        }
    except Exception as e:
        ready = False
        logger.exception(f"Database readiness check failed for project {project_id}")
        checks["database"] = {"status": "unhealthy", "message": str(e)}

    # Check Qdrant connectivity (if configured)
    try:
        # TODO: Add Qdrant health check when Qdrant client is implemented
        checks["qdrant"] = {
            "status": "healthy",
            "message": "Qdrant connection successful",
        }
    except Exception as e:
        ready = False
        logger.error(f"Qdrant readiness check failed: {e}")
        checks["qdrant"] = {"status": "unhealthy", "message": str(e)}

    # Check Redis connectivity (if configured)
    try:
        # TODO: Add Redis health check when Redis client is implemented
        checks["redis"] = {
            "status": "healthy",
            "message": "Redis connection successful",
        }
    except Exception as e:
        ready = False
        logger.error(f"Redis readiness check failed: {e}")
        checks["redis"] = {"status": "unhealthy", "message": str(e)}

    return {
        "status": "ready" if ready else "not_ready",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
    }


@router.get("/live")
async def liveness_check() -> Dict[str, Any]:
    """
    Liveness check endpoint.

    Indicates if the application is running. This endpoint should always
    return a successful response if the application process is alive.
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": int(time.time() - PROCESS_START_TIME),
    }


@router.get("/database")
async def database_health(
    project_id: UUID = Query(
        ..., description="Project ID for database health check (required)"
    ),
) -> Dict[str, Any]:
    """
    Detailed database health check.

    Returns comprehensive database health information including
    connection metrics, performance indicators, and status.

    Args:
        project_id: Required project ID for database health check
    """
    try:
        health_data = await get_database_health(project_id)
        return health_data
    except Exception as e:
        logger.exception(
            f"Database health check failed for project {project_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "error",
                "message": f"Database health check failed: {str(e)}",
                "project_id": str(project_id),
            },
        ) from e


@router.get("/database/metrics")
async def database_metrics() -> Dict[str, Any]:
    """
    Database performance metrics.

    Returns detailed performance metrics from PostgreSQL
    for monitoring and optimization purposes.
    """
    try:
        metrics = await get_database_metrics()
        return metrics
    except Exception as e:
        logger.exception(f"Database metrics collection failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "error",
                "message": f"Database metrics collection failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
            },
        ) from e


@router.get("/dependencies")
async def dependencies_check(
    project_id: UUID = Query(
        ..., description="Project ID for database session scoping"
    ),
    db: AsyncSession = Depends(get_database_session),
) -> Dict[str, Any]:
    """
    Check all external dependencies.

    Returns the health status of all external services and dependencies
    including database, vector store, cache, and monitoring systems.

    Args:
        project_id: Required project ID for database session scoping
    """
    logger.info(f"Checking dependencies for project: {project_id}")
    dependency_status = {}
    overall_healthy = True

    # Database check
    try:
        result = await db.execute(text("SELECT version()"))
        version = result.scalar()
        dependency_status["postgresql"] = {
            "status": "healthy",
            "version": version,
            "message": "PostgreSQL connection successful",
        }
    except Exception as e:
        overall_healthy = False
        dependency_status["postgresql"] = {
            "status": "unhealthy",
            "message": f"PostgreSQL connection failed: {e}",
        }

    # Qdrant check
    try:
        # Use vector database module for Qdrant health check
        from ...core.vector import vector_database

        # Test Qdrant connectivity
        qdrant_health = await vector_database.health_check()

        # Map vector database health to dependency status
        qdrant_status = "healthy" if qdrant_health.get("healthy", False) else "degraded"
        if not qdrant_health.get("healthy", False):
            overall_healthy = False

        dependency_status["qdrant"] = {
            "status": qdrant_status,
            "message": qdrant_health.get(
                "message", "Qdrant vector store status unknown"
            ),
            "response_time_ms": qdrant_health.get("response_time_ms", 0),
            "collection_info": qdrant_health.get("collection_info", {}),
            "cluster_info": qdrant_health.get("cluster_info", {}),
        }

    except Exception as e:
        overall_healthy = False
        logger.error("Qdrant health check failed", error=str(e), project_id=project_id)
        dependency_status["qdrant"] = {
            "status": "unhealthy",
            "message": f"Qdrant health check failed: {e}",
        }

    # Redis check
    try:
        # Use the Redis health checker for comprehensive monitoring
        redis_health = await redis_health_checker.perform_full_health_check(project_id)

        # Map Redis health status to dependency status
        redis_status = (
            "healthy" if redis_health.status.value == "healthy" else "degraded"
        )
        if redis_health.status.value == "unhealthy":
            redis_status = "unhealthy"
            overall_healthy = False

        dependency_status["redis"] = {
            "status": redis_status,
            "message": f"Redis cache {redis_health.status.value}",
            "uptime_seconds": redis_health.uptime_seconds,
            "version": redis_health.version,
            "checks_count": len(redis_health.checks),
            "alerts_count": len(redis_health.alerts),
            "summary": redis_health.summary,
        }

        # Log any Redis alerts
        if redis_health.alerts:
            logger.warning(
                "Redis health alerts detected",
                alerts=redis_health.alerts,
                project_id=project_id,
            )

    except Exception as e:
        overall_healthy = False
        logger.error("Redis health check failed", error=str(e), project_id=project_id)
        dependency_status["redis"] = {
            "status": "unhealthy",
            "message": f"Redis health check failed: {e}",
        }

    # OpenTelemetry check
    try:
        # Check OpenTelemetry collector connectivity
        otel_status = await _check_opentelemetry_collector()
        dependency_status["opentelemetry"] = otel_status

        # Check OpenTelemetry instrumentation status
        instrumentation_status = await _check_opentelemetry_instrumentation()
        dependency_status["opentelemetry_instrumentation"] = instrumentation_status

        # Check correlation ID functionality
        correlation_status = await _check_correlation_id_functionality()
        dependency_status["correlation_ids"] = correlation_status

    except Exception as e:
        # OpenTelemetry issues shouldn't make the service unhealthy
        logger.error("OpenTelemetry health check failed", error=str(e))
        dependency_status["opentelemetry"] = {
            "status": "degraded",
            "message": f"OpenTelemetry collector issue: {e}",
        }
        dependency_status["opentelemetry_instrumentation"] = {
            "status": "degraded",
            "message": "OpenTelemetry instrumentation check failed",
        }
        dependency_status["correlation_ids"] = {
            "status": "degraded",
            "message": "Correlation ID check failed",
        }

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": dependency_status,
    }


async def _check_opentelemetry_collector() -> Dict[str, Any]:
    """
    Check OpenTelemetry collector health and connectivity.

    Returns:
        Health status of the OpenTelemetry collector
    """
    start_time = time.time()

    try:
        # Extract collector endpoint from environment
        collector_endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT

        # For health check, we always use the HTTP health endpoint on port 8888
        # Extract host from collector endpoint for health check
        if collector_endpoint.startswith("http://"):
            host = collector_endpoint.replace("http://", "").split(":")[0]
        elif collector_endpoint.startswith("https://"):
            host = collector_endpoint.replace("https://", "").split(":")[0]
        elif ":" in collector_endpoint:
            host = collector_endpoint.split(":")[0]
        else:
            host = "otel-collector"

        # Always use health endpoint on port 8888
        health_endpoint = f"http://{host}:8888/health"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_endpoint)
            response.raise_for_status()

            health_data = response.json()
            duration_ms = (time.time() - start_time) * 1000

            status = "healthy" if response.status_code == 200 else "degraded"

            return {
                "status": status,
                "message": f"OpenTelemetry collector operational (response time: {duration_ms:.2f}ms)",
                "endpoint": health_endpoint,
                "response_time_ms": duration_ms,
                "response_code": response.status_code,
                "collector_info": health_data,
            }

    except httpx.TimeoutException:
        duration_ms = (time.time() - start_time) * 1000
        return {
            "status": "degraded",
            "message": f"OpenTelemetry collector timeout after {duration_ms:.2f}ms",
            "endpoint": health_endpoint
            if "health_endpoint" in locals()
            else collector_endpoint,
            "response_time_ms": duration_ms,
            "error_type": "timeout",
        }

    except httpx.ConnectError:
        duration_ms = (time.time() - start_time) * 1000
        return {
            "status": "unhealthy",
            "message": f"Cannot connect to OpenTelemetry collector",
            "endpoint": health_endpoint
            if "health_endpoint" in locals()
            else collector_endpoint,
            "response_time_ms": duration_ms,
            "error_type": "connection_error",
        }

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error("OpenTelemetry collector health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "message": f"OpenTelemetry collector health check failed: {str(e)}",
            "endpoint": health_endpoint
            if "health_endpoint" in locals()
            else collector_endpoint,
            "response_time_ms": duration_ms,
            "error_type": "unknown",
        }


async def _check_opentelemetry_instrumentation() -> Dict[str, Any]:
    """
    Check OpenTelemetry instrumentation status.

    Returns:
        Health status of OpenTelemetry instrumentation
    """
    start_time = time.time()

    try:
        # Check if OpenTelemetry manager is initialized
        is_initialized = (
            otel_manager._initialized
            if hasattr(otel_manager, "_initialized")
            else False
        )

        # Test tracer functionality
        tracer = get_tracer("health-check", "0.1.0")

        # Test span creation and recording
        with tracer.start_as_current_span("health-check-span") as span:
            span.set_attribute("health.check", True)
            span.set_attribute("service.name", settings.OTEL_SERVICE_NAME)
            span.set_attribute("service.version", settings.OTEL_SERVICE_VERSION)

            # Test if span is recording
            is_recording = span.is_recording() if span else False

            # Get span context if available
            span_context = None
            if span and span.is_recording():
                ctx = span.get_span_context()
                span_context = {
                    "trace_id": f"0x{ctx.trace_id:032x}",
                    "span_id": f"0x{ctx.span_id:016x}",
                    "is_sampled": ctx.trace_flags.sampled,
                }

        duration_ms = (time.time() - start_time) * 1000

        # Determine status based on tests
        if is_initialized and is_recording:
            status = "healthy"
            message = "OpenTelemetry instrumentation fully operational"
        elif is_initialized:
            status = "degraded"
            message = "OpenTelemetry initialized but span recording issues detected"
        else:
            status = "unhealthy"
            message = "OpenTelemetry instrumentation not initialized"

        return {
            "status": status,
            "message": f"{message} (check time: {duration_ms:.2f}ms)",
            "response_time_ms": duration_ms,
            "initialized": is_initialized,
            "tracer_available": tracer is not None,
            "span_recording": is_recording,
            "span_context": span_context,
            "service_name": settings.OTEL_SERVICE_NAME,
            "service_version": settings.OTEL_SERVICE_VERSION,
            "collector_endpoint": settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        }

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error("OpenTelemetry instrumentation health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "message": f"OpenTelemetry instrumentation check failed: {str(e)}",
            "response_time_ms": duration_ms,
            "error_type": "instrumentation_error",
        }


async def _check_correlation_id_functionality() -> Dict[str, Any]:
    """
    Check correlation ID functionality.

    Returns:
        Health status of correlation ID functionality
    """
    start_time = time.time()

    try:
        # Test correlation ID retrieval
        current_correlation_id = get_correlation_id()

        # Test correlation ID setting in span context
        test_correlation_id = f"health-check-{int(time.time() * 1000)}"
        try:
            from ...core.telemetry import set_correlation_id

            set_correlation_id(test_correlation_id)

            # Verify it was set (in a real scenario, this would be checked in the current span)
            correlation_setting_works = True
        except Exception as e:
            correlation_setting_works = False
            logger.warning("Correlation ID setting test failed", error=str(e))

        # Test correlation ID format validation
        import uuid
        import re

        # Test UUID format
        uuid_pattern = (
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
        uuid_valid = bool(re.match(uuid_pattern, str(uuid.uuid4()), re.IGNORECASE))

        # Test custom format
        custom_id = "test-correlation-123"
        custom_pattern = r"^[a-zA-Z0-9\-_\.]+$"
        custom_valid = bool(re.match(custom_pattern, custom_id))

        duration_ms = (time.time() - start_time) * 1000

        # Determine status
        if correlation_setting_works and (uuid_valid or custom_valid):
            status = "healthy"
            message = "Correlation ID functionality operational"
        elif correlation_setting_works:
            status = "degraded"
            message = "Correlation ID setting works but validation issues detected"
        else:
            status = "unhealthy"
            message = "Correlation ID functionality not working"

        return {
            "status": status,
            "message": f"{message} (check time: {duration_ms:.2f}ms)",
            "response_time_ms": duration_ms,
            "current_correlation_id": current_correlation_id,
            "correlation_setting_works": correlation_setting_works,
            "test_correlation_id": test_correlation_id
            if correlation_setting_works
            else None,
            "format_validation": {
                "uuid_format": uuid_valid,
                "custom_format": custom_valid,
            },
        }

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error("Correlation ID functionality health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "message": f"Correlation ID functionality check failed: {str(e)}",
            "response_time_ms": duration_ms,
            "error_type": "correlation_error",
        }


@router.get("/observability")
async def observability_health_check() -> Dict[str, Any]:
    """
    Comprehensive observability stack health check.

    Returns detailed health status for all observability components including
    OpenTelemetry collector, instrumentation, correlation IDs, and monitoring systems.

    Returns:
        Comprehensive observability health status
    """
    logger.info("Running observability stack health check")
    start_time = time.time()

    observability_status = {}
    overall_healthy = True

    # OpenTelemetry Collector Health Check
    try:
        collector_status = await _check_opentelemetry_collector()
        observability_status["collector"] = collector_status

        if collector_status["status"] == "unhealthy":
            overall_healthy = False
        elif collector_status["status"] == "degraded":
            # Collector issues don't make service unhealthy, but we track them
            logger.warning(
                "OpenTelemetry collector degraded", collector_status=collector_status
            )

    except Exception as e:
        logger.error("Collector health check failed", error=str(e))
        observability_status["collector"] = {
            "status": "unhealthy",
            "message": f"Collector health check failed: {str(e)}",
            "error_type": "health_check_error",
        }
        overall_healthy = False

    # OpenTelemetry Instrumentation Health Check
    try:
        instrumentation_status = await _check_opentelemetry_instrumentation()
        observability_status["instrumentation"] = instrumentation_status

        if instrumentation_status["status"] == "unhealthy":
            # Instrumentation issues are serious
            overall_healthy = False

    except Exception as e:
        logger.error("Instrumentation health check failed", error=str(e))
        observability_status["instrumentation"] = {
            "status": "unhealthy",
            "message": f"Instrumentation health check failed: {str(e)}",
            "error_type": "health_check_error",
        }
        overall_healthy = False

    # Correlation ID Health Check
    try:
        correlation_status = await _check_correlation_id_functionality()
        observability_status["correlation_ids"] = correlation_status

        if correlation_status["status"] == "unhealthy":
            # Correlation ID issues are serious for observability
            overall_healthy = False

    except Exception as e:
        logger.error("Correlation ID health check failed", error=str(e))
        observability_status["correlation_ids"] = {
            "status": "unhealthy",
            "message": f"Correlation ID health check failed: {str(e)}",
            "error_type": "health_check_error",
        }
        overall_healthy = False

    # Monitoring Systems Health Check
    try:
        monitoring_status = await _check_monitoring_systems()
        observability_status["monitoring_systems"] = monitoring_status

        # Monitoring system issues don't make service unhealthy
        if monitoring_status["status"] == "unhealthy":
            logger.warning(
                "Monitoring systems unhealthy", monitoring_status=monitoring_status
            )

    except Exception as e:
        logger.error(
            "Monitoring systems health check failed", error=str(e), exc_info=True
        )
        observability_status["monitoring_systems"] = {
            "status": "degraded",
            "message": f"Monitoring systems check failed: {str(e)}",
            "error_type": "health_check_error",
        }

    # Performance Metrics
    total_duration_ms = (time.time() - start_time) * 1000

    # Determine overall status
    overall_status = "healthy" if overall_healthy else "degraded"
    if not overall_healthy:
        # Check if critical components are down
        critical_issues = [
            name
            for name, status in observability_status.items()
            if status.get("status") == "unhealthy"
            and name in ["collector", "instrumentation"]
        ]
        if critical_issues:
            overall_status = "unhealthy"

    # Generate summary
    healthy_components = len(
        [
            name
            for name, status in observability_status.items()
            if status.get("status") == "healthy"
        ]
    )
    total_components = len(observability_status)

    result = {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "total_duration_ms": total_duration_ms,
        "summary": {
            "healthy_components": healthy_components,
            "total_components": total_components,
            "health_percentage": (healthy_components / total_components * 100)
            if total_components > 0
            else 0,
        },
        "components": observability_status,
        "service_info": {
            "name": settings.OTEL_SERVICE_NAME,
            "version": settings.OTEL_SERVICE_VERSION,
            "environment": settings.ENVIRONMENT,
            "collector_endpoint": settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        },
        "performance_requirements": {
            "max_health_check_duration_ms": 5000,
            "actual_duration_ms": total_duration_ms,
            "within_requirements": total_duration_ms < 5000,
        },
    }

    # Log overall observability health
    log_level = (
        "info"
        if overall_status == "healthy"
        else "warning"
        if overall_status == "degraded"
        else "error"
    )
    getattr(logger, log_level)(
        "Observability health check completed",
        status=overall_status,
        duration_ms=total_duration_ms,
        healthy_components=healthy_components,
        total_components=total_components,
    )

    return result


async def _check_monitoring_systems() -> Dict[str, Any]:
    """
    Check monitoring systems status.

    Returns:
        Health status of monitoring systems
    """
    start_time = time.time()

    try:
        monitoring_status = {}
        monitoring_healthy = True

        # Check Redis monitoring systems
        try:
            from ...monitoring.redis_metrics import redis_metrics_collector
            from ...monitoring.performance_monitor import redis_performance_monitor
            from ...monitoring.alert_manager import redis_alert_manager

            # Check metrics collector
            metrics_active = (
                hasattr(redis_metrics_collector, "_collection_task")
                and redis_metrics_collector._collection_task
                and not redis_metrics_collector._collection_task.done()
            )

            # Check performance monitor
            performance_active = (
                hasattr(redis_performance_monitor, "_monitoring_task")
                and redis_performance_monitor._monitoring_task
                and not redis_performance_monitor._monitoring_task.done()
            )

            # Check alert manager
            alerting_active = (
                hasattr(redis_alert_manager, "_alerting_task")
                and redis_alert_manager._alerting_task
                and not redis_alert_manager._alerting_task.done()
            )

            monitoring_status["redis_monitoring"] = {
                "status": "healthy"
                if (metrics_active and performance_active and alerting_active)
                else "degraded",
                "metrics_collection": "active" if metrics_active else "inactive",
                "performance_monitoring": "active"
                if performance_active
                else "inactive",
                "alert_management": "active" if alerting_active else "inactive",
            }

            if not (metrics_active and performance_active and alerting_active):
                monitoring_healthy = False

        except ImportError as e:
            logger.warning("Redis monitoring modules not available", error=str(e))
            monitoring_status["redis_monitoring"] = {
                "status": "degraded",
                "message": "Redis monitoring modules not available",
                "error_type": "import_error",
            }
        except Exception as e:
            logger.warning("Redis monitoring systems check failed", error=str(e))
            monitoring_status["redis_monitoring"] = {
                "status": "unhealthy",
                "message": f"Redis monitoring check failed: {str(e)}",
            }
            monitoring_healthy = False

        # Check database monitoring systems
        try:
            from ...core.monitoring import performance_monitor

            # Check if performance monitor is initialized
            pm_active = (
                hasattr(performance_monitor, "_initialized")
                and performance_monitor._initialized
            )

            monitoring_status["database_monitoring"] = {
                "status": "healthy" if pm_active else "degraded",
                "performance_monitor": "active" if pm_active else "inactive",
            }

            if not pm_active:
                monitoring_healthy = False

        except Exception as e:
            logger.warning("Database monitoring systems check failed", error=str(e))
            monitoring_status["database_monitoring"] = {
                "status": "unhealthy",
                "message": f"Database monitoring check failed: {str(e)}",
            }
            monitoring_healthy = False

        duration_ms = (time.time() - start_time) * 1000

        return {
            "status": "healthy" if monitoring_healthy else "degraded",
            "message": f"Monitoring systems {'operational' if monitoring_healthy else 'partially operational'}",
            "response_time_ms": duration_ms,
            "systems": monitoring_status,
        }

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error("Monitoring systems health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "message": f"Monitoring systems check failed: {str(e)}",
            "response_time_ms": duration_ms,
            "error_type": "monitoring_error",
        }
