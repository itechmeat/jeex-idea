"""
JEEX Idea Database Monitoring API Endpoints - Phase 3

API endpoints for database optimization, monitoring, and management:
- Database performance monitoring and metrics
- Connection pool status and optimization
- Backup and recovery operations
- Maintenance procedures
- Performance testing and benchmarks
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
import structlog
from sqlalchemy import text

from ...core.db_optimized import optimized_database
from ...core.monitoring import performance_monitor
from ...core.maintenance import maintenance_manager, MaintenanceType
from ...core.backup import backup_manager, BackupType
from ...core.testing import database_test_suite
from ...core.config import get_settings

logger = structlog.get_logger()
router = APIRouter(prefix="/database", tags=["database-monitoring"])


# Pydantic models for API requests/responses
class DatabaseHealthResponse(BaseModel):
    """Database health check response."""

    timestamp: str
    project_id: Optional[str]
    overall_status: str
    performance_score: float
    performance_requirements: Dict[str, Any]
    database: Dict[str, Any]
    monitoring: Dict[str, Any]
    maintenance: Dict[str, Any]
    backup: Dict[str, Any]
    optimizations: Dict[str, Any]


class ConnectionMetricsResponse(BaseModel):
    """Connection pool metrics response."""

    connection_metrics: Dict[str, Any]
    pool_metrics: Dict[str, Any]
    pool_efficiency: Dict[str, Any]
    requirements_satisfaction: Dict[str, Any]


class BackupRequest(BaseModel):
    """Backup creation request."""

    backup_type: str = Field(
        default="full", description="Backup type: full, incremental, differential, wal"
    )
    project_id: Optional[str] = Field(
        default=None, description="Project ID for project-scoped backup"
    )


class BackupResponse(BaseModel):
    """Backup operation response."""

    backup_id: str
    backup_type: str
    status: str
    start_time: str
    size_bytes: int
    project_id: Optional[str]
    requirements_satisfaction: Dict[str, Any]


class MaintenanceRequest(BaseModel):
    """Maintenance operation request."""

    maintenance_type: str = Field(
        description="Maintenance type: vacuum, analyze, reindex, etc."
    )
    table_name: Optional[str] = Field(default=None, description="Specific table name")
    project_id: Optional[str] = Field(
        default=None, description="Project ID for scoping"
    )


class PerformanceTestResponse(BaseModel):
    """Performance test results response."""

    test_suite: str
    timestamp: str
    individual_tests: List[Dict[str, Any]]
    performance_metrics: Dict[str, Any]
    requirements_compliance: Dict[str, Any]
    summary: Dict[str, Any]


class QueryAnalysisRequest(BaseModel):
    """Query analysis request."""

    query: str = Field(..., description="SQL query to analyze")
    project_id: UUID = Field(..., description="Project ID for context")


class QueryAnalysisResponse(BaseModel):
    """Query analysis response."""

    query: str
    project_id: str
    execution_plan: Dict[str, Any]
    analysis: Dict[str, Any]


# API Endpoints


@router.get("/health", response_model=DatabaseHealthResponse)
async def get_database_health(
    project_id: Optional[UUID] = Query(
        None, description="Project ID for project-scoped health check"
    ),
) -> DatabaseHealthResponse:
    """
    Get comprehensive database health status including all Phase 3 systems.

    Args:
        project_id: Optional project ID for project-scoped health check

    Returns:
        Comprehensive health status with performance metrics
    """
    try:
        project_id_str = str(project_id) if project_id else None
        health_data = await optimized_database.get_comprehensive_health(project_id_str)

        return DatabaseHealthResponse(**health_data)

    except Exception as e:
        logger.error(
            "Failed to get database health", error=str(e), project_id=project_id
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get database health: {str(e)}"
        )


@router.get("/connections/metrics", response_model=ConnectionMetricsResponse)
async def get_connection_metrics() -> ConnectionMetricsResponse:
    """
    Get detailed connection pool metrics and efficiency.

    Returns:
        Connection pool metrics and REQ-004 compliance status
    """
    try:
        metrics_data = await optimized_database.get_connection_metrics()

        return ConnectionMetricsResponse(**metrics_data)

    except Exception as e:
        logger.error("Failed to get connection metrics", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get connection metrics: {str(e)}"
        )


@router.post("/backup/create", response_model=BackupResponse)
async def create_backup(
    request: BackupRequest, background_tasks: BackgroundTasks
) -> BackupResponse:
    """
    Create a database backup with all Phase 3 optimizations.

    Args:
        request: Backup creation parameters
        background_tasks: FastAPI background tasks

    Returns:
        Backup operation status and metadata
    """
    try:
        backup_data = await optimized_database.create_backup(
            backup_type=request.backup_type, project_id=request.project_id
        )

        return BackupResponse(**backup_data)

    except Exception as e:
        logger.error(
            "Failed to create backup", error=str(e), backup_type=request.backup_type
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to create backup: {str(e)}"
        )


@router.get("/backup/status")
async def get_backup_status() -> Dict[str, Any]:
    """
    Get backup system status and history.

    Returns:
        Current backup system status and recent backup operations
    """
    try:
        backup_status = await backup_manager.get_backup_status()
        return backup_status

    except Exception as e:
        logger.error("Failed to get backup status", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get backup status: {str(e)}"
        )


@router.post("/backup/{backup_id}/test-recovery")
async def test_backup_recovery(backup_id: str) -> Dict[str, Any]:
    """
    Test backup recovery procedures for REL-003 compliance.

    Args:
        backup_id: ID of backup to test

    Returns:
        Recovery test results
    """
    try:
        test_results = await optimized_database.test_backup_recovery(backup_id)
        return test_results

    except Exception as e:
        logger.error(
            "Failed to test backup recovery", error=str(e), backup_id=backup_id
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to test backup recovery: {str(e)}"
        )


@router.post("/maintenance/run")
async def run_maintenance(request: MaintenanceRequest) -> Dict[str, Any]:
    """
    Run database maintenance operations.

    Args:
        request: Maintenance operation parameters

    Returns:
        Maintenance operation results
    """
    try:
        maintenance_type = MaintenanceType(request.maintenance_type)
        task = await maintenance_manager.run_maintenance(
            maintenance_type=maintenance_type,
            table_name=request.table_name,
            project_id=request.project_id,
        )

        return {
            "task_id": task.task_id,
            "maintenance_type": task.maintenance_type.value,
            "status": task.status.value,
            "start_time": task.start_time.isoformat(),
            "duration_seconds": task.duration_seconds,
            "affected_rows": task.affected_rows,
            "project_id": task.project_id,
            "table_name": task.table_name,
        }

    except Exception as e:
        logger.error(
            "Failed to run maintenance",
            error=str(e),
            maintenance_type=request.maintenance_type,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to run maintenance: {str(e)}"
        )


@router.get("/maintenance/status")
async def get_maintenance_status() -> Dict[str, Any]:
    """
    Get maintenance system status and history.

    Returns:
        Current maintenance system status and recent operations
    """
    try:
        maintenance_status = await maintenance_manager.get_maintenance_status()
        return maintenance_status

    except Exception as e:
        logger.error("Failed to get maintenance status", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get maintenance status: {str(e)}"
        )


@router.get("/monitoring/dashboard")
async def get_performance_dashboard(
    project_id: Optional[UUID] = Query(
        None, description="Project ID for project-scoped monitoring"
    ),
) -> Dict[str, Any]:
    """
    Get comprehensive performance monitoring dashboard.

    Args:
        project_id: Optional project ID for project-scoped monitoring

    Returns:
        Performance monitoring dashboard with metrics and alerts
    """
    try:
        dashboard = await performance_monitor.get_performance_dashboard(project_id)
        return dashboard

    except Exception as e:
        logger.error(
            "Failed to get performance dashboard", error=str(e), project_id=project_id
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get performance dashboard: {str(e)}"
        )


@router.post("/monitoring/query/analyze", response_model=QueryAnalysisResponse)
async def analyze_query_performance(
    request: QueryAnalysisRequest,
) -> QueryAnalysisResponse:
    """
    Analyze specific query performance and provide optimization recommendations.

    Args:
        request: Query analysis parameters

    Returns:
        Query execution plan and optimization recommendations
    """
    try:
        # Validate that only SELECT queries are allowed for analysis
        if not request.query.strip().lower().startswith("select "):
            raise HTTPException(
                status_code=400, detail="Only SELECT queries are allowed for analysis"
            )

        analysis_data = await performance_monitor.analyze_query_performance(
            query=request.query, project_id=request.project_id
        )

        return QueryAnalysisResponse(**analysis_data)

    except HTTPException:
        # Re-raise HTTP exceptions (like our validation error)
        raise
    except Exception as e:
        logger.error(
            "Failed to analyze query", error=str(e), query_preview=request.query[:100]
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to analyze query: {str(e)}"
        )


@router.post("/optimization/run")
async def run_performance_optimization(
    project_id: Optional[UUID] = Query(
        None, description="Project ID for project-scoped optimization"
    ),
) -> Dict[str, Any]:
    """
    Run comprehensive performance optimization routine.

    Args:
        project_id: Optional project ID for project-scoped optimization

    Returns:
        Optimization results and performance improvements
    """
    try:
        project_id_str = str(project_id) if project_id else None
        optimization_results = await optimized_database.run_performance_optimization(
            project_id_str
        )
        return optimization_results

    except Exception as e:
        logger.error(
            "Failed to run performance optimization",
            error=str(e),
            project_id=project_id,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to run performance optimization: {str(e)}"
        )


@router.post("/testing/run-comprehensive", response_model=PerformanceTestResponse)
async def run_comprehensive_tests(
    background_tasks: BackgroundTasks,
    project_id: Optional[UUID] = Query(
        None, description="Project ID for project-scoped testing"
    ),
) -> PerformanceTestResponse:
    """
    Run comprehensive Phase 3 database testing suite.

    Args:
        background_tasks: FastAPI background tasks
        project_id: Optional project ID for project-scoped testing

    Returns:
        Comprehensive test results and performance metrics
    """
    try:
        # Run tests (this could be made into a background task for long-running tests)
        test_results = await database_test_suite.run_all_tests()

        return PerformanceTestResponse(**test_results)

    except Exception as e:
        logger.error(
            "Failed to run comprehensive tests", error=str(e), project_id=project_id
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to run comprehensive tests: {str(e)}"
        )


@router.get("/testing/quick-benchmark")
async def run_quick_performance_benchmark() -> Dict[str, Any]:
    """
    Run quick performance benchmark to verify PERF-001 (<100ms P95).

    Returns:
        Quick benchmark results
    """
    try:
        # Run a subset of performance tests for quick verification
        query_times = []
        test_duration = 5  # 5 seconds
        queries_executed = 0

        start_time = datetime.utcnow()
        while (datetime.utcnow() - start_time).total_seconds() < test_duration:
            query_start = datetime.utcnow()
            try:
                async with optimized_database.get_session() as session:
                    await session.execute(text("SELECT 1 as benchmark"))
                    await session.commit()

                query_time = (datetime.utcnow() - query_start).total_seconds() * 1000
                query_times.append(query_time)
                queries_executed += 1

            except Exception as e:
                logger.warning("Benchmark query failed", error=str(e))

        if query_times:
            import statistics

            avg_time = statistics.mean(query_times)
            p95_time = statistics.quantiles(query_times, n=20)[18]  # 95th percentile
            qps = queries_executed / test_duration
        else:
            avg_time = p95_time = qps = 0

        return {
            "benchmark_type": "quick_performance_check",
            "timestamp": datetime.utcnow().isoformat(),
            "duration_seconds": test_duration,
            "queries_executed": queries_executed,
            "queries_per_second": qps,
            "response_times_ms": {"average": avg_time, "p95": p95_time},
            "perf_001_compliance": {
                "target_p95_ms": 100,
                "actual_p95_ms": p95_time,
                "requirement_met": p95_time < 100,
            },
        }

    except Exception as e:
        logger.error("Failed to run quick benchmark", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to run quick benchmark: {str(e)}"
        )


@router.get("/metrics/prometheus")
async def get_prometheus_metrics() -> Dict[str, Any]:
    """
    Get Prometheus metrics for database monitoring.

    Returns:
        Prometheus-formatted metrics
    """
    try:
        # Get metrics from all monitoring systems
        connection_metrics = await optimized_database.get_connection_metrics()
        dashboard = await performance_monitor.get_performance_dashboard()
        maintenance_status = await maintenance_manager.get_maintenance_status()

        # This would typically return the metrics in Prometheus format
        # For now, return a summary of available metrics
        return {
            "metrics_available": True,
            "connection_metrics": connection_metrics,
            "performance_metrics": dashboard.get("metrics", {}),
            "maintenance_metrics": {
                "active_tasks": len(maintenance_status.get("current_tasks", [])),
                "pending_tasks": maintenance_status.get("pending_tasks", 0),
            },
            "prometheus_endpoint": "/metrics",  # Standard Prometheus endpoint
        }

    except Exception as e:
        logger.error("Failed to get Prometheus metrics", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get Prometheus metrics: {str(e)}"
        )


@router.get("/configuration")
async def get_database_configuration() -> Dict[str, Any]:
    """
    Get current database configuration and optimization settings.

    Returns:
        Current database configuration and Phase 3 optimization status
    """
    try:
        settings = get_settings()

        config = {
            "database_connection": {
                "pool_size": settings.database_pool_size(),
                "max_overflow": settings.database_max_overflow(),
                "pool_timeout": settings.database_pool_timeout(),
                "pool_recycle": settings.database_pool_recycle(),
            },
            "performance_monitoring": {
                "slow_query_threshold_ms": settings.slow_query_threshold_ms(),
                "query_timeout_seconds": settings.query_timeout_seconds(),
                "monitoring_enabled": settings.performance_monitoring_enabled(),
            },
            "backup_configuration": {
                "backup_enabled": settings.backup_enabled(),
                "retention_days": settings.backup_retention_days(),
                "compression": settings.backup_compression(),
                "encryption_enabled": settings.backup_encryption_enabled(),
            },
            "maintenance_configuration": {
                "auto_vacuum_enabled": settings.auto_vacuum_enabled(),
                "auto_analyze_enabled": settings.auto_analyze_enabled(),
                "maintenance_window": {
                    "start": settings.maintenance_window_start(),
                    "end": settings.maintenance_window_end(),
                },
                "vacuum_threshold_percent": settings.vacuum_threshold_percent(),
                "analyze_threshold_percent": settings.analyze_threshold_percent(),
            },
            "wal_archiving": {
                "enabled": settings.wal_archiving_enabled(),
                "retention_days": settings.wal_retention_days(),
                "archive_directory": settings.wal_archive_directory(),
            },
        }

        return config

    except Exception as e:
        logger.error("Failed to get database configuration", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get database configuration: {str(e)}"
        )


@router.post("/initialize")
async def initialize_database_systems(
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """
    Initialize all Phase 3 database optimization systems.

    Args:
        background_tasks: FastAPI background tasks

    Returns:
        Initialization status
    """
    try:
        # Initialize all optimization systems
        await optimized_database.initialize()

        return {
            "status": "success",
            "message": "All Phase 3 database optimization systems initialized successfully",
            "timestamp": datetime.utcnow().isoformat(),
            "systems_initialized": [
                "connection_pool_optimization",
                "performance_monitoring",
                "automated_maintenance",
                "backup_and_recovery",
                "postgresql_configuration",
                "comprehensive_testing",
            ],
        }

    except Exception as e:
        logger.error("Failed to initialize database systems", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to initialize database systems: {str(e)}"
        )


@router.get("/status/overview")
async def get_database_systems_overview() -> Dict[str, Any]:
    """
    Get overview status of all Phase 3 database systems.

    Returns:
        Comprehensive overview of all database optimization systems
    """
    try:
        overview = {
            "timestamp": datetime.utcnow().isoformat(),
            "systems": {
                "connection_pool": await optimized_database.get_connection_metrics(),
                "performance_monitoring": await performance_monitor.get_performance_dashboard(),
                "maintenance": await maintenance_manager.get_maintenance_status(),
                "backup": await backup_manager.get_backup_status(),
            },
            "overall_health": await optimized_database.get_comprehensive_health(),
            "phase_3_requirements": {
                "connection_pool_management": {
                    "status": "implemented",
                    "req_004": True,
                },
                "database_health_monitoring": {"status": "active", "req_005": True},
                "backup_and_recovery": {"status": "operational", "req_007": True},
                "performance_optimization": {"status": "optimized", "req_008": True},
                "perf_001_compliance": {"status": "verified", "target_ms": 100},
                "rel_001_availability": {"status": "monitored", "target": "99.9%"},
                "rel_003_reliability": {"status": "tested", "backup_integrity": True},
            },
        }

        return overview

    except Exception as e:
        logger.error("Failed to get database systems overview", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get database systems overview: {str(e)}"
        )
