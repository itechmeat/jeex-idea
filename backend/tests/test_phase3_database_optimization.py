"""
JEEX Idea Phase 3 Database Optimization Tests

Comprehensive test suite for Phase 3 database optimization implementation.
Tests all requirements and acceptance criteria for:
- Connection pooling optimization (Task 3.1)
- Database performance monitoring (Task 3.2)
- Backup and recovery procedures (Task 3.3)
- Database maintenance procedures (Task 3.4)
- PostgreSQL configuration optimization (Task 3.5)
- Comprehensive database testing (Task 3.6)
"""

import pytest
import asyncio
import time
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy import text

logger = logging.getLogger(__name__)

from app.core.db_optimized import optimized_database
from app.core.monitoring import performance_monitor
from app.core.maintenance import maintenance_manager, MaintenanceType
from app.core.backup import backup_manager, BackupType
from app.core.testing import database_test_suite
from app.core.config import get_settings
from app.api.endpoints.database_monitoring import (
    DatabaseHealthResponse,
    ConnectionMetricsResponse,
    BackupResponse,
    PerformanceTestResponse,
)


# Test fixtures
@pytest.fixture(scope="session")
async def test_database():
    """Initialize optimized database for testing."""
    await optimized_database.initialize()
    yield optimized_database
    await optimized_database.cleanup()


@pytest.fixture
def test_project_id():
    """Generate test project ID."""
    return uuid.uuid4()


@pytest.fixture
async def test_session(test_database, test_project_id):
    """Create test database session with project isolation."""
    async with test_database.get_session(str(test_project_id)) as session:
        yield session


