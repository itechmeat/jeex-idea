"""
Queue Repository

Redis implementation of task queue repository.
Provides atomic queue operations, priority handling, and task status tracking.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from uuid import UUID

from ...services.queues.queue_manager import (
    TaskData,
    TaskType,
    TaskPriority,
    TaskStatus,
)
from ...infrastructure.redis.connection_factory import redis_connection_factory
from ...infrastructure.redis.exceptions import (
    RedisException,
    RedisConnectionException,
    RedisOperationTimeoutException,
)

logger = logging.getLogger(__name__)


class QueueRepository:
    """
    Redis repository for task queue operations.

    Provides atomic queue operations, priority handling, and comprehensive
    task status tracking with project isolation.
    """

    def __init__(self):
        self._redis_factory = redis_connection_factory
        self._lua_scripts = {}

    async def initialize(self) -> None:
        """Initialize repository and load Lua scripts."""
        try:
            await self._load_lua_scripts()
            logger.info("Queue repository initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize queue repository: {e}")
            raise

    async def _load_lua_scripts(self) -> None:
        """Load Redis Lua scripts for atomic queue operations."""

        # Atomic enqueue with priority
        enqueue_script = """
        local queue_key = KEYS[1]
        local priority_key = KEYS[2]
        local task_key = KEYS[3]
        local status_key = KEYS[4]
        local project_queue_key = KEYS[5]

        local priority = tonumber(ARGV[1])
        local task_data = ARGV[2]
        local max_size = tonumber(ARGV[3])
        local project_id = ARGV[4]
        local now = ARGV[5]

        -- Check queue size limit
        local queue_size = redis.call('LLEN', queue_key)
        if queue_size >= max_size then
            return {0, "Queue full", queue_size}
        end

        -- Check project-specific limit (25% of total)
        local project_size = redis.call('LLEN', project_queue_key)
        if project_size >= (max_size / 4) then
            return {0, "Project queue full", queue_size}
        end

        -- Store task data
        redis.call('SET', task_key, task_data)
        redis.call('EXPIRE', task_key, 86400)  -- 24 hours

        -- Add to priority queue (negative score for high-first ordering)
        redis.call('ZADD', priority_key, -priority, task_data)
        redis.call('EXPIRE', priority_key, 86400)

        -- Add to project queue
        redis.call('RPUSH', project_queue_key, task_data)
        redis.call('EXPIRE', project_queue_key, 86400)

        -- Initialize status
        redis.call('HMSET', status_key,
            'status', 'queued',
            'queued_at', now,
            'attempts', '0'
        )
        redis.call('EXPIRE', status_key, 86400)

        return {1, "Task enqueued", queue_size + 1}
        """

        # Atomic dequeue with priority handling
        dequeue_script = """
        local priority_key = KEYS[1]
        local queue_key = KEYS[2]
        local project_queue_key = KEYS[3]
        local task_key_prefix = KEYS[4]

        local worker_id = ARGV[1]
        local now = ARGV[2]

        -- Get highest priority task
        local tasks = redis.call('ZRANGE', priority_key, 0, 0)
        if #tasks == 0 then
            return {0, "No tasks available"}
        end

        local task_data = tasks[1]
        local task_info = cjson.decode(task_data)

        -- Remove from priority queue
        redis.call('ZREM', priority_key, task_data)

        -- Remove from project queue
        local project_queue_key = queue_key .. ":project:" .. task_info.project_id
        redis.call('LREM', project_queue_key, 1, task_data)

        -- Update status to running
        local status_key = task_key_prefix .. task_info.task_id .. ":status"
        local current_attempts = tonumber(redis.call('HGET', status_key, 'attempts') or 0)

        redis.call('HMSET', status_key,
            'status', 'running',
            'worker_id', worker_id,
            'started_at', now,
            'attempts', tostring(current_attempts + 1)
        )

        return {1, task_data, current_attempts + 1}
        """

        # Complete task with result
        complete_script = """
        local task_key_prefix = KEYS[1]
        local task_id = ARGV[1]
        local status = ARGV[2]
        local result = ARGV[3]
        local error = ARGV[4]
        local worker_id = ARGV[5]
        local now = ARGV[6]

        local status_key = task_key_prefix .. task_id .. ":status"

        local update_data = {
            'status', status,
            'completed_at', now
        }

        if result ~= "" then
            table.insert(update_data, 'result')
            table.insert(update_data, result)
        end

        if error ~= "" then
            table.insert(update_data, 'error')
            table.insert(update_data, error)
        end

        if worker_id ~= "" then
            table.insert(update_data, 'worker_id')
            table.insert(update_data, worker_id)
        end

        redis.call('HMSET', status_key, unpack(update_data))
        return {1, "Status updated"}
        """

        async with self._redis_factory.get_connection() as redis_client:
            self._lua_scripts["enqueue"] = await redis_client.script_load(
                enqueue_script
            )
            self._lua_scripts["dequeue"] = await redis_client.script_load(
                dequeue_script
            )
            self._lua_scripts["complete"] = await redis_client.script_load(
                complete_script
            )

    async def enqueue_task(
        self, task_data: TaskData, max_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Enqueue task with atomic operations.

        Args:
            task_data: Task data to enqueue
            max_size: Maximum queue size

        Returns:
            Enqueue result
        """
        try:
            queue_name = self._get_queue_name(task_data.task_type)
            queue_key = f"queue:{queue_name}"
            priority_key = f"{queue_key}:priority"
            task_key = f"task:{task_data.task_id}"
            status_key = f"task:{task_data.task_id}:status"
            project_queue_key = f"{queue_key}:project:{task_data.project_id}"

            task_json = json.dumps(task_data.dict(), default=str)

            async with self._redis_factory.get_connection(
                str(task_data.project_id)
            ) as redis_client:
                result = await redis_client.evalsha(
                    self._lua_scripts["enqueue"],
                    5,  # number of keys
                    queue_key,
                    priority_key,
                    task_key,
                    status_key,
                    project_queue_key,
                    task_data.priority.value,
                    task_json,
                    max_size,
                    str(task_data.project_id),
                    datetime.utcnow().isoformat(),
                )

            success, message, queue_size = result[0], result[1], result[2]

            return {
                "success": bool(success),
                "message": message,
                "queue_size": queue_size,
                "task_id": str(task_data.task_id),
            }

        except Exception as e:
            logger.error(f"Failed to enqueue task {task_data.task_id}: {e}")
            raise

    async def dequeue_task(
        self, task_type: TaskType, worker_id: str, project_id: Optional[UUID] = None
    ) -> Optional[TaskData]:
        """
        Dequeue highest priority task.

        Args:
            task_type: Type of task to dequeue
            worker_id: Worker ID for task assignment
            project_id: Optional project ID for project-specific tasks

        Returns:
            Task data or None if no tasks available
        """
        try:
            queue_name = self._get_queue_name(task_type)
            priority_key = f"queue:{queue_name}:priority"
            queue_key = f"queue:{queue_name}"
            task_key_prefix = "task:"

            async with self._redis_factory.get_connection(
                str(project_id) if project_id else None
            ) as redis_client:
                result = await redis_client.evalsha(
                    self._lua_scripts["dequeue"],
                    4,  # number of keys
                    priority_key,
                    queue_key,
                    "",
                    task_key_prefix,
                    worker_id,
                    datetime.utcnow().isoformat(),
                )

            success, task_json, attempts = (
                result[0],
                result[1],
                result[2] if len(result) > 2 else 0,
            )

            if not success:
                return None

            return TaskData.parse_raw(task_json)

        except Exception as e:
            logger.error(f"Failed to dequeue task of type {task_type.value}: {e}")
            raise

    async def complete_task(
        self,
        task_id: UUID,
        status: TaskStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> bool:
        """
        Complete task with status and result.

        Args:
            task_id: Task ID to complete
            status: Task completion status
            result: Optional task result
            error: Optional error message
            worker_id: Worker ID that completed the task

        Returns:
            True if task completed successfully
        """
        try:
            task_key_prefix = "task:"

            result_json = json.dumps(result, default=str) if result else ""
            error_msg = error or ""
            worker = worker_id or ""

            async with self._redis_factory.get_connection() as redis_client:
                result = await redis_client.evalsha(
                    self._lua_scripts["complete"],
                    1,  # number of keys
                    task_key_prefix,
                    str(task_id),
                    status.value,
                    result_json,
                    error_msg,
                    worker,
                    datetime.utcnow().isoformat(),
                )

            return bool(result[0])

        except Exception as e:
            logger.error(f"Failed to complete task {task_id}: {e}")
            return False

    async def get_task_status(self, task_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get task status information.

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
                    return {
                        "status": status_data.get("status"),
                        "worker_id": status_data.get("worker_id"),
                        "queued_at": status_data.get("queued_at"),
                        "started_at": status_data.get("started_at"),
                        "completed_at": status_data.get("completed_at"),
                        "attempts": int(status_data.get("attempts", 0)),
                        "error": status_data.get("error"),
                        "result": status_data.get("result"),
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

    async def get_queue_size(self, task_type: TaskType) -> int:
        """
        Get current queue size for task type.

        Args:
            task_type: Task type to check

        Returns:
            Queue size
        """
        try:
            queue_name = self._get_queue_name(task_type)
            priority_key = f"queue:{queue_name}:priority"

            async with self._redis_factory.get_connection() as redis_client:
                return await redis_client.zcard(priority_key)

        except Exception as e:
            logger.error(f"Failed to get queue size for {task_type.value}: {e}")
            return 0

    async def get_project_queue_size(
        self, task_type: TaskType, project_id: UUID
    ) -> int:
        """
        Get queue size for specific project.

        Args:
            task_type: Task type to check
            project_id: Project ID

        Returns:
            Project queue size
        """
        try:
            queue_name = self._get_queue_name(task_type)
            project_queue_key = f"queue:{queue_name}:project:{project_id}"

            async with self._redis_factory.get_connection(
                str(project_id)
            ) as redis_client:
                return await redis_client.llen(project_queue_key)

        except Exception as e:
            logger.error(f"Failed to get project queue size for {project_id}: {e}")
            return 0

    async def get_queue_stats(self, task_type: TaskType) -> Dict[str, Any]:
        """
        Get comprehensive queue statistics.

        Args:
            task_type: Task type to get stats for

        Returns:
            Queue statistics
        """
        try:
            queue_name = self._get_queue_name(task_type)
            priority_key = f"queue:{queue_name}:priority"

            async with self._redis_factory.get_connection() as redis_client:
                # Get priority distribution
                priority_counts = {}
                for priority in range(1, 51):  # Priorities 1-50
                    count = await redis_client.zcount(
                        priority_key, -priority, -priority
                    )
                    if count > 0:
                        priority_counts[priority] = count

                # Get tasks by status
                status_counts = {}
                for status in TaskStatus:
                    pattern = "task:*:status"
                    keys = await redis_client.keys(pattern)
                    count = 0
                    for key in keys:
                        task_status = await redis_client.hget(key, "status")
                        if task_status == status.value:
                            count += 1
                    status_counts[status.value] = count

                # Get oldest and newest tasks
                oldest = await redis_client.zrange(priority_key, 0, 0, withscores=True)
                newest = await redis_client.zrange(
                    priority_key, -1, -1, withscores=True
                )

                oldest_timestamp = oldest[0][1] if oldest and oldest[0] else None
                newest_timestamp = newest[0][1] if newest and newest[0] else None

                total_tasks = await redis_client.zcard(priority_key)

                return {
                    "task_type": task_type.value,
                    "queue_name": queue_name,
                    "total_tasks": total_tasks,
                    "priority_distribution": priority_counts,
                    "status_distribution": status_counts,
                    "oldest_task_timestamp": float(oldest_timestamp)
                    if oldest_timestamp
                    else None,
                    "newest_task_timestamp": float(newest_timestamp)
                    if newest_timestamp
                    else None,
                    "timestamp": datetime.utcnow().isoformat(),
                }

        except Exception as e:
            logger.error(f"Failed to get queue stats for {task_type.value}: {e}")
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

    def _get_queue_name(self, task_type: TaskType) -> str:
        """Get queue name for task type."""
        queue_names = {
            TaskType.EMBEDDING_COMPUTATION: "embeddings",
            TaskType.AGENT_TASK: "agent_tasks",
            TaskType.DOCUMENT_EXPORT: "exports",
            TaskType.BATCH_PROCESSING: "batch",
            TaskType.NOTIFICATION: "notifications",
            TaskType.CLEANUP: "cleanup",
            TaskType.HEALTH_CHECK: "health_checks",
        }
        return queue_names.get(task_type, "default")

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
            stats["total_tasks"] += queue_stats.get("total_tasks", 0)

        return stats


# Global queue repository instance
queue_repository = QueueRepository()
