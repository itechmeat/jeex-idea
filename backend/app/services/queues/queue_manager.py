"""
Queue Manager Service

Primary task queue management service with Redis backend.
Provides atomic queue operations, priority handling, and task status tracking.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List, Union, Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.core.config import settings
from app.infrastructure.redis.connection_factory import redis_connection_factory
from app.infrastructure.redis.exceptions import (
    RedisException,
    RedisOperationTimeoutException,
    RedisConnectionException,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class TaskType(str, Enum):
    """Task types for queue management."""

    EMBEDDING_COMPUTATION = "embedding_computation"
    AGENT_TASK = "agent_task"
    DOCUMENT_EXPORT = "document_export"
    BATCH_PROCESSING = "batch_processing"
    NOTIFICATION = "notification"
    CLEANUP = "cleanup"
    HEALTH_CHECK = "health_check"


class TaskPriority(int, Enum):
    """Task priority levels (higher number = higher priority)."""

    LOW = 1
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20
    URGENT = 50


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


class TaskStatus(str, Enum):
    """Task execution status."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class TaskData(BaseModel):
    """Task data model."""

    task_id: UUID = Field(default_factory=uuid4)
    task_type: TaskType = Field(..., description="Type of task")
    project_id: UUID = Field(..., description="Project ID for isolation")
    priority: TaskPriority = Field(TaskPriority.NORMAL, description="Task priority")
    data: Dict[str, Any] = Field(default_factory=dict, description="Task payload")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    scheduled_at: Optional[datetime] = Field(
        None, description="Scheduled execution time"
    )
    timeout_seconds: int = Field(default=300, ge=1, le=3600, description="Task timeout")
    max_attempts: int = Field(
        default=3, ge=1, le=10, description="Maximum retry attempts"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, v):
        """Validate scheduled execution time."""
        if v and v < datetime.utcnow():
            raise ValueError("scheduled_at cannot be in the past")
        return v


class TaskResult(BaseModel):
    """Task execution result."""

    task_id: UUID
    status: TaskStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    attempts: int = 0
    worker_id: Optional[str] = None


