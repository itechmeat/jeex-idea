"""
Redis Metrics Collector

Comprehensive Redis metrics collection with OpenTelemetry integration.
Tracks memory usage, connection pools, command execution times, and error rates.
Implements Domain-Driven patterns with project isolation.
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID
from contextlib import asynccontextmanager

from redis.asyncio import Redis
from redis.exceptions import RedisError
from opentelemetry import trace, metrics
from opentelemetry.trace import Status, StatusCode
from opentelemetry.metrics import Observation
from prometheus_client import (
    Gauge,
    Histogram,
    Counter,
    CollectorRegistry,
    generate_latest,
)
import structlog

from ..core.config import settings
from ..infrastructure.redis.connection_factory import redis_connection_factory

logger = structlog.get_logger(__name__)


class RedisCommandType(Enum):
    """Redis command types for categorization."""

    READ = "read"  # GET, HGET, LRANGE, etc.
    WRITE = "write"  # SET, HSET, LPUSH, etc.
    DELETE = "delete"  # DEL, EXPIRE, etc.
    ADMIN = "admin"  # PING, INFO, CONFIG, etc.


@dataclass
class RedisCommandMetrics:
    """Metrics for a Redis command execution."""

    command: str
    command_type: RedisCommandType
    duration_ms: float
    success: bool
    error_message: Optional[str] = None
    project_id: Optional[UUID] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    key_count: int = 0
    response_size_bytes: int = 0


@dataclass
class RedisMemoryMetrics:
    """Redis memory usage metrics."""

    timestamp: datetime
    used_memory_bytes: int
    used_memory_rss_bytes: int
    used_memory_peak_bytes: int
    used_memory_percentage: float
    max_memory_bytes: int
    memory_fragmentation_ratio: float
    keyspace_hits: int
    keyspace_misses: int
    hit_rate: float


@dataclass
class RedisConnectionMetrics:
    """Redis connection pool metrics."""

    timestamp: datetime
    active_connections: int
    idle_connections: int
    created_connections: int
    max_connections: int
    connection_utilization: float
    pool_name: str
    project_id: Optional[UUID] = None


class RedisMetricsCollector:
    """
    Comprehensive Redis metrics collection with OpenTelemetry integration.

    Features:
    - Memory usage monitoring with 80% threshold alerts
    - Connection pool monitoring and reporting
    - Command execution time tracking
    - Error rate monitoring for Redis operations
    - Project-scoped metrics collection
    - Prometheus-compatible metrics
    - OpenTelemetry integration
    """

    def __init__(self):
        self.settings = settings

        # Metrics storage
        self._command_metrics: List[RedisCommandMetrics] = []
        self._memory_metrics: List[RedisMemoryMetrics] = []
        self._connection_metrics: List[RedisConnectionMetrics] = []
        self._max_history_size = 10000

        # Alert thresholds
        self.memory_alert_threshold = 0.8  # 80% memory usage
        self.error_rate_threshold = 0.05  # 5% error rate
        self.slow_command_threshold_ms = 100  # 100ms for Redis commands

        # Internal state for OpenTelemetry callbacks
        self._latest_memory_percentage = 0
        self._latest_active_connections = 0
        self._latest_error_rate = 0

        # Setup OpenTelemetry
        self._setup_opentelemetry()

        # Setup Prometheus metrics
        self._setup_prometheus_metrics()

        # Background collection task
        self._collection_task: Optional[asyncio.Task] = None

        logger.info(
            "Redis metrics collector initialized",
            memory_alert_threshold=self.memory_alert_threshold,
            error_rate_threshold=self.error_rate_threshold,
            slow_command_threshold_ms=self.slow_command_threshold_ms,
        )

    def _setup_opentelemetry(self) -> None:
        """Setup OpenTelemetry metrics for Redis."""
        try:
            # Get meter
            self.meter = metrics.get_meter(__name__)

            # Create observable gauges
            self.redis_memory_usage = self.meter.create_observable_gauge(
                "redis.memory.usage_bytes",
                callbacks=[self._observe_memory_usage],
                description="Redis memory usage in bytes",
            )

            self.redis_memory_percentage = self.meter.create_observable_gauge(
                "redis.memory.usage_percentage",
                callbacks=[self._observe_memory_percentage],
                description="Redis memory usage as percentage of max memory",
            )

            self.redis_active_connections = self.meter.create_observable_gauge(
                "redis.connections.active",
                callbacks=[self._observe_active_connections],
                description="Number of active Redis connections",
            )

            self.redis_error_rate = self.meter.create_observable_gauge(
                "redis.errors.rate",
                callbacks=[self._observe_error_rate],
                description="Redis error rate (0-1)",
            )

            # Create histograms
            self.redis_command_duration = self.meter.create_histogram(
                "redis.commands.duration_ms",
                description="Redis command execution time in milliseconds",
                unit="ms",
            )

            # Create counters
            self.redis_commands_total = self.meter.create_counter(
                "redis.commands.total",
                description="Total number of Redis commands executed",
            )

            self.redis_errors_total = self.meter.create_counter(
                "redis.errors.total",
                description="Total number of Redis errors",
            )

            self.redis_slow_commands_total = self.meter.create_counter(
                "redis.slow_commands.total",
                description="Total number of slow Redis commands",
            )

            logger.info("OpenTelemetry Redis metrics configured")

        except Exception as e:
            logger.warning(
                "Failed to setup OpenTelemetry Redis metrics",
                error=str(e),
            )
            # Set up no-op meter as fallback
            self.meter = metrics.get_meter(__name__)

    def _setup_prometheus_metrics(self) -> None:
        """Setup Prometheus metrics for Redis."""
        self.registry = CollectorRegistry()

        # Memory metrics
        self.prom_redis_memory_bytes = Gauge(
            "jeex_redis_memory_bytes",
            "Redis memory usage in bytes",
            registry=self.registry,
        )

        self.prom_redis_memory_percentage = Gauge(
            "jeex_redis_memory_percentage",
            "Redis memory usage as percentage of max memory (0-100)",
            registry=self.registry,
        )

        self.prom_redis_memory_fragmentation_ratio = Gauge(
            "jeex_redis_memory_fragmentation_ratio",
            "Redis memory fragmentation ratio",
            registry=self.registry,
        )

        self.prom_redis_hit_rate = Gauge(
            "jeex_redis_hit_rate",
            "Redis cache hit rate (0-1)",
            registry=self.registry,
        )

        # Connection metrics
        self.prom_redis_connections_active = Gauge(
            "jeex_redis_connections_active",
            "Number of active Redis connections",
            registry=self.registry,
        )

        self.prom_redis_connections_idle = Gauge(
            "jeex_redis_connections_idle",
            "Number of idle Redis connections",
            registry=self.registry,
        )

        self.prom_redis_connection_utilization = Gauge(
            "jeex_redis_connection_utilization",
            "Redis connection pool utilization ratio (0-1)",
            registry=self.registry,
        )

        # Command metrics
        self.prom_redis_command_duration_seconds = Histogram(
            "jeex_redis_command_duration_seconds",
            "Redis command execution time in seconds",
            buckets=[0.0001, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
            registry=self.registry,
        )

        self.prom_redis_commands_total = Counter(
            "jeex_redis_commands_total",
            "Total number of Redis commands executed",
            ["command_type", "success"],
            registry=self.registry,
        )

        self.prom_redis_errors_total = Counter(
            "jeex_redis_errors_total",
            "Total number of Redis errors",
            ["error_type"],
            registry=self.registry,
        )

        self.prom_redis_slow_commands_total = Counter(
            "jeex_redis_slow_commands_total",
            "Total number of slow Redis commands",
            ["command_type"],
            registry=self.registry,
        )

        # Memory alerts
        self.prom_redis_memory_alerts_total = Counter(
            "jeex_redis_memory_alerts_total",
            "Total number of Redis memory alerts",
            ["threshold"],
            registry=self.registry,
        )

    def _observe_memory_usage(self, options) -> List[Observation]:
        """Callback for memory usage observable gauge."""
        # Calculate bytes from percentage for backward compatibility
        # This is approximate since we don't store max_memory in the callback state
        if self._latest_memory_percentage > 0:
            # Use a reasonable max memory assumption (1GB) for bytes calculation
            # In a real scenario, this should be stored separately or retrieved from latest metrics
            estimated_max_memory = 1024 * 1024 * 1024  # 1GB
            estimated_bytes = (
                self._latest_memory_percentage / 100
            ) * estimated_max_memory
        else:
            estimated_bytes = 0
        return [Observation(estimated_bytes)]

    def _observe_memory_percentage(self, options) -> List[Observation]:
        """Callback for memory percentage observable gauge."""
        return [
            Observation(self._latest_memory_percentage)
        ]  # Already in percentage (0-100)

    def _observe_active_connections(self, options) -> List[Observation]:
        """Callback for active connections observable gauge."""
        return [Observation(self._latest_active_connections)]

    def _observe_error_rate(self, options) -> List[Observation]:
        """Callback for error rate observable gauge."""
        return [Observation(self._latest_error_rate)]

    async def start_collection(self) -> None:
        """Start background metrics collection."""
        if self._collection_task is None:
            self._collection_task = asyncio.create_task(self._collection_loop())
            logger.info("Redis metrics collection started")

    async def stop_collection(self) -> None:
        """Stop background metrics collection."""
        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
            self._collection_task = None
            logger.info("Redis metrics collection stopped")

    async def _collection_loop(self) -> None:
        """Background metrics collection loop."""
        while True:
            try:
                await self._collect_memory_metrics()
                await self._collect_connection_metrics()
                await self._cleanup_old_metrics()
                await asyncio.sleep(30)  # Collect every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Redis metrics collection error", error=str(e))
                await asyncio.sleep(30)

    @asynccontextmanager
    async def trace_command(
        self,
        command: str,
        command_type: RedisCommandType,
        project_id: Optional[UUID] = None,
    ):
        """
        Trace Redis command execution with metrics collection.

        Args:
            command: Redis command being executed
            command_type: Type of command (read/write/delete/admin)
            project_id: Optional project ID for context isolation
        """
        start_time = time.time()
        success = True
        error_message = None

        try:
            yield
        except Exception as e:
            success = False
            error_message = str(e)
            raise
        finally:
            duration_ms = (time.time() - start_time) * 1000

            # Record command metrics
            await self._record_command_metrics(
                command=command,
                command_type=command_type,
                duration_ms=duration_ms,
                success=success,
                error_message=error_message,
                project_id=project_id,
            )

    async def _record_command_metrics(
        self,
        command: str,
        command_type: RedisCommandType,
        duration_ms: float,
        success: bool,
        error_message: Optional[str] = None,
        project_id: Optional[UUID] = None,
    ) -> None:
        """Record metrics for a Redis command execution."""
        # Create command metrics record
        command_metrics = RedisCommandMetrics(
            command=command[:50],  # Truncate for storage
            command_type=command_type,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message[:100] if error_message else None,
            project_id=project_id,
        )

        # Store in history
        self._command_metrics.append(command_metrics)
        if len(self._command_metrics) > self._max_history_size:
            self._command_metrics.pop(0)

        # Update OpenTelemetry metrics
        self.redis_command_duration.record(duration_ms)
        self.redis_commands_total.add(1)

        if not success:
            self.redis_errors_total.add(1)

        # Update Prometheus metrics
        self.prom_redis_command_duration_seconds.observe(duration_ms / 1000)
        self.prom_redis_commands_total.labels(
            command_type=command_type.value, success="true" if success else "false"
        ).inc()

        if not success:
            error_type = (
                "connection_error"
                if "connection" in (error_message or "").lower()
                else "command_error"
            )
            self.prom_redis_errors_total.labels(error_type=error_type).inc()

        # Check for slow command
        if duration_ms > self.slow_command_threshold_ms:
            self.redis_slow_commands_total.add(1)
            self.prom_redis_slow_commands_total.labels(
                command_type=command_type.value
            ).inc()

            logger.warning(
                "Slow Redis command detected",
                command=command,
                duration_ms=duration_ms,
                threshold_ms=self.slow_command_threshold_ms,
                project_id=project_id,
            )

        # Log command execution
        if success:
            logger.debug(
                "Redis command executed",
                command=command,
                duration_ms=duration_ms,
                command_type=command_type.value,
                project_id=project_id,
            )
        else:
            logger.error(
                "Redis command failed",
                command=command,
                duration_ms=duration_ms,
                error_message=error_message,
                command_type=command_type.value,
                project_id=project_id,
            )

    async def _collect_memory_metrics(self) -> None:
        """Collect Redis memory usage metrics."""
        try:
            async with redis_connection_factory.get_admin_connection() as redis_client:
                # Get Redis INFO memory section
                info = await redis_client.info("memory")

                # Extract memory information
                used_memory = info.get("used_memory", 0)
                used_memory_rss = info.get("used_memory_rss", 0)
                used_memory_peak = info.get("used_memory_peak", 0)
                max_memory = info.get("maxmemory", 0)

                # Calculate memory percentage
                memory_percentage = 0
                if max_memory > 0:
                    memory_percentage = (used_memory / max_memory) * 100

                # Get memory fragmentation ratio
                fragmentation_ratio = 1.0
                if used_memory > 0:
                    fragmentation_ratio = used_memory_rss / used_memory

                # Get keyspace stats
                stats_info = await redis_client.info("stats")
                keyspace_hits = stats_info.get("keyspace_hits", 0)
                keyspace_misses = stats_info.get("keyspace_misses", 0)

                # Calculate hit rate
                total_requests = keyspace_hits + keyspace_misses
                hit_rate = keyspace_hits / total_requests if total_requests > 0 else 0

                # Create memory metrics record
                memory_metrics = RedisMemoryMetrics(
                    timestamp=datetime.utcnow(),
                    used_memory_bytes=used_memory,
                    used_memory_rss_bytes=used_memory_rss,
                    used_memory_peak_bytes=used_memory_peak,
                    used_memory_percentage=memory_percentage,
                    max_memory_bytes=max_memory,
                    memory_fragmentation_ratio=fragmentation_ratio,
                    keyspace_hits=keyspace_hits,
                    keyspace_misses=keyspace_misses,
                    hit_rate=hit_rate,
                )

                # Store in history
                self._memory_metrics.append(memory_metrics)
                if len(self._memory_metrics) > self._max_history_size:
                    self._memory_metrics.pop(0)

                # Update internal state for OpenTelemetry with percentage value
                self._latest_memory_percentage = memory_percentage

                # Update Prometheus metrics
                self.prom_redis_memory_bytes.set(used_memory)
                self.prom_redis_memory_percentage.set(memory_percentage)
                self.prom_redis_memory_fragmentation_ratio.set(fragmentation_ratio)
                self.prom_redis_hit_rate.set(hit_rate)

                # Check memory alert threshold
                if memory_percentage > (self.memory_alert_threshold * 100):
                    await self._trigger_memory_alert(memory_percentage, memory_metrics)

                logger.debug(
                    "Redis memory metrics collected",
                    used_memory_mb=used_memory / 1024 / 1024,
                    memory_percentage=memory_percentage,
                    hit_rate=hit_rate,
                )

        except Exception as e:
            logger.error("Failed to collect Redis memory metrics", error=str(e))

    async def _collect_connection_metrics(self) -> None:
        """Collect Redis connection pool metrics."""
        try:
            # Get connection factory metrics
            factory_metrics = redis_connection_factory.get_metrics()

            # Get Redis INFO clients section
            async with redis_connection_factory.get_admin_connection() as redis_client:
                client_info = await redis_client.info("clients")
                connected_clients = client_info.get("connected_clients", 0)

            # Calculate connection metrics
            total_connections = 0
            for pool_data in factory_metrics["pools"].values():
                total_connections += pool_data.get("created_connections", 0)

            connection_utilization = 0
            max_connections = (
                factory_metrics["pools"].get("default", {}).get("max_connections", 10)
            )
            if max_connections > 0:
                connection_utilization = connected_clients / max_connections

            # Create connection metrics record
            connection_metrics = RedisConnectionMetrics(
                timestamp=datetime.utcnow(),
                active_connections=connected_clients,
                idle_connections=max(0, max_connections - connected_clients),
                created_connections=total_connections,
                max_connections=max_connections,
                connection_utilization=connection_utilization,
                pool_name="default",
            )

            # Store in history
            self._connection_metrics.append(connection_metrics)
            if len(self._connection_metrics) > self._max_history_size:
                self._connection_metrics.pop(0)

            # Update internal state for OpenTelemetry
            self._latest_active_connections = connected_clients

            # Update Prometheus metrics
            self.prom_redis_connections_active.set(connected_clients)
            self.prom_redis_connections_idle.set(connection_metrics.idle_connections)
            self.prom_redis_connection_utilization.set(connection_utilization)

            logger.debug(
                "Redis connection metrics collected",
                active_connections=connected_clients,
                connection_utilization=connection_utilization,
            )

        except Exception as e:
            logger.error("Failed to collect Redis connection metrics", error=str(e))

    async def _trigger_memory_alert(
        self, memory_percentage: float, memory_metrics: RedisMemoryMetrics
    ) -> None:
        """Trigger memory usage alert."""
        logger.warning(
            "Redis memory usage alert",
            memory_percentage=memory_percentage,
            threshold_percent=self.memory_alert_threshold * 100,
            used_memory_mb=memory_metrics.used_memory_bytes / 1024 / 1024,
            max_memory_mb=memory_metrics.max_memory_bytes / 1024 / 1024,
        )

        # Update Prometheus alert counter
        self.prom_redis_memory_alerts_total.labels(
            threshold=f"{self.memory_alert_threshold * 100}%"
        ).inc()

    async def _cleanup_old_metrics(self) -> None:
        """Clean up old metrics to prevent memory leaks."""
        cutoff_time = datetime.utcnow() - timedelta(hours=1)

        # Cleanup old command metrics
        self._command_metrics = [
            m for m in self._command_metrics if m.timestamp > cutoff_time
        ]

        # Cleanup old memory metrics
        self._memory_metrics = [
            m for m in self._memory_metrics if m.timestamp > cutoff_time
        ]

        # Cleanup old connection metrics
        self._connection_metrics = [
            m for m in self._connection_metrics if m.timestamp > cutoff_time
        ]

    async def get_metrics_summary(
        self, project_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Get comprehensive Redis metrics summary."""
        # Filter by project if specified
        command_metrics = self._command_metrics
        if project_id:
            command_metrics = [m for m in command_metrics if m.project_id == project_id]

        # Calculate error rate
        recent_commands = [
            m
            for m in command_metrics
            if m.timestamp > datetime.utcnow() - timedelta(minutes=5)
        ]

        error_rate = 0
        if recent_commands:
            error_count = sum(1 for m in recent_commands if not m.success)
            error_rate = error_count / len(recent_commands)

        # Update internal state for OpenTelemetry
        self._latest_error_rate = error_rate

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "project_id": str(project_id) if project_id else None,
            "memory": await self._get_memory_summary(),
            "connections": await self._get_connection_summary(),
            "commands": await self._get_command_summary(command_metrics),
            "performance": {
                "error_rate_5m": error_rate,
                "slow_commands_threshold_ms": self.slow_command_threshold_ms,
                "slow_commands_count": sum(
                    1
                    for m in recent_commands
                    if m.duration_ms > self.slow_command_threshold_ms
                ),
            },
            "prometheus_metrics": generate_latest(self.registry).decode("utf-8"),
        }

    async def _get_memory_summary(self) -> Dict[str, Any]:
        """Get memory usage summary."""
        if not self._memory_metrics:
            return {"status": "no_data"}

        latest = self._memory_metrics[-1]
        return {
            "used_memory_mb": latest.used_memory_bytes / 1024 / 1024,
            "used_memory_percentage": latest.used_memory_percentage,
            "max_memory_mb": latest.max_memory_bytes / 1024 / 1024,
            "fragmentation_ratio": latest.memory_fragmentation_ratio,
            "hit_rate": latest.hit_rate,
            "keyspace_hits": latest.keyspace_hits,
            "keyspace_misses": latest.keyspace_misses,
            "alert_threshold_percent": self.memory_alert_threshold * 100,
            "alert_active": latest.used_memory_percentage
            > (self.memory_alert_threshold * 100),
        }

    async def _get_connection_summary(self) -> Dict[str, Any]:
        """Get connection pool summary."""
        if not self._connection_metrics:
            return {"status": "no_data"}

        latest = self._connection_metrics[-1]
        return {
            "active_connections": latest.active_connections,
            "idle_connections": latest.idle_connections,
            "max_connections": latest.max_connections,
            "connection_utilization": latest.connection_utilization,
            "utilization_percentage": latest.connection_utilization * 100,
        }

    async def _get_command_summary(
        self, command_metrics: List[RedisCommandMetrics]
    ) -> Dict[str, Any]:
        """Get command execution summary."""
        if not command_metrics:
            return {"status": "no_data"}

        recent_commands = [
            m
            for m in command_metrics
            if m.timestamp > datetime.utcnow() - timedelta(minutes=5)
        ]

        if not recent_commands:
            return {"status": "no_recent_data"}

        # Calculate statistics
        total_commands = len(recent_commands)
        successful_commands = sum(1 for m in recent_commands if m.success)
        failed_commands = total_commands - successful_commands

        durations = [m.duration_ms for m in recent_commands]
        avg_duration = sum(durations) / len(durations)
        max_duration = max(durations)
        min_duration = min(durations)

        # Calculate percentiles
        sorted_durations = sorted(durations)
        p50 = sorted_durations[len(sorted_durations) // 2]
        p95 = sorted_durations[int(len(sorted_durations) * 0.95)]
        p99 = sorted_durations[int(len(sorted_durations) * 0.99)]

        # Group by command type
        by_type = {}
        for metrics in recent_commands:
            cmd_type = metrics.command_type.value
            if cmd_type not in by_type:
                by_type[cmd_type] = {"count": 0, "success": 0, "total_duration": 0}

            by_type[cmd_type]["count"] += 1
            if metrics.success:
                by_type[cmd_type]["success"] += 1
            by_type[cmd_type]["total_duration"] += metrics.duration_ms

        # Calculate averages by type
        for cmd_type in by_type:
            count = by_type[cmd_type]["count"]
            if count > 0:
                by_type[cmd_type]["avg_duration_ms"] = (
                    by_type[cmd_type]["total_duration"] / count
                )
                by_type[cmd_type]["success_rate"] = by_type[cmd_type]["success"] / count

        return {
            "total_commands_5m": total_commands,
            "successful_commands_5m": successful_commands,
            "failed_commands_5m": failed_commands,
            "success_rate_5m": successful_commands / total_commands
            if total_commands > 0
            else 0,
            "duration_stats_ms": {
                "average": avg_duration,
                "min": min_duration,
                "max": max_duration,
                "p50": p50,
                "p95": p95,
                "p99": p99,
            },
            "by_command_type": by_type,
        }


# Global Redis metrics collector instance
redis_metrics_collector = RedisMetricsCollector()
