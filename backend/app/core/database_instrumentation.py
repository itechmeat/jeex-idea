"""
JEEX Idea Database Instrumentation for OpenTelemetry

Enhanced database instrumentation with comprehensive monitoring,
slow query detection, connection pool metrics, and project isolation.

Implements Task 2.1 requirements:
- SQLAlchemy auto-instrumentation enhancement
- Database spans with query type, table name, execution time
- Connection pool metrics (active, idle connections)
- Slow query detection for queries > 1 second
- Project_id inclusion in all database span attributes
"""

import time
import asyncio
import logging
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
from uuid import UUID
from dataclasses import dataclass

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.sql import ClauseElement
from opentelemetry import trace
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
import structlog

from .config import get_settings
from .telemetry import get_tracer, add_span_attribute

logger = structlog.get_logger()


@dataclass
class QueryMetrics:
    """Metrics for database query performance tracking."""

    query_type: str
    table_name: Optional[str]
    execution_time_ms: float
    row_count: Optional[int]
    project_id: UUID
    timestamp: float

    @property
    def is_slow_query(self) -> bool:
        """Check if query is slow (> 1 second)."""
        return self.execution_time_ms > 1000.0


class DatabaseInstrumentor:
    """
    Enhanced database instrumentation for OpenTelemetry.

    Provides comprehensive database monitoring with:
    - Query-level tracing with detailed attributes
    - Slow query detection and logging
    - Connection pool metrics tracking
    - Project-based span isolation
    """

    def __init__(self):
        self.settings = get_settings()
        self.tracer = get_tracer(__name__, "0.1.0")
        self._instrumented = False

        # Metrics tracking
        self._connection_metrics = {
            "active_connections": 0,
            "idle_connections": 0,
            "total_connections": 0,
            "pool_hit_rate": 0.0,
        }

        # Slow query tracking
        self._slow_queries: List[QueryMetrics] = []
        self._max_slow_queries = 1000  # Keep last 1000 slow queries

        logger.info("Database instrumentor initialized")

    async def instrument_database(self, engine: AsyncEngine) -> None:
        """
        Instrument database engine with enhanced OpenTelemetry monitoring.

        Args:
            engine: SQLAlchemy async engine to instrument
        """
        if self._instrumented:
            logger.warning("Database already instrumented")
            return

        try:
            # Enhanced SQLAlchemy instrumentation with custom hooks
            await self._setup_enhanced_instrumentation(engine)

            # Setup connection pool monitoring
            self._setup_pool_monitoring(engine)

            # Setup query performance monitoring
            self._setup_query_monitoring(engine)

            self._instrumented = True
            logger.info("Database instrumentation completed successfully")

        except Exception as e:
            logger.error("Failed to instrument database", error=str(e))
            raise

    async def _setup_enhanced_instrumentation(self, engine: AsyncEngine) -> None:
        """Setup enhanced SQLAlchemy instrumentation with custom attributes."""

        def before_cursor_execute(
            conn, cursor, statement, parameters, context, executemany
        ):
            """Capture query start time and extract metadata."""
            context._query_start_time = time.perf_counter()
            context._statement = statement
            context._parameters = parameters

            # Extract table name and query type for enhanced monitoring
            query_info = self._parse_query(statement)
            context._query_type = query_info.get("query_type", "unknown")
            context._table_name = query_info.get("table_name")

            # Start OpenTelemetry span for detailed query tracking
            span_name = f"db.{context._query_type}"
            if context._table_name:
                span_name += f".{context._table_name}"

            span = self.tracer.start_as_current_span(span_name)
            context._otel_span = span

            # Set standard database attributes
            span.set_attribute(SpanAttributes.DB_SYSTEM, "postgresql")
            span.set_attribute(SpanAttributes.DB_STATEMENT, statement)
            span.set_attribute("db.query_type", context._query_type)

            if context._table_name:
                span.set_attribute("db.table_name", context._table_name)

            # Add project context if available
            project_id = self._extract_project_id_from_context(context)
            if project_id:
                span.set_attribute("jeex.project_id", str(project_id))

            logger.debug(
                "Database query started",
                query_type=context._query_type,
                table_name=context._table_name,
            )

        def after_cursor_execute(
            conn, cursor, statement, parameters, context, executemany
        ):
            """Capture query completion and update metrics."""
            if not hasattr(context, "_query_start_time"):
                return

            execution_time = (time.perf_counter() - context._query_start_time) * 1000
            query_type = getattr(context, "_query_type", "unknown")
            table_name = getattr(context, "_table_name", None)
            span = getattr(context, "_otel_span", None)

            # Update span with performance metrics
            if span and span.is_recording():
                span.set_attribute(SpanAttributes.DB_DURATION_MS, execution_time)

                # Add row count if available
                if hasattr(cursor, "rowcount") and cursor.rowcount >= 0:
                    span.set_attribute("db.row_count", cursor.rowcount)

                # Mark as slow query if applicable
                if execution_time > 1000.0:
                    span.set_attribute("db.slow_query", True)
                    logger.warning(
                        "Slow query detected",
                        query_type=query_type,
                        table_name=table_name,
                        execution_time_ms=execution_time,
                    )

                span.end()

            # Track slow queries for analysis
            project_id = self._extract_project_id_from_context(context) or "unknown"
            if execution_time > 1000.0:
                self._record_slow_query(
                    QueryMetrics(
                        query_type=query_type,
                        table_name=table_name,
                        execution_time_ms=execution_time,
                        row_count=getattr(cursor, "rowcount", None),
                        project_id=str(project_id),
                        timestamp=time.time(),
                    )
                )

            logger.debug(
                "Database query completed",
                query_type=query_type,
                table_name=table_name,
                execution_time_ms=execution_time,
            )

        def handle_error(context, exception):
            """Handle database errors and add to span."""
            span = getattr(context, "_otel_span", None)
            if span and span.is_recording():
                span.set_attribute("db.error", True)
                span.set_attribute("db.error_message", str(exception))
                span.record_exception(exception)
                span.end()

            logger.error(
                "Database query error",
                error=str(exception),
                query_type=getattr(context, "_query_type", "unknown"),
                table_name=getattr(context, "_table_name", None),
            )

        # Register enhanced event listeners
        event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
        event.listen(engine.sync_engine, "after_cursor_execute", after_cursor_execute)
        event.listen(engine.sync_engine, "handle_error", handle_error)

        # Enable standard SQLAlchemy instrumentation
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            enable_commenter=True,
            enable_metric=True,
        )

        logger.info("Enhanced SQLAlchemy instrumentation configured")

    def _setup_pool_monitoring(self, engine: AsyncEngine) -> None:
        """Setup connection pool metrics monitoring."""

        @event.listens_for(engine.pool, "connect")
        def receive_connect(dbapi_connection, connection_record):
            """Track new connections."""
            self._connection_metrics["total_connections"] += 1
            self._connection_metrics["active_connections"] += 1

            # Add connection info to current span
            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("db.connection.created", True)

        @event.listens_for(engine.pool, "checkout")
        def receive_checkout(dbapi_connection, connection_record, connection_proxy):
            """Track connection checkout."""
            self._connection_metrics["active_connections"] += 1
            self._connection_metrics["idle_connections"] -= 1

            # Add checkout metrics to span
            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("db.connection.checkout", True)
                span.set_attribute(
                    "db.pool.active", self._connection_metrics["active_connections"]
                )

        @event.listens_for(engine.pool, "checkin")
        def receive_checkin(dbapi_connection, connection_record):
            """Track connection checkin."""
            self._connection_metrics["active_connections"] -= 1
            self._connection_metrics["idle_connections"] += 1

            # Add checkin metrics to span
            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("db.connection.checkin", True)
                span.set_attribute(
                    "db.pool.active", self._connection_metrics["active_connections"]
                )

        logger.info("Connection pool monitoring configured")

    def _setup_query_monitoring(self, engine: AsyncEngine) -> None:
        """Setup query performance monitoring and metrics collection."""

        @event.listens_for(engine.sync_engine, "before_execute")
        def receive_before_execute(
            conn, clauseelement, multiparams, params, execution_options
        ):
            """Monitor query execution start."""
            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("db.execute.start", True)

                # Add query type based on clause element
                if isinstance(clauseelement, ClauseElement):
                    query_type = clauseelement.__class__.__name__.lower()
                    span.set_attribute("db.query.clause_type", query_type)

        @event.listens_for(engine.sync_engine, "after_execute")
        def receive_after_execute(
            conn, clauseelement, multiparams, params, execution_options, result
        ):
            """Monitor query execution completion."""
            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("db.execute.complete", True)

                # Add result count if available
                if hasattr(result, "rowcount") and result.rowcount >= 0:
                    span.set_attribute("db.result.rows", result.rowcount)

        logger.info("Query performance monitoring configured")

    def _parse_query(self, statement: str) -> Dict[str, Any]:
        """
        Parse SQL statement to extract query type and table name.

        Args:
            statement: SQL statement to parse

        Returns:
            Dictionary with query_type and table_name
        """
        try:
            # Simple SQL parsing for common patterns
            statement_upper = statement.strip().upper()

            # Extract query type
            if statement_upper.startswith(
                ("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER")
            ):
                query_type = statement_upper.split()[0].lower()
            else:
                query_type = "unknown"

            # Extract table name for basic queries
            table_name = None
            try:
                if query_type == "select" and "FROM" in statement_upper:
                    # Extract table name after FROM
                    from_part = statement_upper.split("FROM")[1].strip()
                    table_name = from_part.split()[0].strip('"[]')
                elif query_type in ["insert", "update", "delete"]:
                    # Extract table name from first part
                    first_part = statement.strip().split()[1:]
                    for token in first_part:
                        if not token.upper() in [
                            "INTO",
                            "TABLE",
                            "FROM",
                            "WHERE",
                            "VALUES",
                            "SET",
                        ]:
                            table_name = token.strip('"[]')
                            break
            except Exception:
                # Table name extraction failed, continue without it
                pass

            return {"query_type": query_type, "table_name": table_name}

        except Exception as e:
            logger.debug("Failed to parse query", error=str(e))
            return {"query_type": "unknown", "table_name": None}

    def _extract_project_id_from_context(self, context) -> Optional[UUID]:
        """
        Extract project ID from execution context.

        Args:
            context: SQLAlchemy execution context

        Returns:
            Project ID if available, None otherwise
        """
        try:
            # Try to get project_id from execution options
            if hasattr(context, "execution_options"):
                project_id = context.execution_options.get("project_id")
                if project_id:
                    return (
                        UUID(str(project_id))
                        if isinstance(project_id, str)
                        else project_id
                    )

            # Try to get from current OpenTelemetry span
            span = trace.get_current_span()
            if span and span.is_recording():
                project_id = span.attributes.get("jeex.project_id")
                if project_id:
                    return UUID(str(project_id))

            return None

        except Exception:
            return None

    def _record_slow_query(self, query_metrics: QueryMetrics) -> None:
        """
        Record slow query for analysis and alerting.

        Args:
            query_metrics: Query metrics to record
        """
        self._slow_queries.append(query_metrics)

        # Keep only the most recent slow queries
        if len(self._slow_queries) > self._max_slow_queries:
            self._slow_queries = self._slow_queries[-self._max_slow_queries :]

        # Log slow query for immediate visibility
        logger.warning(
            "Slow query recorded",
            query_type=query_metrics.query_type,
            table_name=query_metrics.table_name,
            execution_time_ms=query_metrics.execution_time_ms,
            project_id=query_metrics.project_id,
            row_count=query_metrics.row_count,
        )

        # Add slow query metric to current span
        add_span_attribute("db.slow_query_recorded", True)
        add_span_attribute("db.slow_query_time_ms", query_metrics.execution_time_ms)

    def get_connection_metrics(self) -> Dict[str, Any]:
        """
        Get current connection pool metrics.

        Returns:
            Dictionary with connection pool metrics

        TODO: MEDIUM PRIORITY - Add defensive checks for empty duration lists to prevent division by zero
        """
        return {
            "connection_metrics": self._connection_metrics.copy(),
            "slow_queries_count": len(self._slow_queries),
            "last_slow_queries": [
                {
                    "query_type": sq.query_type,
                    "table_name": sq.table_name,
                    "execution_time_ms": sq.execution_time_ms,
                    "project_id": sq.project_id,
                    "timestamp": sq.timestamp,
                }
                for sq in self._slow_queries[-10:]  # Last 10 slow queries
            ],
        }

    def get_slow_queries(
        self, project_id: UUID, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get slow queries for analysis.

        Args:
            project_id: Required project ID to filter by
            limit: Maximum number of queries to return

        Returns:
            List of slow query metrics

        Raises:
            ValueError: If project_id is None
        """
        if project_id is None:
            raise ValueError("project_id is required for slow queries retrieval")

        queries = self._slow_queries

        # Filter by project ID (required)
        queries = [sq for sq in queries if sq.project_id == project_id]

        # Return most recent queries up to limit
        recent_queries = sorted(queries, key=lambda x: x.timestamp, reverse=True)[
            :limit
        ]

        return [
            {
                "query_type": sq.query_type,
                "table_name": sq.table_name,
                "execution_time_ms": sq.execution_time_ms,
                "row_count": sq.row_count,
                "project_id": str(sq.project_id),
                "timestamp": sq.timestamp,
                "is_slow_query": sq.is_slow_query,
            }
            for sq in recent_queries
        ]

    def reset_metrics(self) -> None:
        """Reset all collected metrics."""
        self._slow_queries.clear()
        logger.info("Database instrumentation metrics reset")


# Global database instrumentor instance
database_instrumentor = DatabaseInstrumentor()


async def instrument_database_engine(engine: AsyncEngine) -> None:
    """
    Instrument database engine with enhanced OpenTelemetry monitoring.

    Args:
        engine: SQLAlchemy async engine to instrument
    """
    await database_instrumentor.instrument_database(engine)


def get_database_instrumentation_metrics() -> Dict[str, Any]:
    """
    Get database instrumentation metrics.

    Returns:
        Dictionary with instrumentation metrics
    """
    return database_instrumentor.get_connection_metrics()


def get_slow_queries(project_id: UUID, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get slow queries for analysis.

    Args:
        project_id: Required project ID to filter by
        limit: Maximum number of queries to return

    Returns:
        List of slow query metrics

    Raises:
        ValueError: If project_id is None
    """
    return database_instrumentor.get_slow_queries(project_id, limit)


@asynccontextmanager
async def traced_database_session(session: AsyncSession, project_id: UUID):
    """
    Context manager for traced database session with project isolation.

    Args:
        session: Database session to trace
        project_id: Project ID for span attribution

    Yields:
        Database session with enhanced tracing
    """
    tracer = get_tracer(__name__)

    with tracer.start_as_current_span("database.session") as span:
        # Add project context to span
        span.set_attribute("jeex.project_id", str(project_id))
        span.set_attribute("db.session.project_isolated", True)

        # Add session-level metrics
        start_time = time.perf_counter()

        try:
            yield session

            # Record session success metrics
            duration_ms = (time.perf_counter() - start_time) * 1000
            span.set_attribute("db.session.duration_ms", duration_ms)
            span.set_attribute("db.session.success", True)

        except Exception as e:
            # Record session error metrics
            duration_ms = (time.perf_counter() - start_time) * 1000
            span.set_attribute("db.session.duration_ms", duration_ms)
            span.set_attribute("db.session.success", False)
            span.set_attribute("db.session.error", str(e))
            span.record_exception(e)
            raise


# Export key functions and classes
__all__ = [
    "DatabaseInstrumentor",
    "database_instrumentor",
    "QueryMetrics",
    "instrument_database_engine",
    "get_database_instrumentation_metrics",
    "get_slow_queries",
    "traced_database_session",
]
