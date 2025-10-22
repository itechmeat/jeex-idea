"""
Queue Retry Policies

Retry mechanisms and policies for failed tasks.
Implements exponential backoff, jitter, and smart retry strategies.
"""

import asyncio
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.queues.queue_manager import TaskData, TaskType, TaskPriority


def promote_task_priority(current_priority: TaskPriority) -> TaskPriority:
    """
    Promote task priority to the next level for retry.

    Args:
        current_priority: Current task priority

    Returns:
        Next priority level (capped at URGENT)

    Priority mapping:
    - LOW (1) → NORMAL (5)
    - NORMAL (5) → HIGH (10)
    - HIGH (10) → CRITICAL (20)
    - CRITICAL (20) → URGENT (50)
    - URGENT (50) → URGENT (50)  # cap at highest
    """
    priority_mapping = {
        TaskPriority.LOW: TaskPriority.NORMAL,
        TaskPriority.NORMAL: TaskPriority.HIGH,
        TaskPriority.HIGH: TaskPriority.CRITICAL,
        TaskPriority.CRITICAL: TaskPriority.URGENT,
        TaskPriority.URGENT: TaskPriority.URGENT,  # Cap at highest
    }

    # Return mapped priority or URGENT as fallback for unknown values
    return priority_mapping.get(current_priority, TaskPriority.URGENT)


class RetryPolicy(BaseModel):
    """Base retry policy configuration."""

    max_attempts: int = Field(
        default=3, ge=1, le=10, description="Maximum retry attempts"
    )
    base_delay_seconds: float = Field(
        default=1.0, ge=0.1, le=60.0, description="Base delay in seconds"
    )
    max_delay_seconds: float = Field(
        default=300.0, ge=1.0, le=3600.0, description="Maximum delay in seconds"
    )
    multiplier: float = Field(
        default=2.0, ge=1.0, le=10.0, description="Delay multiplier"
    )
    jitter: bool = Field(default=True, description="Add jitter to delays")
    retryable_exceptions: List[str] = Field(
        default_factory=list, description="List of retryable exception types"
    )


