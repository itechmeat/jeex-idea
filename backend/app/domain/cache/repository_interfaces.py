"""
Cache Repository Interfaces

Abstract repository interfaces following DDD Repository pattern.
Defines contracts for cache persistence implementations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from uuid import UUID
import warnings

from .entities import (
    ProjectCache,
    UserSession,
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
    All operations MUST be scoped to project_id for security isolation.
    """

    @abstractmethod
    async def save(self, cache: ProjectCache, project_id: UUID) -> None:
        """Save project cache entry."""
        pass

    @abstractmethod
    async def find_by_project_id(self, project_id: UUID) -> Optional[ProjectCache]:
        """Find cache entry by project ID."""
        pass

    @abstractmethod
    async def find_by_key(
        self, key: CacheKey, project_id: UUID
    ) -> Optional[ProjectCache]:
        """Find cache entry by key within project scope."""
        pass

    @abstractmethod
    async def invalidate_by_project_id(self, project_id: UUID) -> int:
        """Invalidate all cache entries for project."""
        pass

    @abstractmethod
    async def invalidate_by_tag(self, tag: CacheTag, project_id: UUID) -> int:
        """Invalidate cache entries by tag within project scope."""
        pass

    @abstractmethod
    async def find_expired(self, project_id: UUID) -> List[ProjectCache]:
        """Find expired cache entries for project."""
        pass

    @abstractmethod
    async def delete(self, key: CacheKey, project_id: UUID) -> bool:
        """Delete cache entry by key within project scope."""
        pass

    @abstractmethod
    async def exists(self, key: CacheKey, project_id: UUID) -> bool:
        """Check if cache entry exists within project scope."""
        pass

    @abstractmethod
    async def get_ttl(self, key: CacheKey, project_id: UUID) -> Optional[int]:
        """Get remaining TTL for cache entry within project scope."""
        pass

    @abstractmethod
    async def extend_ttl(self, key: CacheKey, ttl: TTL, project_id: UUID) -> bool:
        """Extend TTL for cache entry within project scope."""
        pass

    @abstractmethod
    async def record_metrics(
        self, operations: List[CacheMetrics], project_id: UUID
    ) -> None:
        """Record cache operation metrics for project."""
        pass


class UserSessionRepository(ABC):
    """
    Abstract repository for user session operations.

    Defines contract for session persistence and management.
    All operations MUST be scoped to project_id for security isolation.
    """

    @abstractmethod
    async def save(self, session: UserSession, project_id: UUID) -> None:
        """Save user session within project scope."""
        pass

    @abstractmethod
    async def find_by_session_id(
        self, session_id: UUID, project_id: UUID
    ) -> Optional[UserSession]:
        """Find session by session ID within project scope."""
        pass

    @abstractmethod
    async def find_by_user_id(
        self, user_id: UUID, project_id: UUID
    ) -> List[UserSession]:
        """Find all sessions for user within project scope."""
        pass

    @abstractmethod
    async def find_active_by_user_id(
        self, user_id: UUID, project_id: UUID
    ) -> List[UserSession]:
        """Find active sessions for user within project scope."""
        pass

    @abstractmethod
    async def delete(self, session_id: UUID, project_id: UUID) -> bool:
        """Delete session by ID within project scope."""
        pass

    @abstractmethod
    async def invalidate_all_for_user(self, user_id: UUID, project_id: UUID) -> int:
        """Invalidate all sessions for user within project scope."""
        pass

    @abstractmethod
    async def find_expired(self, project_id: UUID) -> List[UserSession]:
        """Find expired sessions for project."""
        pass

    @abstractmethod
    async def cleanup_expired(self, project_id: UUID) -> int:
        """Clean up expired sessions for project."""
        pass

    @abstractmethod
    async def extend_session(
        self, session_id: UUID, ttl: TTL, project_id: UUID
    ) -> bool:
        """Extend session TTL within project scope."""
        pass

    @abstractmethod
    async def update_activity(self, session_id: UUID, project_id: UUID) -> bool:
        """Update session last activity within project scope."""
        pass


