"""
Dead Letter Queue

Handles tasks that have exceeded retry attempts or are otherwise unprocessable.
Provides monitoring, alerting, and manual intervention capabilities.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from opentelemetry import trace

from app.infrastructure.redis.connection_factory import redis_connection_factory
from app.services.queues.queue_manager import TaskData, TaskType, TaskStatus

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class DeadLetterTask(BaseModel):
    """Dead letter task model."""

    original_task_id: UUID
    task_type: TaskType
    project_id: UUID
    original_data: Dict[str, Any]
    error_message: str
    error_type: str
    attempts: int
    first_failed_at: datetime
    last_failed_at: datetime
    worker_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    manual_review_required: bool = Field(default=True)
    severity: str = Field(default="medium")  # low, medium, high, critical
    category: str = Field(
        default="retry_exhausted"
    )  # retry_exhausted, invalid_data, system_error
    auto_retry_eligible: bool = Field(default=False)
    next_auto_retry_at: Optional[datetime] = None


class DeadLetterQueue:
    """
    Dead letter queue for failed tasks.

    Stores tasks that have exceeded retry attempts and provides
    mechanisms for monitoring, alerting, and manual intervention.
    """

    def __init__(self):
        self._redis_factory = redis_connection_factory

    async def add_task(
        self,
        task_data: TaskData,
        error: str,
        worker_id: Optional[str] = None,
        attempts: int = 0,
        category: str = "retry_exhausted",
        severity: str = "medium",
    ) -> UUID:
        """
        Add task to dead letter queue.

        Args:
            task_data: Original task data
            error: Error message
            worker_id: Worker ID that failed
            attempts: Number of attempts made
            category: Failure category
            severity: Failure severity

        Returns:
            Dead letter task ID
        """
        with tracer.start_as_current_span("dead_letter.add_task") as span:
            span.set_attribute("task_id", str(task_data.task_id))
            span.set_attribute("task_type", task_data.task_type.value)
            span.set_attribute("category", category)
            span.set_attribute("severity", severity)

            try:
                now = datetime.utcnow()

                # Determine if auto retry is eligible
                auto_retry_eligible = await self._is_auto_retry_eligible(
                    task_data, error, attempts
                )
                next_auto_retry_at = None
                if auto_retry_eligible:
                    next_auto_retry_at = now + await self._calculate_auto_retry_delay(
                        attempts
                    )

                dead_letter_task = DeadLetterTask(
                    original_task_id=task_data.task_id,
                    task_type=task_data.task_type,
                    project_id=task_data.project_id,
                    original_data=task_data.data,
                    error_message=error,
                    error_type=self._extract_error_type(error),
                    attempts=attempts,
                    first_failed_at=now,
                    last_failed_at=now,
                    worker_id=worker_id,
                    metadata=task_data.metadata,
                    severity=severity,
                    category=category,
                    auto_retry_eligible=auto_retry_eligible,
                    next_auto_retry_at=next_auto_retry_at,
                )

                # Store in Redis
                await self._store_dead_letter_task(dead_letter_task)

                # Update statistics
                await self._update_stats(dead_letter_task)

                # Alert if critical
                if severity in ["high", "critical"]:
                    await self._send_alert(dead_letter_task)

                logger.warning(
                    f"Task {task_data.task_id} added to dead letter queue",
                    extra={
                        "task_id": str(task_data.task_id),
                        "task_type": task_data.task_type.value,
                        "error": error,
                        "attempts": attempts,
                        "category": category,
                        "severity": severity,
                    },
                )

                span.set_attribute(
                    "dead_letter_task_id", str(dead_letter_task.original_task_id)
                )
                return dead_letter_task.original_task_id

            except Exception as e:
                logger.error(f"Failed to add task to dead letter queue: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def get_task(
        self, project_id: UUID, task_id: UUID
    ) -> Optional[DeadLetterTask]:
        """
        Get dead letter task by ID.

        Args:
            project_id: Project ID (required for isolation)
            task_id: Task ID to retrieve

        Returns:
            Dead letter task or None if not found
        """
        if not project_id:
            raise ValueError("project_id is required")

        try:
            task_key = f"proj:{project_id}:dead_letter_queue:task:{task_id}"

            async with self._redis_factory.get_connection(
                str(project_id)
            ) as redis_client:
                task_json = await redis_client.get(task_key)

                if task_json:
                    task = DeadLetterTask.model_validate_json(task_json)
                    # Verify project isolation
                    if task.project_id != project_id:
                        logger.error(
                            f"Project isolation violation: task {task_id} belongs to different project"
                        )
                        return None
                    return task

            return None

        except Exception as e:
            logger.error(
                f"Failed to get dead letter task {task_id} for project {project_id}: {e}"
            )
            return None

    async def list_tasks(
        self,
        project_id: UUID,
        limit: int = 100,
        offset: int = 0,
        task_type: Optional[TaskType] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[DeadLetterTask]:
        """
        List dead letter tasks with filtering.

        Args:
            project_id: Project ID (required for isolation)
            limit: Maximum number of tasks to return
            offset: Offset for pagination
            task_type: Filter by task type
            severity: Filter by severity
            category: Filter by category

        Returns:
            List of dead letter tasks
        """
        if not project_id:
            raise ValueError("project_id is required")

        try:
            # Get all task keys using scan_iter for better performance
            async with self._redis_factory.get_connection(
                str(project_id)
            ) as redis_client:
                pattern = f"proj:{project_id}:dead_letter_queue:task:*"
                task_keys = []
                async for key in redis_client.scan_iter(match=pattern):
                    task_keys.append(key)

            tasks = []
            # Apply offset and process keys
            for key in task_keys[offset:]:
                if len(tasks) >= limit:
                    break

                async with self._redis_factory.get_connection(
                    str(project_id)
                ) as redis_client:
                    task_json = await redis_client.get(key)
                    if task_json:
                        task = DeadLetterTask.model_validate_json(task_json)

                        # Verify project isolation (double-check)
                        if task.project_id != project_id:
                            logger.error(
                                f"Project isolation violation: task key {key} belongs to different project"
                            )
                            continue

                        # Apply filters
                        if task_type and task.task_type != task_type:
                            continue
                        if severity and task.severity != severity:
                            continue
                        if category and task.category != category:
                            continue

                        tasks.append(task)

            # Sort by last failed time (newest first)
            tasks.sort(key=lambda t: t.last_failed_at, reverse=True)

            return tasks

        except Exception as e:
            logger.error(
                f"Failed to list dead letter tasks for project {project_id}: {e}"
            )
            return []

    async def retry_task(
        self, project_id: UUID, task_id: UUID, worker_id: Optional[str] = None
    ) -> bool:
        """
        Manually retry a dead letter task.

        Args:
            project_id: Project ID (required for isolation)
            task_id: Task ID to retry
            worker_id: Worker ID for the retry

        Returns:
            True if task was successfully requeued
        """
        if not project_id:
            raise ValueError("project_id is required")

        try:
            dead_letter_task = await self.get_task(project_id, task_id)
            if not dead_letter_task:
                return False

            # Verify project isolation
            if dead_letter_task.project_id != project_id:
                logger.error(
                    f"Project isolation violation: task {task_id} belongs to different project"
                )
                return False

            # Create new task data for retry
            from .queue_manager import queue_manager, TaskPriority

            # Reset task data for retry
            new_metadata = dead_letter_task.metadata.copy()
            new_metadata.update(
                {
                    "dead_letter_retry": True,
                    "original_error": dead_letter_task.error_message,
                    "original_attempts": dead_letter_task.attempts,
                    "retried_at": datetime.utcnow().isoformat(),
                }
            )

            # Requeue with normal priority
            await queue_manager.enqueue_task(
                task_type=dead_letter_task.task_type,
                project_id=dead_letter_task.project_id,
                data=dead_letter_task.original_data,
                priority=TaskPriority.NORMAL,
                max_attempts=3,  # Give it a few more attempts
                metadata=new_metadata,
            )

            # Remove from dead letter queue
            await self.remove_task(project_id, task_id)

            logger.info(
                f"Dead letter task {task_id} manually requeued for project {project_id}",
                extra={
                    "project_id": str(project_id),
                    "task_id": str(task_id),
                    "worker_id": worker_id,
                },
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to retry dead letter task {task_id} for project {project_id}: {e}"
            )
            return False

    async def remove_task(self, project_id: UUID, task_id: UUID) -> bool:
        """
        Remove task from dead letter queue.

        Args:
            project_id: Project ID (required for isolation)
            task_id: Task ID to remove

        Returns:
            True if task was removed
        """
        if not project_id:
            raise ValueError("project_id is required")

        try:
            task_key = f"proj:{project_id}:dead_letter_queue:task:{task_id}"

            async with self._redis_factory.get_connection(
                str(project_id)
            ) as redis_client:
                deleted = await redis_client.delete(task_key)

            if deleted:
                logger.info(
                    f"Removed dead letter task {task_id} for project {project_id}"
                )

            return bool(deleted)

        except Exception as e:
            logger.error(
                f"Failed to remove dead letter task {task_id} for project {project_id}: {e}"
            )
            return False

    async def get_statistics(self, project_id: UUID) -> Dict[str, Any]:
        """
        Get dead letter queue statistics.

        Args:
            project_id: Project ID (required for isolation)

        Returns:
            Dead letter queue statistics
        """
        if not project_id:
            raise ValueError("project_id is required")

        try:
            # Use scan_iter for better performance
            async with self._redis_factory.get_connection(
                str(project_id)
            ) as redis_client:
                # Get total count using scan_iter
                pattern = f"proj:{project_id}:dead_letter_queue:task:*"
                task_keys = []
                async for key in redis_client.scan_iter(match=pattern):
                    task_keys.append(key)
                total_count = len(task_keys)

                # Initialize statistics
                stats = {
                    "project_id": str(project_id),
                    "total_tasks": total_count,
                    "by_task_type": {},
                    "by_severity": {},
                    "by_category": {},
                    "by_age": {"1h": 0, "24h": 0, "7d": 0, "30d": 0},
                    "auto_retry_eligible": 0,
                    "manual_review_required": 0,
                    "oldest_task": None,
                    "newest_task": None,
                    "timestamp": datetime.utcnow().isoformat(),
                }

                now = datetime.utcnow()

                for key in task_keys:
                    task_json = await redis_client.get(key)
                    if task_json:
                        task = DeadLetterTask.model_validate_json(task_json)

                        # Verify project isolation (double-check)
                        if task.project_id != project_id:
                            logger.error(
                                f"Project isolation violation: task key {key} belongs to different project"
                            )
                            continue

                        # Count by task type
                        task_type_key = task.task_type.value
                        stats["by_task_type"][task_type_key] = (
                            stats["by_task_type"].get(task_type_key, 0) + 1
                        )

                        # Count by severity
                        stats["by_severity"][task.severity] = (
                            stats["by_severity"].get(task.severity, 0) + 1
                        )

                        # Count by category
                        stats["by_category"][task.category] = (
                            stats["by_category"].get(task.category, 0) + 1
                        )

                        # Count by age
                        age = now - task.last_failed_at
                        if age <= timedelta(hours=1):
                            stats["by_age"]["1h"] += 1
                        elif age <= timedelta(days=1):
                            stats["by_age"]["24h"] += 1
                        elif age <= timedelta(days=7):
                            stats["by_age"]["7d"] += 1
                        else:
                            stats["by_age"]["30d"] += 1

                        # Count special categories
                        if task.auto_retry_eligible:
                            stats["auto_retry_eligible"] += 1
                        if task.manual_review_required:
                            stats["manual_review_required"] += 1

                        # Track oldest and newest
                        if not stats[
                            "oldest_task"
                        ] or task.last_failed_at < datetime.fromisoformat(
                            stats["oldest_task"]
                        ):
                            stats["oldest_task"] = task.last_failed_at.isoformat()
                        if not stats[
                            "newest_task"
                        ] or task.last_failed_at > datetime.fromisoformat(
                            stats["newest_task"]
                        ):
                            stats["newest_task"] = task.last_failed_at.isoformat()

                return stats

        except Exception as e:
            logger.error(
                f"Failed to get dead letter statistics for project {project_id}: {e}"
            )
            return {
                "error": str(e),
                "project_id": str(project_id),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def process_auto_retries(self, project_id: UUID) -> int:
        """
        Process auto-retry eligible tasks.

        Args:
            project_id: Project ID (required for isolation)

        Returns:
            Number of tasks requeued for auto retry
        """
        if not project_id:
            raise ValueError("project_id is required")

        retry_count = 0

        try:
            tasks = await self.list_tasks(
                project_id=project_id, limit=1000
            )  # Get all tasks for project

            for task in tasks:
                if task.auto_retry_eligible and task.next_auto_retry_at:
                    if datetime.utcnow() >= task.next_auto_retry_at:
                        if await self.retry_task(project_id, task.original_task_id):
                            retry_count += 1

            if retry_count > 0:
                logger.info(
                    f"Auto-retried {retry_count} dead letter tasks for project {project_id}"
                )

            return retry_count

        except Exception as e:
            logger.error(
                f"Failed to process auto retries for project {project_id}: {e}"
            )
            return 0

    async def cleanup_old_tasks(self, project_id: UUID, max_age_days: int = 30) -> int:
        """
        Clean up old dead letter tasks.

        Args:
            project_id: Project ID (required for isolation)
            max_age_days: Maximum age in days

        Returns:
            Number of tasks cleaned up
        """
        if not project_id:
            raise ValueError("project_id is required")

        try:
            cutoff_time = datetime.utcnow() - timedelta(days=max_age_days)
            tasks = await self.list_tasks(
                project_id=project_id, limit=10000
            )  # Get all tasks for project

            cleaned_count = 0
            for task in tasks:
                if task.last_failed_at < cutoff_time:
                    if await self.remove_task(project_id, task.original_task_id):
                        cleaned_count += 1

            if cleaned_count > 0:
                logger.info(
                    f"Cleaned up {cleaned_count} old dead letter tasks for project {project_id}"
                )

            return cleaned_count

        except Exception as e:
            logger.error(
                f"Failed to cleanup old dead letter tasks for project {project_id}: {e}"
            )
            return 0

    async def _store_dead_letter_task(self, task: DeadLetterTask) -> None:
        """Store dead letter task in Redis."""
        task_key = (
            f"proj:{task.project_id}:dead_letter_queue:task:{task.original_task_id}"
        )
        task_json = json.dumps(task.model_dump(), default=str)

        async with self._redis_factory.get_connection(
            str(task.project_id)
        ) as redis_client:
            await redis_client.set(task_key, task_json, ex=86400 * 30)  # 30 days TTL

    async def _update_stats(self, task: DeadLetterTask) -> None:
        """Update dead letter statistics."""
        stats_key = f"proj:{task.project_id}:dead_letter_stats"
        async with self._redis_factory.get_connection(
            str(task.project_id)
        ) as redis_client:
            # Increment counters
            await redis_client.hincrby(stats_key, "total_tasks", 1)
            await redis_client.hincrby(
                stats_key, f"task_type:{task.task_type.value}", 1
            )
            await redis_client.hincrby(stats_key, f"severity:{task.severity}", 1)
            await redis_client.hincrby(stats_key, f"category:{task.category}", 1)

            # Set expiration
            await redis_client.expire(stats_key, 86400 * 7)  # 7 days

    async def _is_auto_retry_eligible(
        self, task_data: TaskData, error: str, attempts: int
    ) -> bool:
        """Determine if task is eligible for auto retry."""
        # Only auto retry for certain error types
        retryable_errors = ["timeout", "connection", "temporary", "rate limit"]
        error_lower = error.lower()

        if not any(err in error_lower for err in retryable_errors):
            return False

        # Only auto retry for certain task types
        auto_retry_types = [
            TaskType.EMBEDDING_COMPUTATION,
            TaskType.AGENT_TASK,
            TaskType.DOCUMENT_EXPORT,
        ]
        if task_data.task_type not in auto_retry_types:
            return False

        # Don't auto retry if too many attempts
        if attempts >= 5:
            return False

        return True

    async def _calculate_auto_retry_delay(self, attempts: int) -> timedelta:
        """Calculate delay for auto retry."""
        # Exponential backoff with max delay of 1 hour
        delay_minutes = min(2**attempts, 60)
        return timedelta(minutes=delay_minutes)

    def _extract_error_type(self, error: str) -> str:
        """Extract error type from error message."""
        if "timeout" in error.lower():
            return "TimeoutError"
        elif "connection" in error.lower():
            return "ConnectionError"
        elif "rate limit" in error.lower():
            return "RateLimitError"
        elif "validation" in error.lower():
            return "ValidationError"
        else:
            return "UnknownError"

    async def _send_alert(self, task: DeadLetterTask) -> None:
        """Send alert for critical dead letter tasks."""
        # TODO: Implement alerting mechanism
        logger.error(
            f"CRITICAL: Task {task.original_task_id} failed with severity {task.severity}",
            extra={
                "task_id": str(task.original_task_id),
                "task_type": task.task_type.value,
                "error": task.error_message,
                "severity": task.severity,
                "category": task.category,
            },
        )


# Global dead letter queue instance
dead_letter_queue = DeadLetterQueue()
