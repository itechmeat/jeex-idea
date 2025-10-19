"""
JEEX Idea Database Configuration - Phase 3 Optimization

Advanced database connection management with:
- Optimized connection pooling (pool_size=20, max_overflow=30)
- Connection retry logic with exponential backoff
- Circuit breaker pattern for database unavailability
- Pool metrics collection and monitoring
- Project isolation enforcement
"""

import asyncio
import time
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

import asyncpg
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text, event
from sqlalchemy.pool import QueuePool
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import pybreaker
import structlog
from prometheus_client import Gauge, Histogram, Counter

from .config import get_settings

logger = structlog.get_logger()


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class DatabaseMetrics:
    """Database connection pool metrics."""

    active_connections: int = 0
    idle_connections: int = 0
    total_connections: int = 0
    overflow_connections: int = 0
    pool_hit_rate: float = 0.0
    connection_wait_time: float = 0.0
    failed_connections: int = 0
    successful_connections: int = 0
    circuit_state: CircuitState = CircuitState.CLOSED


class DatabaseCircuitBreaker(pybreaker.CircuitBreaker):
    """Database circuit breaker with custom failure detection."""

    def __init__(self, **kwargs):
        super().__init__(
            fail_max=5,  # Open circuit after 5 failures
            reset_timeout=60,  # Reset after 60 seconds
            **kwargs,
        )
        self._failure_count = 0
        self._last_failure_time = None