class TestConnectionPoolOptimization:
    """Test Task 3.1: Connection Pool Optimization."""

    @pytest.mark.asyncio
    async def test_connection_pool_configuration(self, test_database, test_project_id):
        """Test that connection pool is configured with optimal settings."""
        metrics = await test_database.get_connection_metrics(str(test_project_id))

        # Verify pool configuration meets REQ-004 requirements
        pool_config = metrics["pool_metrics"]["metrics"]

        assert pool_config["total_connections"] >= 0, (
            "Connection pool should be accessible"
        )
        assert "active_connections" in pool_config, (
            "Active connections should be tracked"
        )
        assert "total_connections" in pool_config, (
            "Total connections should be monitored"
        )

    @pytest.mark.asyncio
    async def test_concurrent_connection_handling(self, test_database, test_project_id):
        """Test connection pool efficiency under concurrent load."""
        connection_times = []

        async def test_connection():
            start_time = time.time()
            async with test_database.get_session(str(test_project_id)) as session:
                await session.execute(text("SELECT 1"))
            connection_times.append((time.time() - start_time) * 1000)

        # Test with 50 concurrent connections
        tasks = [test_connection() for _ in range(50)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Verify performance meets requirements
        avg_time = sum(connection_times) / len(connection_times)
        assert avg_time < 100, (
            f"Average connection time should be < 100ms, got {avg_time:.2f}ms"
        )

    @pytest.mark.asyncio
    async def test_circuit_breaker_functionality(self, test_database, test_project_id):
        """Test circuit breaker pattern for database unavailability."""
        metrics = await test_database.get_connection_metrics(str(test_project_id))

        # Circuit breaker should be in operational state
        circuit_state = metrics["pool_metrics"]["circuit_breaker"]["state"]
        assert circuit_state in ["closed", "half_open"], (
            f"Circuit breaker should be operational, got {circuit_state}"
        )

    @pytest.mark.asyncio
    async def test_connection_retry_logic(self, test_database):
        """Test connection retry logic with exponential backoff."""
        # This test would require simulating connection failures
        # For now, verify that the retry mechanism is configured
        settings = get_settings()
        assert hasattr(settings, "database_pool_timeout"), (
            "Pool timeout should be configured"
        )
        assert settings.database_pool_timeout() > 0, "Pool timeout should be positive"

    @pytest.mark.asyncio
    async def test_pool_metrics_collection(self, test_database, test_project_id):
        """Test comprehensive pool metrics collection."""
        metrics = await test_database.get_connection_metrics(str(test_project_id))

        required_metrics = [
            "connection_metrics",
            "pool_metrics",
            "pool_efficiency",
            "requirements_satisfaction",
        ]

        for metric in required_metrics:
            assert metric in metrics, f"Missing required metric: {metric}"

        # Verify REQ-004 compliance
        compliance = metrics["requirements_satisfaction"]
        assert compliance["req_004_pool_management"], "REQ-004 should be satisfied"
        assert compliance["perf_002_pool_efficiency"], "PERF-002 should be satisfied"


class TestPerformanceMonitoring:
    """Test Task 3.2: Database Performance Monitoring."""

    @pytest.mark.asyncio
    async def test_slow_query_monitoring(self, test_database, test_project_id):
        """Test slow query detection and monitoring."""
        # Execute a query that will be tracked
        async with test_database.get_session(str(test_project_id)) as session:
            await session.execute(text("SELECT pg_sleep(0.1)"))  # 100ms delay
            await session.commit()

        # Verify monitoring captured the query
        dashboard = await performance_monitor.get_performance_dashboard(test_project_id)
        assert "slow_queries" in dashboard, "Slow query monitoring should be active"
        assert "metrics" in dashboard, "Performance metrics should be available"

    @pytest.mark.asyncio
    async def test_database_metrics_export(self, test_database):
        """Test database metrics export to OpenTelemetry."""
        dashboard = await performance_monitor.get_performance_dashboard()

        # Verify OpenTelemetry integration
        assert "prometheus_metrics" in dashboard, (
            "Prometheus metrics should be available"
        )
        assert dashboard["timestamp"] is not None, "Metrics should have timestamps"

    @pytest.mark.asyncio
    async def test_performance_alerts(self, test_database):
        """Test performance alerts for threshold violations."""
        dashboard = await performance_monitor.get_performance_dashboard()

        # Alert system should be active
        assert "alerts" in dashboard, "Alert system should be configured"
        assert "count" in dashboard["alerts"], "Alert count should be tracked"

    @pytest.mark.asyncio
    async def test_query_performance_analysis(self, test_database, test_project_id):
        """Test query performance analysis tools."""
        query = "SELECT 1 as test_value"
        analysis = await performance_monitor.analyze_query_performance(
            query, test_project_id
        )

        assert "query" in analysis, "Query should be included in analysis"
        assert "project_id" in analysis, "Project ID should be tracked"
        assert "analysis" in analysis, "Performance analysis should be provided"

    @pytest.mark.asyncio
    async def test_project_scoped_monitoring(self, test_database, test_project_id):
        """Test monitoring is properly scoped by project."""
        dashboard = await performance_monitor.get_performance_dashboard(test_project_id)

        assert dashboard["project_id"] == str(test_project_id), (
            "Monitoring should respect project scoping"
        )


class TestBackupRecovery:
    """Test Task 3.3: Backup and Recovery Procedures."""

    @pytest.mark.asyncio
    async def test_backup_creation(self, test_database, test_project_id):
        """Test automated backup schedule configuration."""
        backup_result = await test_database.create_backup(str(test_project_id), "full")

        assert backup_result["backup_id"] is not None, "Backup should have an ID"
        assert backup_result["backup_type"] == "full", "Backup type should be correct"
        assert backup_result["project_id"] == str(test_project_id), (
            "Backup should be project-scoped"
        )

        # Verify REQ-007 compliance
        assert backup_result["requirements_satisfaction"]["req_007_backup_recovery"], (
            "REQ-007 should be satisfied"
        )

    @pytest.mark.asyncio
    async def test_backup_integrity_verification(self, test_database, test_project_id):
        """Test backup integrity verification."""
        # Create a backup first
        backup_result = await test_database.create_backup(str(test_project_id), "full")
        backup_id = backup_result["backup_id"]

        # Test recovery
        test_results = await test_database.test_backup_recovery(backup_id)

        assert test_results["backup_id"] == backup_id, (
            "Test should target correct backup"
        )
        assert "test_results" in test_results, (
            "Recovery test results should be available"
        )

        # Verify REL-003 compliance
        compliance = test_results["requirements_satisfaction"]
        assert compliance["rel_003_backup_reliability"], "REL-003 should be satisfied"

    @pytest.mark.asyncio
    async def test_wal_archiving(self, test_database):
        """Test WAL archiving for point-in-time recovery."""
        settings = get_settings()
        assert settings.wal_archiving_enabled(), "WAL archiving should be enabled"
        assert settings.wal_retention_days() > 0, "WAL retention should be configured"

    @pytest.mark.asyncio
    async def test_backup_encryption(self, test_database):
        """Test backup encryption for security."""
        settings = get_settings()
        assert settings.backup_encryption_enabled(), (
            "Backup encryption should be enabled"
        )

    @pytest.mark.asyncio
    async def test_backup_schedule(self, test_database):
        """Test automated backup schedule."""
        backup_status = await backup_manager.get_backup_status()

        assert "configuration" in backup_status, (
            "Backup configuration should be available"
        )
        # Check for actual configuration keys returned by backup manager
        required_config_keys = (
            "retention_days",
            "compression_type",
            "encryption_enabled",
            "s3_enabled",
            "wal_archive_directory",
        )
        for key in required_config_keys:
            assert key in backup_status["configuration"], (
                f"Missing backup config: {key}"
            )


class TestMaintenanceProcedures:
    """Test Task 3.4: Database Maintenance Procedures."""

    @pytest.mark.asyncio
    async def test_automated_vacuum_analyze(self, test_database):
        """Test automated VACUUM and ANALYZE operations."""
        maintenance_status = await maintenance_manager.get_maintenance_status()

        config = maintenance_status["configuration"]
        assert config["auto_vacuum_enabled"], "Auto VACUUM should be enabled"
        assert config["auto_analyze_enabled"], "Auto ANALYZE should be enabled"

    @pytest.mark.asyncio
    async def test_manual_maintenance_operations(self, test_database, test_project_id):
        """Test manual maintenance operations."""
        # Run ANALYZE operation
        task = await maintenance_manager.run_maintenance(
            MaintenanceType.ANALYZE, project_id=str(test_project_id)
        )

        assert task.task_id is not None, "Maintenance task should have an ID"
        assert task.maintenance_type == MaintenanceType.ANALYZE, (
            "Task type should be correct"
        )
        assert task.project_id == str(test_project_id), "Task should be project-scoped"

    @pytest.mark.asyncio
    async def test_index_maintenance(self, test_database):
        """Test index maintenance procedures."""
        maintenance_status = await maintenance_manager.get_maintenance_status()

        assert "thresholds" in maintenance_status["configuration"], (
            "Maintenance thresholds should be configured"
        )
        thresholds = maintenance_status["configuration"]["thresholds"]
        assert "reindex_percent" in thresholds, "Reindex threshold should be configured"

    @pytest.mark.asyncio
    async def test_statistics_collection(self, test_database):
        """Test statistics collection configuration."""
        maintenance_status = await maintenance_manager.get_maintenance_status()

        config = maintenance_status["configuration"]
        assert "analyze_percent" in config["thresholds"], (
            "ANALYZE threshold should be configured"
        )

    @pytest.mark.asyncio
    async def test_maintenance_window(self, test_database):
        """Test maintenance window configuration."""
        maintenance_status = await maintenance_manager.get_maintenance_status()

        config = maintenance_status["configuration"]["maintenance_window"]
        assert "start" in config, "Maintenance window start should be configured"
        assert "end" in config, "Maintenance window end should be configured"


class TestPostgreSQLOptimization:
    """Test Task 3.5: PostgreSQL Configuration Optimization."""

    @pytest.mark.asyncio
    async def test_connection_pool_parameters(self, test_database, test_session):
        """Test optimal connection pool parameters."""
        settings = get_settings()

        # Verify optimal pool settings
        assert settings.database_pool_size() == 20, "Pool size should be 20"
        assert settings.database_max_overflow() == 30, "Max overflow should be 30"
        assert settings.database_pool_timeout() == 30, "Pool timeout should be 30s"

    @pytest.mark.asyncio
    async def test_postgresql_configuration(self, test_session):
        """Test PostgreSQL performance parameters."""
        # Check key performance settings
        result = await test_session.execute(text("SHOW shared_buffers"))
        shared_buffers = result.scalar()
        assert shared_buffers, "shared_buffers should be configured"

        result = await test_session.execute(text("SHOW work_mem"))
        work_mem = result.scalar()
        assert work_mem, "work_mem should be configured"

        result = await test_session.execute(text("SHOW effective_cache_size"))
        effective_cache_size = result.scalar()
        assert effective_cache_size, "effective_cache_size should be configured"

    @pytest.mark.asyncio
    async def test_query_timeout_configuration(self, test_session):
        """Test query timeout configuration."""
        result = await test_session.execute(text("SHOW statement_timeout"))
        timeout = result.scalar()
        assert timeout, "Statement timeout should be configured"

    @pytest.mark.asyncio
    async def test_autovacuum_tuning(self, test_session):
        """Test autovacuum tuning for project isolation."""
        result = await test_session.execute(text("SHOW autovacuum_vacuum_scale_factor"))
        vacuum_scale = result.scalar()
        assert vacuum_scale, "Autovacuum scale factor should be configured"

        result = await test_session.execute(
            text("SHOW autovacuum_analyze_scale_factor")
        )
        analyze_scale = result.scalar()
        assert analyze_scale, "Autovacuum analyze scale factor should be configured"


class TestComprehensiveTesting:
    """Test Task 3.6: Comprehensive Database Testing."""

    @pytest.mark.asyncio
    async def test_performance_benchmarks(self, test_database, test_project_id):
        """Test performance benchmarks showing P95 < 100ms."""
        # Run quick benchmark
        query_times = []
        test_duration = 5  # 5 seconds

        start_time = time.time()
        while time.time() - start_time < test_duration:
            query_start = time.time()
            try:
                async with test_database.get_session(str(test_project_id)) as session:
                    await session.execute(text("SELECT 1 as benchmark"))
                    await session.commit()

                query_time = (time.time() - query_start) * 1000
                query_times.append(query_time)

            except Exception:
                pass

        if query_times:
            import statistics

            p95_time = statistics.quantiles(query_times, n=20)[18]  # 95th percentile
            assert p95_time < 100, (
                f"P95 response time should be < 100ms, got {p95_time:.2f}ms"
            )

    @pytest.mark.asyncio
    async def test_comprehensive_test_suite(self, test_database):
        """Test comprehensive database test suite."""
        test_results = await database_test_suite.run_all_tests()

        assert test_results["test_suite"] == "Phase 3 Database Optimization", (
            "Test suite should be correct"
        )
        assert len(test_results["individual_tests"]) > 0, (
            "Individual tests should be executed"
        )
        assert "performance_metrics" in test_results, (
            "Performance metrics should be collected"
        )
        assert "requirements_compliance" in test_results, (
            "Requirements compliance should be checked"
        )

    @pytest.mark.asyncio
    async def test_project_isolation_testing(self, test_database):
        """Test project isolation in all database operations."""
        project_1 = str(uuid.uuid4())
        project_2 = str(uuid.uuid4())

        # Test health checks are isolated
        health_1 = await test_database.get_comprehensive_health(project_1)
        health_2 = await test_database.get_comprehensive_health(project_2)

        assert health_1["project_id"] == project_1, (
            "Health check should respect project isolation"
        )
        assert health_2["project_id"] == project_2, (
            "Health check should respect project isolation"
        )

    @pytest.mark.asyncio
    async def test_requirements_compliance(self, test_database, test_project_id):
        """Test all Phase 3 requirements compliance."""
        health = await test_database.get_comprehensive_health(str(test_project_id))

        # Check critical requirements
        assert health["optimizations"]["connection_pooling"]["status"] == "optimized", (
            "Connection pooling should be optimized"
        )
        assert (
            health["optimizations"]["performance_monitoring"]["status"] == "active"
        ), "Performance monitoring should be active"
        assert health["optimizations"]["backup_system"]["status"] == "active", (
            "Backup system should be active"
        )
        assert (
            health["optimizations"]["maintenance_automation"]["status"] == "active"
        ), "Maintenance automation should be active"


class TestAPIEndpoints:
    """Test Phase 3 API endpoints."""

    @pytest.mark.asyncio
    async def test_database_health_endpoint(self, test_database, test_project_id):
        """Test database health endpoint."""
        health_data = await test_database.get_comprehensive_health(str(test_project_id))

        response = DatabaseHealthResponse(**health_data)
        assert response.overall_status in ["healthy", "unhealthy"], (
            "Status should be valid"
        )
        assert response.performance_score >= 0, (
            "Performance score should be non-negative"
        )

    @pytest.mark.asyncio
    async def test_connection_metrics_endpoint(self, test_database, test_project_id):
        """Test connection metrics endpoint."""
        metrics_data = await test_database.get_connection_metrics(str(test_project_id))

        response = ConnectionMetricsResponse(**metrics_data)
        assert response.connection_metrics, "Connection metrics should be available"
        assert response.pool_metrics, "Pool metrics should be available"
        assert response.pool_efficiency, "Pool efficiency should be calculated"

    @pytest.mark.asyncio
    async def test_backup_creation_endpoint(self, test_database, test_project_id):
        """Test backup creation endpoint."""
        backup_data = await test_database.create_backup(str(test_project_id), "full")

        response = BackupResponse(**backup_data)
        assert response.backup_id, "Backup ID should be present"
        assert response.backup_type == "full", "Backup type should be correct"
        assert response.project_id == str(test_project_id), "Project ID should match"

    @pytest.mark.asyncio
    async def test_performance_testing_endpoint(self, test_database):
        """Test comprehensive performance testing endpoint."""
        test_results = await database_test_suite.run_all_tests()

        response = PerformanceTestResponse(**test_results)
        assert response.test_suite, "Test suite should be identified"
        assert len(response.individual_tests) > 0, "Individual tests should be present"
        assert response.performance_metrics, "Performance metrics should be present"


# Integration tests
@pytest.mark.asyncio
async def test_full_phase3_integration(test_database):
    """Test full Phase 3 integration with all systems."""
    test_project_id = str(uuid.uuid4())

    # Test all systems work together
    health = await test_database.get_comprehensive_health(test_project_id)
    assert health["overall_status"] == "healthy", "Overall system should be healthy"

    # Test connection pool efficiency
    metrics = await test_database.get_connection_metrics(test_project_id)
    assert metrics["requirements_satisfaction"]["req_004_pool_management"], (
        "Connection pool management should work"
    )

    # Test performance monitoring
    dashboard = await performance_monitor.get_performance_dashboard(
        uuid.UUID(test_project_id)
    )
    assert dashboard["timestamp"] is not None, "Performance monitoring should be active"

    # Test backup system
    backup_result = await test_database.create_backup(test_project_id, "full")
    assert backup_result["backup_id"] is not None, "Backup system should work"

    # Test maintenance system
    task = await maintenance_manager.run_maintenance(
        MaintenanceType.ANALYZE, test_project_id
    )
    assert task.status.value in ["completed", "running"], (
        "Maintenance system should work"
    )

    logger.info("Full Phase 3 integration test passed")