class QueueManager:
    """
    High-performance task queue manager with Redis backend.

    Implements atomic queue operations, priority handling, and comprehensive
    task status tracking with project isolation.
    """

    # Queue configurations
    QUEUES = {
        TaskType.EMBEDDING_COMPUTATION: {
            "name": "embeddings",
            "max_size": 1000,
            "priority_levels": 5,
            "processing_timeout": 600,  # 10 minutes
        },
        TaskType.AGENT_TASK: {
            "name": "agent_tasks",
            "max_size": 500,
            "priority_levels": 5,
            "processing_timeout": 1800,  # 30 minutes
        },
        TaskType.DOCUMENT_EXPORT: {
            "name": "exports",
            "max_size": 200,
            "priority_levels": 3,
            "processing_timeout": 1200,  # 20 minutes
        },
        TaskType.BATCH_PROCESSING: {
            "name": "batch",
            "max_size": 100,
            "priority_levels": 3,
            "processing_timeout": 3600,  # 1 hour
        },
        TaskType.NOTIFICATION: {
            "name": "notifications",
            "max_size": 5000,
            "priority_levels": 2,
            "processing_timeout": 30,  # 30 seconds
        },
        TaskType.CLEANUP: {
            "name": "cleanup",
            "max_size": 100,
            "priority_levels": 2,
            "processing_timeout": 600,  # 10 minutes
        },
        TaskType.HEALTH_CHECK: {
            "name": "health_checks",
            "max_size": 50,
            "priority_levels": 1,
            "processing_timeout": 60,  # 1 minute
        },
    }

    def __init__(self, bootstrap_project_id: Optional[UUID] = None):
        self._redis_factory = redis_connection_factory
        self._lua_scripts = {}
        self._initialized = False
        self._lock = asyncio.Lock()
        self._bootstrap_project_id = bootstrap_project_id

    async def initialize(self) -> None:
        """Initialize queue manager and load Lua scripts."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            try:
                await self._load_lua_scripts()
                self._initialized = True
                logger.info("Queue manager initialized successfully")

            except Exception as e:
                logger.error(f"Failed to initialize queue manager: {e}")
                raise

    async def _load_lua_scripts(self) -> None:
        """Load Redis Lua scripts for atomic queue operations."""

        # Atomic enqueue script
        enqueue_script = """
        local queue_key = KEYS[1]
        local task_key = KEYS[2]
        local status_key = KEYS[3]
        local priority = tonumber(ARGV[1])
        local task_data = ARGV[2]
        local max_size = tonumber(ARGV[3])
        local project_id = ARGV[4]

        -- Check queue size limit
        local queue_size = redis.call('LLEN', queue_key)
        if queue_size >= max_size then
            return {0, "Queue full"}
        end

        -- Check project-specific limits if needed
        local project_queue_key = queue_key .. ":project:" .. project_id
        local project_size = redis.call('LLEN', project_queue_key)
        if project_size >= max_size / 4 then  -- 25% of total limit per project
            return {0, "Project queue full"}
        end

        -- Store task data
        redis.call('SET', task_key, task_data)
        redis.call('EXPIRE', task_key, 86400)  -- 24 hours

        -- Add to priority queue (score = negative priority for high-first)
        redis.call('ZADD', queue_key .. ":priority", -priority, task_data)

        -- Add to project queue
        redis.call('RPUSH', project_queue_key, task_data)
        redis.call('EXPIRE', project_queue_key, 86400)

        -- Update status
        redis.call('HSET', status_key, 'status', 'queued', 'queued_at', ARGV[5])
        redis.call('EXPIRE', status_key, 86400)

        return {1, "Task enqueued", queue_size + 1}
        """

        # Atomic dequeue script
        dequeue_script = """
        local queue_key = KEYS[1]
        local project_key = KEYS[2]
        local worker_id = ARGV[1]

        -- Get highest priority task
        local tasks = redis.call('ZRANGE', queue_key .. ":priority", 0, 0)
        if #tasks == 0 then
            return {0, "No tasks available"}
        end

        local task_data = tasks[1]
        local task_info = cjson.decode(task_data)

        -- Remove from priority queue
        redis.call('ZREM', queue_key .. ":priority", task_data)

        -- Remove from project queue
        local project_queue_key = queue_key .. ":project:" .. task_info.project_id
        redis.call('LREM', project_queue_key, 1, task_data)

        -- Update status to running
        local status_key = "task:" .. task_info.task_id .. ":status"
        local current_attempts = tonumber(redis.call('HGET', status_key, 'attempts') or 0)
        redis.call('HSET', status_key,
            'status', 'running',
            'worker_id', worker_id,
            'started_at', ARGV[2],
            'attempts', tostring(current_attempts + 1)
        )

        return {1, task_data}
        """

        async with self._redis_factory.get_admin_connection() as redis_client:
            self._lua_scripts["enqueue"] = await redis_client.script_load(
                enqueue_script
            )
            self._lua_scripts["dequeue"] = await redis_client.script_load(
                dequeue_script
            )

    async def enqueue_task(
        self,
        task_type: TaskType,
        project_id: UUID,
        data: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        scheduled_at: Optional[datetime] = None,
        timeout_seconds: Optional[int] = None,
        max_attempts: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UUID:
        """
        Enqueue task with priority and scheduling.

        Args:
            task_type: Type of task to enqueue
            project_id: Project ID for isolation
            data: Task payload data
            priority: Task priority
            scheduled_at: Optional scheduled execution time
            timeout_seconds: Task timeout in seconds
            max_attempts: Maximum retry attempts
            metadata: Additional metadata

        Returns:
            Task ID of enqueued task

        Raises:
            RedisException: If enqueue fails
            ValueError: If queue is full or parameters invalid
        """
        await self.initialize()

        queue_config = self.QUEUES.get(task_type)
        if not queue_config:
            raise ValueError(f"Unknown task type: {task_type}")

        task = TaskData(
            task_type=task_type,
            project_id=project_id,
            priority=priority,
            data=data,
            scheduled_at=scheduled_at,
            timeout_seconds=timeout_seconds or queue_config["processing_timeout"],
            max_attempts=max_attempts or 3,
            metadata=metadata or {},
        )

        with tracer.start_as_current_span("queue_manager.enqueue") as span:
            span.set_attribute("task_id", str(task.task_id))
            span.set_attribute("task_type", task_type.value)
            span.set_attribute("project_id", str(project_id))
            span.set_attribute("priority", priority.value)

            try:
                queue_name = queue_config["name"]
                queue_key = f"queue:{queue_name}"
                task_key = f"task:{task.task_id}"
                status_key = f"task:{task.task_id}:status"

                task_json = json.dumps(task.dict(), default=str)

                async with self._redis_factory.get_connection(
                    str(project_id)
                ) as redis_client:
                    # Use atomic enqueue script
                    result = await redis_client.evalsha(
                        self._lua_scripts["enqueue"],
                        3,  # number of keys
                        queue_key,
                        task_key,
                        status_key,
                        task.priority.value,
                        task_json,
                        queue_config["max_size"],
                        str(project_id),
                        datetime.utcnow().isoformat(),
                    )

                success, message = result[0], result[1]

                if not success:
                    raise ValueError(f"Failed to enqueue task: {message}")

                span.set_attribute("queue_size", result[2] if len(result) > 2 else 0)
                span.set_status(Status(StatusCode.OK))

                logger.info(
                    f"Enqueued task {task.task_id} of type {task_type.value}",
                    extra={
                        "task_id": str(task.task_id),
                        "task_type": task_type.value,
                        "project_id": str(project_id),
                        "priority": priority.value,
                    },
                )

                return task.task_id

            except Exception as e:
                logger.error(f"Failed to enqueue task: {e}")
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise

    async def dequeue_task(
        self,
        task_type: TaskType,
        worker_id: str,
        project_id: Optional[UUID] = None,
        timeout_seconds: int = 30,
    ) -> Optional[TaskData]:
        """
        Dequeue next available task with priority handling.

        Args:
            task_type: Type of task to dequeue
            worker_id: Worker ID for task assignment
            project_id: Optional project ID for project-specific tasks
            timeout_seconds: Timeout for blocking dequeue

        Returns:
            Task data or None if no task available

        Raises:
            RedisException: If dequeue fails
        """
        await self.initialize()

        queue_config = self.QUEUES.get(task_type)
        if not queue_config:
            raise ValueError(f"Unknown task type: {task_type}")

        with tracer.start_as_current_span("queue_manager.dequeue") as span:
            span.set_attribute("task_type", task_type.value)
            span.set_attribute("worker_id", worker_id)
            if project_id:
                span.set_attribute("project_id", str(project_id))

            try:
                # Import repository here to avoid circular imports
                from app.infrastructure.repositories.queue_repository import (
                    queue_repository,
                )

                queue_name = queue_config["name"]

                # CRITICAL FIX: Pass timeout_seconds to repository for proper blocking behavior
                # If project_id specified, try project-specific dequeue first
                if project_id:
                    task_data = await queue_repository.dequeue_task(
                        task_type, worker_id, project_id, timeout_seconds
                    )
                    if task_data:
                        span.set_attribute("task_id", str(task_data.task_id))
                        span.set_attribute("project_id", str(task_data.project_id))
                        span.set_attribute("queue_source", "project_specific")
                        span.set_status(Status(StatusCode.OK))
                        return task_data

                # Fallback to general queue - use default project_id
                default_project_id = (
                    project_id
                    or self._bootstrap_project_id
                    or UUID("12345678-1234-5678-9abc-123456789abc")
                )  # TODO: Extract from context
                task_data = await queue_repository.dequeue_task(
                    task_type, worker_id, default_project_id, timeout_seconds
                )

                if task_data:
                    span.set_attribute("task_id", str(task_data.task_id))
                    span.set_attribute("project_id", str(task_data.project_id))
                    span.set_attribute("queue_source", "general")
                    span.set_status(Status(StatusCode.OK))
                    return task_data
                else:
                    span.set_attribute("no_tasks_available", True)
                    span.set_status(Status(StatusCode.OK))
                    return None

            except Exception as e:
                logger.error(f"Failed to dequeue task: {e}")
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise

    async def _process_dequeued_task(
        self, task_json: str, worker_id: str, project_id: str
    ) -> TaskData:
        """Process dequeued task and update status."""
        task_data = TaskData.parse_raw(task_json)
        status_key = f"task:{task_data.task_id}:status"

        async with self._redis_factory.get_connection(project_id) as redis_client:
            current_attempts = int(await redis_client.hget(status_key, "attempts") or 0)
            await redis_client.hset(
                status_key,
                mapping={
                    "status": TaskStatus.RUNNING.value,
                    "worker_id": worker_id,
                    "started_at": datetime.utcnow().isoformat(),
                    "attempts": str(current_attempts + 1),
                },
            )

        return task_data

    async def complete_task(
        self,
        task_id: UUID,
        result: Optional[Dict[str, Any]] = None,
        worker_id: Optional[str] = None,
    ) -> bool:
        """
        Mark task as completed.

        Args:
            task_id: Task ID to complete
            result: Task execution result
            worker_id: Worker ID that completed the task

        Returns:
            True if task marked as completed
        """
        return await self._update_task_status(
            task_id, TaskStatus.COMPLETED, result=result, worker_id=worker_id
        )

    async def fail_task(
        self,
        task_id: UUID,
        error: str,
        worker_id: Optional[str] = None,
        retry: bool = True,
    ) -> bool:
        """
        Mark task as failed and optionally retry.

        Args:
            task_id: Task ID that failed
            error: Error message
            worker_id: Worker ID that failed the task
            retry: Whether to retry the task

        Returns:
            True if task status updated
        """
        # Get task data to check retry attempts
        task_data = await self.get_task_data(task_id)
        if not task_data:
            return False

        # Check if we should retry
        if retry and task_data.max_attempts > 0:
            status = await self.get_task_status(task_id)
            current_attempts = status.get("attempts", 0)

            if current_attempts < task_data.max_attempts:
                # Requeue task with exponential backoff
                await self._retry_task(task_id, current_attempts)
                return await self._update_task_status(
                    task_id, TaskStatus.RETRYING, error=error, worker_id=worker_id
                )

        # Mark as failed (no more retries)
        return await self._update_task_status(
            task_id, TaskStatus.FAILED, error=error, worker_id=worker_id
        )

    async def _retry_task(self, task_id: UUID, attempt: int) -> bool:
        """Retry task with exponential backoff."""
        task_data = await self.get_task_data(task_id)
        if not task_data:
            return False

        # Calculate backoff delay
        delay_seconds = min(2**attempt, 300)  # Max 5 minutes
        scheduled_at = datetime.utcnow() + timedelta(seconds=delay_seconds)

        # Promote priority for retry using proper enum mapping
        new_priority = promote_task_priority(task_data.priority)

        return await self.enqueue_task(
            task_type=task_data.task_type,
            project_id=task_data.project_id,
            data=task_data.data,
            priority=new_priority,
            scheduled_at=scheduled_at,
            timeout_seconds=task_data.timeout_seconds,
            max_attempts=task_data.max_attempts - 1,
            metadata={**task_data.metadata, "retry_attempt": attempt + 1},
        )

    async def cancel_task(self, task_id: UUID) -> bool:
        """
        Cancel a queued or running task.

        Args:
            task_id: Task ID to cancel

        Returns:
            True if task cancelled
        """
        return await self._update_task_status(task_id, TaskStatus.CANCELLED)

    async def get_task_status(self, task_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get current task status.

        Args:
            task_id: Task ID to check

        Returns:
            Task status information or None if not found
        """
        try:
            # Import repository here to avoid circular imports
            from app.infrastructure.repositories.queue_repository import (
                queue_repository,
            )

            # First get task data to extract project_id
            task_data = await self.get_task_data(task_id)
            if not task_data:
                return None

            # Use repository method with project_id
            status_data = await queue_repository.get_task_status(
                task_id, task_data.project_id
            )

            if status_data:
                return {
                    "status": status_data.get("status"),
                    "worker_id": status_data.get("worker_id"),
                    "queued_at": status_data.get("queued_at"),
                    "started_at": status_data.get("started_at"),
                    "completed_at": status_data.get("completed_at"),
                    "attempts": int(status_data.get("attempts", 0)),
                    "error": status_data.get("error"),
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get task status for {task_id}: {e}")
            return None

    async def get_task_data(self, task_id: UUID) -> Optional[TaskData]:
        """
        Get task data.

        Args:
            task_id: Task ID to retrieve

        Returns:
            Task data or None if not found
        """
        try:
            # Import repository here to avoid circular imports
            from app.infrastructure.repositories.queue_repository import (
                queue_repository,
            )

            # Try to find project_id from known task associations
            # For now, use a default project_id - TODO: Extract from context
            default_project_id = self._bootstrap_project_id or UUID(
                "12345678-1234-5678-9abc-123456789abc"
            )

            # Use repository method with project_id
            return await queue_repository.get_task_data(task_id, default_project_id)

        except Exception as e:
            logger.error(f"Failed to get task data for {task_id}: {e}")
            return None

    async def _update_task_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> bool:
        """Update task status atomically."""
        try:
            # Import repository here to avoid circular imports
            from app.infrastructure.repositories.queue_repository import (
                queue_repository,
            )

            # Get task data to extract project_id
            task_data = await self.get_task_data(task_id)
            if not task_data:
                logger.error(f"Cannot update status for unknown task {task_id}")
                return False

            # Update status using repository
            success = await queue_repository.complete_task(
                task_id=task_id,
                project_id=task_data.project_id,
                status=status,
                result=result,
                error=error,
                worker_id=worker_id,
            )

            if success:
                logger.debug(f"Updated task {task_id} status to {status.value}")
            else:
                logger.error(
                    f"Failed to update task {task_id} status to {status.value}"
                )

            return success

        except Exception as e:
            logger.error(f"Failed to update task status for {task_id}: {e}")
            return False

    async def get_queue_stats(
        self, task_type: TaskType, project_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Get queue statistics.

        Args:
            task_type: Task type to get stats for
            project_id: Optional project ID for project-specific stats

        Returns:
            Queue statistics
        """
        try:
            # Import repository here to avoid circular imports
            from app.infrastructure.repositories.queue_repository import (
                queue_repository,
            )

            # Use default project_id if not provided
            default_project_id = (
                project_id
                or self._bootstrap_project_id
                or UUID("12345678-1234-5678-9abc-123456789abc")
            )

            # Use repository method with project_id
            return await queue_repository.get_queue_stats(task_type, default_project_id)

        except Exception as e:
            logger.error(f"Failed to get queue stats for {task_type}: {e}")
            return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

    async def cleanup_expired_tasks(self, max_age_hours: int = 24) -> int:
        """
        Clean up expired task data.

        Args:
            max_age_hours: Maximum age for task data

        Returns:
            Number of tasks cleaned up
        """
        try:
            # Import repository here to avoid circular imports
            from app.infrastructure.repositories.queue_repository import (
                queue_repository,
            )

            # Use default project_id for cleanup - TODO: Clean up for all projects
            default_project_id = self._bootstrap_project_id or UUID(
                "12345678-1234-5678-9abc-123456789abc"
            )

            # Use repository method with project_id
            return await queue_repository.cleanup_expired_tasks(
                default_project_id, max_age_hours
            )

        except Exception as e:
            logger.error(f"Failed to cleanup expired tasks: {e}")
            return 0

    async def get_all_queue_stats(
        self, project_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Get statistics for all queues.

        Args:
            project_id: Optional project ID for project-specific stats

        Returns:
            All queue statistics
        """
        try:
            # Import repository here to avoid circular imports
            from app.infrastructure.repositories.queue_repository import (
                queue_repository,
            )

            # Use default project_id if not provided
            default_project_id = (
                project_id
                or self._bootstrap_project_id
                or UUID("12345678-1234-5678-9abc-123456789abc")
            )

            # Use repository method with project_id
            return await queue_repository.get_all_queue_stats(default_project_id)

        except Exception as e:
            logger.error(f"Failed to get all queue stats: {e}")
            return {
                "queues": {},
                "total_tasks": 0,
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
            }


# Global queue manager instance
# Optional bootstrap project_id from environment for system initialization
_bootstrap_project_id = None
try:
    from app.core.config import settings

    if hasattr(settings, "BOOTSTRAP_PROJECT_ID"):
        _bootstrap_project_id = UUID(settings.BOOTSTRAP_PROJECT_ID)
except (ImportError, AttributeError, ValueError):
    pass

queue_manager = QueueManager(bootstrap_project_id=_bootstrap_project_id)