class RetryStrategy(ABC):
    """Abstract base class for retry strategies."""

    @abstractmethod
    async def should_retry(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> bool:
        """
        Determine if task should be retried.

        Args:
            task_data: Task data
            error: Exception that occurred
            attempt: Current attempt number

        Returns:
            True if task should be retried
        """
        pass

    @abstractmethod
    async def calculate_delay(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> float:
        """
        Calculate retry delay in seconds.

        Args:
            task_data: Task data
            error: Exception that occurred
            attempt: Current attempt number

        Returns:
            Delay in seconds
        """
        pass

    @abstractmethod
    async def update_task_for_retry(
        self, task_data: TaskData, error: Exception, attempt: int, delay: float
    ) -> TaskData:
        """
        Update task data for retry.

        Args:
            task_data: Original task data
            error: Exception that occurred
            attempt: Current attempt number
            delay: Calculated delay

        Returns:
            Updated task data
        """
        pass


class ExponentialBackoffRetry(RetryStrategy):
    """
    Exponential backoff retry strategy with jitter.

    Implements exponential backoff with optional jitter to prevent
    thundering herd problems.
    """

    def __init__(self, policy: Optional[RetryPolicy] = None):
        self.policy = policy or RetryPolicy()

    async def should_retry(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> bool:
        """Determine if task should be retried with exponential backoff."""
        # Check maximum attempts
        if attempt >= self.policy.max_attempts:
            return False

        # Check if error type is retryable
        if self.policy.retryable_exceptions:
            error_type = type(error).__name__
            if error_type not in self.policy.retryable_exceptions:
                return False

        # Additional business logic for specific task types
        if await self._is_retryable_for_task_type(task_data.task_type, error):
            return True

        # Check if error is retryable by default
        return await self._is_retryable_error(error)

    async def calculate_delay(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> float:
        """Calculate exponential backoff delay with jitter."""
        # Calculate base delay
        delay = self.policy.base_delay_seconds * (
            self.policy.multiplier ** (attempt - 1)
        )

        # Apply maximum delay limit
        delay = min(delay, self.policy.max_delay_seconds)

        # Add jitter if enabled
        if self.policy.jitter:
            # Add ±25% jitter
            jitter_factor = 0.25
            jitter_amount = delay * jitter_factor
            delay += random.uniform(-jitter_amount, jitter_amount)

        # Ensure minimum delay
        delay = max(delay, 0.1)

        return delay

    async def update_task_for_retry(
        self, task_data: TaskData, error: Exception, attempt: int, delay: float
    ) -> TaskData:
        """Update task data for retry."""
        # Calculate new scheduled time
        scheduled_at = datetime.utcnow() + timedelta(seconds=delay)

        # Update metadata
        new_metadata = task_data.metadata.copy()
        new_metadata.update(
            {
                "retry_attempt": attempt,
                "retry_error": str(error),
                "retry_error_type": type(error).__name__,
                "retry_delay_seconds": delay,
                "last_retry_at": datetime.utcnow().isoformat(),
            }
        )

        # Promote priority for retries using proper enum mapping
        new_priority = promote_task_priority(task_data.priority)

        # Create updated task data
        updated_task = task_data.model_copy(
            update={
                "scheduled_at": scheduled_at,
                "priority": new_priority,
                "metadata": new_metadata,
            }
        )

        return updated_task

    async def _is_retryable_for_task_type(
        self, task_type: TaskType, error: Exception
    ) -> bool:
        """Check if error is retryable for specific task type."""
        # Task-specific retry logic
        if task_type == TaskType.EMBEDDING_COMPUTATION:
            # Retry embedding failures for rate limiting or temporary issues
            retryable_errors = ["RateLimitError", "TemporaryFailure", "ConnectionError"]
            return type(error).__name__ in retryable_errors

        elif task_type == TaskType.AGENT_TASK:
            # Retry agent tasks for network issues or temporary unavailability
            retryable_errors = ["NetworkError", "TimeoutError", "TemporaryFailure"]
            return type(error).__name__ in retryable_errors

        elif task_type == TaskType.DOCUMENT_EXPORT:
            # Retry export failures for storage issues or temporary problems
            retryable_errors = ["StorageError", "TemporaryFailure", "TimeoutError"]
            return type(error).__name__ in retryable_errors

        return False

    async def _is_retryable_error(self, error: Exception) -> bool:
        """Check if error is generally retryable."""
        # Common retryable error patterns
        retryable_patterns = [
            "timeout",
            "connection",
            "network",
            "temporary",
            "rate limit",
            "service unavailable",
            "internal server error",
        ]

        error_message = str(error).lower()
        error_type = type(error).__name__.lower()

        for pattern in retryable_patterns:
            if pattern in error_message or pattern in error_type:
                return True

        return False


class LinearBackoffRetry(RetryStrategy):
    """
    Linear backoff retry strategy.

    Implements linear delay increase with fixed intervals.
    """

    def __init__(self, policy: Optional[RetryPolicy] = None):
        self.policy = policy or RetryPolicy()

    async def should_retry(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> bool:
        """Determine if task should be retried with linear backoff."""
        if attempt >= self.policy.max_attempts:
            return False

        if self.policy.retryable_exceptions:
            error_type = type(error).__name__
            if error_type not in self.policy.retryable_exceptions:
                return False

        return True

    async def calculate_delay(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> float:
        """Calculate linear backoff delay."""
        delay = self.policy.base_delay_seconds * attempt
        delay = min(delay, self.policy.max_delay_seconds)

        if self.policy.jitter:
            jitter_amount = delay * 0.1
            delay += random.uniform(-jitter_amount, jitter_amount)

        return max(delay, 0.1)

    async def update_task_for_retry(
        self, task_data: TaskData, error: Exception, attempt: int, delay: float
    ) -> TaskData:
        """Update task data for retry."""
        scheduled_at = datetime.utcnow() + timedelta(seconds=delay)

        new_metadata = task_data.metadata.copy()
        new_metadata.update(
            {
                "retry_attempt": attempt,
                "retry_error": str(error),
                "retry_delay_seconds": delay,
            }
        )

        return task_data.model_copy(
            update={"scheduled_at": scheduled_at, "metadata": new_metadata}
        )


class FixedDelayRetry(RetryStrategy):
    """
    Fixed delay retry strategy.

    Uses the same delay for all retry attempts.
    """

    def __init__(self, policy: Optional[RetryPolicy] = None):
        self.policy = policy or RetryPolicy()

    async def should_retry(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> bool:
        """Determine if task should be retried with fixed delay."""
        if attempt >= self.policy.max_attempts:
            return False

        if self.policy.retryable_exceptions:
            error_type = type(error).__name__
            if error_type not in self.policy.retryable_exceptions:
                return False

        return True

    async def calculate_delay(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> float:
        """Calculate fixed delay."""
        delay = self.policy.base_delay_seconds

        if self.policy.jitter:
            jitter_amount = delay * 0.1
            delay += random.uniform(-jitter_amount, jitter_amount)

        return max(delay, 0.1)

    async def update_task_for_retry(
        self, task_data: TaskData, error: Exception, attempt: int, delay: float
    ) -> TaskData:
        """Update task data for retry."""
        scheduled_at = datetime.utcnow() + timedelta(seconds=delay)

        new_metadata = task_data.metadata.copy()
        new_metadata.update(
            {
                "retry_attempt": attempt,
                "retry_error": str(error),
                "retry_delay_seconds": delay,
            }
        )

        return task_data.model_copy(
            update={"scheduled_at": scheduled_at, "metadata": new_metadata}
        )


class SmartRetryStrategy(RetryStrategy):
    """
    Smart retry strategy that adapts based on error patterns and task history.

    Analyzes error patterns, task success rates, and system load to
    make intelligent retry decisions.
    """

    def __init__(self, policy: Optional[RetryPolicy] = None):
        self.policy = policy or RetryPolicy()
        self.exponential_backoff = ExponentialBackoffRetry(policy)

    async def should_retry(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> bool:
        """Determine if task should be retried using smart logic."""
        # Check basic retry conditions
        if not await self.exponential_backoff.should_retry(task_data, error, attempt):
            return False

        # Apply smart retry logic
        return await self._smart_retry_decision(task_data, error, attempt)

    async def calculate_delay(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> float:
        """Calculate smart retry delay."""
        base_delay = await self.exponential_backoff.calculate_delay(
            task_data, error, attempt
        )

        # Apply smart delay adjustments
        return await self._adjust_delay_smartly(task_data, error, attempt, base_delay)

    async def update_task_for_retry(
        self, task_data: TaskData, error: Exception, attempt: int, delay: float
    ) -> TaskData:
        """Update task data with smart retry metadata."""
        updated_task = await self.exponential_backoff.update_task_for_retry(
            task_data, error, attempt, delay
        )

        # Add smart retry metadata
        new_metadata = updated_task.metadata.copy()
        new_metadata.update(
            {
                "smart_retry": True,
                "retry_decision_factors": await self._get_decision_factors(
                    task_data, error, attempt
                ),
            }
        )

        return updated_task.model_copy(update={"metadata": new_metadata})

    async def _smart_retry_decision(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> bool:
        """Make smart retry decision based on various factors."""
        # Check system load (would integrate with monitoring)
        system_load = await self._get_system_load()
        if system_load > 0.9 and attempt > 2:
            return False  # Don't retry under high load

        # Check error frequency for this task type
        error_frequency = await self._get_error_frequency(
            task_data.task_type, type(error).__name__
        )
        if error_frequency > 0.5 and attempt > 1:
            return False  # Don't retry if error is frequent

        # Check time of day (avoid retries during maintenance windows)
        current_hour = datetime.utcnow().hour
        if 2 <= current_hour <= 4 and attempt > 1:
            return False  # Avoid retries during maintenance window

        # Check recent success rate for this task type
        success_rate = await self._get_recent_success_rate(task_data.task_type)
        if success_rate < 0.1 and attempt > 1:
            return False  # Don't retry if success rate is very low

        return True

    async def _adjust_delay_smartly(
        self, task_data: TaskData, error: Exception, attempt: int, base_delay: float
    ) -> float:
        """Adjust delay based on smart factors."""
        delay = base_delay

        # Increase delay during high system load
        system_load = await self._get_system_load()
        if system_load > 0.8:
            delay *= 1.5

        # Increase delay for frequent errors
        error_frequency = await self._get_error_frequency(
            task_data.task_type, type(error).__name__
        )
        if error_frequency > 0.3:
            delay *= 1.3

        # Decrease delay for historically successful task types
        success_rate = await self._get_recent_success_rate(task_data.task_type)
        if success_rate > 0.9:
            delay *= 0.7

        return min(max(delay, 0.1), self.policy.max_delay_seconds)

    async def _get_system_load(self) -> float:
        """Get current system load (0.0 to 1.0)."""
        # TODO: Integrate with system monitoring
        return 0.5  # Placeholder

    async def _get_error_frequency(self, task_type: TaskType, error_type: str) -> float:
        """Get error frequency for task type and error type."""
        # TODO: Calculate from recent task history
        return 0.1  # Placeholder

    async def _get_recent_success_rate(self, task_type: TaskType) -> float:
        """Get recent success rate for task type."""
        # TODO: Calculate from recent task history
        return 0.8  # Placeholder

    async def _get_decision_factors(
        self, task_data: TaskData, error: Exception, attempt: int
    ) -> Dict[str, Any]:
        """Get factors that influenced the retry decision."""
        return {
            "system_load": await self._get_system_load(),
            "error_frequency": await self._get_error_frequency(
                task_data.task_type, type(error).__name__
            ),
            "success_rate": await self._get_recent_success_rate(task_data.task_type),
            "attempt": attempt,
            "error_type": type(error).__name__,
        }


# Retry policy presets for different scenarios
class RetryPolicyPresets:
    """Predefined retry policies for common scenarios."""

    # Aggressive retry for critical tasks
    CRITICAL_TASKS = RetryPolicy(
        max_attempts=5,
        base_delay_seconds=0.5,
        max_delay_seconds=60.0,
        multiplier=1.5,
        jitter=True,
    )

    # Conservative retry for expensive operations
    EXPENSIVE_OPERATIONS = RetryPolicy(
        max_attempts=2,
        base_delay_seconds=5.0,
        max_delay_seconds=300.0,
        multiplier=2.0,
        jitter=True,
    )

    # Standard retry for general tasks
    STANDARD = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=1.0,
        max_delay_seconds=300.0,
        multiplier=2.0,
        jitter=True,
    )

    # Quick retry for temporary issues
    QUICK_RETRY = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=0.1,
        max_delay_seconds=10.0,
        multiplier=1.2,
        jitter=True,
    )

    # Slow retry for external dependencies
    EXTERNAL_DEPENDENCIES = RetryPolicy(
        max_attempts=4,
        base_delay_seconds=2.0,
        max_delay_seconds=600.0,
        multiplier=2.5,
        jitter=True,
    )


# Create default retry strategies
exponential_backoff_retry = ExponentialBackoffRetry(RetryPolicyPresets.STANDARD)
linear_backoff_retry = LinearBackoffRetry(RetryPolicyPresets.STANDARD)
fixed_delay_retry = FixedDelayRetry(RetryPolicyPresets.STANDARD)
smart_retry_strategy = SmartRetryStrategy(RetryPolicyPresets.STANDARD)
