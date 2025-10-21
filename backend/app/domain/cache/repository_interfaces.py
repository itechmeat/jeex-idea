"""
Cache Repository Interfaces

Abstract repository interfaces following DDD Repository pattern.
Defines contracts for cache persistence implementations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from uuid import UUID

from .entities import (
    ProjectCache,
    UserSession,
    TaskQueue,
    Progress,
    RateLimit,
    QueuedTask,
)
from .value_objects import (
    CacheKey,
    TTL,
    CacheTag,
    QueuePriority,
    RateLimitWindow,
    CacheMetrics,
)


class ProjectCacheRepository(ABC):
    """
    Abstract repository for project cache operations.

    Defines contract for project cache persistence and retrieval.
    """

    @abstractmethod
    async def save(self, cache: ProjectCache) -> None:
        """Save project cache entry."""
        pass

    @abstractmethod
    async def find_by_project_id(self, project_id: UUID) -> Optional[ProjectCache]:
        """Find cache entry by project ID."""
        pass

    @abstractmethod
    async def find_by_key(self, key: CacheKey) -> Optional[ProjectCache]:
        """Find cache entry by key."""
        pass

    @abstractmethod
    async def invalidate_by_project_id(self, project_id: UUID) -> int:
        """Invalidate all cache entries for project."""
        pass

    @abstractmethod
    async def invalidate_by_tag(self, tag: CacheTag) -> int:
        """Invalidate cache entries by tag."""
        pass

    @abstractmethod
    async def find_expired(self) -> List[ProjectCache]:
        """Find expired cache entries."""
        pass

    @abstractmethod
    async def delete(self, key: CacheKey) -> bool:
        """Delete cache entry by key."""
        pass

    @abstractmethod
    async def exists(self, key: CacheKey) -> bool:
        """Check if cache entry exists."""
        pass

    @abstractmethod
    async def get_ttl(self, key: CacheKey) -> Optional[int]:
        """Get remaining TTL for cache entry."""
        pass

    @abstractmethod
    async def extend_ttl(self, key: CacheKey, ttl: TTL) -> bool:
        """Extend TTL for cache entry."""
        pass

    @abstractmethod
    async def record_metrics(self, operations: List[CacheMetrics]) -> None:
        """Record cache operation metrics."""
        pass


class UserSessionRepository(ABC):
    """
    Abstract repository for user session operations.

    Defines contract for session persistence and management.
    """

    @abstractmethod
    async def save(self, session: UserSession) -> None:
        """Save user session."""
        pass

    @abstractmethod
    async def find_by_session_id(self, session_id: UUID) -> Optional[UserSession]:
        """Find session by session ID."""
        pass

    @abstractmethod
    async def find_by_user_id(self, user_id: UUID) -> List[UserSession]:
        """Find all sessions for user."""
        pass

    @abstractmethod
    async def find_active_by_user_id(self, user_id: UUID) -> List[UserSession]:
        """Find active sessions for user."""
        pass

    @abstractmethod
    async def delete(self, session_id: UUID) -> bool:
        """Delete session by ID."""
        pass

    @abstractmethod
    async def invalidate_all_for_user(self, user_id: UUID) -> int:
        """Invalidate all sessions for user."""
        pass

    @abstractmethod
    async def find_expired(self) -> List[UserSession]:
        """Find expired sessions."""
        pass

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Clean up expired sessions."""
        pass

    @abstractmethod
    async def extend_session(self, session_id: UUID, ttl: TTL) -> bool:
        """Extend session TTL."""
        pass

    @abstractmethod
    async def update_activity(self, session_id: UUID) -> bool:
        """Update session last activity."""
        pass


class TaskQueueRepository(ABC):
    """
    Abstract repository for task queue operations.

    Defines contract for task queue management and persistence.
    """

    @abstractmethod
    async def enqueue(self, queue_name: str, task: QueuedTask) -> None:
        """Add task to queue."""
        pass

    @abstractmethod
    async def dequeue(self, queue_name: str) -> Optional[QueuedTask]:
        """Remove and return next task from queue."""
        pass

    @abstractmethod
    async def peek(self, queue_name: str) -> Optional[QueuedTask]:
        """Peek at next task without removing it."""
        pass

    @abstractmethod
    async def get_queue_size(self, queue_name: str) -> int:
        """Get queue size."""
        pass

    @abstractmethod
    async def get_queue_status(self, queue_name: str) -> Dict[str, Any]:
        """Get detailed queue status."""
        pass

    @abstractmethod
    async def update_task_status(
        self, task_id: UUID, status: str, error_message: Optional[str] = None
    ) -> bool:
        """Update task status."""
        pass

    @abstractmethod
    async def find_task_by_id(self, task_id: UUID) -> Optional[QueuedTask]:
        """Find task by ID."""
        pass

    @abstractmethod
    async def find_tasks_by_status(
        self, queue_name: str, status: str
    ) -> List[QueuedTask]:
        """Find tasks by status."""
        pass

    @abstractmethod
    async def move_to_dead_letter(self, task_id: UUID, error_message: str) -> bool:
        """Move task to dead letter queue."""
        pass

    @abstractmethod
    async def requeue_failed_tasks(self, queue_name: str) -> int:
        """Requeue failed tasks."""
        pass

    @abstractmethod
    async def clear_queue(self, queue_name: str) -> int:
        """Clear all tasks from queue."""
        pass

    @abstractmethod
    async def get_queue_metrics(self, queue_name: str) -> Dict[str, Any]:
        """Get queue metrics."""
        pass


