"""
Redis Health Checker

Comprehensive health check service for Redis infrastructure.
Monitors Redis service availability, performance, and configuration.
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

from redis.asyncio import Redis
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    TimeoutError as RedisTimeoutError,
    AuthenticationError as RedisAuthError,
    RedisError,
)
import structlog

from ..core.config import settings
from ..infrastructure.redis.connection_factory import redis_connection_factory

logger = structlog.get_logger(__name__)


class HealthStatus(Enum):
    """Health check status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class HealthCheckType(Enum):
    """Types of health checks."""

    BASIC_CONNECTIVITY = "basic_connectivity"
    MEMORY_USAGE = "memory_usage"
    CONNECTION_POOL = "connection_pool"
    PERFORMANCE = "performance"
    PERSISTENCE = "persistence"
    REPLICATION = "replication"


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    check_type: HealthCheckType
    status: HealthStatus
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    project_id: Optional[UUID] = None


@dataclass
class RedisHealthStatus:
    """Overall Redis health status."""

    status: HealthStatus
    timestamp: datetime
    uptime_seconds: float
    version: str
    mode: str  # standalone, cluster, sentinel
    checks: List[HealthCheckResult]
    summary: Dict[str, Any] = field(default_factory=dict)
    alerts: List[str] = field(default_factory=list)


