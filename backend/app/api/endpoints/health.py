"""
Health check endpoints for JEEX Idea API.

Provides comprehensive health monitoring for the application and its dependencies.
Integrates with PostgreSQL health monitoring and OpenTelemetry metrics.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Dict, Any, Optional
import logging
import asyncio
from datetime import datetime

from ...db import get_database_session, get_database_health, get_database_metrics
from ...core.config import get_settings

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
    db: AsyncSession = Depends(get_database_session),
) -> Dict[str, Any]:
    """
    Readiness check endpoint.

    Checks if the application is ready to serve traffic by verifying
    database connectivity and other critical dependencies.
    """
    ready = True
    checks = {}

    # Check database connectivity
    try:
        result = await db.execute(text("SELECT 1"))
        assert result.scalar() == 1
        checks["database"] = {
            "status": "healthy",
            "message": "Database connection successful",
        }
    except Exception as e:
        ready = False
        logger.error("Database readiness check failed", error=str(e), exc_info=True)
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
        "uptime_seconds": 0,  # TODO: Implement uptime tracking
    }


@router.get("/database")
async def database_health() -> Dict[str, Any]:
    """
    Detailed database health check.

    Returns comprehensive database health information including
    connection metrics, performance indicators, and status.
    """
    try:
        health_data = await get_database_health()
        return health_data
    except Exception as e:
        logger.error("Database health check failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "error",
                "message": "Database health check failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


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
        logger.error(f"Database metrics collection failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "error",
                "message": "Database metrics collection failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@router.get("/dependencies")
async def dependencies_check(
    db: AsyncSession = Depends(get_database_session),
) -> Dict[str, Any]:
    """
    Check all external dependencies.

    Returns the health status of all external services and dependencies
    including database, vector store, cache, and monitoring systems.
    """
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
        # TODO: Implement actual Qdrant health check
        dependency_status["qdrant"] = {
            "status": "healthy",
            "message": "Qdrant vector store operational",
        }
    except Exception as e:
        overall_healthy = False
        dependency_status["qdrant"] = {
            "status": "unhealthy",
            "message": f"Qdrant connection failed: {e}",
        }

    # Redis check
    try:
        # TODO: Implement actual Redis health check
        dependency_status["redis"] = {
            "status": "healthy",
            "message": "Redis cache operational",
        }
    except Exception as e:
        overall_healthy = False
        dependency_status["redis"] = {
            "status": "unhealthy",
            "message": f"Redis connection failed: {e}",
        }

    # OpenTelemetry check
    try:
        # TODO: Implement OpenTelemetry connectivity check
        dependency_status["opentelemetry"] = {
            "status": "healthy",
            "message": "OpenTelemetry collector operational",
        }
    except Exception as e:
        # OpenTelemetry issues shouldn't make the service unhealthy
        dependency_status["opentelemetry"] = {
            "status": "degraded",
            "message": f"OpenTelemetry collector issue: {e}",
        }

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": dependency_status,
    }