class ProgressRepository(ABC):
    """
    Abstract repository for progress tracking operations.

    Defines contract for progress persistence and retrieval.
    """

    @abstractmethod
    async def save(self, progress: Progress) -> None:
        """Save progress tracker."""
        pass

    @abstractmethod
    async def find_by_correlation_id(self, correlation_id: UUID) -> Optional[Progress]:
        """Find progress by correlation ID."""
        pass

    @abstractmethod
    async def update_progress(
        self, correlation_id: UUID, step: int, message: str
    ) -> bool:
        """Update progress step."""
        pass

    @abstractmethod
    async def complete_progress(
        self, correlation_id: UUID, message: str = "Operation completed"
    ) -> bool:
        """Mark progress as completed."""
        pass

    @abstractmethod
    async def fail_progress(self, correlation_id: UUID, error_message: str) -> bool:
        """Mark progress as failed."""
        pass

    @abstractmethod
    async def delete(self, correlation_id: UUID) -> bool:
        """Delete progress tracker."""
        pass

    @abstractmethod
    async def find_expired(self, max_age_hours: int = 1) -> List[Progress]:
        """Find expired progress trackers."""
        pass

    @abstractmethod
    async def cleanup_expired(self, max_age_hours: int = 1) -> int:
        """Clean up expired progress trackers."""
        pass

    @abstractmethod
    async def extend_ttl(self, correlation_id: UUID, ttl: TTL) -> bool:
        """Extend progress TTL."""
        pass

    @abstractmethod
    async def get_active_progress(self) -> List[Progress]:
        """Get all active progress trackers."""
        pass


class RateLimitRepository(ABC):
    """
    Abstract repository for rate limiting operations.

    Defines contract for rate limit state management.
    """

    @abstractmethod
    async def save(self, rate_limit: RateLimit) -> None:
        """Save rate limit state."""
        pass

    @abstractmethod
    async def find_by_identifier(
        self, identifier: str, limit_type: str, window: RateLimitWindow
    ) -> Optional[RateLimit]:
        """Find rate limit by identifier."""
        pass

    @abstractmethod
    async def check_and_increment(
        self, identifier: str, limit_type: str, window: RateLimitWindow, limit: int
    ) -> bool:
        """Check if request is allowed and increment count."""
        pass

    @abstractmethod
    async def get_current_count(
        self, identifier: str, limit_type: str, window: RateLimitWindow
    ) -> int:
        """Get current request count."""
        pass

    @abstractmethod
    async def get_remaining_requests(
        self, identifier: str, limit_type: str, window: RateLimitWindow, limit: int
    ) -> int:
        """Get remaining requests in window."""
        pass

    @abstractmethod
    async def get_reset_time(
        self, identifier: str, limit_type: str, window: RateLimitWindow
    ) -> Optional[datetime]:
        """Get window reset time."""
        pass

    @abstractmethod
    async def reset_window(
        self, identifier: str, limit_type: str, window: RateLimitWindow
    ) -> bool:
        """Reset rate limit window."""
        pass

    @abstractmethod
    async def delete(
        self, identifier: str, limit_type: str, window: RateLimitWindow
    ) -> bool:
        """Delete rate limit state."""
        pass

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Clean up expired rate limit entries."""
        pass

    @abstractmethod
    async def get_rate_limit_metrics(self) -> Dict[str, Any]:
        """Get rate limiting metrics."""
        pass


class CacheHealthRepository(ABC):
    """
    Abstract repository for cache health monitoring.

    Defines contract for health checks and metrics collection.
    """

    @abstractmethod
    async def get_memory_usage(self) -> Dict[str, Any]:
        """Get Redis memory usage statistics."""
        pass

    @abstractmethod
    async def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information."""
        pass

    @abstractmethod
    async def get_operation_stats(self) -> Dict[str, Any]:
        """Get operation statistics."""
        pass

    @abstractmethod
    async def perform_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        pass

    @abstractmethod
    async def get_key_distribution(self) -> Dict[str, int]:
        """Get key distribution by pattern."""
        pass

    @abstractmethod
    async def get_slow_operations(
        self, threshold_ms: float = 100.0
    ) -> List[Dict[str, Any]]:
        """Get slow operations above threshold."""
        pass

    @abstractmethod
    async def cleanup_expired_keys(self) -> int:
        """Clean up expired keys."""
        pass


# Composite repository interface
class CacheRepository(ABC):
    """
    Composite cache repository interface.

    Combines all cache repository interfaces for unified access.
    """

    @property
    @abstractmethod
    def project_cache(self) -> ProjectCacheRepository:
        """Project cache repository."""
        pass

    @property
    @abstractmethod
    def user_session(self) -> UserSessionRepository:
        """User session repository."""
        pass

    @property
    @abstractmethod
    def task_queue(self) -> TaskQueueRepository:
        """Task queue repository."""
        pass

    @property
    @abstractmethod
    def progress(self) -> ProgressRepository:
        """Progress repository."""
        pass

    @property
    @abstractmethod
    def rate_limit(self) -> RateLimitRepository:
        """Rate limit repository."""
        pass

    @property
    @abstractmethod
    def health(self) -> CacheHealthRepository:
        """Health monitoring repository."""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize repository connections."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close repository connections."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        pass

    @abstractmethod
    async def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics."""
        pass
