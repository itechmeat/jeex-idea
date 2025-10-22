"""
Instrumented Redis Service Wrapper

Enhanced Redis service with comprehensive OpenTelemetry instrumentation.
This wrapper integrates with the existing Redis service to provide detailed
operation tracing, cache metrics, and performance monitoring.

Implements Task 2.2 requirements:
- Redis client instrumentation capturing operation spans
- Cache hit/miss ratios calculated and exported as metrics
- Operation latency metrics (GET, SET, DEL, etc.)
- Memory usage statistics from Redis INFO command
- Connection pool metrics and error rates
"""

import asyncio
import logging
import time
from typing import Dict, Any, Union, List, Optional, Callable
from contextlib import asynccontextmanager
from uuid import UUID

import redis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from ...core.redis_instrumentation import redis_instrumentation, RedisCommandCategory
from ...core.telemetry import get_tracer, add_span_attribute
from .redis_service import RedisService, redis_service
from .connection_factory import redis_connection_factory

logger = logging.getLogger(__name__)


class InstrumentedRedisService:
    """
    Instrumented Redis service wrapper with comprehensive OpenTelemetry integration.

    Provides enhanced monitoring while maintaining all existing Redis service functionality.
    """

    def __init__(self, base_service: RedisService):
        self.base_service = base_service
        self.tracer = get_tracer(__name__)

    async def initialize(self) -> None:
        """Initialize both base service and instrumentation."""
        await self.base_service.initialize()

        # Start background collection for enhanced metrics
        try:
            async with self.base_service._get_system_connection() as redis_client:
                await redis_instrumentation.start_background_collection(redis_client)
        except Exception as e:
            logger.warning(f"Failed to start enhanced Redis instrumentation: {e}")

    @asynccontextmanager
    async def get_connection(self, project_id: Union[str, UUID]):
        """
        Get Redis connection with enhanced instrumentation.

        Args:
            project_id: Project ID for key isolation

        Yields:
            Instrumented Redis client wrapper
        """
        async with self.base_service.get_connection(project_id) as redis_client:
            yield InstrumentedRedisClient(redis_client, project_id)

    @asynccontextmanager
    async def _get_system_connection(self):
        """Get system-level Redis connection."""
        async with self.base_service._get_system_connection() as redis_client:
            yield InstrumentedRedisClient(redis_client, None, is_system_connection=True)

    async def execute_with_retry(
        self, operation: str, func, *args, project_id: str, **kwargs
    ) -> Any:
        """
        Execute Redis operation with enhanced tracing and retry logic.

        Args:
            operation: Operation description
            func: Redis function to execute
            *args: Function arguments
            project_id: Project ID for connection isolation
            **kwargs: Function keyword arguments

        Returns:
            Operation result
        """
        # Use enhanced instrumentation wrapper
        async with redis_instrumentation.trace_operation(
            operation, UUID(project_id)
        ) as span:
            try:
                result = await self.base_service.execute_with_retry(
                    operation, func, *args, project_id=project_id, **kwargs
                )

                # Add custom span attributes
                add_span_attribute("redis.operation_type", operation)
                add_span_attribute("redis.project_isolated", True)

                return result

            except Exception as e:
                # Error attributes are already added by the enhanced instrumentation
                raise

    async def get_comprehensive_metrics(
        self, project_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive Redis metrics including enhanced instrumentation data.

        Args:
            project_id: Optional project ID for scoped metrics

        Returns:
            Comprehensive metrics dictionary
        """
        # Get base service metrics
        base_metrics = self.base_service.get_metrics()

        # Get enhanced instrumentation metrics
        cache_performance = redis_instrumentation.get_cache_performance_summary()
        error_stats = redis_instrumentation.get_error_rate_stats()
        latency_stats = await redis_instrumentation.get_command_latency_stats()

        # Get memory stats if possible
        memory_stats = {}
        try:
            async with self._get_system_connection() as redis_client:
                memory_stats = await redis_instrumentation.collect_redis_info(
                    redis_client
                )
                memory_stats = {
                    "used_memory_mb": memory_stats.used_memory / 1024 / 1024,
                    "used_memory_rss_mb": memory_stats.used_memory_rss / 1024 / 1024,
                    "max_memory_mb": memory_stats.max_memory / 1024 / 1024,
                    "fragmentation_ratio": memory_stats.memory_fragmentation_ratio,
                    "maxmemory_policy": memory_stats.maxmemory_policy,
                    "allocator_allocated_mb": memory_stats.allocator_allocated
                    / 1024
                    / 1024,
                    "allocator_active_mb": memory_stats.allocator_active / 1024 / 1024,
                }
        except Exception as e:
            logger.warning(f"Failed to collect memory stats: {e}")

        # Get connection pool stats
        connection_stats = {}
        try:
            connection_stats = await redis_instrumentation.collect_connection_stats(
                project_id=project_id
            )
            connection_stats = {
                "pool_name": connection_stats.pool_name,
                "active_connections": connection_stats.active_connections,
                "idle_connections": connection_stats.idle_connections,
                "max_connections": connection_stats.max_connections,
                "connection_utilization": connection_stats.connection_utilization,
                "connection_errors_total": connection_stats.connection_errors_total,
                "connection_timeouts_total": connection_stats.connection_timeouts_total,
            }
        except Exception as e:
            logger.warning(f"Failed to collect connection stats: {e}")

        return {
            "timestamp": time.time(),
            "project_id": str(project_id) if project_id else None,
            "base_service": base_metrics,
            "cache_performance": cache_performance,
            "error_rates": error_stats,
            "command_latencies": latency_stats,
            "memory_usage": memory_stats,
            "connection_pool": connection_stats,
        }

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform enhanced health check with instrumentation metrics.

        Returns:
            Comprehensive health status
        """
        # Get base health check
        base_health = await self.base_service.health_check()

        # Add instrumentation-specific health indicators
        enhanced_health = {
            "instrumentation_status": "healthy",
            "cache_hit_ratio": redis_instrumentation.get_cache_performance_summary()[
                "hit_ratio"
            ],
            "recent_error_rate": redis_instrumentation.get_error_rate_stats()[
                "error_rate"
            ],
        }

        # Combine health information
        combined_health = {
            **base_health,
            "enhanced_instrumentation": enhanced_health,
        }

        # Determine overall status
        if enhanced_health["recent_error_rate"] > 0.1:  # 10% error rate threshold
            combined_health["status"] = "degraded"
            combined_health["instrumentation_status"] = "degraded"

        return combined_health

    async def close(self) -> None:
        """Close both base service and instrumentation."""
        await redis_instrumentation.stop_background_collection()
        await self.base_service.close()


class InstrumentedRedisClient:
    """
    Instrumented Redis client wrapper that automatically traces operations.

    Wraps Redis client operations with OpenTelemetry spans and metrics collection.
    """

    def __init__(
        self,
        redis_client: Union[Redis, "ProjectIsolatedRedisClient"],
        project_id: Optional[Union[str, UUID]] = None,
        is_system_connection: bool = False,
    ):
        self._redis = redis_client
        self._project_id = (
            UUID(project_id) if isinstance(project_id, str) else project_id
        )
        self._is_system_connection = is_system_connection

    def _validate_key(self, key: str) -> None:
        """Validate Redis key parameter."""
        if not isinstance(key, str):
            raise ValueError(f"Redis key must be a string, got {type(key)}")
        if not key.strip():
            raise ValueError("Redis key cannot be empty or whitespace")

    def _validate_value(self, value) -> None:
        """Validate Redis value parameter."""
        if value is None:
            raise ValueError("Redis value cannot be None")
        if not isinstance(value, (str, bytes, int, float)):
            raise ValueError(
                f"Redis value must be a string, bytes, or number, got {type(value)}"
            )

    def _validate_ttl(self, seconds: int) -> None:
        """Validate TTL/expires parameter."""
        if not isinstance(seconds, int):
            raise ValueError(f"TTL must be an integer, got {type(seconds)}")
        if seconds < 0:
            raise ValueError("TTL must be non-negative")

    def _validate_name_and_key(self, name: str, key: str) -> None:
        """Validate hash field name and key."""
        self._validate_key(name)
        if not isinstance(key, str):
            raise ValueError(f"Hash field key must be a string, got {type(key)}")
        if not key.strip():
            raise ValueError("Hash field key cannot be empty or whitespace")

    def _validate_mapping(self, mapping: dict) -> None:
        """Validate hash mapping parameter."""
        if not isinstance(mapping, dict):
            raise ValueError(f"Hash mapping must be a dict, got {type(mapping)}")
        if not mapping:
            raise ValueError("Hash mapping cannot be empty")

    async def get(self, key: str, **kwargs) -> Optional[str]:
        """GET operation with instrumentation."""
        self._validate_key(key)
        command = f"GET {key}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            result = await self._redis.get(key, **kwargs)
            # Cache hit detection - result is None for miss
            redis_instrumentation._cache_misses += 1 if result is None else 0
            redis_instrumentation._cache_hits += 1 if result is not None else 0
            return result

    async def set(self, key: str, value, **kwargs) -> bool:
        """SET operation with instrumentation."""
        self._validate_key(key)
        self._validate_value(value)
        command = f"SET {key}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.set(key, value, **kwargs)

    async def delete(self, key: str, **kwargs) -> int:
        """DELETE operation with instrumentation."""
        self._validate_key(key)
        command = f"DEL {key}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.delete(key, **kwargs)

    async def exists(self, key: str, **kwargs) -> int:
        """EXISTS operation with instrumentation."""
        self._validate_key(key)
        command = f"EXISTS {key}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.exists(key, **kwargs)

    async def expire(self, key: str, seconds: int, **kwargs) -> bool:
        """EXPIRE operation with instrumentation."""
        self._validate_key(key)
        self._validate_ttl(seconds)
        command = f"EXPIRE {key} {seconds}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.expire(key, seconds, **kwargs)

    async def ttl(self, key: str, **kwargs) -> int:
        """TTL operation with instrumentation."""
        self._validate_key(key)
        command = f"TTL {key}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.ttl(key, **kwargs)

    # Hash operations
    async def hget(self, name: str, key: str, **kwargs) -> Optional[str]:
        """HGET operation with instrumentation."""
        self._validate_name_and_key(name, key)
        command = f"HGET {name} {key}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.hget(name, key, **kwargs)

    async def hset(self, name: str, key: str, value, **kwargs) -> int:
        """HSET operation with instrumentation."""
        self._validate_name_and_key(name, key)
        self._validate_value(value)
        command = f"HSET {name} {key}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.hset(name, key, value, **kwargs)

    async def hgetall(self, name: str, **kwargs) -> dict:
        """HGETALL operation with instrumentation."""
        self._validate_key(name)
        command = f"HGETALL {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.hgetall(name, **kwargs)

    async def hmset(self, name: str, mapping: dict, **kwargs) -> bool:
        """HMSET operation with instrumentation."""
        self._validate_key(name)
        self._validate_mapping(mapping)
        command = f"HMSET {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.hmset(name, mapping, **kwargs)

    # List operations
    async def lpush(self, name: str, *values, **kwargs) -> int:
        """LPUSH operation with instrumentation."""
        command = f"LPUSH {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.lpush(name, *values, **kwargs)

    async def rpush(self, name: str, *values, **kwargs) -> int:
        """RPUSH operation with instrumentation."""
        command = f"RPUSH {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.rpush(name, *values, **kwargs)

    async def lpop(self, name: str, **kwargs) -> Optional[str]:
        """LPOP operation with instrumentation."""
        command = f"LPOP {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.lpop(name, **kwargs)

    async def rpop(self, name: str, **kwargs) -> Optional[str]:
        """RPOP operation with instrumentation."""
        command = f"RPOP {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.rpop(name, **kwargs)

    async def lrange(self, name: str, start: int, end: int, **kwargs) -> list:
        """LRANGE operation with instrumentation."""
        command = f"LRANGE {name} {start} {end}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.lrange(name, start, end, **kwargs)

    async def llen(self, name: str, **kwargs) -> int:
        """LLEN operation with instrumentation."""
        command = f"LLEN {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.llen(name, **kwargs)

    # Set operations
    async def sadd(self, name: str, *values, **kwargs) -> int:
        """SADD operation with instrumentation."""
        command = f"SADD {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.sadd(name, *values, **kwargs)

    async def smembers(self, name: str, **kwargs) -> set:
        """SMEMBERS operation with instrumentation."""
        command = f"SMEMBERS {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.smembers(name, **kwargs)

    async def srem(self, name: str, *values, **kwargs) -> int:
        """SREM operation with instrumentation."""
        command = f"SREM {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.srem(name, *values, **kwargs)

    # Sorted set operations
    async def zadd(self, name: str, mapping: dict, **kwargs) -> int:
        """ZADD operation with instrumentation."""
        command = f"ZADD {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.zadd(name, mapping, **kwargs)

    async def zrange(
        self, name: str, start: int, end: int, withscores: bool = False, **kwargs
    ) -> list:
        """ZRANGE operation with instrumentation."""
        command = f"ZRANGE {name} {start} {end}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.zrange(
                name, start, end, withscores=withscores, **kwargs
            )

    async def zrem(self, name: str, *values, **kwargs) -> int:
        """ZREM operation with instrumentation."""
        command = f"ZREM {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.zrem(name, *values, **kwargs)

    async def zcard(self, name: str, **kwargs) -> int:
        """ZCARD operation with instrumentation."""
        command = f"ZCARD {name}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.zcard(name, **kwargs)

    # Counter operations
    async def incr(self, key: str, amount: int = 1, **kwargs) -> int:
        """INCR operation with instrumentation."""
        command = f"INCR {key}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.incr(key, amount, **kwargs)

    async def incrby(self, key: str, amount: int = 1, **kwargs) -> int:
        """INCRBY operation with instrumentation."""
        command = f"INCRBY {key} {amount}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.incrby(key, amount, **kwargs)

    # Scan operations
    async def scan(
        self, cursor: int = 0, match: str = None, count: int = None, **kwargs
    ):
        """SCAN operation with instrumentation."""
        command = f"SCAN {cursor}"
        if match:
            command += f" MATCH {match}"
        if count:
            command += f" COUNT {count}"

        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.scan(
                cursor=cursor, match=match, count=count, **kwargs
            )

    async def scan_iter(self, match: str = None, count: int = None, **kwargs):
        """SCAN_ITER operation with instrumentation."""
        command = "SCAN_ITER"
        if match:
            command += f" MATCH {match}"

        async with redis_instrumentation.trace_operation(command, self._project_id):
            async for key in self._redis.scan_iter(match=match, count=count, **kwargs):
                yield key

    # System operations
    async def ping(self, **kwargs) -> bool:
        """PING operation with instrumentation."""
        command = "PING"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.ping(**kwargs)

    async def info(self, section: Optional[str] = None, **kwargs) -> dict:
        """INFO operation with instrumentation."""
        command = f"INFO {section}" if section else "INFO"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.info(section, **kwargs)

    async def flushdb(self, **kwargs) -> bool:
        """FLUSHDB operation with instrumentation."""
        command = "FLUSHDB"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.flushdb(**kwargs)

    async def flushall(self, **kwargs) -> bool:
        """FLUSHALL operation with instrumentation."""
        command = "FLUSHALL"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.flushall(**kwargs)

    # Memory operations
    async def memory_usage(self, key: str, **kwargs) -> Optional[int]:
        """MEMORY USAGE operation with instrumentation."""
        command = f"MEMORY USAGE {key}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.memory_usage(key, **kwargs)

    # Script operations
    async def eval(self, script: str, numkeys: int, *keys_and_args, **kwargs):
        """EVAL operation with instrumentation."""
        command = f"EVAL script_keys:{numkeys}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.eval(script, numkeys, *keys_and_args, **kwargs)

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args, **kwargs):
        """EVALSHA operation with instrumentation."""
        command = f"EVALSHA {sha} keys:{numkeys}"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.evalsha(sha, numkeys, *keys_and_args, **kwargs)

    async def script_load(self, script: str, **kwargs) -> str:
        """SCRIPT LOAD operation with instrumentation."""
        command = "SCRIPT LOAD"
        async with redis_instrumentation.trace_operation(command, self._project_id):
            return await self._redis.script_load(script, **kwargs)

    # Delegate unknown attributes to underlying client
    def __getattr__(self, name):
        """Delegate unknown attributes to underlying Redis client."""
        return getattr(self._redis, name)


# Global instrumented Redis service instance
instrumented_redis_service = InstrumentedRedisService(redis_service)
