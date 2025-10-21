"""
Redis Infrastructure Exceptions

Domain-specific exceptions for Redis operations.
Follows project standards for error handling without fallbacks.
"""

from typing import Optional, Any, Dict
from fastapi import HTTPException


class RedisException(Exception):
    """Base exception for Redis-related errors.

    All Redis operations should raise this or its subclasses.
    Never swallow Redis exceptions - always preserve context.
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class RedisConnectionException(RedisException):
    """Raised when Redis connection fails or is lost."""

    def __init__(
        self,
        message: str = "Redis connection failed",
        host: Optional[str] = None,
        port: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if host:
            details["host"] = host
        if port:
            details["port"] = port
        if original_error:
            details["original_error"] = str(original_error)

        super().__init__(
            message=message, error_code="REDIS_CONNECTION_ERROR", details=details
        )


class RedisAuthenticationException(RedisException):
    """Raised when Redis authentication fails."""

    def __init__(
        self,
        message: str = "Redis authentication failed",
        username: Optional[str] = None,
    ):
        details = {}
        if username:
            details["username"] = username

        super().__init__(
            message=message, error_code="REDIS_AUTH_ERROR", details=details
        )


class RedisOperationTimeoutException(RedisException):
    """Raised when Redis operation times out."""

    def __init__(
        self, operation: str, timeout_seconds: float, key: Optional[str] = None
    ):
        details = {"operation": operation, "timeout_seconds": timeout_seconds}
        if key:
            details["key"] = key

        super().__init__(
            message=f"Redis operation '{operation}' timed out after {timeout_seconds}s",
            error_code="REDIS_TIMEOUT_ERROR",
            details=details,
        )


class RedisMemoryException(RedisException):
    """Raised when Redis memory limits are exceeded."""

    def __init__(
        self,
        message: str = "Redis memory limit exceeded",
        memory_usage: Optional[int] = None,
        memory_limit: Optional[int] = None,
    ):
        details = {}
        if memory_usage:
            details["memory_usage"] = memory_usage
        if memory_limit:
            details["memory_limit"] = memory_limit

        super().__init__(
            message=message, error_code="REDIS_MEMORY_ERROR", details=details
        )


class RedisCircuitBreakerOpenException(RedisException):
    """Raised when Redis circuit breaker is open."""

    def __init__(
        self, message: str = "Redis circuit breaker is open - service unavailable"
    ):
        super().__init__(
            message=message,
            error_code="REDIS_CIRCUIT_BREAKER_OPEN",
            details={"service_status": "unavailable"},
        )


class RedisKeyNotFoundException(RedisException):
    """Raised when expected Redis key is not found."""

    def __init__(self, key: str, project_id: Optional[str] = None):
        details = {"key": key}
        if project_id:
            details["project_id"] = project_id

        super().__init__(
            message=f"Redis key not found: {key}",
            error_code="REDIS_KEY_NOT_FOUND",
            details=details,
        )


class RedisProjectIsolationException(RedisException):
    """Raised when project isolation is violated."""

    def __init__(
        self,
        message: str,
        project_id: Optional[str] = None,
        key_pattern: Optional[str] = None,
    ):
        details = {}
        if project_id:
            details["project_id"] = project_id
        if key_pattern:
            details["key_pattern"] = key_pattern

        super().__init__(
            message=message,
            error_code="REDIS_PROJECT_ISOLATION_VIOLATION",
            details=details,
        )


class RedisConfigurationException(RedisException):
    """Raised when Redis configuration is invalid."""

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        config_value: Optional[Any] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if config_key:
            details["config_key"] = config_key
        if config_value is not None:
            details["config_value"] = str(config_value)
        if original_error:
            details["original_error"] = str(original_error)

        super().__init__(
            message=message, error_code="REDIS_CONFIGURATION_ERROR", details=details
        )


class RedisPoolExhaustedException(RedisException):
    """Raised when Redis connection pool is exhausted."""

    def __init__(self, pool_size: int, active_connections: int):
        details = {"pool_size": pool_size, "active_connections": active_connections}

        super().__init__(
            message=f"Redis connection pool exhausted: {active_connections}/{pool_size}",
            error_code="REDIS_POOL_EXHAUSTED",
            details=details,
        )


# HTTP Exceptions for API layer
class RedisHTTPException(HTTPException):
    """HTTP exception wrapper for Redis errors."""

    def __init__(self, redis_exception: RedisException, status_code: int = 503):
        self.redis_exception = redis_exception
        super().__init__(
            status_code=status_code,
            detail={
                "error": redis_exception.error_code,
                "message": redis_exception.message,
                "details": redis_exception.details,
            },
        )
