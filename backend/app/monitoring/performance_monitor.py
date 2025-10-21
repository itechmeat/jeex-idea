"""
Redis Performance Monitor

Advanced Redis performance monitoring with real-time analytics.
Tracks command performance, connection efficiency, and system resource usage.
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
from collections import defaultdict, deque
import statistics

from redis.asyncio import Redis
from redis.exceptions import RedisError
import structlog

from ..core.config import settings
from ..infrastructure.redis.connection_factory import redis_connection_factory
from .redis_metrics import redis_metrics_collector, RedisCommandType

logger = structlog.get_logger(__name__)


class PerformanceLevel(Enum):
    """Performance level classifications."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


@dataclass
class CommandPerformanceStats:
    """Performance statistics for Redis commands."""

    command: str
    command_type: RedisCommandType
    count: int
    success_count: int
    error_count: int
    total_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    avg_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
    p99_duration_ms: float
    error_rate: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ConnectionPerformanceStats:
    """Performance statistics for Redis connections."""

    pool_name: str
    active_connections: int
    idle_connections: int
    total_connections: int
    max_connections: int
    connection_utilization: float
    avg_response_time_ms: float
    connection_errors: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MemoryPerformanceStats:
    """Performance statistics for Redis memory usage."""

    used_memory_mb: float
    max_memory_mb: float
    memory_percentage: float
    fragmentation_ratio: float
    hit_rate: float
    eviction_rate: float
    key_count: int
    expire_count: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PerformanceInsight:
    """Performance insight with recommendations."""

    metric_name: str
    current_value: float
    threshold: float
    performance_level: PerformanceLevel
    message: str
    recommendations: List[str]
    timestamp: datetime = field(default_factory=datetime.utcnow)


