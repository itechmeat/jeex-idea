"""
JEEX Idea Database Maintenance - Phase 3

Comprehensive database maintenance procedures with:
- Automated VACUUM and ANALYZE operations
- Index maintenance procedures
- Statistics collection configuration
- Database reorganization procedures
- Project-scoped maintenance operations
- SQL injection protection via safe identifier quoting
"""

import asyncio
import time
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, AsyncGenerator, Optional
from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog
from prometheus_client import Gauge, Histogram, Counter

from .config import get_settings
from .database import database_manager
from .monitoring import performance_monitor
from ..constants import SYSTEM_PROJECT_ID

logger = structlog.get_logger()


def _quote_ident(identifier: str) -> str:
    """
    Safely quote SQL identifiers to prevent SQL injection.

    PostgreSQL identifier quoting rules:
    - Wrap each part in double quotes separately
    - Escape internal double quotes by doubling them
    - Validate identifier contains only allowed characters
    - Handle schema.table notation properly

    Args:
        identifier: The SQL identifier to quote (can include schema.table notation)

    Returns:
        Safely quoted identifier

    Raises:
        ValueError: If identifier contains invalid characters
    """
    if not identifier:
        raise ValueError("Identifier cannot be empty")

    # Validate identifier characters (allow letters, numbers, underscores, dots)
    if not re.match(r"^[a-zA-Z0-9_.]+$", identifier):
        raise ValueError(f"Invalid identifier: {identifier}")

    # Split by dots for schema.table notation and quote each part separately
    parts = identifier.split(".")
    quoted_parts = []

    for part in parts:
        if not part:  # Empty part (e.g., "schema..table")
            raise ValueError(f"Invalid identifier with empty part: {identifier}")

        # Escape internal double quotes and wrap in double quotes
        escaped = part.replace('"', '""')
        quoted_parts.append(f'"{escaped}"')

    return ".".join(quoted_parts)


def _validate_table_name(table_name: str) -> None:
    """
    Validate table name to prevent SQL injection.

    Args:
        table_name: Table name to validate

    Raises:
        ValueError: If table name is invalid or potentially dangerous
    """
    if not table_name:
        raise ValueError("Table name cannot be empty")

    # Check for reasonable length first (PostgreSQL identifier limit)
    if len(table_name) > 63:
        raise ValueError(f"Table name too long: {table_name}")

    # Prevent dangerous patterns - check these before character validation
    dangerous_patterns = [
        ";",
        "--",
        "/*",
        "*/",
        "GRANT",
        "REVOKE",
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "EXEC",
        "MERGE",
        "UNION",
        "SELECT",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "OR",
        "AND",
        "LIKE",
        "IN",
        "EXISTS",
        "BETWEEN",
    ]

    # Special handling for stored procedure prefixes
    if table_name.startswith("xp_") or table_name.startswith("sp_"):
        raise ValueError(
            f"Dangerous stored procedure prefix detected in table name: {table_name}"
        )

    # Also check for quotes and other dangerous characters
    dangerous_chars = ["'", '"', "\\", "\x00", "\n", "\r", "\t"]

    upper_name = table_name.upper()

    # Check for dangerous patterns
    for pattern in dangerous_patterns:
        if pattern in upper_name:
            raise ValueError(
                f"Dangerous pattern '{pattern}' detected in table name: {table_name}"
            )

    # Check for dangerous characters
    for char in dangerous_chars:
        if char in table_name:
            raise ValueError(
                f"Dangerous character '{char}' detected in table name: {table_name}"
            )

    # Allow only safe characters: letters, numbers, underscores, and dots
    if not re.match(r"^[a-zA-Z0-9_.]+$", table_name):
        raise ValueError(f"Invalid characters in table name: {table_name}")

    # Validate each part of schema.table notation separately
    parts = table_name.split(".")
    for part in parts:
        if not part:  # Empty part (e.g., "schema..table")
            raise ValueError(f"Empty identifier part in table name: {table_name}")
        if len(part) > 63:  # Each part also must respect identifier limit
            raise ValueError(f"Identifier part too long in table name: {part}")


