"""
Redis Infrastructure Module

Domain-Driven Redis infrastructure with connection pooling,
circuit breaker protection, and project isolation.

This module provides:
- RedisService: Main Redis service with health monitoring
- RedisConnectionFactory: Connection management with project isolation
- Circuit breaker pattern for resilience
- Comprehensive exception handling
- OpenTelemetry instrumentation
"""

from .redis_service import RedisService, redis_service, RedisServiceConfig
from .connection_factory import (
    RedisConnectionFactory,
    redis_connection_factory,
    ProjectIsolatedRedisClient,
)
from .circuit_breaker import (
    RedisCircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerMetrics,
    circuit_breaker,
)
from .exceptions import (
    RedisException,
    RedisConnectionException,
    RedisAuthenticationException,
    RedisOperationTimeoutException,
    RedisMemoryException,
    RedisCircuitBreakerOpenException,
    RedisKeyNotFoundException,
    RedisProjectIsolationException,
    RedisConfigurationException,
    RedisPoolExhaustedException,
    RedisHTTPException,
)

__all__ = [
    # Main service
    "RedisService",
    "redis_service",
    "RedisServiceConfig",
    # Connection management
    "RedisConnectionFactory",
    "redis_connection_factory",
    "ProjectIsolatedRedisClient",
    # Circuit breaker
    "RedisCircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "CircuitBreakerMetrics",
    "circuit_breaker",
    # Exceptions
    "RedisException",
    "RedisConnectionException",
    "RedisAuthenticationException",
    "RedisOperationTimeoutException",
    "RedisMemoryException",
    "RedisCircuitBreakerOpenException",
    "RedisKeyNotFoundException",
    "RedisProjectIsolationException",
    "RedisConfigurationException",
    "RedisPoolExhaustedException",
    "RedisHTTPException",
]