class RedisPerformanceMonitor:
    """
    Advanced Redis performance monitoring with real-time analytics.

    Features:
    - Command performance analysis with percentile tracking
    - Connection pool efficiency monitoring
    - Memory performance analytics
    - Performance insights and recommendations
    - Real-time performance alerts
    - Project-scoped performance tracking
    - Historical performance trending
    """

    def __init__(self):
        self.settings = settings

        # Performance thresholds
        self.excellent_response_time_ms = 10  # < 10ms = excellent
        self.good_response_time_ms = 25  # < 25ms = good
        self.fair_response_time_ms = 50  # < 50ms = fair
        self.poor_response_time_ms = 100  # < 100ms = poor
        self.critical_response_time_ms = 1000  # > 1s = critical

        self.excellent_hit_rate = 0.95  # > 95% = excellent
        self.good_hit_rate = 0.90  # > 90% = good
        self.fair_hit_rate = 0.80  # > 80% = fair
        self.poor_hit_rate = 0.70  # > 70% = poor

        self.excellent_memory_usage = 0.5  # < 50% = excellent
        self.good_memory_usage = 0.7  # < 70% = good
        self.fair_memory_usage = 0.8  # < 80% = fair
        self.poor_memory_usage = 0.9  # < 90% = poor

        # Performance data storage
        self._command_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )
        self._connection_history: deque = deque(maxlen=100)
        self._memory_history: deque = deque(maxlen=100)
        self._insights: List[PerformanceInsight] = []
        self._max_insights = 100

        # Performance analysis task
        self._analysis_task: Optional[asyncio.Task] = None

        logger.info(
            "Redis performance monitor initialized",
            excellent_response_time_ms=self.excellent_response_time_ms,
            excellent_hit_rate=self.excellent_hit_rate,
            excellent_memory_usage=self.excellent_memory_usage,
        )

    async def start_monitoring(self) -> None:
        """Start background performance monitoring."""
        if self._analysis_task is None:
            self._analysis_task = asyncio.create_task(self._analysis_loop())
            logger.info("Redis performance monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop background performance monitoring."""
        if self._analysis_task:
            self._analysis_task.cancel()
            try:
                await self._analysis_task
            except asyncio.CancelledError:
                pass
            self._analysis_task = None
            logger.info("Redis performance monitoring stopped")

    async def _analysis_loop(self) -> None:
        """Background performance analysis loop."""
        while True:
            try:
                await self._analyze_command_performance()
                await self._analyze_connection_performance()
                await self._analyze_memory_performance()
                await self._generate_performance_insights()
                await self._cleanup_old_data()
                await asyncio.sleep(60)  # Analyze every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Redis performance analysis error", error=str(e))
                await asyncio.sleep(60)

    async def track_command_performance(
        self,
        command: str,
        command_type: RedisCommandType,
        duration_ms: float,
        success: bool,
        project_id: Optional[UUID] = None,
    ) -> None:
        """
        Track command performance for analysis.

        Args:
            command: Redis command executed
            command_type: Type of command
            duration_ms: Execution duration
            success: Whether command succeeded
            project_id: Optional project ID
        """
        # Store in command history
        command_key = f"{command_type.value}:{command}"
        self._command_history[command_key].append(
            {
                "duration_ms": duration_ms,
                "success": success,
                "timestamp": datetime.utcnow(),
                "project_id": project_id,
            }
        )

        logger.debug(
            "Command performance tracked",
            command=command,
            command_type=command_type.value,
            duration_ms=duration_ms,
            success=success,
            project_id=project_id,
        )

    async def _analyze_command_performance(self) -> None:
        """Analyze command performance statistics."""
        current_time = datetime.utcnow()
        cutoff_time = current_time - timedelta(minutes=5)  # Analyze last 5 minutes

        command_stats = {}

        for command_key, executions in self._command_history.items():
            # Filter recent executions
            recent_executions = [e for e in executions if e["timestamp"] > cutoff_time]

            if not recent_executions:
                continue

            # Calculate statistics
            durations = [e["duration_ms"] for e in recent_executions]
            success_count = sum(1 for e in recent_executions if e["success"])
            error_count = len(recent_executions) - success_count

            command_parts = command_key.split(":", 1)
            command_type = RedisCommandType(command_parts[0])
            command = command_parts[1] if len(command_parts) > 1 else "unknown"

            # Calculate percentiles
            sorted_durations = sorted(durations)
            p50 = statistics.median(sorted_durations) if sorted_durations else 0
            p95 = (
                sorted_durations[int(len(sorted_durations) * 0.95)]
                if sorted_durations
                else 0
            )
            p99 = (
                sorted_durations[int(len(sorted_durations) * 0.99)]
                if sorted_durations
                else 0
            )

            stats = CommandPerformanceStats(
                command=command,
                command_type=command_type,
                count=len(recent_executions),
                success_count=success_count,
                error_count=error_count,
                total_duration_ms=sum(durations),
                min_duration_ms=min(durations) if durations else 0,
                max_duration_ms=max(durations) if durations else 0,
                avg_duration_ms=statistics.mean(durations) if durations else 0,
                p50_duration_ms=p50,
                p95_duration_ms=p95,
                p99_duration_ms=p99,
                error_rate=error_count / len(recent_executions)
                if recent_executions
                else 0,
            )

            command_stats[command_key] = stats

            # Log slow commands
            if stats.p95_duration_ms > self.poor_response_time_ms:
                logger.warning(
                    "Slow command detected",
                    command=command,
                    command_type=command_type.value,
                    p95_duration_ms=stats.p95_duration_ms,
                    count=stats.count,
                )

        # Store analysis results
        if command_stats:
            logger.debug(
                "Command performance analysis completed",
                commands_analyzed=len(command_stats),
                total_executions=sum(s.count for s in command_stats.values()),
            )

    async def _analyze_connection_performance(self) -> None:
        """Analyze connection pool performance."""
        try:
            # Get current connection metrics
            factory_metrics = redis_connection_factory.get_metrics()

            async with redis_connection_factory.get_connection() as redis_client:
                client_info = await redis_client.info("clients")
                connected_clients = client_info.get("connected_clients", 0)

            # Calculate connection statistics
            pools = factory_metrics.get("pools", {})
            default_pool = pools.get("default", {})
            max_connections = default_pool.get("max_connections", 10)
            created_connections = default_pool.get("created_connections", 0)

            connection_utilization = (
                connected_clients / max_connections if max_connections > 0 else 0
            )

            # Create connection performance stats
            connection_stats = ConnectionPerformanceStats(
                pool_name="default",
                active_connections=connected_clients,
                idle_connections=max(0, max_connections - connected_clients),
                total_connections=created_connections,
                max_connections=max_connections,
                connection_utilization=connection_utilization,
                avg_response_time_ms=0,  # Would need additional tracking
                connection_errors=0,  # Would need additional tracking
            )

            # Store in history
            self._connection_history.append(connection_stats)

            # Log connection issues
            if connection_utilization > 0.9:
                logger.warning(
                    "High connection pool utilization",
                    utilization=connection_utilization,
                    active_connections=connected_clients,
                    max_connections=max_connections,
                )

        except Exception as e:
            logger.error("Failed to analyze connection performance", error=str(e))

    async def _analyze_memory_performance(self) -> None:
        """Analyze memory performance."""
        try:
            async with redis_connection_factory.get_connection() as redis_client:
                # Get memory and stats info
                memory_info = await redis_client.info("memory")
                stats_info = await redis_client.info("stats")

                # Extract memory metrics
                used_memory = memory_info.get("used_memory", 0)
                max_memory = memory_info.get("maxmemory", 0)
                used_memory_rss = memory_info.get("used_memory_rss", 0)
                mem_fragmentation_ratio = (
                    used_memory_rss / used_memory if used_memory > 0 else 1
                )

                # Calculate memory percentage
                memory_percentage = (
                    (used_memory / max_memory * 100) if max_memory > 0 else 0
                )

                # Get cache statistics
                keyspace_hits = stats_info.get("keyspace_hits", 0)
                keyspace_misses = stats_info.get("keyspace_misses", 0)
                total_requests = keyspace_hits + keyspace_misses
                hit_rate = keyspace_hits / total_requests if total_requests > 0 else 0

                # Get eviction statistics
                evicted_keys = stats_info.get("evicted_keys", 0)
                expired_keys = stats_info.get("expired_keys", 0)

                # Get key count
                keyspace_info = await redis_client.info("keyspace")
                key_count = 0
                for db_stats in keyspace_info.values():
                    if isinstance(db_stats, dict):
                        key_count += db_stats.get("keys", 0)

                # Create memory performance stats
                memory_stats = MemoryPerformanceStats(
                    used_memory_mb=used_memory / 1024 / 1024,
                    max_memory_mb=max_memory / 1024 / 1024,
                    memory_percentage=memory_percentage,
                    fragmentation_ratio=mem_fragmentation_ratio,
                    hit_rate=hit_rate,
                    eviction_rate=evicted_keys / 1000,  # Rate per second (approximate)
                    key_count=key_count,
                    expire_count=expired_keys,
                )

                # Store in history
                self._memory_history.append(memory_stats)

                # Log memory issues
                if memory_percentage > 90:
                    logger.warning(
                        "Critical memory usage",
                        memory_percentage=memory_percentage,
                        used_memory_mb=memory_stats.used_memory_mb,
                    )

                if hit_rate < 0.8:
                    logger.warning(
                        "Low cache hit rate",
                        hit_rate=hit_rate,
                        keyspace_hits=keyspace_hits,
                        keyspace_misses=keyspace_misses,
                    )

        except Exception as e:
            logger.error("Failed to analyze memory performance", error=str(e))

    async def _generate_performance_insights(self) -> None:
        """Generate performance insights and recommendations."""
        insights = []

        # Analyze command performance
        for command_key, executions in self._command_history.items():
            if not executions:
                continue

            recent_executions = [
                e
                for e in executions
                if e["timestamp"] > datetime.utcnow() - timedelta(minutes=5)
            ]

            if len(recent_executions) < 10:  # Need sufficient data
                continue

            durations = [e["duration_ms"] for e in recent_executions]
            avg_duration = statistics.mean(durations)
            p95_duration = sorted(durations)[int(len(durations) * 0.95)]

            # Generate insights for slow commands
            if p95_duration > self.poor_response_time_ms:
                performance_level = (
                    PerformanceLevel.POOR
                    if p95_duration < self.critical_response_time_ms
                    else PerformanceLevel.CRITICAL
                )

                command_parts = command_key.split(":", 1)
                command_type = command_parts[0]
                command_name = command_parts[1] if len(command_parts) > 1 else "unknown"

                recommendations = [
                    f"Consider optimizing {command_name} command execution",
                    "Check for large values being stored/retrieved",
                    "Review Redis configuration for performance tuning",
                ]

                if command_type == "read":
                    recommendations.extend(
                        [
                            "Consider using Redis pipelining for multiple reads",
                            "Check if data can be cached more efficiently",
                        ]
                    )
                elif command_type == "write":
                    recommendations.extend(
                        [
                            "Consider using batch operations for multiple writes",
                            "Review write-heavy operations for optimization",
                        ]
                    )

                insight = PerformanceInsight(
                    metric_name=f"command_{command_key}_p95_duration",
                    current_value=p95_duration,
                    threshold=self.poor_response_time_ms,
                    performance_level=performance_level,
                    message=f"{command_name} command P95 response time is {p95_duration:.2f}ms",
                    recommendations=recommendations,
                )

                insights.append(insight)

        # Analyze memory performance
        if self._memory_history:
            latest_memory = self._memory_history[-1]

            if latest_memory.memory_percentage > self.poor_memory_usage:
                performance_level = (
                    PerformanceLevel.CRITICAL
                    if latest_memory.memory_percentage > 0.9
                    else PerformanceLevel.POOR
                )

                recommendations = [
                    "Review and clean up unused keys",
                    "Consider increasing Redis memory limit",
                    "Implement more aggressive TTL policies",
                    "Review data serialization efficiency",
                ]

                insight = PerformanceInsight(
                    metric_name="memory_usage_percentage",
                    current_value=latest_memory.memory_percentage,
                    threshold=self.poor_memory_usage,
                    performance_level=performance_level,
                    message=f"Memory usage is {latest_memory.memory_percentage:.1f}% of limit",
                    recommendations=recommendations,
                )

                insights.append(insight)

            if latest_memory.hit_rate < self.poor_hit_rate:
                performance_level = (
                    PerformanceLevel.POOR
                    if latest_memory.hit_rate > 0.6
                    else PerformanceLevel.CRITICAL
                )

                recommendations = [
                    "Review cache access patterns",
                    "Consider increasing TTL for frequently accessed data",
                    "Implement cache warming strategies",
                    "Review cache key design for better hit rates",
                ]

                insight = PerformanceInsight(
                    metric_name="cache_hit_rate",
                    current_value=latest_memory.hit_rate,
                    threshold=self.poor_hit_rate,
                    performance_level=performance_level,
                    message=f"Cache hit rate is {latest_memory.hit_rate:.1%}",
                    recommendations=recommendations,
                )

                insights.append(insight)

        # Store insights
        self._insights.extend(insights)

        # Keep only recent insights
        if len(self._insights) > self._max_insights:
            self._insights = self._insights[-self._max_insights :]

        # Log insights
        for insight in insights:
            log_method = {
                PerformanceLevel.EXCELLENT: logger.debug,
                PerformanceLevel.GOOD: logger.info,
                PerformanceLevel.FAIR: logger.warning,
                PerformanceLevel.POOR: logger.warning,
                PerformanceLevel.CRITICAL: logger.error,
            }.get(insight.performance_level, logger.info)

            log_method(
                "Performance insight generated",
                metric_name=insight.metric_name,
                current_value=insight.current_value,
                threshold=insight.threshold,
                performance_level=insight.performance_level.value,
                message=insight.message,
                recommendations_count=len(insight.recommendations),
            )

    async def _cleanup_old_data(self) -> None:
        """Clean up old performance data."""
        cutoff_time = datetime.utcnow() - timedelta(hours=1)

        # Clean up command history
        for command_key in list(self._command_history.keys()):
            executions = self._command_history[command_key]
            self._command_history[command_key] = deque(
                [e for e in executions if e["timestamp"] > cutoff_time], maxlen=1000
            )

            # Remove empty command histories
            if not self._command_history[command_key]:
                del self._command_history[command_key]

        # Clean up insights
        self._insights = [
            insight for insight in self._insights if insight.timestamp > cutoff_time
        ]

    async def get_performance_dashboard(
        self, project_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Get comprehensive performance dashboard data."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "project_id": str(project_id) if project_id else None,
            "performance_summary": await self._get_performance_summary(),
            "command_performance": await self._get_command_performance_summary(),
            "connection_performance": await self._get_connection_performance_summary(),
            "memory_performance": await self._get_memory_performance_summary(),
            "performance_insights": await self._get_performance_insights(),
            "recommendations": await self._get_performance_recommendations(),
        }

    async def _get_performance_summary(self) -> Dict[str, Any]:
        """Get overall performance summary."""
        if not self._memory_history:
            return {"status": "no_data"}

        latest_memory = self._memory_history[-1]

        # Determine overall performance level
        memory_level = self._get_performance_level(
            latest_memory.memory_percentage,
            [
                self.excellent_memory_usage,
                self.good_memory_usage,
                self.fair_memory_usage,
                self.poor_memory_usage,
            ],
        )

        hit_rate_level = self._get_performance_level(
            latest_memory.hit_rate,
            [
                self.excellent_hit_rate,
                self.good_hit_rate,
                self.fair_hit_rate,
                self.poor_hit_rate,
            ],
            reverse=True,  # Higher hit rate is better
        )

        # Overall level is the worse of the two
        overall_level = max(memory_level, hit_rate_level, key=lambda x: x.value)

        return {
            "overall_performance_level": overall_level.value,
            "memory_performance_level": memory_level.value,
            "hit_rate_performance_level": hit_rate_level.value,
            "memory_usage_percentage": latest_memory.memory_percentage,
            "cache_hit_rate": latest_memory.hit_rate,
            "fragmentation_ratio": latest_memory.fragmentation_ratio,
            "active_connections": self._connection_history[-1].active_connections
            if self._connection_history
            else 0,
        }

    def _get_performance_level(
        self, value: float, thresholds: List[float], reverse: bool = False
    ) -> PerformanceLevel:
        """Get performance level based on value and thresholds."""
        if reverse:
            # For metrics where higher is better (like hit rate)
            if value >= thresholds[0]:
                return PerformanceLevel.EXCELLENT
            elif value >= thresholds[1]:
                return PerformanceLevel.GOOD
            elif value >= thresholds[2]:
                return PerformanceLevel.FAIR
            elif value >= thresholds[3]:
                return PerformanceLevel.POOR
            else:
                return PerformanceLevel.CRITICAL
        else:
            # For metrics where lower is better (like memory usage)
            if value <= thresholds[0]:
                return PerformanceLevel.EXCELLENT
            elif value <= thresholds[1]:
                return PerformanceLevel.GOOD
            elif value <= thresholds[2]:
                return PerformanceLevel.FAIR
            elif value <= thresholds[3]:
                return PerformanceLevel.POOR
            else:
                return PerformanceLevel.CRITICAL

    async def _get_command_performance_summary(self) -> Dict[str, Any]:
        """Get command performance summary."""
        command_summary = {}

        for command_key, executions in self._command_history.items():
            if not executions:
                continue

            recent_executions = [
                e
                for e in executions
                if e["timestamp"] > datetime.utcnow() - timedelta(minutes=5)
            ]

            if not recent_executions:
                continue

            durations = [e["duration_ms"] for e in recent_executions]
            success_count = sum(1 for e in recent_executions if e["success"])

            command_parts = command_key.split(":", 1)
            command_type = command_parts[0]
            command_name = command_parts[1] if len(command_parts) > 1 else "unknown"

            command_summary[command_key] = {
                "command": command_name,
                "command_type": command_type,
                "count_5m": len(recent_executions),
                "success_rate": success_count / len(recent_executions),
                "avg_duration_ms": statistics.mean(durations),
                "p95_duration_ms": sorted(durations)[int(len(durations) * 0.95)],
                "performance_level": self._get_performance_level(
                    sorted(durations)[int(len(durations) * 0.95)],
                    [
                        self.excellent_response_time_ms,
                        self.good_response_time_ms,
                        self.fair_response_time_ms,
                        self.poor_response_time_ms,
                    ],
                ).value,
            }

        return command_summary

    async def _get_connection_performance_summary(self) -> Dict[str, Any]:
        """Get connection performance summary."""
        if not self._connection_history:
            return {"status": "no_data"}

        latest = self._connection_history[-1]

        return {
            "active_connections": latest.active_connections,
            "idle_connections": latest.idle_connections,
            "max_connections": latest.max_connections,
            "connection_utilization": latest.connection_utilization,
            "utilization_percentage": latest.connection_utilization * 100,
            "performance_level": self._get_performance_level(
                latest.connection_utilization, [0.5, 0.7, 0.8, 0.9]
            ).value,
        }

    async def _get_memory_performance_summary(self) -> Dict[str, Any]:
        """Get memory performance summary."""
        if not self._memory_history:
            return {"status": "no_data"}

        latest = self._memory_history[-1]

        return {
            "used_memory_mb": latest.used_memory_mb,
            "max_memory_mb": latest.max_memory_mb,
            "memory_percentage": latest.memory_percentage,
            "fragmentation_ratio": latest.fragmentation_ratio,
            "hit_rate": latest.hit_rate,
            "key_count": latest.key_count,
            "eviction_rate": latest.eviction_rate,
            "memory_performance_level": self._get_performance_level(
                latest.memory_percentage,
                [
                    self.excellent_memory_usage,
                    self.good_memory_usage,
                    self.fair_memory_usage,
                    self.poor_memory_usage,
                ],
            ).value,
            "hit_rate_performance_level": self._get_performance_level(
                latest.hit_rate,
                [
                    self.excellent_hit_rate,
                    self.good_hit_rate,
                    self.fair_hit_rate,
                    self.poor_hit_rate,
                ],
                reverse=True,
            ).value,
        }

    async def _get_performance_insights(self) -> List[Dict[str, Any]]:
        """Get recent performance insights."""
        return [
            {
                "metric_name": insight.metric_name,
                "current_value": insight.current_value,
                "threshold": insight.threshold,
                "performance_level": insight.performance_level.value,
                "message": insight.message,
                "timestamp": insight.timestamp.isoformat(),
            }
            for insight in self._insights[-10:]  # Last 10 insights
        ]

    async def _get_performance_recommendations(self) -> List[str]:
        """Get performance recommendations."""
        recommendations = set()

        # Collect recommendations from recent insights
        for insight in self._insights[-20:]:  # Last 20 insights
            recommendations.update(insight.recommendations)

        # Add general recommendations based on current state
        if self._memory_history:
            latest_memory = self._memory_history[-1]

            if latest_memory.memory_percentage > 0.8:
                recommendations.add(
                    "Consider implementing Redis memory optimization strategies"
                )

            if latest_memory.hit_rate < 0.8:
                recommendations.add("Review caching strategy to improve hit rate")

        if self._connection_history:
            latest_connection = self._connection_history[-1]

            if latest_connection.connection_utilization > 0.8:
                recommendations.add("Consider increasing Redis connection pool size")

        return list(recommendations)


# Global Redis performance monitor instance
redis_performance_monitor = RedisPerformanceMonitor()