class TaskQueueRepository(ABC):
    """
    Abstract repository for task queue operations.

    Defines contract for task queue management and persistence.
    All operations MUST be scoped to project_id for security isolation.
    """

    @abstractmethod
    async def enqueue(
        self, queue_name: str, task: QueuedTask, project_id: UUID
    ) -> None:
        """Add task to queue within project scope."""
        pass

    @abstractmethod
    async def dequeue(self, queue_name: str, project_id: UUID) -> Optional[QueuedTask]:
        """Remove and return next task from queue within project scope."""
        pass

    @abstractmethod
    async def peek(self, queue_name: str, project_id: UUID) -> Optional[QueuedTask]:
        """Peek at next task without removing it within project scope."""
        pass

    @abstractmethod
    async def get_queue_size(self, queue_name: str, project_id: UUID) -> int:
        """Get queue size within project scope."""
        pass

    @abstractmethod
    async def get_queue_status(
        self, queue_name: str, project_id: UUID
    ) -> Dict[str, Any]:
        """Get detailed queue status within project scope."""
        pass

    @abstractmethod
    async def update_task_status(
        self,
        task_id: UUID,
        status: str,
        project_id: UUID,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update task status within project scope."""
        pass

    @abstractmethod
    async def find_task_by_id(
        self, task_id: UUID, project_id: UUID
    ) -> Optional[QueuedTask]:
        """Find task by ID within project scope."""
        pass

    @abstractmethod
    async def find_tasks_by_status(
        self, queue_name: str, status: str, project_id: UUID
    ) -> List[QueuedTask]:
        """Find tasks by status within project scope."""
        pass

    @abstractmethod
    async def move_to_dead_letter(
        self, task_id: UUID, error_message: str, project_id: UUID
    ) -> bool:
        """Move task to dead letter queue within project scope."""
        pass

    @abstractmethod
    async def requeue_failed_tasks(self, queue_name: str, project_id: UUID) -> int:
        """Requeue failed tasks within project scope."""
        pass

    @abstractmethod
    async def clear_queue(self, queue_name: str, project_id: UUID) -> int:
        """Clear all tasks from queue within project scope."""
        pass

    @abstractmethod
    async def get_queue_metrics(
        self, queue_name: str, project_id: UUID
    ) -> Dict[str, Any]:
        """Get queue metrics within project scope."""
        pass


class ProgressRepository(ABC):
    """
    Abstract repository for progress tracking operations.

    Defines contract for progress persistence and retrieval.
    All operations MUST be scoped to project_id for security isolation.
    """

    @abstractmethod
    async def save(self, progress: Progress, project_id: UUID) -> None:
        """Save progress tracker within project scope."""
        pass

    @abstractmethod
    async def find_by_correlation_id(
        self, correlation_id: UUID, project_id: UUID
    ) -> Optional[Progress]:
        """Find progress by correlation ID within project scope."""
        pass

    @abstractmethod
    async def update_progress(
        self, correlation_id: UUID, step: int, message: str, project_id: UUID
    ) -> bool:
        """Update progress step within project scope."""
        pass

    @abstractmethod
    async def complete_progress(
        self,
        correlation_id: UUID,
        project_id: UUID,
        message: str = "Operation completed",
    ) -> bool:
        """Mark progress as completed within project scope."""
        pass

    @abstractmethod
    async def fail_progress(
        self, correlation_id: UUID, error_message: str, project_id: UUID
    ) -> bool:
        """Mark progress as failed within project scope."""
        pass

    @abstractmethod
    async def delete(self, correlation_id: UUID, project_id: UUID) -> bool:
        """Delete progress tracker within project scope."""
        pass

    @abstractmethod
    async def find_expired(
        self, project_id: UUID, max_age_hours: int = 1
    ) -> List[Progress]:
        """Find expired progress trackers for project."""
        pass

    @abstractmethod
    async def cleanup_expired(self, project_id: UUID, max_age_hours: int = 1) -> int:
        """Clean up expired progress trackers for project."""
        pass

    @abstractmethod
    async def extend_ttl(
        self, correlation_id: UUID, ttl: TTL, project_id: UUID
    ) -> bool:
        """Extend progress TTL within project scope."""
        pass

    @abstractmethod
    async def get_active_progress(self, project_id: UUID) -> List[Progress]:
        """Get all active progress trackers for project."""
        pass


class RateLimitRepository(ABC):
    """
    Abstract repository for rate limiting operations.

    Defines contract for rate limit state management.
    All operations MUST be scoped to project_id for security isolation.
    """

    @abstractmethod
    async def save(self, rate_limit: RateLimit, project_id: UUID) -> None:
        """Save rate limit state within project scope."""
        pass

    @abstractmethod
    async def find_by_identifier(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        project_id: UUID,
    ) -> Optional[RateLimit]:
        """Find rate limit by identifier within project scope."""
        pass

    @abstractmethod
    async def check_and_increment(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        limit: int,
        project_id: UUID,
    ) -> bool:
        """Check if request is allowed and increment count within project scope."""
        pass

    @abstractmethod
    async def get_current_count(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        project_id: UUID,
    ) -> int:
        """Get current request count within project scope."""
        pass

    @abstractmethod
    async def get_remaining_requests(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        limit: int,
        project_id: UUID,
    ) -> int:
        """Get remaining requests in window within project scope."""
        pass

    @abstractmethod
    async def get_reset_time(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        project_id: UUID,
    ) -> Optional[datetime]:
        """Get window reset time within project scope."""
        pass

    @abstractmethod
    async def reset_window(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        project_id: UUID,
    ) -> bool:
        """Reset rate limit window within project scope."""
        pass

    @abstractmethod
    async def delete(
        self,
        identifier: str,
        limit_type: str,
        window: RateLimitWindow,
        project_id: UUID,
    ) -> bool:
        """Delete rate limit state within project scope."""
        pass

    @abstractmethod
    async def cleanup_expired(self, project_id: UUID) -> int:
        """Clean up expired rate limit entries for project."""
        pass

    @abstractmethod
    async def get_rate_limit_metrics(self, project_id: UUID) -> Dict[str, Any]:
        """Get rate limiting metrics for project."""
        pass


class CacheHealthRepository(ABC):
    """
    Abstract repository for cache health monitoring.

    Defines contract for health checks and metrics collection.
    Health monitoring operations require project_id for tenant isolation.
    """

    @abstractmethod
    async def get_memory_usage(self, project_id: UUID) -> Dict[str, Any]:
        """Get Redis memory usage statistics for project."""
        pass

    @abstractmethod
    async def get_connection_info(self, project_id: UUID) -> Dict[str, Any]:
        """Get connection information for project."""
        pass

    @abstractmethod
    async def get_operation_stats(self, project_id: UUID) -> Dict[str, Any]:
        """Get operation statistics for project."""
        pass

    @abstractmethod
    async def perform_health_check(self, project_id: UUID) -> Dict[str, Any]:
        """Perform comprehensive health check for project."""
        pass

    @abstractmethod
    async def get_key_distribution(self, project_id: UUID) -> Dict[str, int]:
        """Get key distribution by pattern for project."""
        pass

    @abstractmethod
    async def get_slow_operations(
        self, project_id: UUID, threshold_ms: float = 100.0
    ) -> List[Dict[str, Any]]:
        """Get slow operations above threshold for project."""
        pass

    @abstractmethod
    async def cleanup_expired_keys(self, project_id: UUID) -> int:
        """Clean up expired keys for project."""
        pass


# Helper function for backward compatibility with deprecation warning
def _deprecated_method_warning(method_name: str) -> None:
    """Emit deprecation warning for methods without project_id."""
    warnings.warn(
        f"{method_name}() called without project_id parameter. "
        "This method will require project_id in future versions. "
        "Update your implementation to include project_id for security isolation.",
        DeprecationWarning,
        stacklevel=3,
    )


# Composite repository interface
class CacheRepository(ABC):
    """
    Composite cache repository interface.

    Combines all cache repository interfaces for unified access.
    All operations MUST be scoped to project_id for security isolation.
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
    async def health_check(self, project_id: UUID) -> Dict[str, Any]:
        """Perform comprehensive health check for project."""
        pass

    @abstractmethod
    async def get_metrics(self, project_id: UUID) -> Dict[str, Any]:
        """Get comprehensive metrics for project."""
        pass
