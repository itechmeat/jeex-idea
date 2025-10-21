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

from pydantic import BaseModel, Field, validator

from opentelemetry import trace

from ...core.config import settings
from ...infrastructure.redis.connection_factory import redis_connection_factory
from ...infrastructure.redis.exceptions import (
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

    @validator("scheduled_at")
    def validate_scheduled_at(cls, v, values):
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

    def __init__(self):
        self._redis_factory = redis_connection_factory
        self._lua_scripts = {}
        self._initialized = False
        self._lock = asyncio.Lock()

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
        redis.call('HSET', status_key, 'status', 'queued', 'queued_at', ARGV[4])
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
        redis.call('HMSET', status_key,
            'status', 'running',
            'worker_id', worker_id,
            'started_at', ARGV[2],
            'attempts', tostring(tonumber(redis.call('HGET', status_key, 'attempts') or 0) + 1)
        )

        return {1, task_data}
        """

        async with self._redis_factory.get_connection() as redis_client:
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
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
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

            try:
                queue_name = queue_config["name"]
                queue_key = f"queue:{queue_name}"

                # If project_id specified, try project-specific queue first
                if project_id:
                    project_queue_key = f"{queue_key}:project:{project_id}"

                    async with self._redis_factory.get_connection(
                        str(project_id)
                    ) as redis_client:
                        # Try to get from project queue first
                        task_json = await redis_client.blpop(
                            project_queue_key, timeout=1
                        )

                        if task_json:
                            # Found task in project queue, update status and return
                            return await self._process_dequeued_task(
                                task_json[1], worker_id, str(project_id)
                            )

                # Fallback to general queue
                async with self._redis_factory.get_connection() as redis_client:
                    result = await redis_client.evalsha(
                        self._lua_scripts["dequeue"],
                        2,  # number of keys
                        queue_key,
                        str(project_id) if project_id else "",
                        worker_id,
                        datetime.utcnow().isoformat(),
                    )

                success, task_json = result[0], result[1]

                if not success:
                    span.set_attribute("no_tasks_available", True)
                    return None

                task_data = TaskData.parse_raw(task_json)
                span.set_attribute("task_id", str(task_data.task_id))
                span.set_attribute("project_id", str(task_data.project_id))

                return task_data

            except Exception as e:
                logger.error(f"Failed to dequeue task: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def _process_dequeued_task(
        self, task_json: str, worker_id: str, project_id: str
    ) -> TaskData:
        """Process dequeued task and update status."""
        task_data = TaskData.parse_raw(task_json)
        status_key = f"task:{task_data.task_id}:status"

        async with self._redis_factory.get_connection(project_id) as redis_client:
            await redis_client.hmset(
                status_key,
                {
                    "status": TaskStatus.RUNNING.value,
                    "worker_id": worker_id,
                    "started_at": datetime.utcnow().isoformat(),
                    "attempts": str(
                        int(await redis_client.hget(status_key, "attempts") or 0) + 1
                    ),
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

        # Requeue with higher priority for retry
        new_priority = min(task_data.priority.value + 2, TaskPriority.URGENT.value)

        return await self.enqueue_task(
            task_type=task_data.task_type,
            project_id=task_data.project_id,
            data=task_data.data,
            priority=TaskPriority(new_priority),
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
            status_key = f"task:{task_id}:status"

            async with self._redis_factory.get_connection() as redis_client:
                status_data = await redis_client.hgetall(status_key)

                if status_data:
                    # Convert string values to appropriate types
                    return {
                        "status": status_data.get("status"),
                        "worker_id": status_data.get("worker_id"),
                        "created_at": status_data.get("created_at"),
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
            task_key = f"task:{task_id}"

            async with self._redis_factory.get_connection() as redis_client:
                task_json = await redis_client.get(task_key)

                if task_json:
                    return TaskData.parse_raw(task_json)

            return None

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
            status_key = f"task:{task_id}:status"

            update_data = {
                "status": status.value,
                "completed_at": datetime.utcnow().isoformat(),
            }

            if result:
                update_data["result"] = json.dumps(result, default=str)

            if error:
                update_data["error"] = error

            if worker_id:
                update_data["worker_id"] = worker_id

            async with self._redis_factory.get_connection() as redis_client:
                await redis_client.hmset(status_key, update_data)

            logger.debug(f"Updated task {task_id} status to {status.value}")
            return True

        except Exception as e:
            logger.error(f"Failed to update task status for {task_id}: {e}")
            return False

    async def get_queue_stats(self, task_type: TaskType) -> Dict[str, Any]:
        """
        Get queue statistics.

        Args:
            task_type: Task type to get stats for

        Returns:
            Queue statistics
        """
        queue_config = self.QUEUES.get(task_type)
        if not queue_config:
            return {}

        try:
            queue_name = queue_config["name"]
            queue_key = f"queue:{queue_name}"

            async with self._redis_factory.get_connection() as redis_client:
                # Get queue sizes
                total_tasks = await redis_client.zcard(f"{queue_key}:priority")

                # Get tasks by status
                status_counts = {}
                for status in TaskStatus:
                    pattern = f"task:*:status"
                    keys = await redis_client.keys(pattern)
                    count = 0
                    for key in keys:
                        task_status = await redis_client.hget(key, "status")
                        if task_status == status.value:
                            count += 1
                    status_counts[status.value] = count

                return {
                    "task_type": task_type.value,
                    "queue_name": queue_name,
                    "total_queued": total_tasks,
                    "max_size": queue_config["max_size"],
                    "status_counts": status_counts,
                    "utilization": (total_tasks / queue_config["max_size"]) * 100,
                    "timestamp": datetime.utcnow().isoformat(),
                }

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
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
            cleaned_count = 0

            async with self._redis_factory.get_connection() as redis_client:
                # Find expired task keys
                task_pattern = "task:*"
                task_keys = await redis_client.keys(task_pattern)

                for key in task_keys:
                    # Skip status keys
                    if key.endswith(":status"):
                        continue

                    task_json = await redis_client.get(key)
                    if task_json:
                        try:
                            task_data = TaskData.parse_raw(task_json)
                            if task_data.created_at < cutoff_time:
                                # Delete task data and status
                                await redis_client.delete(key)
                                await redis_client.delete(f"{key}:status")
                                cleaned_count += 1
                        except:
                            pass

            logger.info(f"Cleaned up {cleaned_count} expired tasks")
            return cleaned_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired tasks: {e}")
            return 0

    async def get_all_queue_stats(self) -> Dict[str, Any]:
        """
        Get statistics for all queues.

        Returns:
            All queue statistics
        """
        stats = {
            "queues": {},
            "total_tasks": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }

        for task_type in TaskType:
            queue_stats = await self.get_queue_stats(task_type)
            stats["queues"][task_type.value] = queue_stats
            stats["total_tasks"] += queue_stats.get("total_queued", 0)

        return stats


# Global queue manager instance
queue_manager = QueueManager()
