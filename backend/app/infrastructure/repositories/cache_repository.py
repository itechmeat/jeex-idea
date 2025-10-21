"""
Redis Cache Repository Implementation

Infrastructure implementation of cache repository interfaces using Redis.
Provides Redis-backed persistence for domain entities with project isolation.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from uuid import UUID

import redis.asyncio as Redis
from redis.exceptions import RedisError

from opentelemetry import trace

from ...domain.cache.entities import (
    ProjectCache,
    UserSession,
    Progress,
    RateLimit,
    QueuedTask,
)
from ...domain.cache.value_objects import (
    CacheKey,
    TTL,
    CacheTag,
    QueuePriority,
    RateLimitWindow,
    CacheMetrics,
    CacheVersion,
)
from ...domain.cache.repository_interfaces import (
    CacheRepository,
    ProjectCacheRepository,
    UserSessionRepository,
    TaskQueueRepository,
    ProgressRepository,
    RateLimitRepository,
    CacheHealthRepository,
)
from ...infrastructure.redis.redis_service import redis_service
from ...infrastructure.redis.exceptions import RedisException
from ...services.queues.dead_letter import dead_letter_queue

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def _window_secs(window: RateLimitWindow) -> int:
    """Convert RateLimitWindow to integer seconds."""
    return int(str(window.value).rstrip("s"))


class RedisProjectCacheRepository(ProjectCacheRepository):
    """Redis implementation of project cache repository."""

    def __init__(self):
        self.metrics_buffer: List[CacheMetrics] = []
        self.metrics_buffer_size = 100

    async def save(self, cache: ProjectCache, project_id: UUID) -> None:
        """Save project cache entry to Redis."""
        start_time = time.time()
        key = cache.get_key()

        try:
            async with redis_service.get_connection(
                str(cache.project_id)
            ) as redis_client:
                # Prepare cache data
                cache_data = {
                    "project_id": str(cache.project_id),
                    "data": cache.data,
                    "version": cache.version.value,
                    "created_at": cache.created_at.isoformat(),
                    "expires_at": cache.expires_at.isoformat(),
                    "tags": [tag.value for tag in cache.tags],
                    "size_bytes": cache.size_bytes,
                    "access_count": cache.access_count,
                    "last_accessed_at": cache.last_accessed_at.isoformat()
                    if cache.last_accessed_at
                    else None,
                }

                # Calculate TTL
                ttl_seconds = max(
                    1, int((cache.expires_at - datetime.utcnow()).total_seconds())
                )

                # Store in Redis with TTL
                await redis_client.setex(
                    key.value, ttl_seconds, json.dumps(cache_data, default=str)
                )

                # Record metrics
                execution_time = (time.time() - start_time) * 1000
                self._record_metric(
                    "set",
                    str(key),
                    False,
                    execution_time,
                    cache.size_bytes,
                    str(cache.project_id),
                )

                logger.debug(
                    f"Saved project cache: {key.value}",
                    extra={
                        "project_id": str(cache.project_id),
                        "size_bytes": cache.size_bytes,
                    },
                )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._record_metric(
                "set",
                str(key),
                False,
                execution_time,
                None,
                str(cache.project_id),
                str(e),
            )
            logger.exception(f"Failed to save project cache {key.value}: {e}")
            raise RedisException(f"Failed to save project cache: {str(e)}") from e

    async def find_by_project_id(self, project_id: UUID) -> Optional[ProjectCache]:
        """Find cache entry by project ID."""
        start_time = time.time()
        key = CacheKey.project_data(project_id)

        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                cache_data = await redis_client.get(key.value)

                if cache_data:
                    cache = self._deserialize_project_cache(cache_data)
                    if cache and not cache.is_expired():
                        cache.access()
                        # Update access count and timestamp
                        await self._update_access_stats(cache)

                        execution_time = (time.time() - start_time) * 1000
                        self._record_metric(
                            "get",
                            str(key),
                            True,
                            execution_time,
                            cache.size_bytes,
                            str(project_id),
                        )

                        return cache

                execution_time = (time.time() - start_time) * 1000
                self._record_metric(
                    "get", str(key), False, execution_time, None, str(project_id)
                )
                return None

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._record_metric(
                "get", str(key), False, execution_time, None, str(project_id), str(e)
            )
            logger.exception(f"Failed to find project cache {project_id}: {e}")
            raise RedisException(f"Failed to find project cache: {str(e)}") from e

    async def find_by_key(
        self, key: CacheKey, project_id: UUID
    ) -> Optional[ProjectCache]:
        """Find cache entry by key within project scope."""
        try:
            return await self.find_by_project_id(project_id)

        except Exception as e:
            logger.exception(f"Failed to find cache by key {key.value}: {e}")
            raise RedisException(f"Failed to find cache by key: {str(e)}") from e

    async def invalidate_by_project_id(self, project_id: UUID) -> int:
        """Invalidate all cache entries for project."""
        start_time = time.time()
        count = 0

        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                # Find all project-related keys using cursor-based SCAN
                pattern = f"project:{project_id}:*"
                keys_to_delete = []

                # Use SCAN for non-blocking iteration
                cursor = 0
                while True:
                    cursor, keys = await redis_client.scan(
                        cursor, match=pattern, count=100
                    )
                    keys_to_delete.extend(keys)
                    if cursor == 0:
                        break

                # Use UNLINK for non-blocking deletion
                if keys_to_delete:
                    count = await redis_client.unlink(*keys_to_delete)

                execution_time = (time.time() - start_time) * 1000
                self._record_metric(
                    "delete",
                    f"project:{project_id}:*",
                    False,
                    execution_time,
                    None,
                    str(project_id),
                )

                logger.info(
                    f"Invalidated {count} cache entries for project {project_id}",
                    extra={"project_id": str(project_id), "count": count},
                )

                return count

        except Exception as e:
            logger.exception(
                f"Failed to invalidate caches for project {project_id}: {e}"
            )
            raise RedisException(f"Failed to invalidate caches: {str(e)}") from e

    async def invalidate_by_tag(self, tag: CacheTag, project_id: UUID) -> int:
        """Invalidate cache entries by tag within project scope."""
        # Note: Redis doesn't have native tag-based invalidation
        # This would require maintaining a tag index or using a different approach
        # For now, this is a placeholder implementation
        logger.warning(
            f"Tag-based invalidation not implemented for tag: {tag.value} in project {project_id}"
        )
        return 0

    async def find_expired(self, project_id: UUID) -> List[ProjectCache]:
        """Find expired cache entries for project."""
        # Note: Redis automatically handles TTL expiration
        # This would require scanning all keys which is inefficient
        # For now, return empty list
        return []

    async def delete(self, key: CacheKey, project_id: UUID) -> bool:
        """Delete cache entry by key within project scope."""
        start_time = time.time()

        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                result = await redis_client.delete(key.value)

                execution_time = (time.time() - start_time) * 1000
                self._record_metric(
                    "delete", str(key), False, execution_time, None, str(project_id)
                )

                return result > 0

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._record_metric(
                "delete", str(key), False, execution_time, None, str(project_id), str(e)
            )
            logger.exception(f"Failed to delete cache entry {key.value}: {e}")
            raise RedisException(f"Failed to delete cache entry: {str(e)}") from e

    async def exists(self, key: CacheKey, project_id: UUID) -> bool:
        """Check if cache entry exists within project scope."""
        start_time = time.time()

        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                result = await redis_client.exists(key.value)

                execution_time = (time.time() - start_time) * 1000
                self._record_metric(
                    "exists", str(key), False, execution_time, None, str(project_id)
                )

                return result > 0

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._record_metric(
                "exists", str(key), False, execution_time, None, str(project_id), str(e)
            )
            logger.exception(f"Failed to check cache entry existence {key.value}: {e}")
            raise RedisException(
                f"Failed to check cache entry existence: {str(e)}"
            ) from e

    async def get_ttl(self, key: CacheKey, project_id: UUID) -> Optional[int]:
        """Get remaining TTL for cache entry within project scope."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                ttl = await redis_client.ttl(key.value)
                return ttl if ttl > 0 else None

        except Exception as e:
            logger.exception(f"Failed to get TTL for cache entry {key.value}: {e}")
            raise RedisException(f"Failed to get TTL: {str(e)}") from e

    async def extend_ttl(self, key: CacheKey, ttl: TTL, project_id: UUID) -> bool:
        """Extend TTL for cache entry within project scope."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                result = await redis_client.expire(key.value, ttl.seconds)
                return result

        except Exception as e:
            logger.exception(f"Failed to extend TTL for cache entry {key.value}: {e}")
            raise RedisException(f"Failed to extend TTL: {str(e)}") from e

    async def record_metrics(
        self, operations: List[CacheMetrics], project_id: UUID
    ) -> None:
        """Record cache operation metrics for project."""
        self.metrics_buffer.extend(operations)

        # Flush buffer if it's full
        if len(self.metrics_buffer) >= self.metrics_buffer_size:
            await self._flush_metrics()

    def _deserialize_project_cache(self, cache_data: str) -> Optional[ProjectCache]:
        """Deserialize project cache from JSON."""
        try:
            data = json.loads(cache_data)
            return ProjectCache(
                project_id=UUID(data["project_id"]),
                data=data["data"],
                version=CacheVersion(data["version"]),
                created_at=datetime.fromisoformat(data["created_at"]),
                expires_at=datetime.fromisoformat(data["expires_at"]),
                tags=[CacheTag(tag) for tag in data.get("tags", [])],
                size_bytes=data.get("size_bytes", 0),
                access_count=data.get("access_count", 0),
                last_accessed_at=datetime.fromisoformat(data["last_accessed_at"])
                if data.get("last_accessed_at")
                else None,
            )
        except Exception as e:
            logger.error(f"Failed to deserialize project cache: {e}")
            return None

    async def _update_access_stats(self, cache: ProjectCache) -> None:
        """Update access statistics for cache entry."""
        try:
            async with redis_service.get_connection(
                str(cache.project_id)
            ) as redis_client:
                key = cache.get_key()
                cache_data = await redis_client.get(key.value)

                if cache_data:
                    data = json.loads(cache_data)
                    data["access_count"] = cache.access_count
                    data["last_accessed_at"] = cache.last_accessed_at.isoformat()

                    ttl_seconds = max(
                        1, int((cache.expires_at - datetime.utcnow()).total_seconds())
                    )
                    await redis_client.setex(
                        key.value, ttl_seconds, json.dumps(data, default=str)
                    )

        except Exception as e:
            logger.warning(
                f"Failed to update access stats for cache {cache.project_id}: {e}"
            )

    def _record_metric(
        self,
        operation_type: str,
        key_pattern: str,
        hit: bool,
        execution_time_ms: float,
        data_size_bytes: Optional[int],
        project_id: Optional[str],
        error: Optional[str] = None,
    ) -> None:
        """Record cache operation metric."""
        metric = CacheMetrics(
            operation_type=operation_type,
            key_pattern=key_pattern,
            hit=hit,
            execution_time_ms=execution_time_ms,
            data_size_bytes=data_size_bytes,
            project_id=project_id,
            error=error,
        )
        self.metrics_buffer.append(metric)

    async def _flush_metrics(self) -> None:
        """Flush metrics buffer to monitoring system."""
        if not self.metrics_buffer:
            return

        try:
            # Here you would send metrics to your monitoring system
            # For now, just log them
            logger.debug(f"Cache metrics: {len(self.metrics_buffer)} operations")
            self.metrics_buffer.clear()

        except Exception as e:
            logger.warning(f"Failed to flush cache metrics: {e}")


class RedisUserSessionRepository(UserSessionRepository):
    """Redis implementation of user session repository."""

    async def save(self, session: UserSession, project_id: UUID) -> None:
        """Save user session within project scope."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                session_data = {
                    "session_id": str(session.session_id),
                    "user_id": str(session.user_id),
                    "user_data": session.user_data,
                    "project_access": [str(pid) for pid in session.project_access],
                    "created_at": session.created_at.isoformat(),
                    "last_activity_at": session.last_activity_at.isoformat(),
                    "expires_at": session.expires_at.isoformat()
                    if session.expires_at
                    else None,
                    "is_active": session.is_active,
                    "project_id": str(project_id),
                }

                key = session.get_key()
                ttl_seconds = (
                    max(
                        1, int((session.expires_at - datetime.utcnow()).total_seconds())
                    )
                    if session.expires_at
                    else 7200
                )

                await redis_client.setex(
                    key.value, ttl_seconds, json.dumps(session_data, default=str)
                )

                logger.debug(
                    f"Saved user session: {session.session_id} for project {project_id}"
                )

        except Exception as e:
            logger.exception(f"Failed to save user session {session.session_id}: {e}")
            raise RedisException(f"Failed to save user session: {str(e)}") from e

    async def find_by_session_id(
        self, session_id: UUID, project_id: UUID
    ) -> Optional[UserSession]:
        """Find session by session ID within project scope."""
        try:
            key = CacheKey.user_session(session_id)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                session_data = await redis_client.get(key.value)

                if session_data:
                    session = self._deserialize_user_session(session_data)
                    if session and session.is_valid():
                        return session

            return None

        except Exception as e:
            logger.exception(f"Failed to find user session {session_id}: {e}")
            raise RedisException(f"Failed to find user session: {str(e)}") from e

    async def find_by_user_id(
        self, user_id: UUID, project_id: UUID
    ) -> List[UserSession]:
        """Find all sessions for user within project scope."""
        # Note: This would require scanning all session keys which is inefficient
        # In practice, you'd maintain a user->sessions index
        logger.warning(
            f"find_by_user_id not efficiently implemented for user {user_id} in project {project_id}"
        )
        return []

    async def find_active_by_user_id(
        self, user_id: UUID, project_id: UUID
    ) -> List[UserSession]:
        """Find active sessions for user within project scope."""
        # Similar to find_by_user_id, this would need an index
        logger.warning(
            f"find_active_by_user_id not efficiently implemented for user {user_id} in project {project_id}"
        )
        return []

    async def delete(self, session_id: UUID, project_id: UUID) -> bool:
        """Delete session by ID within project scope."""
        try:
            key = CacheKey.user_session(session_id)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                result = await redis_client.delete(key.value)
                return result > 0

        except Exception as e:
            logger.exception(f"Failed to delete user session {session_id}: {e}")
            raise RedisException(f"Failed to delete user session: {str(e)}") from e

    async def invalidate_all_for_user(self, user_id: UUID, project_id: UUID) -> int:
        """Invalidate all sessions for user within project scope."""
        # Note: Would need user->sessions index for efficient implementation
        logger.warning(
            f"invalidate_all_for_user not efficiently implemented for user {user_id} in project {project_id}"
        )
        return 0

    async def find_expired(self, project_id: UUID) -> List[UserSession]:
        """Find expired sessions for project."""
        # Redis handles TTL expiration automatically
        return []

    async def cleanup_expired(self, project_id: UUID) -> int:
        """Clean up expired sessions for project."""
        # Redis handles TTL expiration automatically
        return 0

    async def extend_session(
        self, session_id: UUID, ttl: TTL, project_id: UUID
    ) -> bool:
        """Extend session TTL within project scope."""
        try:
            key = CacheKey.user_session(session_id)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                # Update session expiry time first
                session_data = await redis_client.get(key.value)
                if session_data:
                    data = json.loads(session_data)
                    data["expires_at"] = (
                        datetime.utcnow() + timedelta(seconds=ttl.seconds)
                    ).isoformat()
                    await redis_client.setex(
                        key.value, ttl.seconds, json.dumps(data, default=str)
                    )
                    return True

                return False

        except Exception as e:
            logger.exception(f"Failed to extend session {session_id}: {e}")
            raise RedisException(f"Failed to extend session: {str(e)}") from e

    async def update_activity(self, session_id: UUID, project_id: UUID) -> bool:
        """Update session last activity within project scope."""
        try:
            key = CacheKey.user_session(session_id)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                session_data = await redis_client.get(key.value)
                if session_data:
                    data = json.loads(session_data)
                    data["last_activity_at"] = datetime.utcnow().isoformat()

                    # Get remaining TTL
                    ttl = await redis_client.ttl(key.value)
                    if ttl > 0:
                        await redis_client.setex(
                            key.value, ttl, json.dumps(data, default=str)
                        )
                        return True

                return False

        except Exception as e:
            logger.exception(f"Failed to update session activity {session_id}: {e}")
            raise RedisException(f"Failed to update session activity: {str(e)}") from e

    def _deserialize_user_session(self, session_data: str) -> Optional[UserSession]:
        """Deserialize user session from JSON."""
        try:
            data = json.loads(session_data)
            return UserSession(
                session_id=UUID(data["session_id"]),
                user_id=UUID(data["user_id"]),
                user_data=data["user_data"],
                project_access=[UUID(pid) for pid in data.get("project_access", [])],
                created_at=datetime.fromisoformat(data["created_at"]),
                last_activity_at=datetime.fromisoformat(data["last_activity_at"]),
                expires_at=datetime.fromisoformat(data["expires_at"])
                if data.get("expires_at")
                else None,
                is_active=data.get("is_active", True),
            )
        except Exception as e:
            logger.error(f"Failed to deserialize user session: {e}")
            return None