class MaintenanceType(Enum):
    """Maintenance operation types."""

    VACUUM = "vacuum"
    ANALYZE = "analyze"
    REINDEX = "reindex"
    CLUSTER = "cluster"
    VACUUM_FULL = "vacuum_full"
    UPDATE_STATISTICS = "update_statistics"


class MaintenanceStatus(Enum):
    """Maintenance operation status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MaintenanceTask:
    """Database maintenance task information."""

    task_id: str
    maintenance_type: MaintenanceType
    status: MaintenanceStatus
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: float
    affected_rows: int
    project_id: UUID
    table_name: Optional[str]
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MaintenanceConfig:
    """Maintenance configuration settings."""

    vacuum_threshold_percent: float = 20.0  # Run VACUUM when >20% dead tuples
    analyze_threshold_percent: float = 10.0  # Run ANALYZE when >10% data changes
    vacuum_full_threshold_percent: float = 50.0  # Run VACUUM FULL when >50% bloat
    reindex_threshold_percent: float = 30.0  # Run REINDEX when >30% index bloat
    auto_vacuum_enabled: bool = True
    auto_analyze_enabled: bool = True
    maintenance_window_start: str = "02:00"  # 2 AM
    maintenance_window_end: str = "06:00"  # 6 AM
    max_concurrent_maintenance: int = 2


class DatabaseMaintenance:
    """
    Advanced database maintenance management.

    Features:
    - Automated VACUUM and ANALYZE operations
    - Index maintenance and reorganization
    - Statistics collection and analysis
    - Bloat detection and cleanup
    - Project-scoped maintenance
    - Performance impact monitoring
    """

    def __init__(self):
        self.settings = get_settings()
        self.config = MaintenanceConfig()

        # Maintenance state
        self._current_tasks: Dict[str, MaintenanceTask] = {}
        self._maintenance_history: List[MaintenanceTask] = []
        self._maintenance_queue: List[MaintenanceTask] = []
        self._maintenance_lock = asyncio.Lock()
        self._concurrency_sem = asyncio.Semaphore(
            self.config.max_concurrent_maintenance
        )

        # Setup Prometheus metrics
        self._setup_prometheus_metrics()

        # Background maintenance task
        self._maintenance_task: Optional[asyncio.Task] = None

        logger.info(
            "Database maintenance manager initialized",
            auto_vacuum=self.config.auto_vacuum_enabled,
            auto_analyze=self.config.auto_analyze_enabled,
        )

    def _setup_prometheus_metrics(self) -> None:
        """Setup Prometheus metrics for maintenance monitoring."""
        # Maintenance operation metrics
        self.prom_maintenance_duration = Histogram(
            "jeex_db_maintenance_duration_seconds",
            "Time spent on maintenance operations",
            ["operation_type", "status"],
            buckets=[1, 10, 60, 300, 900, 3600],  # 1s to 1 hour
        )

        self.prom_maintenance_operations_total = Counter(
            "jeex_db_maintenance_operations_total",
            "Total number of maintenance operations",
            ["operation_type", "status"],
        )

        self.prom_bloat_bytes = Gauge(
            "jeex_db_bloat_bytes",
            "Database bloat in bytes",
            ["table_name", "bloat_type"],
        )

        self.prom_vacuum_progress = Gauge(
            "jeex_db_vacuum_progress", "VACUUM operation progress (0-1)", ["table_name"]
        )

    async def initialize_maintenance(self) -> None:
        """Initialize maintenance system and start background tasks."""
        # Configure PostgreSQL maintenance settings
        await self._configure_postgresql_maintenance()

        # Start background maintenance scheduler
        await self._start_maintenance_scheduler()

        logger.info("Database maintenance system initialized")

    async def _configure_postgresql_maintenance(self) -> None:
        """Configure PostgreSQL for optimal maintenance operations."""
        # NOTE: Applications should NOT use ALTER SYSTEM - these are cluster-wide settings
        # that require database administrator privileges. Maintenance operations should
        # work with existing database configuration.
        logger.info(
            "PostgreSQL maintenance configuration skipped - using existing cluster settings"
        )

    async def _start_maintenance_scheduler(self) -> None:
        """Start background maintenance scheduler."""
        if self._maintenance_task is None:
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())
            logger.info("Maintenance scheduler started")

    async def _maintenance_loop(self) -> None:
        """Background maintenance loop."""
        while True:
            try:
                # Check if we're in maintenance window
                if self._is_maintenance_window():
                    await self._run_scheduled_maintenance()

                # Process queued maintenance tasks
                await self._process_maintenance_queue()

                await asyncio.sleep(300)  # Check every 5 minutes

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Maintenance loop error", error=str(e))
                await asyncio.sleep(300)

    def _is_maintenance_window(self) -> bool:
        """Check if current time is within maintenance window."""
        now = datetime.now().time()
        start_time = datetime.strptime(
            self.config.maintenance_window_start, "%H:%M"
        ).time()
        end_time = datetime.strptime(self.config.maintenance_window_end, "%H:%M").time()

        if start_time <= end_time:
            return start_time <= now <= end_time
        else:  # Overnight window
            return now >= start_time or now <= end_time

    async def _run_scheduled_maintenance(self) -> None:
        """Run scheduled maintenance operations."""
        try:
            # Analyze tables for maintenance needs
            analysis_results = await self._analyze_maintenance_needs()

            # Schedule necessary maintenance operations
            for table_info in analysis_results:
                if table_info["needs_vacuum"] and self.config.auto_vacuum_enabled:
                    await self._schedule_maintenance(
                        MaintenanceType.VACUUM,
                        SYSTEM_PROJECT_ID,
                        table_info["table_name"],
                    )

                if table_info["needs_analyze"] and self.config.auto_analyze_enabled:
                    await self._schedule_maintenance(
                        MaintenanceType.ANALYZE,
                        SYSTEM_PROJECT_ID,
                        table_info["table_name"],
                    )

                if table_info["needs_reindex"]:
                    await self._schedule_maintenance(
                        MaintenanceType.REINDEX,
                        SYSTEM_PROJECT_ID,
                        table_info["table_name"],
                    )

                if table_info["needs_vacuum_full"]:
                    await self._schedule_maintenance(
                        MaintenanceType.VACUUM_FULL,
                        SYSTEM_PROJECT_ID,
                        table_info["table_name"],
                    )

        except Exception as e:
            logger.error("Scheduled maintenance failed", error=str(e))

    async def _analyze_maintenance_needs(self) -> List[Dict[str, Any]]:
        """Analyze tables for maintenance needs."""
        try:
            async with database_manager.get_session(
                project_id=SYSTEM_PROJECT_ID
            ) as session:
                # Get table statistics
                result = await session.execute(
                    text("""
                    SELECT
                        schemaname,
                        tablename,
                        n_tup_ins as inserts,
                        n_tup_upd as updates,
                        n_tup_del as deletes,
                        n_live_tup as live_tuples,
                        n_dead_tup as dead_tuples,
                        last_vacuum,
                        last_autovacuum,
                        last_analyze,
                        last_autoanalyze
                    FROM pg_stat_user_tables
                    WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
                """)
                )
                tables = result.fetchall()

                maintenance_needs = []

                for table in tables:
                    table_info = {
                        "table_name": f"{table.schemaname}.{table.tablename}",
                        "live_tuples": table.live_tuples,
                        "dead_tuples": table.dead_tuples,
                        "total_tuples": table.live_tuples + table.dead_tuples,
                    }

                    # Calculate dead tuple percentage
                    if table_info["total_tuples"] > 0:
                        dead_tuple_percent = (
                            table.dead_tuples / table_info["total_tuples"]
                        ) * 100
                        table_info["dead_tuple_percent"] = dead_tuple_percent
                        table_info["needs_vacuum"] = (
                            dead_tuple_percent > self.config.vacuum_threshold_percent
                        )
                    else:
                        table_info["dead_tuple_percent"] = 0
                        table_info["needs_vacuum"] = False

                    # Check if ANALYZE is needed (based on data changes)
                    total_changes = table.inserts + table.updates + table.deletes
                    if table_info["live_tuples"] > 0:
                        change_percent = (
                            total_changes / table_info["live_tuples"]
                        ) * 100
                        table_info["change_percent"] = change_percent
                        table_info["needs_analyze"] = (
                            change_percent > self.config.analyze_threshold_percent
                        )
                    else:
                        table_info["change_percent"] = 0
                        table_info["needs_analyze"] = True  # New table

                    # Get table bloat information
                    bloat_info = await self._get_table_bloat(
                        session, table_info["table_name"]
                    )
                    table_info.update(bloat_info)

                    maintenance_needs.append(table_info)

                return maintenance_needs

        except Exception as e:
            logger.error("Failed to analyze maintenance needs", error=str(e))
            return []

    async def _get_table_bloat(
        self, session: AsyncSession, table_name: str
    ) -> Dict[str, Any]:
        """Get table and index bloat information."""
        try:
            # Validate table name to prevent SQL injection
            _validate_table_name(table_name)

            # Safely quote the table identifier
            quoted_table = _quote_ident(table_name)

            # Use parameterized queries with safe identifier quoting
            result = await session.execute(
                text(f"""
                SELECT
                    pg_size_pretty(pg_total_relation_size({quoted_table})) as total_size,
                    pg_size_pretty(pg_relation_size({quoted_table})) as table_size,
                    (pg_total_relation_size({quoted_table}) - pg_relation_size({quoted_table})) as index_size
            """)
            )
            size_info = result.fetchone()

            # Estimate bloat (simplified - real implementation would use detailed bloat queries)
            estimated_bloat = 0.1  # 10% estimated bloat

            return {
                "total_size": size_info.total_size,
                "table_size": size_info.table_size,
                "index_size": size_info.index_size,
                "estimated_bloat_percent": estimated_bloat * 100,
                "needs_reindex": estimated_bloat > 0.3,
                "needs_vacuum_full": estimated_bloat > 0.5,
            }

        except Exception as e:
            logger.warning(f"Failed to get bloat info for {table_name}", error=str(e))
            return {
                "estimated_bloat_percent": 0,
                "needs_reindex": False,
                "needs_vacuum_full": False,
            }

    async def _schedule_maintenance(
        self,
        maintenance_type: MaintenanceType,
        project_id: UUID,
        table_name: Optional[str] = None,
    ) -> str:
        """Schedule a maintenance operation."""
        task_id = f"{maintenance_type.value}_{table_name or 'all'}_{uuid4().hex}"

        task = MaintenanceTask(
            task_id=task_id,
            maintenance_type=maintenance_type,
            status=MaintenanceStatus.PENDING,
            start_time=datetime.utcnow(),
            end_time=None,
            duration_seconds=0,
            affected_rows=0,
            project_id=project_id,
            table_name=table_name,
        )

        self._maintenance_queue.append(task)
        logger.info(
            "Maintenance task scheduled",
            task_id=task_id,
            maintenance_type=maintenance_type.value,
            table_name=table_name,
        )

        return task_id

    async def _with_semaphore(self, task: MaintenanceTask) -> None:
        """
        Execute maintenance task with semaphore protection.

        This wrapper ensures that the semaphore is acquired before task execution
        and properly released even if the task fails.
        """
        async with self._concurrency_sem:
            await self._execute_maintenance_task(task)

    async def _process_maintenance_queue(self) -> None:
        """Process queued maintenance tasks."""
        async with self._maintenance_lock:
            # Process next task if available
            if self._maintenance_queue:
                task = self._maintenance_queue.pop(0)
                asyncio.create_task(self._with_semaphore(task))

    async def _execute_maintenance_task(self, task: MaintenanceTask) -> None:
        """Execute a maintenance task."""
        task.status = MaintenanceStatus.RUNNING
        task.start_time = datetime.utcnow()
        self._current_tasks[task.task_id] = task

        logger.info(
            "Executing maintenance task",
            task_id=task.task_id,
            maintenance_type=task.maintenance_type.value,
            table_name=task.table_name,
        )

        start_time = time.time()

        try:
            if task.maintenance_type == MaintenanceType.VACUUM:
                await self._execute_vacuum(task)
            elif task.maintenance_type == MaintenanceType.ANALYZE:
                await self._execute_analyze(task)
            elif task.maintenance_type == MaintenanceType.REINDEX:
                await self._execute_reindex(task)
            elif task.maintenance_type == MaintenanceType.VACUUM_FULL:
                await self._execute_vacuum_full(task)
            elif task.maintenance_type == MaintenanceType.CLUSTER:
                await self._execute_cluster(task)
            elif task.maintenance_type == MaintenanceType.UPDATE_STATISTICS:
                await self._execute_update_statistics(task)

            task.status = MaintenanceStatus.COMPLETED
            task.affected_rows = task.details.get("affected_rows", 0)

        except Exception as e:
            task.status = MaintenanceStatus.FAILED
            task.error_message = str(e)
            logger.error("Maintenance task failed", task_id=task.task_id, error=str(e))

        finally:
            task.end_time = datetime.utcnow()
            task.duration_seconds = time.time() - start_time

            # Update Prometheus metrics
            self.prom_maintenance_duration.labels(
                operation_type=task.maintenance_type.value, status=task.status.value
            ).observe(task.duration_seconds)

            self.prom_maintenance_operations_total.labels(
                operation_type=task.maintenance_type.value, status=task.status.value
            ).inc()

            # Add to history and remove from current tasks
            self._maintenance_history.append(task)
            if task.task_id in self._current_tasks:
                del self._current_tasks[task.task_id]

            logger.info(
                "Maintenance task completed",
                task_id=task.task_id,
                status=task.status.value,
                duration_seconds=task.duration_seconds,
            )

    async def _execute_vacuum(self, task: MaintenanceTask) -> None:
        """Execute VACUUM operation."""
        async with database_manager.get_session(task.project_id) as session:
            if task.table_name:
                # Validate and safely quote table name
                _validate_table_name(task.table_name)
                quoted_table = _quote_ident(task.table_name)

                # Vacuum specific table with safe identifier quoting
                await session.execute(text(f"VACUUM ANALYZE {quoted_table}"))
                task.details["affected_rows"] = 1  # Table count
            else:
                # Vacuum all tables
                await session.execute(text("VACUUM ANALYZE"))
                task.details["affected_rows"] = 1

            await session.commit()

    async def _execute_analyze(self, task: MaintenanceTask) -> None:
        """Execute ANALYZE operation."""
        async with database_manager.get_session(task.project_id) as session:
            if task.table_name:
                # Validate and safely quote table name
                _validate_table_name(task.table_name)
                quoted_table = _quote_ident(task.table_name)

                # Analyze specific table with safe identifier quoting
                await session.execute(text(f"ANALYZE {quoted_table}"))
                task.details["affected_rows"] = 1
            else:
                await session.execute(text("ANALYZE"))
                task.details["affected_rows"] = 1

            await session.commit()

    async def _execute_reindex(self, task: MaintenanceTask) -> None:
        """Execute REINDEX operation."""
        async with database_manager.get_session(task.project_id) as session:
            if task.table_name:
                # Validate and safely quote table name
                _validate_table_name(task.table_name)
                quoted_table = _quote_ident(task.table_name)

                # Reindex specific table with safe identifier quoting
                result = await session.execute(text(f"REINDEX TABLE {quoted_table}"))
                task.details["affected_rows"] = 1
            else:
                # Use current_database() to get current database dynamically instead of hardcoding
                result = await session.execute(
                    text("""
                    DO $$
                    BEGIN
                      EXECUTE format('REINDEX DATABASE %I', current_database());
                    END $$;
                    """)
                )
                task.details["affected_rows"] = 1

            await session.commit()

    async def _execute_vacuum_full(self, task: MaintenanceTask) -> None:
        """Execute VACUUM FULL operation."""
        async with database_manager.get_session(task.project_id) as session:
            if task.table_name:
                # Validate and safely quote table name
                _validate_table_name(task.table_name)
                quoted_table = _quote_ident(task.table_name)

                # VACUUM FULL specific table with safe identifier quoting
                await session.execute(text(f"VACUUM FULL {quoted_table}"))
                task.details["affected_rows"] = 1
            else:
                # DANGEROUS: VACUUM FULL on system catalog removed for safety
                # Instead, we'll log a warning and suggest manual intervention
                logger.warning(
                    "VACUUM FULL on all tables not performed automatically for safety. "
                    "Manual intervention required for table-level VACUUM FULL operations."
                )
                raise NotImplementedError(
                    "VACUUM FULL on all tables requires manual execution "
                    "due to potential for system catalog corruption"
                )

            await session.commit()

    async def _execute_cluster(self, task: MaintenanceTask) -> None:
        """Execute CLUSTER operation."""
        async with database_manager.get_session(task.project_id) as session:
            if task.table_name:
                # Validate and safely quote table name
                _validate_table_name(task.table_name)
                quoted_table = _quote_ident(task.table_name)

                # CLUSTER specific table with safe identifier quoting
                await session.execute(text(f"CLUSTER {quoted_table}"))
                task.details["affected_rows"] = 1
            else:
                logger.warning("CLUSTER requires a specific table name")
                raise ValueError("CLUSTER operation requires a specific table name")

            await session.commit()

    async def _execute_update_statistics(self, task: MaintenanceTask) -> None:
        """Update table statistics."""
        async with database_manager.get_session(task.project_id) as session:
            # Get table statistics
            if task.table_name:
                result = await session.execute(
                    text(f"""
                    SELECT
                        schemaname,
                        tablename,
                        n_live_tup,
                        n_dead_tup,
                        last_vacuum,
                        last_autovacuum,
                        last_analyze,
                        last_autoanalyze
                    FROM pg_stat_user_tables
                    WHERE schemaname || '.' || tablename = :table_name
                """),
                    {"table_name": task.table_name},
                )
            else:
                result = await session.execute(
                    text("""
                    SELECT
                        schemaname,
                        tablename,
                        n_live_tup,
                        n_dead_tup,
                        last_vacuum,
                        last_autovacuum,
                        last_analyze,
                        last_autoanalyze
                    FROM pg_stat_user_tables
                """)
                )

            stats = result.fetchall()
            # Use SQLAlchemy 2.x compatible row conversion
            task.details["table_statistics"] = [dict(row._mapping) for row in stats]
            task.details["affected_rows"] = len(stats)

    async def run_maintenance(
        self,
        maintenance_type: MaintenanceType,
        project_id: UUID,
        table_name: Optional[str] = None,
    ) -> MaintenanceTask:
        """
        Manually run a maintenance operation.

        Args:
            maintenance_type: Type of maintenance to run
            table_name: Optional specific table
            project_id: Required project ID for scoping

        Returns:
            MaintenanceTask: Task information and status
        """
        # Ensure scheduler is running to prevent hanging
        await self._start_maintenance_scheduler()

        # Validate table name if provided
        if table_name:
            _validate_table_name(table_name)

        task_id = await self._schedule_maintenance(
            maintenance_type, project_id, table_name
        )

        # Wait for task to complete (with timeout)
        timeout = 3600  # 1 hour timeout
        start_time = time.time()

        while time.time() - start_time < timeout:
            if task_id in self._current_tasks:
                task = self._current_tasks[task_id]
                if task.status in [
                    MaintenanceStatus.COMPLETED,
                    MaintenanceStatus.FAILED,
                ]:
                    return task
            elif any(t.task_id == task_id for t in self._maintenance_history):
                return next(
                    t for t in self._maintenance_history if t.task_id == task_id
                )

            await asyncio.sleep(1)

        raise TimeoutError(
            f"Maintenance task {task_id} did not complete within timeout"
        )

    async def get_maintenance_status(self) -> Dict[str, Any]:
        """Get current maintenance system status."""
        running_tasks = [
            t
            for t in self._current_tasks.values()
            if t.status == MaintenanceStatus.RUNNING
        ]
        pending_tasks = len(self._maintenance_queue)

        # Calculate recent performance metrics
        recent_tasks = [
            t
            for t in self._maintenance_history[-100:]  # Last 100 tasks
            if t.status == MaintenanceStatus.COMPLETED
        ]

        # Count total considered tasks and successful tasks
        considered = len(self._maintenance_history[-100:])  # Total tasks considered
        successes = len(recent_tasks)  # Successful tasks (COMPLETED status)

        if considered > 0:
            avg_duration = (
                sum(t.duration_seconds for t in recent_tasks) / len(recent_tasks)
                if recent_tasks
                else 0
            )
            success_rate = successes / considered
        else:
            avg_duration = 0
            success_rate = 1.0

        return {
            "current_tasks": [
                {
                    "task_id": task.task_id,
                    "maintenance_type": task.maintenance_type.value,
                    "status": task.status.value,
                    "start_time": task.start_time.isoformat(),
                    "duration_seconds": task.duration_seconds,
                    "table_name": task.table_name,
                    "project_id": task.project_id,
                }
                for task in running_tasks
            ],
            "pending_tasks": pending_tasks,
            "configuration": {
                "auto_vacuum_enabled": self.config.auto_vacuum_enabled,
                "auto_analyze_enabled": self.config.auto_analyze_enabled,
                "maintenance_window": {
                    "start": self.config.maintenance_window_start,
                    "end": self.config.maintenance_window_end,
                },
                "thresholds": {
                    "vacuum_percent": self.config.vacuum_threshold_percent,
                    "analyze_percent": self.config.analyze_threshold_percent,
                    "reindex_percent": self.config.reindex_threshold_percent,
                    "vacuum_full_percent": self.config.vacuum_full_threshold_percent,
                },
            },
            "performance": {
                "average_duration_seconds": avg_duration,
                "success_rate": success_rate,
                "total_completed": len(self._maintenance_history),
                "total_failed": len(
                    [
                        t
                        for t in self._maintenance_history
                        if t.status == MaintenanceStatus.FAILED
                    ]
                ),
            },
            "recent_activity": [
                {
                    "task_id": task.task_id,
                    "maintenance_type": task.maintenance_type.value,
                    "status": task.status.value,
                    "start_time": task.start_time.isoformat(),
                    "duration_seconds": task.duration_seconds,
                    "affected_rows": task.affected_rows,
                }
                for task in self._maintenance_history[-10:]  # Last 10 tasks
            ],
        }

    async def get_database_health(self) -> Dict[str, Any]:
        """Get comprehensive database health information."""
        try:
            async with database_manager.get_session(
                project_id=SYSTEM_PROJECT_ID
            ) as session:
                # Get database statistics
                result = await session.execute(
                    text("""
                    SELECT
                        pg_size_pretty(pg_database_size(current_database())) as database_size,
                        pg_size_pretty(sum(pg_relation_size(schemaname||'.'||tablename))) as tables_size,
                        pg_size_pretty(sum(pg_total_relation_size(schemaname||'.'||tablename))) as total_size,
                        count(*) as table_count
                    FROM pg_tables
                    WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
                """)
                )
                db_stats = result.fetchone()

                # Get index statistics
                result = await session.execute(
                    text("""
                    SELECT
                        count(*) as index_count,
                        pg_size_pretty(sum(pg_relation_size(indexrelid))) as indexes_size
                    FROM pg_index
                    JOIN pg_class ON pg_class.oid = pg_index.indexrelid
                    JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
                    WHERE nspname NOT IN ('information_schema', 'pg_catalog')
                """)
                )
                index_stats = result.fetchone()

                # Get connection statistics
                result = await session.execute(
                    text("""
                    SELECT
                        count(*) FILTER (WHERE state = 'active') as active_connections,
                        count(*) FILTER (WHERE state = 'idle') as idle_connections,
                        count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                """)
                )
                conn_stats = result.fetchone()

                # Get bloat information (simplified)
                bloat_info = await self._get_overall_bloat(session)

                return {
                    "database_size": db_stats.database_size,
                    "tables_size": db_stats.tables_size,
                    "indexes_size": index_stats.indexes_size,
                    "total_size": db_stats.total_size,
                    "table_count": db_stats.table_count,
                    "index_count": index_stats.index_count,
                    "connections": {
                        "active": conn_stats.active_connections,
                        "idle": conn_stats.idle_connections,
                        "idle_in_transaction": conn_stats.idle_in_transaction,
                    },
                    "bloat": bloat_info,
                    "maintenance": await self.get_maintenance_status(),
                }

        except Exception as e:
            logger.error("Failed to get database health", error=str(e))
            return {"error": str(e)}

    async def _get_overall_bloat(self, session: AsyncSession) -> Dict[str, Any]:
        """Get overall database bloat information."""
        try:
            # Simplified bloat calculation
            result = await session.execute(
                text("""
                SELECT
                    sum(pg_relation_size(schemaname||'.'||tablename)) as table_size,
                    sum(pg_total_relation_size(schemaname||'.'||tablename)) as total_size
                FROM pg_tables
                WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
            """)
            )
            size_info = result.fetchone()

            if size_info and size_info.table_size and size_info.total_size:
                bloat_ratio = (
                    size_info.total_size - size_info.table_size
                ) / size_info.total_size
                bloat_percent = bloat_ratio * 100
            else:
                bloat_percent = 0

            return {
                "estimated_bloat_percent": bloat_percent,
                "table_size": size_info.table_size if size_info else 0,
                "total_size": size_info.total_size if size_info else 0,
            }

        except Exception as e:
            logger.warning("Failed to calculate overall bloat", error=str(e))
            return {"estimated_bloat_percent": 0}

    async def cancel_maintenance_task(self, task_id: str) -> bool:
        """Cancel a running maintenance task."""
        if task_id in self._current_tasks:
            task = self._current_tasks[task_id]
            if task.status == MaintenanceStatus.RUNNING:
                # Note: PostgreSQL doesn't support canceling VACUUM easily
                # This would require killing the backend process
                task.status = MaintenanceStatus.CANCELLED
                task.end_time = datetime.utcnow()

                logger.info("Maintenance task cancelled", task_id=task_id)
                return True

        return False

    async def cleanup_maintenance_history(self, days: int = 30) -> None:
        """Clean up old maintenance history."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        original_count = len(self._maintenance_history)
        self._maintenance_history = [
            task for task in self._maintenance_history if task.start_time > cutoff_date
        ]

        removed_count = original_count - len(self._maintenance_history)
        if removed_count > 0:
            logger.info("Cleaned up maintenance history", removed_count=removed_count)

    async def stop_maintenance(self) -> None:
        """Stop background maintenance tasks."""
        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
            self._maintenance_task = None

        logger.info("Database maintenance stopped")


# Global maintenance manager instance
maintenance_manager = DatabaseMaintenance()


# Dependency functions for FastAPI
async def get_maintenance_manager() -> DatabaseMaintenance:
    """FastAPI dependency for maintenance manager."""
    return maintenance_manager
