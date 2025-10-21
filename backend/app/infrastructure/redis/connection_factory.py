"""
Redis Connection Factory

Domain-Driven connection management for Redis with project isolation.
Provides connection pooling, health checks, and automatic reconnection.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Union
from uuid import UUID
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import redis
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    AuthenticationError as RedisAuthError,
    TimeoutError as RedisTimeoutError,
    RedisError,
)

from opentelemetry import trace
from opentelemetry.instrumentation.redis import RedisInstrumentor

from ...core.config import settings
from .exceptions import (
    RedisConnectionException,
    RedisAuthenticationException,
    RedisConfigurationException,
    RedisOperationTimeoutException,
    RedisProjectIsolationException,
    RedisCircuitBreakerOpenException,
)
from .circuit_breaker import RedisCircuitBreaker, CircuitBreakerConfig

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class RedisConnectionFactory:
    """
    Factory for creating and managing Redis connections with project isolation.

    Provides connection pooling, health checks, and circuit breaker protection.
    Ensures project isolation through connection key prefixing.
    """

    def __init__(self):
        self._pools: Dict[str, ConnectionPool] = {}
        self._default_pool: Optional[ConnectionPool] = None
        self._circuit_breaker = RedisCircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=getattr(
                    settings, "CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5
                ),
                recovery_timeout=getattr(
                    settings, "CIRCUIT_BREAKER_RECOVERY_TIMEOUT", 60.0
                ),
                success_threshold=3,
                operation_timeout=10.0,
                failure_exceptions=(
                    RedisConnectionError,
                    RedisAuthError,
                    RedisTimeoutError,
                    ConnectionRefusedError,
                ),
            )
        )
        self._initialized = False
        self._lock = asyncio.Lock()

        # Initialize OpenTelemetry instrumentation
        try:
            RedisInstrumentor().instrument()
            logger.info("Redis OpenTelemetry instrumentation enabled")
        except Exception as e:
            logger.warning(f"Failed to enable Redis OpenTelemetry instrumentation: {e}")

    async def initialize(self) -> None:
        """Initialize connection factory and create default pool."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            try:
                # Parse Redis URL
                redis_url = settings.REDIS_URL
                parsed_url = urlparse(redis_url)

                # Create connection configuration
                connection_kwargs = {
                    "host": parsed_url.hostname or "localhost",
                    "port": parsed_url.port or 6379,
                    "username": parsed_url.username,
                    "password": parsed_url.password,
                    "encoding": "utf-8",
                    "decode_responses": True,
                    "socket_connect_timeout": 10,
                    "socket_timeout": 10,
                    "retry_on_timeout": True,
                    "health_check_interval": 30,
                    "max_connections": settings.REDIS_MAX_CONNECTIONS,
                }

                # Create default connection pool
                self._default_pool = ConnectionPool(**connection_kwargs)
                self._pools["default"] = self._default_pool

                # Test connection
                await self._test_connection(self._default_pool)

                self._initialized = True
                logger.info(
                    "Redis connection factory initialized",
                    extra={
                        "host": connection_kwargs["host"],
                        "port": connection_kwargs["port"],
                        "max_connections": connection_kwargs["max_connections"],
                    },
                )

            except Exception as e:
                logger.error(f"Failed to initialize Redis connection factory: {e}")
                raise RedisConfigurationException(
                    message=f"Redis connection factory initialization failed: {str(e)}",
                    original_error=e,
                )

    async def _test_connection(self, pool: ConnectionPool) -> None:
        """Test connection pool with health check."""
        try:
            redis_client = Redis(connection_pool=pool)
            await redis_client.ping()
            logger.debug("Redis connection test successful")
        except Exception as e:
            if isinstance(e, RedisAuthError):
                raise RedisAuthenticationException(
                    message="Redis authentication failed during initialization",
                    original_error=e,
                )
            else:
                raise RedisConnectionException(
                    message="Redis connection test failed", original_error=e
                )

    @asynccontextmanager
    async def get_connection(self, project_id: str):
        """
        Get Redis connection with project isolation.

        Args:
            project_id: Project ID for key isolation (required)

        Yields:
            Redis client instance

        Raises:
            RedisProjectIsolationException: If project_id is invalid
            RedisConnectionException: If connection fails
            RedisCircuitBreakerOpenException: If circuit breaker is open
        """
        # Validate project_id format
        try:
            UUID(project_id)
        except ValueError:
            raise RedisProjectIsolationException(
                message=f"Invalid project_id format: {project_id}. Must be a valid UUID string."
            )
        await self.initialize()

        # Use project-specific pool
        pool_key = f"project:{project_id}"

        if pool_key not in self._pools:
            await self._create_project_pool(project_id)

        pool = self._pools[pool_key]

        try:
            # Create Redis client with circuit breaker protection
            redis_client = await self._circuit_breaker.call(
                lambda: Redis(connection_pool=pool)
            )

            # Add project isolation wrapper
            if project_id:
                redis_client = ProjectIsolatedRedisClient(redis_client, project_id)

            yield redis_client

        except Exception as e:
            if isinstance(e, RedisCircuitBreakerOpenException):
                raise
            elif isinstance(
                e, (RedisConnectionError, RedisAuthError, RedisTimeoutError)
            ):
                logger.error(f"Redis connection error: {e}")
                raise RedisConnectionException(
                    message=f"Redis connection failed: {str(e)}", original_error=e
                )
            else:
                raise

    async def _create_project_pool(self, project_id: str) -> None:
        """Create project-specific connection pool."""
        async with self._lock:
            pool_key = f"project:{project_id}"
            if pool_key in self._pools:
                return

            # Copy configuration from default pool
            default_pool = self._default_pool
            if not default_pool:
                raise RedisConfigurationException("Default Redis pool not initialized")

            # Create project-specific pool with same configuration
            connection_kwargs = {
                "host": default_pool.connection_kwargs.get("host", "localhost"),
                "port": default_pool.connection_kwargs.get("port", 6379),
                "username": default_pool.connection_kwargs.get("username"),
                "password": default_pool.connection_kwargs.get("password"),
                "encoding": "utf-8",
                "decode_responses": True,
                "socket_connect_timeout": 10,
                "socket_timeout": 10,
                "retry_on_timeout": True,
                "health_check_interval": 30,
                "max_connections": max(
                    2, settings.REDIS_MAX_CONNECTIONS // 4
                ),  # Smaller pools for projects
            }

            pool = ConnectionPool(**connection_kwargs)
            self._pools[pool_key] = pool

            logger.debug(
                f"Created Redis connection pool for project: {project_id}",
                extra={
                    "project_id": project_id,
                    "max_connections": connection_kwargs["max_connections"],
                },
            )

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on Redis connections.

        Returns:
            Health check results with circuit breaker status
        """
        health_status = {
            "status": "unhealthy",
            "timestamp": time.time(),
            "circuit_breaker": self._circuit_breaker.get_status(),
            "pools": {},
            "default_connection": None,
        }

        if not self._initialized:
            health_status["error"] = "Redis connection factory not initialized"
            return health_status

        try:
            # Test default connection
            if self._default_pool:
                redis_client = Redis(connection_pool=self._default_pool)
                start_time = time.time()
                await redis_client.ping()
                response_time = time.time() - start_time

                health_status["default_connection"] = {
                    "status": "healthy",
                    "response_time_ms": round(response_time * 1000, 2),
                }

            # Test circuit breaker
            circuit_status = self._circuit_breaker.get_status()
            if circuit_status["state"] == "closed":
                health_status["status"] = "healthy"
            else:
                health_status["status"] = "degraded"

            # Pool information
            for pool_key, pool in self._pools.items():
                created_connections = getattr(pool, "_created_connections", 0)
                available_connections = (
                    len(pool._available_connections)
                    if hasattr(pool, "_available_connections")
                    else 0
                )

                health_status["pools"][pool_key] = {
                    "created_connections": created_connections,
                    "available_connections": available_connections,
                    "max_connections": pool.max_connections,
                }

        except Exception as e:
            health_status["error"] = str(e)
            logger.error(f"Redis health check failed: {e}")

        return health_status

    async def close(self) -> None:
        """Close all connection pools."""
        async with self._lock:
            for pool_key, pool in self._pools.items():
                try:
                    await pool.disconnect()
                    logger.debug(f"Closed Redis connection pool: {pool_key}")
                except Exception as e:
                    logger.warning(f"Error closing Redis pool {pool_key}: {e}")

            self._pools.clear()
            self._default_pool = None
            self._initialized = False

            logger.info("Redis connection factory closed")

    def get_metrics(self) -> Dict[str, Any]:
        """Get connection factory metrics."""
        return {
            "initialized": self._initialized,
            "pools_count": len(self._pools),
            "circuit_breaker": self._circuit_breaker.get_status(),
            "pools": {
                pool_key: {
                    "max_connections": pool.max_connections,
                    "created_connections": getattr(pool, "_created_connections", 0),
                }
                for pool_key, pool in self._pools.items()
            },
        }


class ProjectIsolatedRedisClient:
    """
    Redis client wrapper that enforces project isolation.

    Automatically prefixes keys with project ID to prevent cross-project data access.
    """

    def __init__(self, redis_client: Redis, project_id: str):
        self._redis = redis_client
        self._project_id = project_id
        self._key_prefix = f"proj:{project_id}:"

    def _make_key(self, key: str) -> str:
        """Create project-isolated key."""
        if key.startswith(self._key_prefix):
            return key  # Already prefixed
        return f"{self._key_prefix}{key}"

    def _extract_original_key(self, key: str) -> str:
        """Extract original key from project-isolated key."""
        if key.startswith(self._key_prefix):
            return key[len(self._key_prefix) :]
        return key

    async def get(self, key: str, **kwargs) -> Optional[str]:
        """Get value with project isolation."""
        return await self._redis.get(self._make_key(key), **kwargs)

    async def set(self, key: str, value, **kwargs) -> bool:
        """Set value with project isolation."""
        return await self._redis.set(self._make_key(key), value, **kwargs)

    async def delete(self, key: str, **kwargs) -> int:
        """Delete key with project isolation."""
        return await self._redis.delete(self._make_key(key), **kwargs)

    async def exists(self, key: str, **kwargs) -> int:
        """Check if key exists with project isolation."""
        return await self._redis.exists(self._make_key(key), **kwargs)

    async def expire(self, key: str, seconds: int, **kwargs) -> bool:
        """Set key expiration with project isolation."""
        return await self._redis.expire(self._make_key(key), seconds, **kwargs)

    async def ttl(self, key: str, **kwargs) -> int:
        """Get key TTL with project isolation."""
        return await self._redis.ttl(self._make_key(key), **kwargs)

    async def hget(self, name: str, key: str, **kwargs) -> Optional[str]:
        """Get hash field with project isolation."""
        return await self._redis.hget(self._make_key(name), key, **kwargs)

    async def hset(self, name: str, key: str, value, **kwargs) -> int:
        """Set hash field with project isolation."""
        return await self._redis.hset(self._make_key(name), key, value, **kwargs)

    async def hgetall(self, name: str, **kwargs) -> dict:
        """Get all hash fields with project isolation."""
        return await self._redis.hgetall(self._make_key(name), **kwargs)

    async def lpush(self, name: str, *values, **kwargs) -> int:
        """Push to list with project isolation."""
        return await self._redis.lpush(self._make_key(name), *values, **kwargs)

    async def rpush(self, name: str, *values, **kwargs) -> int:
        """Push to list with project isolation."""
        return await self._redis.rpush(self._make_key(name), *values, **kwargs)

    async def lpop(self, name: str, **kwargs) -> Optional[str]:
        """Pop from list with project isolation."""
        return await self._redis.lpop(self._make_key(name), **kwargs)

    async def rpop(self, name: str, **kwargs) -> Optional[str]:
        """Pop from list with project isolation."""
        return await self._redis.rpop(self._make_key(name), **kwargs)

    async def lrange(self, name: str, start: int, end: int, **kwargs) -> list:
        """Get list range with project isolation."""
        return await self._redis.lrange(self._make_key(name), start, end, **kwargs)

    async def incr(self, key: str, amount: int = 1, **kwargs) -> int:
        """Increment key with project isolation."""
        return await self._redis.incr(self._make_key(key), amount, **kwargs)

    async def incrby(self, key: str, amount: int = 1, **kwargs) -> int:
        """Increment key by amount with project isolation."""
        return await self._redis.incrby(self._make_key(key), amount, **kwargs)

    async def ping(self, **kwargs) -> bool:
        """Ping Redis server."""
        return await self._redis.ping(**kwargs)

    async def info(self, section: Optional[str] = None, **kwargs) -> dict:
        """Get Redis server information."""
        return await self._redis.info(section, **kwargs)

    # Delegate other methods to underlying client
    def __getattr__(self, name):
        """Delegate other attributes to underlying Redis client."""
        attr = getattr(self._redis, name)
        if callable(attr):
            # For callable methods, we need to wrap them to handle key isolation
            def wrapped_method(*args, **kwargs):
                return attr(*args, **kwargs)

            return wrapped_method
        return attr


# Global connection factory instance
redis_connection_factory = RedisConnectionFactory()
