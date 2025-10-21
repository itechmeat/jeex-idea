"""
Redis Circuit Breaker Implementation

Implements circuit breaker pattern for Redis operations
to prevent cascading failures and provide graceful degradation.
"""

import time
import asyncio
import logging
from enum import Enum
from typing import Callable, Any, Optional, TypeVar, Union
from functools import wraps
from dataclasses import dataclass, field

from .exceptions import RedisCircuitBreakerOpenException

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    # Failure threshold - number of failures before opening
    failure_threshold: int = 5

    # Recovery timeout - seconds to wait before trying again
    recovery_timeout: float = 60.0

    # Success threshold - number of successes needed to close circuit
    success_threshold: int = 3

    # Timeout for individual operations
    operation_timeout: float = 10.0

    # Monitor these exception types as failures
    failure_exceptions: tuple = (
        ConnectionError,
        TimeoutError,
        OSError,
    )


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker monitoring."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    timeout_calls: int = 0
    circuit_opens: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        if self.total_calls == 0:
            return 0.0
        return self.failed_calls / self.total_calls


class RedisCircuitBreaker:
    """
    Circuit breaker for Redis operations.

    Prevents cascading failures by stopping calls to Redis
    when failure threshold is exceeded and service hasn't recovered.
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change_time = time.time()
        self.metrics = CircuitBreakerMetrics()
        self._lock = asyncio.Lock()

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            RedisCircuitBreakerOpenException: If circuit is open
            Exception: Original exception from function call
        """
        async with self._lock:
            # Check if circuit is open and should remain open
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.last_state_change_time = time.time()
                    logger.info(
                        "Circuit breaker transitioning to HALF_OPEN",
                        extra={
                            "failure_count": self.failure_count,
                            "time_since_last_failure": time.time()
                            - (self.last_failure_time or 0),
                        },
                    )
                else:
                    self.metrics.total_calls += 1
                    raise RedisCircuitBreakerOpenException()

        # Execute the function with timeout
        try:
            self.metrics.total_calls += 1
            start_time = time.time()

            # Execute with timeout
            result = await asyncio.wait_for(
                self._execute_function(func, *args, **kwargs),
                timeout=self.config.operation_timeout,
            )

            execution_time = time.time() - start_time

            # Record success
            await self._record_success()

            logger.debug(
                "Circuit breaker: operation succeeded",
                extra={
                    "execution_time": execution_time,
                    "state": self.state.value,
                    "success_rate": self.metrics.success_rate,
                },
            )

            return result

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            await self._record_failure("timeout")
            self.metrics.timeout_calls += 1

            logger.warning(
                "Circuit breaker: operation timed out",
                extra={
                    "execution_time": execution_time,
                    "timeout": self.config.operation_timeout,
                    "state": self.state.value,
                },
            )

            raise

        except Exception as e:
            execution_time = time.time() - start_time

            # Check if this is a failure exception
            if isinstance(e, self.config.failure_exceptions):
                await self._record_failure(type(e).__name__)
            else:
                # Non-failure exceptions don't affect circuit state
                logger.debug(
                    "Circuit breaker: non-failure exception",
                    extra={
                        "exception_type": type(e).__name__,
                        "execution_time": execution_time,
                    },
                )
                raise

            logger.warning(
                "Circuit breaker: operation failed",
                extra={
                    "exception_type": type(e).__name__,
                    "execution_time": execution_time,
                    "failure_count": self.failure_count,
                    "state": self.state.value,
                },
            )

            raise

    async def _execute_function(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute the function (sync or async)."""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            # Run sync function in thread pool
            return await asyncio.to_thread(func, *args, **kwargs)

    async def _record_success(self) -> None:
        """Record successful operation."""
        async with self._lock:
            self.metrics.successful_calls += 1
            self.metrics.last_success_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.last_state_change_time = time.time()

                    logger.info(
                        "Circuit breaker: circuit closed after successful recovery",
                        extra={
                            "success_count": self.success_count,
                            "failure_count": self.failure_count,
                        },
                    )
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                if self.failure_count > 0:
                    self.failure_count = max(0, self.failure_count - 1)

    async def _record_failure(self, failure_type: str) -> None:
        """Record failed operation."""
        async with self._lock:
            self.metrics.failed_calls += 1
            self.metrics.last_failure_time = time.time()
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                # Immediate opening on failure in half-open state
                self.state = CircuitState.OPEN
                self.success_count = 0
                self.last_state_change_time = time.time()
                self.metrics.circuit_opens += 1

                logger.warning(
                    "Circuit breaker: circuit opened again after failure in half-open state",
                    extra={
                        "failure_type": failure_type,
                        "failure_count": self.failure_count,
                    },
                )

            elif self.state == CircuitState.CLOSED:
                self.failure_count += 1

                if self.failure_count >= self.config.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.last_state_change_time = time.time()
                    self.metrics.circuit_opens += 1

                    logger.warning(
                        "Circuit breaker: circuit opened due to failure threshold",
                        extra={
                            "failure_count": self.failure_count,
                            "threshold": self.config.failure_threshold,
                            "failure_type": failure_type,
                        },
                    )

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt circuit reset."""
        if self.last_failure_time is None:
            return True

        time_since_failure = time.time() - self.last_failure_time
        return time_since_failure >= self.config.recovery_timeout

    def get_status(self) -> dict:
        """Get current circuit breaker status for monitoring."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "last_state_change_time": self.last_state_change_time,
            "metrics": {
                "total_calls": self.metrics.total_calls,
                "successful_calls": self.metrics.successful_calls,
                "failed_calls": self.metrics.failed_calls,
                "timeout_calls": self.metrics.timeout_calls,
                "success_rate": self.metrics.success_rate,
                "failure_rate": self.metrics.failure_rate,
                "circuit_opens": self.metrics.circuit_opens,
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "success_threshold": self.config.success_threshold,
                "operation_timeout": self.config.operation_timeout,
            },
        }

    async def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        async with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            self.last_state_change_time = time.time()

            logger.info("Circuit breaker manually reset to CLOSED state")


def circuit_breaker(
    breaker: Optional[RedisCircuitBreaker] = None,
    config: Optional[CircuitBreakerConfig] = None,
):
    """
    Decorator for circuit breaker protection.

    Args:
        breaker: Existing circuit breaker instance
        config: Configuration for new circuit breaker

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Use provided breaker or create new one
        cb_instance = breaker or RedisCircuitBreaker(config or CircuitBreakerConfig())

        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await cb_instance.call(func, *args, **kwargs)

        # Attach circuit breaker to wrapper for monitoring
        wrapper.circuit_breaker = cb_instance  # type: ignore

        return wrapper

    return decorator