class DatabaseManager:
    """
    Advanced database connection manager with optimization and monitoring.

    Features:
    - Optimized connection pooling with configurable parameters
    - Circuit breaker for database unavailability
    - Connection retry logic with exponential backoff
    - Comprehensive metrics collection
    - Project isolation enforcement
    """

    def __init__(self):
        self.settings = get_settings()
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None
        self.circuit_breaker = DatabaseCircuitBreaker()
        self.metrics = DatabaseMetrics()

        # Prometheus metrics
        self._setup_prometheus_metrics()

        # Connection pool monitoring
        self._setup_pool_monitoring()

        logger.info(
            "Database manager initialized",
            pool_size=self.settings.DATABASE_POOL_SIZE,
            max_overflow=self.settings.DATABASE_MAX_OVERFLOW,
        )

    def _setup_prometheus_metrics(self) -> None:
        """Setup Prometheus metrics for database monitoring."""
        # Gauges for current state
        self.db_active_connections = Gauge(
            "jeex_db_active_connections", "Number of active database connections"
        )
        self.db_idle_connections = Gauge(
            "jeex_db_idle_connections", "Number of idle database connections"
        )
        self.db_total_connections = Gauge(
            "jeex_db_total_connections", "Total number of database connections"
        )
        self.db_pool_hit_rate = Gauge(
            "jeex_db_pool_hit_rate", "Connection pool hit rate"
        )

        # Histograms for performance
        self.db_connection_duration = Histogram(
            "jeex_db_connection_duration_seconds",
            "Time spent establishing database connections",
        )
        self.db_query_duration = Histogram(
            "jeex_db_query_duration_seconds", "Time spent executing database queries"
        )

        # Counters for events
        self.db_failed_connections = Counter(
            "jeex_db_failed_connections_total",
            "Total number of failed database connections",
        )
        self.db_successful_connections = Counter(
            "jeex_db_successful_connections_total",
            "Total number of successful database connections",
        )
        self.db_circuit_breaker_trips = Counter(
            "jeex_db_circuit_breaker_trips_total",
            "Total number of circuit breaker trips",
        )

    def _setup_pool_monitoring(self) -> None:
        """Setup connection pool event monitoring."""

        @event.listens_for(QueuePool, "connect")
        def receive_connect(dbapi_connection, connection_record):
            """Track new connections."""
            self.metrics.successful_connections += 1
            self.db_successful_connections.inc()
            logger.debug("Database connection established")

        @event.listens_for(QueuePool, "checkout")
        def receive_checkout(dbapi_connection, connection_record, connection_proxy):
            """Track connection checkout."""
            start_time = time.time()
            connection_proxy._checkout_start = start_time

        @event.listens_for(QueuePool, "checkin")
        def receive_checkin(dbapi_connection, connection_record):
            """Track connection checkin."""
            if hasattr(dbapi_connection, "_checkout_start"):
                wait_time = time.time() - dbapi_connection._checkout_start
                self.metrics.connection_wait_time = wait_time

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(
            (asyncpg.PostgresConnectionError, ConnectionError)
        ),
        before_sleep=lambda retry_state: logger.warning(
            "Database connection retry",
            attempt=retry_state.attempt_number,
            wait_time=retry_state.next_action.sleep,
        ),
    )
    async def _create_engine_with_retry(self) -> AsyncEngine:
        """Create database engine with retry logic."""
        start_time = time.time()

        try:
            engine = create_async_engine(
                self.settings.database_url,
                # Optimized pool settings for Phase 3
                poolclass=QueuePool,
                pool_size=20,  # REQ-004: Connection Pool Management
                max_overflow=30,  # Allow additional connections under load
                pool_pre_ping=True,  # Validate connections before use
                pool_recycle=3600,  # Recycle connections after 1 hour
                pool_timeout=30,  # Wait 30 seconds for connection
                # Performance optimizations
                echo=self.settings.debug,
                future=True,
                # Connection settings
                connect_args={
                    "command_timeout": 60,
                    "server_settings": {
                        "application_name": "jeex_idea_api",
                        "jit": "off",  # Disable JIT for OLTP workloads
                        "statement_timeout": "30000",  # 30 second query timeout
                        "idle_in_transaction_session_timeout": "600000",  # 10 minutes
                        "lock_timeout": "10000",  # 10 seconds
                    },
                },
            )

            # Record connection duration
            duration = time.time() - start_time
            self.db_connection_duration.observe(duration)

            logger.info(
                "Database engine created successfully",
                duration_seconds=duration,
                pool_size=20,
                max_overflow=30,
            )

            return engine

        except Exception as e:
            duration = time.time() - start_time
            self.metrics.failed_connections += 1
            self.db_failed_connections.inc()

            logger.error(
                "Failed to create database engine",
                error=str(e),
                duration_seconds=duration,
            )
            raise

    async def initialize(self) -> None:
        """Initialize database connection with circuit breaker protection."""
        try:
            # Use circuit breaker to protect against cascade failures
            self.engine = await self.circuit_breaker.call_async(
                self._create_engine_with_retry
            )

            # Create session factory with optimized settings
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,  # Manual control for performance
                autocommit=False,
            )

            # Test connection and configure optimizations
            await self._test_and_configure_database()

            logger.info("Database initialized successfully with optimizations")

        except pybreaker.CircuitBreakerError:
            self.metrics.circuit_state = CircuitState.OPEN
            self.db_circuit_breaker_trips.inc()

            logger.error("Database circuit breaker is OPEN - database unavailable")
            raise RuntimeError(
                "Database temporarily unavailable - circuit breaker open"
            )

        except Exception as e:
            self.metrics.circuit_state = CircuitState.OPEN
            self.metrics.failed_connections += 1

            logger.error(
                "Database initialization failed", error=str(e), circuit_state="OPEN", exc_info=True
            )
            raise

    async def _test_and_configure_database(self) -> None:
        """Test database connection and configure performance optimizations."""
        if not self.engine:
            raise RuntimeError("Database engine not initialized")

        async with self.engine.begin() as conn:
            # Test basic connectivity
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

            # Configure PostgreSQL optimizations for Phase 3
            optimizations = [
                # Performance optimizations
                "SET work_mem = '64MB'",  # Memory for sort operations
                "SET maintenance_work_mem = '256MB'",  # Memory for maintenance
                "SET effective_cache_size = '4GB'",  # Estimate of system cache
                "SET random_page_cost = 1.1",  # For SSD storage
                "SET effective_io_concurrency = 200",  # For SSD
                # Monitoring and logging
                "SET log_min_duration_statement = 1000",  # Log slow queries (>1s)
                "SET log_checkpoints = on",
                "SET log_connections = on",
                "SET log_disconnections = on",
                "SET log_lock_waits = on",
                # Autovacuum tuning for project isolation
                "SET autovacuum_vacuum_scale_factor = 0.05",
                "SET autovacuum_analyze_scale_factor = 0.02",
            ]

            for optimization in optimizations:
                await conn.execute(text(optimization))

            logger.info("Database performance optimizations configured")

    @asynccontextmanager
    async def get_session(
        self, project_id: Optional[str] = None
    ) -> AsyncGenerator[AsyncSession, None]:
        """
        Get database session with project isolation and monitoring.

        Args:
            project_id: Optional project ID for isolation logging

        Yields:
            AsyncSession: Database session with transaction management
        """
        if not self.session_factory:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        # Check circuit breaker state
        if self.circuit_breaker.state == pybreaker.CircuitBreaker.OPEN:
            self.metrics.circuit_state = CircuitState.OPEN
            raise RuntimeError(
                "Database temporarily unavailable - circuit breaker open"
            )

        start_time = time.time()

        try:
            async with self.session_factory() as session:
                # Set project context for monitoring
                if project_id:
                    await session.execute(
                        text("SET LOCAL application_name = :app_name"),
                        {"app_name": f"jeex_idea_api_project_{project_id}"},
                    )

                try:
                    yield session
                    await session.commit()

                except Exception as e:
                    await session.rollback()

                    logger.error(
                        "Database transaction failed",
                        error=str(e),
                        project_id=project_id,
                        exc_info=True,
                    )
                    raise

        except Exception as e:
            # Update circuit breaker on failures
            if isinstance(e, (asyncpg.PostgresConnectionError, ConnectionError)):
                self.circuit_breaker._failure_count += 1
                if self.circuit_breaker._failure_count >= self.circuit_breaker.fail_max:
                    self.metrics.circuit_state = CircuitState.OPEN
                    self.db_circuit_breaker_trips.inc()

            raise

        finally:
            # Record query duration
            duration = time.time() - start_time
            self.db_query_duration.observe(duration)

    async def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive database metrics for monitoring."""
        if not self.engine:
            return {
                "status": "not_initialized",
                "circuit_state": self.metrics.circuit_state.value,
            }

        pool = self.engine.pool

        # Update metrics from pool
        self.metrics.active_connections = pool.checkedin() + pool.checkedout()
        self.metrics.idle_connections = pool.checkedin()
        self.metrics.total_connections = pool.size() + pool.overflow()
        self.metrics.overflow_connections = pool.overflow()

        # Update Prometheus metrics
        self.db_active_connections.set(self.metrics.active_connections)
        self.db_idle_connections.set(self.metrics.idle_connections)
        self.db_total_connections.set(self.metrics.total_connections)

        # Get detailed pool stats
        pool_stats = {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "invalid": pool.invalid(),
        }

        # Get circuit breaker state
        circuit_state = {
            "state": self.circuit_breaker.state.value,
            "failure_count": self.circuit_breaker._failure_count,
            "failure_threshold": self.circuit_breaker.fail_max,
            "reset_timeout": self.circuit_breaker.reset_timeout,
        }

        return {
            "status": "healthy",
            "pool": pool_stats,
            "circuit_breaker": circuit_state,
            "metrics": {
                "active_connections": self.metrics.active_connections,
                "idle_connections": self.metrics.idle_connections,
                "total_connections": self.metrics.total_connections,
                "overflow_connections": self.metrics.overflow_connections,
                "connection_wait_time": self.metrics.connection_wait_time,
                "failed_connections": self.metrics.failed_connections,
                "successful_connections": self.metrics.successful_connections,
                "circuit_state": self.metrics.circuit_state.value,
            },
        }

    async def health_check(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform comprehensive database health check.

        Args:
            project_id: Optional project ID for project-scoped health check

        Returns:
            Dict with health status and detailed metrics
        """
        start_time = time.time()

        try:
            async with self.get_session(project_id) as session:
                # Basic connectivity test
                result = await session.execute(text("SELECT 1"))
                assert result.scalar() == 1

                # PostgreSQL version
                result = await session.execute(text("SELECT version()"))
                version = result.scalar()

                # Database size and statistics
                result = await session.execute(
                    text("""
                    SELECT
                        pg_size_pretty(pg_database_size(current_database())) as db_size,
                        pg_stat_get_db_numbackends(oid) as connections,
                        pg_stat_get_db_xact_commit(oid) as commits,
                        pg_stat_get_db_xact_rollback(oid) as rollbacks
                    FROM pg_database
                    WHERE datname = current_database()
                """)
                )
                stats = result.fetchone()

                # Slow query count (queries > 1 second)
                result = await session.execute(
                    text("""
                    SELECT COUNT(*)
                    FROM pg_stat_statements
                    WHERE mean_exec_time > 1000
                """)
                )
                slow_queries = result.scalar()

                duration = time.time() - start_time

                return {
                    "status": "healthy",
                    "duration_seconds": duration,
                    "project_id": project_id,
                    "details": {
                        "version": version,
                        "database_size": stats.db_size,
                        "active_connections": stats.connections,
                        "transactions": {
                            "commits": stats.commits,
                            "rollbacks": stats.rollbacks,
                        },
                        "slow_queries_count": slow_queries,
                        "pool_metrics": await self.get_metrics(),
                    },
                }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Database health check failed",
                error=str(e),
                project_id=project_id,
                duration_seconds=duration,
            )

            return {
                "status": "unhealthy",
                "duration_seconds": duration,
                "project_id": project_id,
                "error": str(e),
                "circuit_state": self.metrics.circuit_state.value,
            }

    async def close(self) -> None:
        """Close database connections and cleanup resources."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

            logger.info("Database connections closed")


# Global database manager instance
database_manager = DatabaseManager()


# Dependency functions for FastAPI
async def get_database_session(
    project_id: Optional[str] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session with project isolation."""
    async with database_manager.get_session(project_id) as session:
        yield session


async def get_database_metrics() -> Dict[str, Any]:
    """FastAPI dependency for database metrics."""
    return await database_manager.get_metrics()


async def get_database_health(project_id: Optional[str] = None) -> Dict[str, Any]:
    """FastAPI dependency for database health check."""
    return await database_manager.health_check(project_id)