class RedisTaskQueueRepository(TaskQueueRepository):
    """Redis implementation of task queue repository."""

    async def enqueue(
        self, queue_name: str, task: QueuedTask, project_id: UUID
    ) -> None:
        """Add task to queue within project scope."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                queue_key = CacheKey.queue(queue_name)
                task_data = {
                    "task_id": str(task.task_id),
                    "task_type": task.task_type,
                    "task_data": task.task_data,
                    "priority": task.priority.value,
                    "status": task.status,
                    "created_at": task.created_at.isoformat(),
                    "updated_at": task.updated_at.isoformat(),
                    "attempts": task.attempts,
                    "max_attempts": task.max_attempts,
                    "error_message": task.error_message,
                    "project_id": str(project_id),
                }

                # Use Redis list for queue (LPUSH for FIFO)
                await redis_client.lpush(
                    queue_key.value, json.dumps(task_data, default=str)
                )

                # Store task status separately
                status_key = task.get_status_key()
                await redis_client.setex(
                    status_key.value,
                    TTL.task_status().seconds,
                    json.dumps(task_data, default=str),
                )

                logger.debug(
                    f"Enqueued task {task.task_id} to {queue_name} for project {project_id}"
                )

        except Exception as e:
            logger.exception(f"Failed to enqueue task {task.task_id}: {e}")
            raise RedisException(f"Failed to enqueue task: {str(e)}") from e

    async def dequeue(self, queue_name: str, project_id: UUID) -> Optional[QueuedTask]:
        """Remove and return next task from queue within project scope."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                queue_key = CacheKey.queue(queue_name)

                # Use RPOP for FIFO
                task_data = await redis_client.rpop(queue_key.value)

                if task_data:
                    task = self._deserialize_queued_task(task_data)
                    if task:
                        # Update status to processing
                        task.update_status("processing")
                        await self.update_task_status(
                            task.task_id, "processing", project_id
                        )
                        return task

                return None

        except Exception as e:
            logger.exception(f"Failed to dequeue task from {queue_name}: {e}")
            raise RedisException(f"Failed to dequeue task: {str(e)}") from e

    async def peek(self, queue_name: str, project_id: UUID) -> Optional[QueuedTask]:
        """Peek at next task without removing it within project scope."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                queue_key = CacheKey.queue(queue_name)

                # Use LRANGE to peek at last element (next to be dequeued)
                tasks = await redis_client.lrange(queue_key.value, -1, -1)

                if tasks:
                    return self._deserialize_queued_task(tasks[0])

                return None

        except Exception as e:
            logger.exception(f"Failed to peek at queue {queue_name}: {e}")
            raise RedisException(f"Failed to peek at queue: {str(e)}") from e

    async def get_queue_size(self, queue_name: str, project_id: UUID) -> int:
        """Get queue size within project scope."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                queue_key = CacheKey.queue(queue_name)
                return await redis_client.llen(queue_key.value)

        except Exception as e:
            logger.exception(f"Failed to get queue size for {queue_name}: {e}")
            raise RedisException(f"Failed to get queue size: {str(e)}") from e

    async def get_queue_status(
        self, queue_name: str, project_id: UUID
    ) -> Dict[str, Any]:
        """Get detailed queue status within project scope."""
        try:
            size = await self.get_queue_size(queue_name, project_id)

            # Count tasks by status (this is inefficient in Redis, would need better design)
            status_counts = {
                "queued": size,
                "processing": 0,
                "completed": 0,
                "failed": 0,
            }

            return {
                "queue_name": queue_name,
                "size": size,
                "status_counts": status_counts,
                "timestamp": datetime.utcnow().isoformat(),
                "project_id": str(project_id),
            }

        except Exception as e:
            logger.exception(f"Failed to get queue status for {queue_name}: {e}")
            raise RedisException(f"Failed to get queue status: {str(e)}") from e

    async def update_task_status(
        self,
        task_id: UUID,
        status: str,
        project_id: UUID,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update task status within project scope."""
        try:
            status_key = CacheKey.task_status(task_id)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                task_data = await redis_client.get(status_key.value)

                if task_data:
                    data = json.loads(task_data)
                    data["status"] = status
                    data["updated_at"] = datetime.utcnow().isoformat()
                    if error_message:
                        data["error_message"] = error_message

                    await redis_client.setex(
                        status_key.value,
                        TTL.task_status().seconds,
                        json.dumps(data, default=str),
                    )
                    return True

                return False

        except Exception as e:
            logger.exception(f"Failed to update task status {task_id}: {e}")
            raise RedisException(f"Failed to update task status: {str(e)}") from e

    async def find_task_by_id(
        self, task_id: UUID, project_id: UUID
    ) -> Optional[QueuedTask]:
        """Find task by ID within project scope."""
        try:
            status_key = CacheKey.task_status(task_id)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                task_data = await redis_client.get(status_key.value)

                if task_data:
                    return self._deserialize_queued_task(task_data)

                return None

        except Exception as e:
            logger.exception(f"Failed to find task {task_id}: {e}")
            raise RedisException(f"Failed to find task: {str(e)}") from e

    async def find_tasks_by_status(
        self, queue_name: str, status: str, project_id: UUID
    ) -> List[QueuedTask]:
        """Find tasks by status within project scope."""
        # Note: This is inefficient in Redis, would need status indexes
        logger.warning(
            f"find_tasks_by_status not efficiently implemented for queue {queue_name} in project {project_id}"
        )
        return []

    async def move_to_dead_letter(
        self, task_id: UUID, error_message: str, project_id: UUID
    ) -> bool:
        """Move task to dead letter queue within project scope."""
        try:
            task = await self.find_task_by_id(task_id, project_id)
            if task:
                task.update_status("failed", error_message)
                task.increment_attempts()

                # Import TaskData and convert QueuedTask to TaskData for DeadLetterQueue
                from ...services.queues.queue_manager import (
                    TaskData,
                    TaskType,
                    TaskPriority,
                )

                # Convert QueuedTask to TaskData format for dead_letter_queue
                task_data = TaskData(
                    task_id=task.task_id,
                    task_type=TaskType(task.task_type)
                    if isinstance(task.task_type, str)
                    else task.task_type,
                    project_id=project_id,
                    priority=task.priority
                    if isinstance(task.priority, TaskPriority)
                    else TaskPriority.NORMAL,
                    data=task.task_data,
                    metadata={"original_status": task.status, "error": error_message},
                )

                # Move to dead letter queue using DeadLetterQueue.add_task()
                await dead_letter_queue.add_task(
                    task_data=task_data,
                    error=error_message,
                    attempts=task.attempts,
                    category="retry_exhausted",
                    severity="medium",
                )
                return True

            return False

        except Exception as e:
            logger.exception(f"Failed to move task {task_id} to dead letter: {e}")
            return False

    async def requeue_failed_tasks(self, queue_name: str, project_id: UUID) -> int:
        """Requeue failed tasks within project scope."""
        # Note: Complex operation requiring dead letter queue processing
        logger.warning(
            f"requeue_failed_tasks not implemented for queue {queue_name} in project {project_id}"
        )
        return 0

    async def clear_queue(self, queue_name: str, project_id: UUID) -> int:
        """Clear all tasks from queue within project scope."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                queue_key = CacheKey.queue(queue_name)
                size = await redis_client.llen(queue_key.value)
                await redis_client.delete(queue_key.value)
                return size

        except Exception as e:
            logger.exception(f"Failed to clear queue {queue_name}: {e}")
            raise RedisException(f"Failed to clear queue: {str(e)}") from e

    async def get_queue_metrics(
        self, queue_name: str, project_id: UUID
    ) -> Dict[str, Any]:
        """Get queue metrics within project scope."""
        try:
            size = await self.get_queue_size(queue_name, project_id)

            return {
                "queue_name": queue_name,
                "size": size,
                "timestamp": datetime.utcnow().isoformat(),
                "project_id": str(project_id),
                "metrics": {
                    "enqueue_rate": 0.0,  # Would need time-series tracking
                    "dequeue_rate": 0.0,
                    "processing_time_avg": 0.0,
                },
            }

        except Exception as e:
            logger.exception(f"Failed to get queue metrics for {queue_name}: {e}")
            raise RedisException(f"Failed to get queue metrics: {str(e)}") from e

    def _deserialize_queued_task(self, task_data: str) -> Optional[QueuedTask]:
        """Deserialize queued task from JSON."""
        try:
            data = json.loads(task_data)
            task = QueuedTask(
                task_id=UUID(data["task_id"]),
                task_type=data["task_type"],
                task_data=data["task_data"],
                priority=QueuePriority(data["priority"]),
                status=data["status"],
                created_at=datetime.fromisoformat(data["created_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
                attempts=data.get("attempts", 0),
                max_attempts=data.get("max_attempts", 3),
                error_message=data.get("error_message"),
                project_id=UUID(data["project_id"]) if data.get("project_id") else None,
            )
            return task

        except Exception as e:
            logger.error(f"Failed to deserialize queued task: {e}")
            return None


class RedisProgressRepository(ProgressRepository):
    """Redis implementation of progress repository."""

    async def save(self, progress: Progress, project_id: UUID) -> None:
        """Save progress tracker within project scope."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                progress_data = {
                    "correlation_id": str(progress.correlation_id),
                    "total_steps": progress.total_steps,
                    "current_step": progress.current_step,
                    "message": progress.message,
                    "step_messages": progress.step_messages,
                    "started_at": progress.started_at.isoformat(),
                    "updated_at": progress.updated_at.isoformat(),
                    "completed_at": progress.completed_at.isoformat()
                    if progress.completed_at
                    else None,
                    "error_message": progress.error_message,
                    "project_id": str(project_id),
                }

                key = progress.get_key()
                ttl_seconds = TTL.progress().seconds

                await redis_client.setex(
                    key.value, ttl_seconds, json.dumps(progress_data, default=str)
                )

        except Exception as e:
            logger.exception(f"Failed to save progress {progress.correlation_id}: {e}")
            raise RedisException(f"Failed to save progress: {str(e)}") from e

    async def find_by_correlation_id(
        self, correlation_id: UUID, project_id: UUID
    ) -> Optional[Progress]:
        """Find progress by correlation ID within project scope."""
        try:
            key = CacheKey.progress(correlation_id)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                progress_data = await redis_client.get(key.value)

                if progress_data:
                    return self._deserialize_progress(progress_data)

                return None

        except Exception as e:
            logger.exception(f"Failed to find progress {correlation_id}: {e}")
            raise RedisException(f"Failed to find progress: {str(e)}") from e

    async def update_progress(
        self, correlation_id: UUID, step: int, message: str, project_id: UUID
    ) -> bool:
        """Update progress step within project scope."""
        try:
            progress = await self.find_by_correlation_id(correlation_id, project_id)
            if progress:
                progress.update_step(step, message)
                await self.save(progress, project_id)
                return True
            return False

        except Exception as e:
            logger.exception(f"Failed to update progress {correlation_id}: {e}")
            raise RedisException(f"Failed to update progress: {str(e)}") from e

    async def complete_progress(
        self,
        correlation_id: UUID,
        project_id: UUID,
        message: str = "Operation completed",
    ) -> bool:
        """Mark progress as completed within project scope."""
        try:
            progress = await self.find_by_correlation_id(correlation_id, project_id)
            if progress:
                progress.complete(message)
                await self.save(progress, project_id)
                return True
            return False

        except Exception as e:
            logger.exception(f"Failed to complete progress {correlation_id}: {e}")
            raise RedisException(f"Failed to complete progress: {str(e)}") from e

    async def fail_progress(
        self, correlation_id: UUID, project_id: UUID, error_message: str
    ) -> bool:
        """Mark progress as failed within project scope."""
        try:
            progress = await self.find_by_correlation_id(correlation_id, project_id)
            if progress:
                progress.fail(error_message)
                await self.save(progress, project_id)
                return True
            return False

        except Exception as e:
            logger.exception(f"Failed to fail progress {correlation_id}: {e}")
            raise RedisException(f"Failed to fail progress: {str(e)}") from e

    async def delete(self, correlation_id: UUID, project_id: UUID) -> bool:
        """Delete progress tracker within project scope."""
        try:
            key = CacheKey.progress(correlation_id)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                result = await redis_client.delete(key.value)
                return result > 0

        except Exception as e:
            logger.exception(f"Failed to delete progress {correlation_id}: {e}")
            raise RedisException(f"Failed to delete progress: {str(e)}") from e

    async def find_expired(
        self, project_id: UUID, max_age_hours: int = 1
    ) -> List[Progress]:
        """Find expired progress trackers for project."""
        # Redis handles TTL expiration automatically
        return []

    async def cleanup_expired(self, project_id: UUID, max_age_hours: int = 1) -> int:
        """Clean up expired progress trackers for project."""
        # Redis handles TTL expiration automatically
        return 0

    async def extend_ttl(
        self, correlation_id: UUID, ttl: TTL, project_id: UUID
    ) -> bool:
        """Extend progress TTL within project scope."""
        try:
            key = CacheKey.progress(correlation_id)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                result = await redis_client.expire(key.value, ttl.seconds)
                return result

        except Exception as e:
            logger.exception(f"Failed to extend progress TTL {correlation_id}: {e}")
            raise RedisException(f"Failed to extend progress TTL: {str(e)}") from e

    async def get_active_progress(self, project_id: UUID) -> List[Progress]:
        """Get all active progress trackers for project."""
        # Note: Would need scanning all progress keys
        logger.warning(
            f"get_active_progress not efficiently implemented for project {project_id}"
        )
        return []

    def _deserialize_progress(self, progress_data: str) -> Optional[Progress]:
        """Deserialize progress from JSON."""
        try:
            data = json.loads(progress_data)
            return Progress(
                correlation_id=UUID(data["correlation_id"]),
                total_steps=data["total_steps"],
                current_step=data.get("current_step", 0),
                message=data.get("message", ""),
                step_messages=data.get("step_messages", []),
                started_at=datetime.fromisoformat(data["started_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
                completed_at=datetime.fromisoformat(data["completed_at"])
                if data.get("completed_at")
                else None,
                error_message=data.get("error_message"),
            )
        except Exception as e:
            logger.error(f"Failed to deserialize progress: {e}")
            return None


class RedisRateLimitRepository(RateLimitRepository):
    """Redis implementation of rate limit repository."""

    async def save(self, rate_limit: RateLimit, project_id: UUID) -> None:
        """Save rate limit state within project scope."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                rate_limit_data = {
                    "identifier": rate_limit.identifier,
                    "limit_type": rate_limit.limit_type,
                    "window": rate_limit.window.value,
                    "limit": rate_limit.limit,
                    "current_count": rate_limit.current_count,
                    "window_start": rate_limit.window_start.isoformat(),
                    "reset_time": rate_limit.reset_time.isoformat()
                    if rate_limit.reset_time
                    else None,
                    "project_id": str(project_id),
                }

                key = rate_limit.get_key()
                ttl_seconds = _window_secs(rate_limit.window)

                await redis_client.setex(
                    key.value, ttl_seconds, json.dumps(rate_limit_data, default=str)
                )

        except Exception as e:
            logger.exception(f"Failed to save rate limit {rate_limit.identifier}: {e}")
            raise RedisException(f"Failed to save rate limit: {str(e)}") from e

    async def find_by_identifier(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        project_id: UUID,
    ) -> Optional[RateLimit]:
        """Find rate limit by identifier within project scope."""
        try:
            key = CacheKey.rate_limit(limit_type, identifier, window)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                rate_limit_data = await redis_client.get(key.value)

                if rate_limit_data:
                    return self._deserialize_rate_limit(rate_limit_data)

                return None

        except Exception as e:
            logger.exception(f"Failed to find rate limit {identifier}: {e}")
            raise RedisException(f"Failed to find rate limit: {str(e)}") from e

    async def check_and_increment(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        limit: int,
        project_id: UUID,
    ) -> bool:
        """Check if request is allowed and increment count within project scope."""
        try:
            key = CacheKey.rate_limit(limit_type, identifier, window)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                # Use Redis pipeline for atomic operations
                pipe = redis_client.pipeline()

                # Get current count
                pipe.get(key.value)

                # Execute pipeline
                results = await pipe.execute()
                current_data = results[0]

                if current_data:
                    # Parse existing data
                    data = json.loads(current_data)
                    current_count = data.get("current_count", 0)
                    reset_time = datetime.fromisoformat(data["reset_time"])

                    # Check if window has expired
                    if datetime.utcnow() > reset_time:
                        # Reset window
                        current_count = 0
                        reset_time = datetime.utcnow() + timedelta(
                            seconds=_window_secs(window)
                        )
                    else:
                        # Check limit
                        if current_count >= limit:
                            return False

                        current_count += 1
                else:
                    # New rate limit entry
                    current_count = 1
                    reset_time = datetime.utcnow() + timedelta(
                        seconds=_window_secs(window)
                    )

                # Save updated data
                rate_limit_data = {
                    "identifier": identifier,
                    "limit_type": limit_type,
                    "window": window.value,
                    "limit": limit,
                    "current_count": current_count,
                    "window_start": (
                        reset_time - timedelta(seconds=_window_secs(window))
                    ).isoformat(),
                    "reset_time": reset_time.isoformat(),
                    "project_id": str(project_id),
                }

                await redis_client.setex(
                    key.value, window.seconds, json.dumps(rate_limit_data, default=str)
                )
                return True

        except Exception as e:
            logger.exception(
                f"Failed to check and increment rate limit {identifier}: {e}"
            )
            raise RedisException(
                f"Failed to check and increment rate limit: {str(e)}"
            ) from e

    async def get_current_count(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        project_id: UUID,
    ) -> int:
        """Get current request count within project scope."""
        try:
            rate_limit = await self.find_by_identifier(
                identifier, limit_type, window, project_id
            )
            return rate_limit.current_count if rate_limit else 0

        except Exception as e:
            logger.error(f"Failed to get current count {identifier}: {e}")
            return 0

    async def get_remaining_requests(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        limit: int,
        project_id: UUID,
    ) -> int:
        """Get remaining requests in window within project scope."""
        try:
            current_count = await self.get_current_count(
                identifier, limit_type, window, project_id
            )
            return max(0, limit - current_count)

        except Exception as e:
            logger.error(f"Failed to get remaining requests {identifier}: {e}")
            return limit

    async def get_reset_time(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        project_id: UUID,
    ) -> Optional[datetime]:
        """Get window reset time within project scope."""
        try:
            rate_limit = await self.find_by_identifier(
                identifier, limit_type, window, project_id
            )
            return rate_limit.reset_time if rate_limit else None

        except Exception as e:
            logger.error(f"Failed to get reset time {identifier}: {e}")
            return None

    async def reset_window(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        project_id: UUID,
    ) -> bool:
        """Reset rate limit window within project scope."""
        try:
            key = CacheKey.rate_limit(limit_type, identifier, window)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                result = await redis_client.delete(key.value)
                return result > 0

        except Exception as e:
            logger.exception(f"Failed to reset rate limit window {identifier}: {e}")
            raise RedisException(f"Failed to reset rate limit window: {str(e)}") from e

    async def delete(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        project_id: UUID,
    ) -> bool:
        """Delete rate limit state within project scope."""
        return await self.reset_window(identifier, limit_type, window, project_id)

    async def cleanup_expired(self, project_id: UUID) -> int:
        """Clean up expired rate limit entries for project."""
        # Redis handles TTL expiration automatically
        return 0

    async def get_rate_limit_metrics(self, project_id: UUID) -> Dict[str, Any]:
        """Get rate limiting metrics for project."""
        # Would need monitoring infrastructure
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "project_id": str(project_id),
            "active_limits": 0,
            "blocked_requests": 0,
            "allow_requests": 0,
        }

    def _deserialize_rate_limit(self, rate_limit_data: str) -> Optional[RateLimit]:
        """Deserialize rate limit from JSON."""
        try:
            data = json.loads(rate_limit_data)
            return RateLimit(
                identifier=data["identifier"],
                limit_type=data["limit_type"],
                window=RateLimitWindow(data["window"]),
                limit=data["limit"],
                current_count=data.get("current_count", 0),
                window_start=datetime.fromisoformat(data["window_start"]),
                reset_time=datetime.fromisoformat(data["reset_time"])
                if data.get("reset_time")
                else None,
            )
        except Exception as e:
            logger.error(f"Failed to deserialize rate limit: {e}")
            return None


class RedisCacheHealthRepository(CacheHealthRepository):
    """Redis implementation of cache health repository."""

    async def get_memory_usage(self, project_id: UUID) -> Dict[str, Any]:
        """Get Redis memory usage statistics for project."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                info = await redis_client.info("memory")

                return {
                    "project_id": str(project_id),
                    "used_memory": info.get("used_memory", 0),
                    "used_memory_human": info.get("used_memory_human", "0B"),
                    "used_memory_rss": info.get("used_memory_rss", 0),
                    "used_memory_peak": info.get("used_memory_peak", 0),
                    "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
                    "maxmemory": info.get("maxmemory", 0),
                    "maxmemory_human": info.get("maxmemory_human", "0B"),
                    "memory_fragmentation_ratio": info.get(
                        "mem_fragmentation_ratio", 0
                    ),
                    "usage_percentage": (
                        info.get("used_memory", 0) / info.get("maxmemory", 1)
                    )
                    * 100
                    if info.get("maxmemory", 0) > 0
                    else 0,
                }

        except Exception as e:
            logger.exception(f"Failed to get memory usage: {e}")
            raise RedisException(f"Failed to get memory usage: {str(e)}") from e

    async def get_connection_info(self, project_id: UUID) -> Dict[str, Any]:
        """Get connection information for project."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                info = await redis_client.info("clients")

                return {
                    "project_id": str(project_id),
                    "connected_clients": info.get("connected_clients", 0),
                    "client_recent_max_input_buffer": info.get(
                        "client_recent_max_input_buffer", 0
                    ),
                    "client_recent_max_output_buffer": info.get(
                        "client_recent_max_output_buffer", 0
                    ),
                    "blocked_clients": info.get("blocked_clients", 0),
                    "tracking_clients": info.get("tracking_clients", 0),
                    "status": "healthy",  # Would need actual health check
                }

        except Exception as e:
            logger.error(f"Failed to get connection info: {e}")
            return {"status": "unhealthy", "error": str(e)}

    async def get_operation_stats(self, project_id: UUID) -> Dict[str, Any]:
        """Get operation statistics for project."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                info = await redis_client.info("stats")

                return {
                    "project_id": str(project_id),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "total_connections_received": info.get(
                        "total_connections_received", 0
                    ),
                    "total_net_input_bytes": info.get("total_net_input_bytes", 0),
                    "total_net_output_bytes": info.get("total_net_output_bytes", 0),
                    "instantaneous_ops_per_sec": info.get(
                        "instantaneous_ops_per_sec", 0
                    ),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                    "hit_rate": info.get("keyspace_hits", 0)
                    / max(
                        1, info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0)
                    ),
                }

        except Exception as e:
            logger.exception(f"Failed to get operation stats: {e}")
            raise RedisException(f"Failed to get operation stats: {str(e)}") from e

    async def perform_health_check(self, project_id: UUID) -> Dict[str, Any]:
        """Perform comprehensive health check for project."""
        try:
            health_status = await redis_service.health_check()
            health_status["project_id"] = str(project_id)
            return health_status

        except Exception as e:
            logger.exception(f"Failed to perform health check: {e}")
            return {
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "project_id": str(project_id),
                "error": str(e),
            }

    async def get_key_distribution(self, project_id: UUID) -> Dict[str, int]:
        """Get key distribution by pattern for project."""
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                # Get info about keyspaces
                info = await redis_client.info("keyspace")
                distribution = {}
                for db_key, db_info in info.items():
                    if db_key.startswith("db"):
                        # Handle both string and dict formats
                        if isinstance(db_info, dict):
                            # Redis returned dict format
                            keys_count = db_info.get("keys", 0)
                            if isinstance(keys_count, str):
                                keys_count = (
                                    int(keys_count) if keys_count.isdigit() else 0
                                )
                            distribution[db_key] = keys_count
                        elif isinstance(db_info, str):
                            # Redis returned string format - parse it
                            if "keys=" in db_info:
                                try:
                                    keys_count = int(
                                        db_info.split("keys=")[1].split(",")[0]
                                    )
                                    distribution[db_key] = keys_count
                                except (ValueError, IndexError):
                                    # Skip entries with invalid keys format
                                    continue
                        # Skip entries with missing/invalid keys
                return distribution
        except Exception as e:
            logger.exception(f"Failed to get key distribution: {e}")
            raise RedisException(f"Failed to get key distribution: {str(e)}") from e

    async def get_slow_operations(
        self, project_id: UUID, threshold_ms: float = 100.0
    ) -> List[Dict[str, Any]]:
        """Get slow operations above threshold for project."""
        # Redis slowlog would need to be enabled
        try:
            async with redis_service.get_connection(str(project_id)) as redis_client:
                slowlog = await redis_client.slowlog_get(
                    10
                )  # Get last 10 slow operations

                slow_operations = []
                for entry in slowlog:
                    # redis-py returns dicts with keys: 'id', 'duration', 'start_time', 'command'
                    execution_time_us = entry["duration"]  # microseconds
                    execution_time_ms = execution_time_us / 1000

                    if execution_time_ms >= threshold_ms:
                        slow_operations.append(
                            {
                                "id": entry["id"],
                                "execution_time_ms": execution_time_ms,
                                "command": entry["command"],
                                "timestamp": entry["start_time"],
                                "project_id": str(project_id),
                            }
                        )

                return slow_operations

        except Exception as e:
            logger.exception(f"Failed to get slow operations: {e}")
            return []

    async def cleanup_expired_keys(self, project_id: UUID) -> int:
        """Clean up expired keys for project."""
        # Redis handles TTL expiration automatically
        return 0


class RedisCacheRepository(CacheRepository):
    """Composite Redis cache repository implementation."""

    def __init__(self):
        self._project_cache = RedisProjectCacheRepository()
        self._user_session = RedisUserSessionRepository()
        self._task_queue = RedisTaskQueueRepository()
        self._progress = RedisProgressRepository()
        self._rate_limit = RedisRateLimitRepository()
        self._health = RedisCacheHealthRepository()

    @property
    def project_cache(self) -> ProjectCacheRepository:
        """Project cache repository."""
        return self._project_cache

    @property
    def user_session(self) -> UserSessionRepository:
        """User session repository."""
        return self._user_session

    @property
    def task_queue(self) -> TaskQueueRepository:
        """Task queue repository."""
        return self._task_queue

    @property
    def progress(self) -> ProgressRepository:
        """Progress repository."""
        return self._progress

    @property
    def rate_limit(self) -> RateLimitRepository:
        """Rate limit repository."""
        return self._rate_limit

    @property
    def health(self) -> CacheHealthRepository:
        """Health monitoring repository."""
        return self._health

    async def initialize(self) -> None:
        """Initialize repository connections."""
        await redis_service.initialize()

    async def close(self) -> None:
        """Close repository connections."""
        await redis_service.close()

    async def health_check(self, project_id: UUID) -> Dict[str, Any]:
        """Perform comprehensive health check for project."""
        return await self.health.perform_health_check(project_id)

    async def get_metrics(self, project_id: UUID) -> Dict[str, Any]:
        """Get comprehensive metrics for project."""
        try:
            # Get metrics from different repositories
            memory_usage = await self.health.get_memory_usage(project_id)
            operation_stats = await self.health.get_operation_stats(project_id)
            connection_info = await self.health.get_connection_info(project_id)
            key_distribution = await self.health.get_key_distribution(project_id)

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "project_id": str(project_id),
                "memory": memory_usage,
                "operations": operation_stats,
                "connections": connection_info,
                "key_distribution": key_distribution,
                "repositories": {
                    "project_cache": "active",
                    "user_session": "active",
                    "task_queue": "active",
                    "progress": "active",
                    "rate_limit": "active",
                    "health": "active",
                },
            }

        except Exception as e:
            logger.exception(f"Failed to get comprehensive metrics: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "project_id": str(project_id),
                "error": str(e),
            }


# Global repository instance
cache_repository = RedisCacheRepository()
