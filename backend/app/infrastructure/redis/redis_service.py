"""
Redis Service - Domain-Driven Connection Management

Main Redis service class with connection pooling, health checks,
automatic reconnection, and project isolation enforcement.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Union, List
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

import redis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from ...core.config import settings
from .connection_factory import redis_connection_factory, ProjectIsolatedRedisClient
from .exceptions import (
    RedisException,
    RedisConnectionException,
    RedisOperationTimeoutException,
    RedisProjectIsolationException,
    RedisMemoryException,
)
from .circuit_breaker import RedisCircuitBreakerOpenException

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class RedisServiceConfig:
    """Configuration for Redis service."""

    # Connection settings
    max_connections: int = 10
    connection_timeout: float = 10.0
    operation_timeout: float = 10.0

    # Health check settings
    health_check_interval: float = 30.0
    health_check_timeout: float = 5.0

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0

    # Memory monitoring
    memory_warning_threshold: float = 0.8  # 80%
    memory_critical_threshold: float = 0.9  # 90%


class RedisService:
    """
    Main Redis service with connection pooling and health monitoring.

    Provides high-level Redis operations with automatic reconnection,
    circuit breaker protection, and project isolation enforcement.
    """

    def __init__(self, config: Optional[RedisServiceConfig] = None):
        self.config = config or RedisServiceConfig(
            max_connections=settings.REDIS_MAX_CONNECTIONS
        )
        self._initialized = False
        self._health_check_task: Optional[asyncio.Task] = None
        self._last_health_check: Optional[Dict[str, Any]] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize Redis service and start health monitoring."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            try:
                # Initialize connection factory
                await redis_connection_factory.initialize()

                # Start health monitoring
                self._health_check_task = asyncio.create_task(self._health_check_loop())

                self._initialized = True
                logger.info("Redis service initialized successfully")

            except Exception as e:
                logger.error(f"Failed to initialize Redis service: {e}")
                raise RedisConnectionException(
                    message=f"Redis service initialization failed: {str(e)}",
                    original_error=e,
                )

    @asynccontextmanager
    async def get_connection(self, project_id: str):
        """
        Get Redis connection with project isolation.

        Args:
            project_id: Project ID for key isolation (required)

        Yields:
            Redis client instance with project isolation

        Raises:
            RedisProjectIsolationException: If project_id is invalid
            RedisConnectionException: If connection fails
            RedisCircuitBreakerOpenException: If circuit breaker is open
        """
        await self.initialize()

        # Validate project_id format
        try:
            UUID(project_id)
        except ValueError:
            raise RedisProjectIsolationException(
                message=f"Invalid project_id format: {project_id}. Must be a valid UUID string."
            )

        async with redis_connection_factory.get_connection(project_id) as redis_client:
            yield redis_client

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check.

        Returns:
            Detailed health status including connection, memory, and circuit breaker
        """
        with tracer.start_as_current_span("redis.health_check") as span:
            try:
                # Get connection factory health status
                factory_health = await redis_connection_factory.health_check()

                # Test basic operations
                test_operations = await self._test_operations()

                # Get Redis info
                redis_info = await self._get_redis_info()

                # Analyze memory usage
                memory_status = self._analyze_memory_usage(redis_info)

                # Combine health information
                health_status = {
                    "status": "healthy",
                    "timestamp": time.time(),
                    "service": "redis",
                    "factory": factory_health,
                    "test_operations": test_operations,
                    "memory": memory_status,
                    "redis_info": {
                        "version": redis_info.get("redis_version"),
                        "uptime_seconds": redis_info.get("uptime_in_seconds"),
                        "connected_clients": redis_info.get("connected_clients"),
                        "total_commands_processed": redis_info.get(
                            "total_commands_processed"
                        ),
                    },
                }

                # Determine overall status
                if factory_health.get("status") == "unhealthy":
                    health_status["status"] = "unhealthy"
                elif memory_status.get("status") == "critical":
                    health_status["status"] = "critical"
                elif memory_status.get("status") == "warning":
                    health_status["status"] = "warning"
                elif test_operations.get("status") != "passed":
                    health_status["status"] = "degraded"

                self._last_health_check = health_status
                span.set_status(Status(StatusCode.OK))
                return health_status

            except Exception as e:
                logger.error(f"Redis health check failed: {e}")
                span.set_status(Status(StatusCode.ERROR, str(e)))

                return {
                    "status": "unhealthy",
                    "timestamp": time.time(),
                    "service": "redis",
                    "error": str(e),
                }

    async def _test_operations(self) -> Dict[str, Any]:
        """Test basic Redis operations."""
        test_results = {"status": "passed", "operations": {}, "response_times_ms": {}}

        try:
            async with self.get_connection() as redis_client:
                # Test ping
                start_time = time.time()
                await redis_client.ping()
                ping_time = (time.time() - start_time) * 1000
                test_results["operations"]["ping"] = "success"
                test_results["response_times_ms"]["ping"] = round(ping_time, 2)

                # Test set/get
                test_key = "health_check_test"
                start_time = time.time()
                await redis_client.set(test_key, "test_value", ex=10)
                await redis_client.get(test_key)
                await redis_client.delete(test_key)
                setget_time = (time.time() - start_time) * 1000
                test_results["operations"]["set_get_delete"] = "success"
                test_results["response_times_ms"]["set_get_delete"] = round(
                    setget_time, 2
                )

        except Exception as e:
            test_results["status"] = "failed"
            test_results["error"] = str(e)
            logger.warning(f"Redis operations test failed: {e}")

        return test_results

    async def _get_redis_info(self) -> Dict[str, Any]:
        """Get Redis server information."""
        try:
            async with self.get_connection() as redis_client:
                info = await redis_client.info()
                return info
        except Exception as e:
            logger.warning(f"Failed to get Redis info: {e}")
            return {}

    def _analyze_memory_usage(self, redis_info: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze Redis memory usage."""
        memory_status = {
            "status": "healthy",
            "usage_bytes": 0,
            "max_memory_bytes": 0,
            "usage_percentage": 0.0,
        }

        try:
            used_memory = redis_info.get("used_memory", 0)
            max_memory = redis_info.get("maxmemory", 0)

            if used_memory and max_memory:
                usage_percentage = used_memory / max_memory
                memory_status.update(
                    {
                        "usage_bytes": used_memory,
                        "max_memory_bytes": max_memory,
                        "usage_percentage": round(usage_percentage, 4),
                    }
                )

                # Determine status based on thresholds
                if usage_percentage >= self.config.memory_critical_threshold:
                    memory_status["status"] = "critical"
                elif usage_percentage >= self.config.memory_warning_threshold:
                    memory_status["status"] = "warning"

                # Log warnings if needed
                if memory_status["status"] in ["warning", "critical"]:
                    logger.warning(
                        f"Redis memory usage {memory_status['status']}: "
                        f"{usage_percentage:.1%} ({used_memory}/{max_memory} bytes)"
                    )

        except Exception as e:
            logger.warning(f"Failed to analyze Redis memory usage: {e}")

        return memory_status

    async def _health_check_loop(self) -> None:
        """Background health check loop."""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                health_status = await self.health_check()

                # Log health status changes
                if self._last_health_check:
                    last_status = self._last_health_check.get("status", "unknown")
                    current_status = health_status.get("status", "unknown")
                    if last_status != current_status:
                        logger.info(
                            f"Redis health status changed: {last_status} -> {current_status}",
                            extra={"health_status": health_status},
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")

    async def execute_with_retry(
        self, operation: str, func, *args, project_id: str, **kwargs
    ) -> Any:
        """
        Execute Redis operation with automatic retry.

        Args:
            operation: Operation description for logging
            func: Redis function to execute
            *args: Function arguments
            project_id: Project ID for connection isolation
            **kwargs: Function keyword arguments

        Returns:
            Operation result

        Raises:
            RedisException: If operation fails after retries
        """
        with tracer.start_as_current_span(f"redis.execute.{operation}") as span:
            span.set_attribute("redis.operation", operation)
            if project_id:
                span.set_attribute("redis.project_id", project_id)

            last_exception = None

            for attempt in range(self.config.max_retries + 1):
                try:
                    async with self.get_connection(project_id) as redis_client:
                        start_time = time.time()
                        result = await func(redis_client, *args, **kwargs)
                        execution_time = time.time() - start_time

                        span.set_attribute(
                            "redis.execution_time_ms", execution_time * 1000
                        )
                        span.set_status(Status(StatusCode.OK))

                        if attempt > 0:
                            logger.info(
                                f"Redis operation succeeded on attempt {attempt + 1}: {operation}",
                                extra={
                                    "operation": operation,
                                    "attempt": attempt + 1,
                                    "execution_time": execution_time,
                                },
                            )

                        return result

                except RedisCircuitBreakerOpenException:
                    # Don't retry circuit breaker errors
                    span.set_status(Status(StatusCode.ERROR, "Circuit breaker open"))
                    raise

                except RedisException:
                    # Don't retry our own exceptions
                    raise

                except Exception as e:
                    last_exception = e
                    logger.warning(
                        f"Redis operation failed (attempt {attempt + 1}/{self.config.max_retries + 1}): {operation}",
                        extra={
                            "operation": operation,
                            "attempt": attempt + 1,
                            "error": str(e),
                        },
                        exc_info=True,
                    )

                    if attempt < self.config.max_retries:
                        await asyncio.sleep(self.config.retry_delay * (2**attempt))

            # All retries failed
            span.set_status(Status(StatusCode.ERROR, str(last_exception)))
            raise RedisException(
                message=f"Redis operation failed after {self.config.max_retries + 1} attempts: {operation}",
                original_error=last_exception,
            )

    async def close(self) -> None:
        """Close Redis service and cleanup resources."""
        async with self._lock:
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
                self._health_check_task = None

            await redis_connection_factory.close()
            self._initialized = False

            logger.info("Redis service closed")

    def get_metrics(self) -> Dict[str, Any]:
        """Get Redis service metrics."""
        return {
            "initialized": self._initialized,
            "config": {
                "max_connections": self.config.max_connections,
                "connection_timeout": self.config.connection_timeout,
                "health_check_interval": self.config.health_check_interval,
                "max_retries": self.config.max_retries,
            },
            "last_health_check": self._last_health_check,
            "connection_factory": redis_connection_factory.get_metrics(),
        }

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global Redis service instance
redis_service = RedisService()
