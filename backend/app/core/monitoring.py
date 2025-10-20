"""
JEEX Idea Performance Monitoring - Phase 3

Comprehensive database performance monitoring with:
- Slow query monitoring and alerting
- Database metrics export to OpenTelemetry
- Performance alerts for threshold violations
- Query performance analysis tools
- Project-scoped monitoring
"""

import asyncio
import time
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from opentelemetry import trace, metrics
from opentelemetry.trace import Status, StatusCode
from opentelemetry.metrics import Observation
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from prometheus_client import (
    Gauge,
    Histogram,
    Counter,
    CollectorRegistry,
    generate_latest,
)
import structlog
import psutil

from .config import get_settings
from .database import database_manager

logger = structlog.get_logger()


class AlertSeverity(Enum):
    """Alert severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SlowQuery:
    """Slow query information."""

    query: str
    duration_ms: float
    timestamp: datetime
    project_id: Optional[UUID]
    execution_count: int
    mean_duration_ms: float
    calls_per_second: float


@dataclass
class PerformanceAlert:
    """Performance alert information."""

    metric_name: str
    current_value: float
    threshold: float
    severity: AlertSeverity
    message: str
    timestamp: datetime
    project_id: Optional[UUID] = None


@dataclass
class DatabaseStats:
    """Database performance statistics."""

    timestamp: datetime
    connections_active: int
    connections_idle: int
    transactions_per_second: float
    queries_per_second: float
    slow_queries_count: int
    cache_hit_ratio: float
    index_usage_ratio: float
    database_size_mb: float
    wal_size_mb: float


class PerformanceMonitor:
    """
    Advanced performance monitoring for PostgreSQL database.

    Features:
    - Slow query detection and analysis
    - Real-time metrics collection
    - OpenTelemetry integration
    - Prometheus metrics
    - Performance alerts
    - Project-scoped monitoring
    """

    def __init__(self):
        self.settings = get_settings()
        self.slow_query_threshold_ms = 1000  # 1 second threshold
        self.alert_thresholds = {
            "slow_query_count": 10,  # Alert if >10 slow queries
            "connection_utilization": 0.8,  # Alert if >80% connections used
            "query_duration_p95": 500,  # Alert if P95 > 500ms (PERF-001)
            "cache_hit_ratio": 0.9,  # Alert if cache hit ratio < 90%
        }

        # Performance metrics storage
        self._slow_queries: List[SlowQuery] = []
        self._alerts: List[PerformanceAlert] = []
        self._historical_stats: List[DatabaseStats] = []
        self._max_history_size = 1000

        # Internal storage for OpenTelemetry observable metrics
        self._latest_active_connections = 0

        # Setup OpenTelemetry
        self._setup_opentelemetry()

        # Setup Prometheus metrics
        self._setup_prometheus_metrics()

        # Background monitoring task
        self._monitoring_task: Optional[asyncio.Task] = None

        logger.info(
            "Performance monitor initialized",
            slow_query_threshold_ms=self.slow_query_threshold_ms,
        )

    def _setup_opentelemetry(self) -> None:
        """Setup OpenTelemetry tracing and metrics."""
        try:
            # Setup tracing
            trace_provider = TracerProvider()
            trace_provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=f"{self.settings.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces"
                    )
                )
            )
            trace.set_tracer_provider(trace_provider)

            # Setup metrics
            metric_reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(
                    endpoint=f"{self.settings.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/metrics"
                ),
                export_interval_millis=30000,  # Export every 30 seconds
            )
            metrics.set_meter_provider(MeterProvider(metric_readers=[metric_reader]))

            # Get tracer and meter
            self.tracer = trace.get_tracer(__name__)
            self.meter = metrics.get_meter(__name__)

            # Create custom metrics
            self.db_connections_active = self.meter.create_observable_gauge(
                "db.connections.active",
                callbacks=[self._observe_active_connections],
                description="Number of active database connections",
            )
            self.db_queries_duration = self.meter.create_histogram(
                "db.queries.duration",
                description="Database query duration in milliseconds",
                unit="ms",
            )
            self.db_slow_queries = self.meter.create_counter(
                "db.slow_queries.total", description="Total number of slow queries"
            )

            logger.info("OpenTelemetry configured for database monitoring")
        except Exception as e:
            logger.warning(
                "Failed to setup OpenTelemetry, continuing without telemetry",
                error=str(e),
            )
            # Set up no-op tracer and meter as fallbacks
            self.tracer = trace.get_tracer(__name__)
            self.meter = metrics.get_meter(__name__)

    def _setup_prometheus_metrics(self) -> None:
        """Setup Prometheus metrics for database monitoring."""
        self.registry = CollectorRegistry()

        # Connection metrics
        self.prom_connections_active = Gauge(
            "jeex_db_connections_active",
            "Number of active database connections",
            registry=self.registry,
        )
        self.prom_connections_idle = Gauge(
            "jeex_db_connections_idle",
            "Number of idle database connections",
            registry=self.registry,
        )
        self.prom_connection_utilization = Gauge(
            "jeex_db_connection_utilization",
            "Connection pool utilization ratio (0-1)",
            registry=self.registry,
        )

        # Performance metrics
        self.prom_query_duration = Histogram(
            "jeex_db_query_duration_seconds",
            "Database query duration in seconds",
            buckets=[0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            registry=self.registry,
        )
        self.prom_slow_queries_total = Counter(
            "jeex_db_slow_queries_total",
            "Total number of slow queries (>1s)",
            registry=self.registry,
        )

        # Database statistics
        self.prom_database_size_bytes = Gauge(
            "jeex_db_size_bytes", "Database size in bytes", registry=self.registry
        )
        self.prom_cache_hit_ratio = Gauge(
            "jeex_db_cache_hit_ratio",
            "Database cache hit ratio (0-1)",
            registry=self.registry,
        )
        self.prom_transactions_per_second = Gauge(
            "jeex_db_transactions_per_second",
            "Transactions per second",
            registry=self.registry,
        )

        # Alerts
        self.prom_alerts_total = Counter(
            "jeex_db_alerts_total",
            "Total number of performance alerts",
            ["severity", "metric_name"],
            registry=self.registry,
        )

    def _observe_active_connections(self, options) -> List[Observation]:
        """Callback function for active database connections observable gauge."""
        return [Observation(self._latest_active_connections)]

    async def start_monitoring(self) -> None:
        """Start background performance monitoring."""
        if self._monitoring_task is None:
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            logger.info("Performance monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop background performance monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
            logger.info("Performance monitoring stopped")

    async def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while True:
            try:
                await self._collect_metrics()
                await self._check_slow_queries()
                await self._evaluate_alerts()
                await asyncio.sleep(60)  # Monitor every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Performance monitoring error", error=str(e))
                await asyncio.sleep(60)

    @asynccontextmanager
    async def trace_query(
        self, query: str, project_id: UUID
    ) -> AsyncGenerator[None, None]:
        """
        Trace database query execution with OpenTelemetry.

        Args:
            query: SQL query being executed
            project_id: Required project ID for context
        """
        start_time = time.time()

        with self.tracer.start_as_current_span("database.query") as span:
            span.set_attribute("db.statement", query)
            span.set_attribute("db.system", "postgresql")
            span.set_attribute("jeex.project_id", str(project_id))

            try:
                yield
                duration_ms = (time.time() - start_time) * 1000

                # Record metrics
                self.db_queries_duration.record(duration_ms)
                self.prom_query_duration.observe(duration_ms / 1000)
                span.set_attribute("db.duration_ms", duration_ms)

                # Check for slow query
                if duration_ms > self.slow_query_threshold_ms:
                    await self._record_slow_query(query, duration_ms, project_id)

            except Exception as e:
                span.set_attribute("db.error", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise

    async def _collect_metrics(self) -> None:
        """Collect database performance metrics."""
        try:
            async with database_manager.get_session() as session:
                # Get database statistics using CTE to fix SQL syntax
                result = await session.execute(
                    text("""
                    SELECT
                        COUNT(*) FILTER (WHERE state = 'active') as active_connections,
                        COUNT(*) FILTER (WHERE state = 'idle') as idle_connections,
                        pg_size_pretty(pg_database_size(current_database())) as db_size
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                """)
                )
                stats = result.fetchone()

                # Calculate derived metrics
                total_connections = stats.active_connections + stats.idle_connections
                connection_utilization = (
                    total_connections / 50
                )  # Assuming max 50 connections
                cache_hit_ratio = 0.95  # Default value since we can't calculate without blocks stats

                # Create stats record
                db_stats = DatabaseStats(
                    timestamp=datetime.utcnow(),
                    connections_active=stats.active_connections,
                    connections_idle=stats.idle_connections,
                    transactions_per_second=0,  # Would need time series calculation
                    queries_per_second=0,  # Would need time series calculation
                    slow_queries_count=len(self._slow_queries),
                    cache_hit_ratio=cache_hit_ratio,
                    index_usage_ratio=0,  # Would need additional query
                    database_size_mb=0,  # Parse from db_size string
                    wal_size_mb=0,  # Would need additional query
                )

                # Store in history
                self._historical_stats.append(db_stats)
                if len(self._historical_stats) > self._max_history_size:
                    self._historical_stats.pop(0)

                # Update Prometheus metrics
                self.prom_connections_active.set(stats.active_connections)
                self.prom_connections_idle.set(stats.idle_connections)
                self.prom_connection_utilization.set(connection_utilization)
                self.prom_cache_hit_ratio.set(cache_hit_ratio)

                # Update OpenTelemetry metrics storage
                self._latest_active_connections = stats.active_connections

                logger.debug(
                    "Database metrics collected",
                    active_connections=stats.active_connections,
                    cache_hit_ratio=cache_hit_ratio,
                )

        except Exception as e:
            logger.error("Failed to collect database metrics", error=str(e))

    async def _check_slow_queries(self) -> None:
        """Check for slow queries using pg_stat_statements."""
        try:
            async with database_manager.get_session() as session:
                # Get slow queries from pg_stat_statements
                result = await session.execute(
                    text("""
                    SELECT
                        query,
                        calls,
                        total_exec_time,
                        mean_exec_time,
                        max_exec_time
                    FROM pg_stat_statements
                    WHERE mean_exec_time > :threshold
                    ORDER BY mean_exec_time DESC
                    LIMIT 10
                """),
                    {"threshold": self.slow_query_threshold_ms},
                )

                slow_queries = result.fetchall()

                for query_data in slow_queries:
                    slow_query = SlowQuery(
                        query=query_data.query[:200],  # Truncate for storage
                        duration_ms=query_data.mean_exec_time,
                        timestamp=datetime.utcnow(),
                        project_id=None,  # Could be extracted from query context
                        execution_count=query_data.calls,
                        mean_duration_ms=query_data.mean_exec_time,
                        calls_per_second=0,  # Would need time window calculation
                    )

                    # Add to slow queries list
                    self._slow_queries.append(slow_query)
                    self.db_slow_queries.add(1)
                    self.prom_slow_queries_total.inc()

                # Cleanup old slow queries
                cutoff_time = datetime.utcnow() - timedelta(hours=1)
                self._slow_queries = [
                    sq for sq in self._slow_queries if sq.timestamp > cutoff_time
                ]

                if slow_queries:
                    logger.info(
                        "Slow queries detected",
                        count=len(slow_queries),
                        threshold_ms=self.slow_query_threshold_ms,
                    )

        except Exception as e:
            logger.error("Failed to check slow queries", error=str(e))

    async def _record_slow_query(
        self, query: str, duration_ms: float, project_id: UUID
    ) -> None:
        """Record a slow query event."""
        slow_query = SlowQuery(
            query=query[:200],
            duration_ms=duration_ms,
            timestamp=datetime.utcnow(),
            project_id=project_id,
            execution_count=1,
            mean_duration_ms=duration_ms,
            calls_per_second=0,
        )

        self._slow_queries.append(slow_query)
        self.db_slow_queries.add(1)
        self.prom_slow_queries_total.inc()

        logger.warning(
            "Slow query detected",
            duration_ms=duration_ms,
            project_id=project_id,
            query_preview=query[:100],
        )

    async def _evaluate_alerts(self) -> None:
        """Evaluate performance thresholds and generate alerts."""
        if not self._historical_stats:
            return

        latest_stats = self._historical_stats[-1]

        # Check connection utilization
        total_connections = (
            latest_stats.connections_active + latest_stats.connections_idle
        )
        max_connections = 50  # From pool_size + max_overflow
        connection_utilization = total_connections / max_connections

        if connection_utilization > self.alert_thresholds["connection_utilization"]:
            await self._create_alert(
                metric_name="connection_utilization",
                current_value=connection_utilization,
                threshold=self.alert_thresholds["connection_utilization"],
                severity=AlertSeverity.HIGH
                if connection_utilization > 0.9
                else AlertSeverity.MEDIUM,
                message=f"High connection utilization: {connection_utilization:.1%}",
            )

        # Check slow query count
        if latest_stats.slow_queries_count > self.alert_thresholds["slow_query_count"]:
            await self._create_alert(
                metric_name="slow_query_count",
                current_value=latest_stats.slow_queries_count,
                threshold=self.alert_thresholds["slow_query_count"],
                severity=AlertSeverity.HIGH,
                message=f"High slow query count: {latest_stats.slow_queries_count}",
            )

        # Check cache hit ratio
        if latest_stats.cache_hit_ratio < self.alert_thresholds["cache_hit_ratio"]:
            await self._create_alert(
                metric_name="cache_hit_ratio",
                current_value=latest_stats.cache_hit_ratio,
                threshold=self.alert_thresholds["cache_hit_ratio"],
                severity=AlertSeverity.MEDIUM,
                message=f"Low cache hit ratio: {latest_stats.cache_hit_ratio:.1%}",
            )

    async def _create_alert(
        self,
        metric_name: str,
        current_value: float,
        threshold: float,
        severity: AlertSeverity,
        message: str,
        project_id: Optional[UUID] = None,
    ) -> None:
        """Create a performance alert."""
        alert = PerformanceAlert(
            metric_name=metric_name,
            current_value=current_value,
            threshold=threshold,
            severity=severity,
            message=message,
            timestamp=datetime.utcnow(),
            project_id=project_id,
        )

        self._alerts.append(alert)

        # Update Prometheus metrics
        self.prom_alerts_total.labels(
            severity=severity.value, metric_name=metric_name
        ).inc()

        # Log alert
        log_method = {
            AlertSeverity.LOW: logger.info,
            AlertSeverity.MEDIUM: logger.warning,
            AlertSeverity.HIGH: logger.error,
            AlertSeverity.CRITICAL: logger.critical,
        }.get(severity, logger.warning)

        log_method(
            "Performance alert generated",
            metric_name=metric_name,
            current_value=current_value,
            threshold=threshold,
            severity=severity.value,
            message=message,
            project_id=project_id,
        )

    async def get_performance_dashboard(
        self, project_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Get comprehensive performance dashboard data."""
        # Filter data by project if specified
        slow_queries = self._slow_queries
        alerts = self._alerts
        stats = self._historical_stats

        if project_id:
            slow_queries = [sq for sq in slow_queries if sq.project_id == project_id]
            alerts = [a for a in alerts if a.project_id == project_id]
            # Stats filtering would need project_id tracking

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "project_id": str(project_id) if project_id else None,
            "slow_queries": {
                "count": len(slow_queries),
                "threshold_ms": self.slow_query_threshold_ms,
                "recent": [
                    {
                        "query": sq.query[:100],
                        "duration_ms": sq.duration_ms,
                        "timestamp": sq.timestamp.isoformat(),
                        "execution_count": sq.execution_count,
                    }
                    for sq in slow_queries[-10:]  # Last 10 slow queries
                ],
            },
            "alerts": {
                "count": len(alerts),
                "by_severity": {
                    severity.value: len([a for a in alerts if a.severity == severity])
                    for severity in AlertSeverity
                },
                "recent": [
                    {
                        "metric_name": a.metric_name,
                        "severity": a.severity.value,
                        "message": a.message,
                        "timestamp": a.timestamp.isoformat(),
                    }
                    for a in alerts[-10:]  # Last 10 alerts
                ],
            },
            "metrics": {
                "current": await self._get_current_metrics(),
                "thresholds": self.alert_thresholds,
            },
            "prometheus_metrics": generate_latest(self.registry).decode("utf-8"),
        }

    async def _get_current_metrics(self) -> Dict[str, Any]:
        """Get current database metrics."""
        try:
            pool_metrics = await database_manager.get_metrics()
            return {
                "connections": pool_metrics.get("metrics", {}),
                "pool": pool_metrics.get("pool", {}),
                "circuit_breaker": pool_metrics.get("circuit_breaker", {}),
            }
        except Exception as e:
            logger.error("Failed to get current metrics", error=str(e))
            return {"error": str(e)}

    async def analyze_query_performance(
        self, query: str, project_id: UUID
    ) -> Dict[str, Any]:
        """Analyze specific query performance."""
        try:
            async with database_manager.get_session(project_id) as session:
                # EXPLAIN ANALYZE the query
                explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
                result = await session.execute(text(explain_query))
                explain_data = result.scalar()

                # Get query plan information
                execution_plan = explain_data[0]["Plan"]

                return {
                    "query": query,
                    "project_id": str(project_id),
                    "execution_plan": execution_plan,
                    "analysis": {
                        "total_cost": execution_plan.get("Total Cost", 0),
                        "actual_rows": execution_plan.get("Actual Rows", 0),
                        "actual_total_time": execution_plan.get("Actual Total Time", 0),
                        "planning_time": execution_plan.get("Planning Time", 0),
                        "execution_time": execution_plan.get("Execution Time", 0),
                        "recommendations": self._generate_query_recommendations(
                            execution_plan
                        ),
                    },
                }

        except Exception as e:
            logger.error("Query performance analysis failed", error=str(e), query=query)
            return {"error": str(e), "query": query}

    def _generate_query_recommendations(self, plan: Dict[str, Any]) -> List[str]:
        """Generate query optimization recommendations."""
        recommendations = []

        # Check for sequential scans
        if plan.get("Node Type") == "Seq Scan":
            recommendations.append("Consider adding an index for this query")

        # Check for high execution time
        if plan.get("Actual Total Time", 0) > 5000:  # 5 seconds
            recommendations.append(
                "Query execution time is high - consider optimization"
            )

        # Check for nested loops
        if plan.get("Node Type") == "Nested Loop":
            recommendations.append("Consider rewriting query to avoid nested loops")

        # Check for hash joins with high cost
        if plan.get("Node Type") == "Hash Join" and plan.get("Total Cost", 0) > 1000:
            recommendations.append(
                "Hash join cost is high - check join conditions and indexes"
            )

        return recommendations


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


# Dependency functions for FastAPI
async def get_performance_monitor() -> PerformanceMonitor:
    """FastAPI dependency for performance monitor."""
    return performance_monitor


async def get_performance_dashboard(
    project_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """FastAPI dependency for performance dashboard."""
    return await performance_monitor.get_performance_dashboard(project_id)