class RedisHealthChecker:
    """
    Comprehensive Redis health checker with multiple check types.

    Features:
    - Basic connectivity checks with response time monitoring
    - Memory usage health checks
    - Connection pool health monitoring
    - Performance health checks
    - Persistence health checks
    - Replication health checks (if applicable)
    - Project-scoped health checks
    - Alert generation for unhealthy conditions
    """

    def __init__(self):
        self.settings = settings

        # Health check thresholds
        self.response_time_threshold_ms = 100  # REQ-001: respond within 100ms
        self.memory_warning_threshold = 0.7  # 70% memory usage warning
        self.memory_critical_threshold = 0.9  # 90% memory usage critical
        self.connection_pool_warning_threshold = (
            0.8  # 80% connection pool usage warning
        )
        self.connection_pool_critical_threshold = (
            0.95  # 95% connection pool usage critical
        )

        # Health check configuration
        self.check_timeout_seconds = 5.0
        self.retry_attempts = 3
        self.retry_delay_seconds = 1.0

        # Background health checking
        self._health_check_task: Optional[asyncio.Task] = None
        # Health check caching - per project
        self._latest_health_status: Dict[UUID, RedisHealthStatus] = {}
        # Monitored project ID for background health checks
        self._project_id: Optional[UUID] = None

        logger.info(
            "Redis health checker initialized",
            response_time_threshold_ms=self.response_time_threshold_ms,
            memory_warning_threshold=self.memory_warning_threshold,
            memory_critical_threshold=self.memory_critical_threshold,
        )

    async def start_health_checks(self) -> None:
        """Start background health checking."""
        if self._health_check_task is None:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info("Redis health checking started")

    async def stop_health_checks(self) -> None:
        """Stop background health checking."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.info("Redis health checking stopped")

    async def _health_check_loop(self) -> None:
        """Background health checking loop."""
        while True:
            try:
                await self.perform_full_health_check()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Redis health check error", error=str(e))
                await asyncio.sleep(60)

    async def perform_full_health_check(self, project_id: UUID) -> RedisHealthStatus:
        """
        Perform comprehensive health check of Redis infrastructure.

        Args:
            project_id: Optional project ID for scoped health checks

        Returns:
            Complete health status with all check results
        """
        start_time = time.time()
        checks = []

        # Perform all health checks
        checks.append(await self._check_basic_connectivity(project_id))
        checks.append(await self._check_memory_usage(project_id))
        checks.append(await self._check_connection_pool(project_id))
        checks.append(await self._check_performance(project_id))
        checks.append(await self._check_persistence(project_id))

        # Determine overall status
        overall_status = self._determine_overall_status(checks)

        # Get Redis server info
        redis_info = await self._get_redis_server_info(project_id)

        # Create health status
        health_status = RedisHealthStatus(
            status=overall_status,
            timestamp=datetime.utcnow(),
            uptime_seconds=redis_info.get("uptime_in_seconds", 0),
            version=redis_info.get("redis_version", "unknown"),
            mode=redis_info.get("redis_mode", "standalone"),
            checks=checks,
            summary=self._generate_health_summary(checks),
            alerts=self._generate_health_alerts(checks),
        )

        # Store latest status - per project
        if project_id:
            self._latest_health_status[project_id] = health_status

        # Log health status
        await self._log_health_status(health_status)

        duration_ms = (time.time() - start_time) * 1000
        logger.debug(
            "Full Redis health check completed",
            status=overall_status.value,
            duration_ms=duration_ms,
            checks_count=len(checks),
            project_id=project_id,
        )

        return health_status

    async def _check_basic_connectivity(self, project_id: UUID) -> HealthCheckResult:
        """Check basic Redis connectivity with response time."""
        start_time = time.time()

        try:
            async with redis_connection_factory.get_connection(
                str(project_id)
            ) as redis_client:
                # Test basic PING command
                ping_result = await asyncio.wait_for(
                    redis_client.ping(), timeout=self.check_timeout_seconds
                )

                if not ping_result:
                    raise RedisError("PING command failed")

                # Test basic SET/GET operations
                test_key = f"health_check:{datetime.utcnow().timestamp()}"
                await redis_client.set(test_key, "test_value", ex=60)
                get_result = await redis_client.get(test_key)
                await redis_client.delete(test_key)

                if get_result != "test_value":
                    raise RedisError("SET/GET test failed")

                duration_ms = (time.time() - start_time) * 1000

                # Determine status based on response time
                if duration_ms > self.response_time_threshold_ms * 2:
                    status = HealthStatus.DEGRADED
                    message = f"Redis response time is slow: {duration_ms:.2f}ms"
                else:
                    status = HealthStatus.HEALTHY
                    message = f"Redis is responsive: {duration_ms:.2f}ms"

                return HealthCheckResult(
                    check_type=HealthCheckType.BASIC_CONNECTIVITY,
                    status=status,
                    message=message,
                    duration_ms=duration_ms,
                    details={
                        "ping_result": ping_result,
                        "set_get_test": "passed",
                        "response_time_ms": duration_ms,
                        "threshold_ms": self.response_time_threshold_ms,
                    },
                    project_id=project_id,
                )

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_type=HealthCheckType.BASIC_CONNECTIVITY,
                status=HealthStatus.UNHEALTHY,
                message=f"Redis health check timed out after {self.check_timeout_seconds}s",
                duration_ms=duration_ms,
                details={"timeout_seconds": self.check_timeout_seconds},
                project_id=project_id,
            )

        except RedisConnectionError as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_type=HealthCheckType.BASIC_CONNECTIVITY,
                status=HealthStatus.UNHEALTHY,
                message=f"Redis connection failed: {str(e)}",
                duration_ms=duration_ms,
                details={"error_type": "connection_error"},
                project_id=project_id,
            )

        except RedisAuthError as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_type=HealthCheckType.BASIC_CONNECTIVITY,
                status=HealthStatus.UNHEALTHY,
                message=f"Redis authentication failed: {str(e)}",
                duration_ms=duration_ms,
                details={"error_type": "auth_error"},
                project_id=project_id,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_type=HealthCheckType.BASIC_CONNECTIVITY,
                status=HealthStatus.UNHEALTHY,
                message=f"Redis health check failed: {str(e)}",
                duration_ms=duration_ms,
                details={"error_type": "unknown_error"},
                project_id=project_id,
            )

    async def _check_memory_usage(self, project_id: UUID) -> HealthCheckResult:
        """Check Redis memory usage."""
        start_time = time.time()

        try:
            async with redis_connection_factory.get_connection(
                str(project_id)
            ) as redis_client:
                # Get memory info
                memory_info = await redis_client.info("memory")

                used_memory = memory_info.get("used_memory", 0)
                max_memory = memory_info.get("maxmemory", 0)
                used_memory_rss = memory_info.get("used_memory_rss", 0)

                # Calculate memory percentage
                memory_percentage = 0
                if max_memory > 0:
                    memory_percentage = (used_memory / max_memory) * 100

                # Determine status
                if memory_percentage >= self.memory_critical_threshold * 100:
                    status = HealthStatus.UNHEALTHY
                    message = f"Critical memory usage: {memory_percentage:.1f}%"
                elif memory_percentage >= self.memory_warning_threshold * 100:
                    status = HealthStatus.DEGRADED
                    message = f"High memory usage: {memory_percentage:.1f}%"
                else:
                    status = HealthStatus.HEALTHY
                    message = f"Memory usage is normal: {memory_percentage:.1f}%"

                duration_ms = (time.time() - start_time) * 1000

                return HealthCheckResult(
                    check_type=HealthCheckType.MEMORY_USAGE,
                    status=status,
                    message=message,
                    duration_ms=duration_ms,
                    details={
                        "used_memory_bytes": used_memory,
                        "used_memory_mb": used_memory / 1024 / 1024,
                        "max_memory_bytes": max_memory,
                        "max_memory_mb": max_memory / 1024 / 1024,
                        "used_memory_rss_bytes": used_memory_rss,
                        "memory_percentage": memory_percentage,
                        "warning_threshold": self.memory_warning_threshold * 100,
                        "critical_threshold": self.memory_critical_threshold * 100,
                    },
                    project_id=project_id,
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_type=HealthCheckType.MEMORY_USAGE,
                status=HealthStatus.UNKNOWN,
                message=f"Failed to check memory usage: {str(e)}",
                duration_ms=duration_ms,
                details={"error": str(e)},
                project_id=project_id,
            )

    async def _check_connection_pool(self, project_id: UUID) -> HealthCheckResult:
        """Check Redis connection pool health."""
        start_time = time.time()

        try:
            # Get connection factory metrics
            factory_metrics = redis_connection_factory.get_metrics()

            # Get Redis client info
            async with redis_connection_factory.get_connection(
                str(project_id)
            ) as redis_client:
                client_info = await redis_client.info("clients")
                connected_clients = client_info.get("connected_clients", 0)

            # Get connection pool metrics
            pools = factory_metrics.get("pools", {})
            pool_key = f"project:{project_id}"
            pool_metrics = pools.get(pool_key) or pools.get("default", {})
            max_connections = pool_metrics.get("max_connections", 10)
            created_connections = pool_metrics.get("created_connections", 0)
            available_connections = pool_metrics.get("available_connections", 0)
            in_use = max(0, created_connections - available_connections)
            connection_utilization = (
                (in_use / max_connections) if max_connections > 0 else 0
            )

            # Determine status
            if connection_utilization >= self.connection_pool_critical_threshold:
                status = HealthStatus.UNHEALTHY
                message = (
                    f"Critical connection pool usage: {connection_utilization:.1%}"
                )
            elif connection_utilization >= self.connection_pool_warning_threshold:
                status = HealthStatus.DEGRADED
                message = f"High connection pool usage: {connection_utilization:.1%}"
            else:
                status = HealthStatus.HEALTHY
                message = (
                    f"Connection pool usage is normal: {connection_utilization:.1%}"
                )

            duration_ms = (time.time() - start_time) * 1000

            return HealthCheckResult(
                check_type=HealthCheckType.CONNECTION_POOL,
                status=status,
                message=message,
                duration_ms=duration_ms,
                details={
                    "connected_clients": connected_clients,
                    "max_connections": max_connections,
                    "created_connections": created_connections,
                    "available_connections": available_connections,
                    "in_use_connections": in_use,
                    "connection_utilization": connection_utilization,
                    "connection_utilization_percentage": connection_utilization * 100,
                    "warning_threshold": self.connection_pool_warning_threshold * 100,
                    "critical_threshold": self.connection_pool_critical_threshold * 100,
                    "pool_key": pool_key,
                    "pools_count": len(pools),
                },
                project_id=project_id,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_type=HealthCheckType.CONNECTION_POOL,
                status=HealthStatus.UNKNOWN,
                message=f"Failed to check connection pool: {str(e)}",
                duration_ms=duration_ms,
                details={"error": str(e)},
                project_id=project_id,
            )

    async def _check_performance(self, project_id: UUID) -> HealthCheckResult:
        """Check Redis performance metrics."""
        start_time = time.time()

        try:
            async with redis_connection_factory.get_connection(
                str(project_id)
            ) as redis_client:
                # Get stats info
                stats_info = await redis_client.info("stats")

                # Extract performance metrics
                keyspace_hits = stats_info.get("keyspace_hits", 0)
                keyspace_misses = stats_info.get("keyspace_misses", 0)
                total_commands_processed = stats_info.get("total_commands_processed", 0)
                instantaneous_ops_per_sec = stats_info.get(
                    "instantaneous_ops_per_sec", 0
                )
                used_cpu_sys = stats_info.get("used_cpu_sys", 0)
                used_cpu_user = stats_info.get("used_cpu_user", 0)

                # Calculate hit rate
                total_requests = keyspace_hits + keyspace_misses
                hit_rate = keyspace_hits / total_requests if total_requests > 0 else 0

                # Determine status based on performance metrics
                issues = []

                # Check hit rate (should be > 80% for healthy cache)
                if hit_rate < 0.8:
                    issues.append(f"Low cache hit rate: {hit_rate:.1%}")

                # Check instantaneous operations (should not be 0 for active Redis)
                if instantaneous_ops_per_sec == 0:
                    issues.append("No recent operations detected")

                if issues:
                    status = HealthStatus.DEGRADED
                    message = "; ".join(issues)
                else:
                    status = HealthStatus.HEALTHY
                    message = "Performance metrics are healthy"

                duration_ms = (time.time() - start_time) * 1000

                return HealthCheckResult(
                    check_type=HealthCheckType.PERFORMANCE,
                    status=status,
                    message=message,
                    duration_ms=duration_ms,
                    details={
                        "keyspace_hits": keyspace_hits,
                        "keyspace_misses": keyspace_misses,
                        "total_commands_processed": total_commands_processed,
                        "instantaneous_ops_per_sec": instantaneous_ops_per_sec,
                        "hit_rate": hit_rate,
                        "hit_rate_percentage": hit_rate * 100,
                        "used_cpu_sys": used_cpu_sys,
                        "used_cpu_user": used_cpu_user,
                    },
                    project_id=project_id,
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_type=HealthCheckType.PERFORMANCE,
                status=HealthStatus.UNKNOWN,
                message=f"Failed to check performance: {str(e)}",
                duration_ms=duration_ms,
                details={"error": str(e)},
                project_id=project_id,
            )

    async def _check_persistence(self, project_id: UUID) -> HealthCheckResult:
        """Check Redis persistence configuration."""
        start_time = time.time()

        try:
            async with redis_connection_factory.get_connection(
                str(project_id)
            ) as redis_client:
                # Get persistence info
                persistence_info = await redis_client.info("persistence")

                # Extract persistence metrics
                loading = persistence_info.get("loading", 0)
                rdb_changes_since_last_save = persistence_info.get(
                    "rdb_changes_since_last_save", 0
                )
                rdb_bgsave_in_progress = persistence_info.get(
                    "rdb_bgsave_in_progress", 0
                )
                rdb_last_save_time = persistence_info.get("rdb_last_save_time", 0)
                aof_enabled = persistence_info.get("aof_enabled", 0)
                aof_rewrite_in_progress = persistence_info.get(
                    "aof_rewrite_in_progress", 0
                )

                # Check if Redis is loading data from disk
                if loading == 1:
                    status = HealthStatus.DEGRADED
                    message = "Redis is currently loading data from disk"
                elif rdb_bgsave_in_progress == 1 or aof_rewrite_in_progress == 1:
                    status = HealthStatus.DEGRADED
                    message = "Background save operation in progress"
                else:
                    status = HealthStatus.HEALTHY
                    message = "Persistence is functioning normally"

                # Calculate time since last save
                last_save_time = (
                    datetime.fromtimestamp(rdb_last_save_time)
                    if rdb_last_save_time > 0
                    else None
                )
                time_since_last_save = None
                if last_save_time:
                    time_since_last_save = (
                        datetime.utcnow() - last_save_time
                    ).total_seconds()

                duration_ms = (time.time() - start_time) * 1000

                return HealthCheckResult(
                    check_type=HealthCheckType.PERSISTENCE,
                    status=status,
                    message=message,
                    duration_ms=duration_ms,
                    details={
                        "loading": loading,
                        "rdb_changes_since_last_save": rdb_changes_since_last_save,
                        "rdb_bgsave_in_progress": rdb_bgsave_in_progress,
                        "rdb_last_save_time": rdb_last_save_time,
                        "rdb_last_save_datetime": last_save_time.isoformat()
                        if last_save_time
                        else None,
                        "time_since_last_save_seconds": time_since_last_save,
                        "aof_enabled": aof_enabled,
                        "aof_rewrite_in_progress": aof_rewrite_in_progress,
                    },
                    project_id=project_id,
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_type=HealthCheckType.PERSISTENCE,
                status=HealthStatus.UNKNOWN,
                message=f"Failed to check persistence: {str(e)}",
                duration_ms=duration_ms,
                details={"error": str(e)},
                project_id=project_id,
            )

    def _determine_overall_status(
        self, checks: List[HealthCheckResult]
    ) -> HealthStatus:
        """Determine overall health status from individual check results."""
        if not checks:
            return HealthStatus.UNKNOWN

        # Check for unhealthy status first
        unhealthy_checks = [c for c in checks if c.status == HealthStatus.UNHEALTHY]
        if unhealthy_checks:
            return HealthStatus.UNHEALTHY

        # Check for degraded status
        degraded_checks = [c for c in checks if c.status == HealthStatus.DEGRADED]
        if degraded_checks:
            return HealthStatus.DEGRADED

        # Check for unknown status
        unknown_checks = [c for c in checks if c.status == HealthStatus.UNKNOWN]
        if unknown_checks:
            return HealthStatus.DEGRADED  # Unknown is treated as degraded

        # All checks are healthy
        return HealthStatus.HEALTHY

    async def _get_redis_server_info(self, project_id: UUID) -> Dict[str, Any]:
        """Get Redis server information."""
        try:
            async with redis_connection_factory.get_connection(
                str(project_id)
            ) as redis_client:
                server_info = await redis_client.info("server")
                return {
                    "redis_version": server_info.get("redis_version", "unknown"),
                    "redis_mode": server_info.get("redis_mode", "standalone"),
                    "os": server_info.get("os", "unknown"),
                    "arch_bits": server_info.get("arch_bits", 0),
                    "uptime_in_seconds": server_info.get("uptime_in_seconds", 0),
                    "uptime_in_days": server_info.get("uptime_in_days", 0),
                }
        except Exception as e:
            logger.error("Failed to get Redis server info", error=str(e))
            return {
                "redis_version": "unknown",
                "redis_mode": "unknown",
                "os": "unknown",
                "arch_bits": 0,
                "uptime_in_seconds": 0,
                "uptime_in_days": 0,
            }

    def _generate_health_summary(
        self, checks: List[HealthCheckResult]
    ) -> Dict[str, Any]:
        """Generate health summary from check results."""
        summary = {
            "total_checks": len(checks),
            "healthy_checks": len(
                [c for c in checks if c.status == HealthStatus.HEALTHY]
            ),
            "degraded_checks": len(
                [c for c in checks if c.status == HealthStatus.DEGRADED]
            ),
            "unhealthy_checks": len(
                [c for c in checks if c.status == HealthStatus.UNHEALTHY]
            ),
            "unknown_checks": len(
                [c for c in checks if c.status == HealthStatus.UNKNOWN]
            ),
            "total_duration_ms": sum(c.duration_ms for c in checks),
            "checks_by_type": {},
        }

        # Group checks by type
        for check in checks:
            check_type = check.check_type.value
            if check_type not in summary["checks_by_type"]:
                summary["checks_by_type"][check_type] = {
                    "status": check.status.value,
                    "message": check.message,
                    "duration_ms": check.duration_ms,
                }

        return summary

    def _generate_health_alerts(self, checks: List[HealthCheckResult]) -> List[str]:
        """Generate health alerts from check results."""
        alerts = []

        for check in checks:
            if check.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]:
                alerts.append(f"{check.check_type.value.upper()}: {check.message}")

        return alerts

    async def _log_health_status(self, health_status: RedisHealthStatus) -> None:
        """Log health status with appropriate level."""
        log_method = {
            HealthStatus.HEALTHY: logger.info,
            HealthStatus.DEGRADED: logger.warning,
            HealthStatus.UNHEALTHY: logger.error,
            HealthStatus.UNKNOWN: logger.warning,
        }.get(health_status.status, logger.info)

        log_method(
            "Redis health status",
            status=health_status.status.value,
            uptime_seconds=health_status.uptime_seconds,
            version=health_status.version,
            mode=health_status.mode,
            checks_count=len(health_status.checks),
            alerts_count=len(health_status.alerts),
            summary=health_status.summary,
        )

        # Log individual alerts if any
        for alert in health_status.alerts:
            logger.warning("Redis health alert", alert=alert)

    async def get_latest_health_status(
        self, project_id: UUID
    ) -> Optional[RedisHealthStatus]:
        """Get the latest health status."""
        if project_id in self._latest_health_status:
            return self._latest_health_status[project_id]

        # If no cached status, perform a new health check
        return await self.perform_full_health_check(project_id)

    async def check_specific_component(
        self,
        check_type: HealthCheckType,
        project_id: UUID,
    ) -> HealthCheckResult:
        """Check a specific component."""
        check_methods = {
            HealthCheckType.BASIC_CONNECTIVITY: self._check_basic_connectivity,
            HealthCheckType.MEMORY_USAGE: self._check_memory_usage,
            HealthCheckType.CONNECTION_POOL: self._check_connection_pool,
            HealthCheckType.PERFORMANCE: self._check_performance,
            HealthCheckType.PERSISTENCE: self._check_persistence,
        }

        # Handle REPLICATION check type - not implemented yet
        if check_type == HealthCheckType.REPLICATION:
            # TODO: Implement Redis replication health check
            # This should check replication lag, slave status, sync status, etc.
            return HealthCheckResult(
                check_type=HealthCheckType.REPLICATION,
                status=HealthStatus.UNKNOWN,
                message="Replication health check is not implemented yet",
                details={"implementation_status": "TODO", "error": "Not implemented"},
                project_id=project_id,
            )

        check_method = check_methods.get(check_type)
        if not check_method:
            raise ValueError(f"Unsupported health check type: {check_type}")

        return await check_method(project_id)


# Global Redis health checker instance
redis_health_checker = RedisHealthChecker()
