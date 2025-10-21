"""
Cache Domain Entities

Core domain entities for cache management following DDD principles.
Encapsulates business logic and invariants for cache operations.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator

from .value_objects import (
    CacheKey,
    TTL,
    CacheEntryStatus,
    CacheVersion,
    CacheTag,
    QueuePriority,
    RateLimitWindow,
)


@dataclass
class ProjectCache:
    """
    Project cache entity.

    Represents cached project data with versioning and metadata.
    """

    project_id: UUID
    data: Dict[str, Any]
    version: CacheVersion
    created_at: datetime
    expires_at: datetime
    tags: List[CacheTag] = field(default_factory=list)
    size_bytes: int = 0
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Initialize project cache entity."""
        if not self.last_accessed_at:
            self.last_accessed_at = self.created_at

        # Add project tag automatically
        project_tag = CacheTag.project(self.project_id)
        if project_tag not in self.tags:
            self.tags.append(project_tag)

    @classmethod
    def create(
        cls,
        project_id: UUID,
        data: Dict[str, Any],
        ttl: TTL,
        version: Optional[CacheVersion] = None,
    ) -> "ProjectCache":
        """Create new project cache entry."""
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=ttl.seconds)

        # Calculate data size (rough estimation)
        import json

        size_bytes = len(json.dumps(data, default=str))

        return cls(
            project_id=project_id,
            data=data,
            version=version or CacheVersion.initial(),
            created_at=now,
            expires_at=expires_at,
            size_bytes=size_bytes,
        )

    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return datetime.utcnow() > self.expires_at

    def access(self) -> None:
        """Record access to cache entry."""
        self.access_count += 1
        self.last_accessed_at = datetime.utcnow()

    def invalidate(self) -> None:
        """Invalidate cache entry."""
        self.expires_at = datetime.utcnow()

    def has_tag(self, tag: CacheTag) -> bool:
        """Check if cache entry has specific tag."""
        return tag in self.tags

    def add_tag(self, tag: CacheTag) -> None:
        """Add tag to cache entry."""
        if tag not in self.tags:
            self.tags.append(tag)

    def get_key(self) -> CacheKey:
        """Get cache key for this entry."""
        return CacheKey.project_data(self.project_id)

    def get_status(self) -> CacheEntryStatus:
        """Get current status of cache entry."""
        if self.is_expired():
            return CacheEntryStatus.EXPIRED
        elif datetime.utcnow() > self.expires_at:
            return CacheEntryStatus.INVALIDATED
        else:
            return CacheEntryStatus.ACTIVE


@dataclass
class UserSession:
    """
    User session entity.

    Represents user authentication session with project access rights.
    """

    session_id: UUID
    user_id: UUID
    user_data: Dict[str, Any]
    project_access: List[UUID] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    is_active: bool = True

    def __post_init__(self) -> None:
        """Initialize user session."""
        if not self.expires_at:
            # Default 2 hour TTL
            self.expires_at = self.created_at + timedelta(hours=2)

    @classmethod
    def create(
        cls,
        user_id: UUID,
        user_data: Dict[str, Any],
        project_access: Optional[List[UUID]] = None,
        ttl: Optional[TTL] = None,
    ) -> "UserSession":
        """Create new user session."""
        session_id = uuid4()
        now = datetime.utcnow()
        expires_at = (
            now + timedelta(seconds=ttl.seconds) if ttl else now + timedelta(hours=2)
        )

        return cls(
            session_id=session_id,
            user_id=user_id,
            user_data=user_data,
            project_access=project_access or [],
            created_at=now,
            last_activity_at=now,
            expires_at=expires_at,
        )

    def is_expired(self) -> bool:
        """Check if session is expired."""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False

    def is_valid(self) -> bool:
        """Check if session is valid."""
        return self.is_active and not self.is_expired()

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity_at = datetime.utcnow()

    def extend_session(self, ttl: TTL) -> None:
        """Extend session expiration."""
        self.expires_at = datetime.utcnow() + timedelta(seconds=ttl.seconds)

    def invalidate(self) -> None:
        """Invalidate session."""
        self.is_active = False

    def has_project_access(self, project_id: UUID) -> bool:
        """Check if session has access to specific project."""
        return project_id in self.project_access

    def grant_project_access(self, project_id: UUID) -> None:
        """Grant access to project."""
        if project_id not in self.project_access:
            self.project_access.append(project_id)

    def revoke_project_access(self, project_id: UUID) -> None:
        """Revoke access to project."""
        if project_id in self.project_access:
            self.project_access.remove(project_id)

    def get_key(self) -> CacheKey:
        """Get cache key for this session."""
        return CacheKey.user_session(self.session_id)


@dataclass
class TaskQueue:
    """
    Task queue entity.

    Represents a background task queue with priority handling.
    """

    queue_name: str
    tasks: List["QueuedTask"] = field(default_factory=list)
    max_size: int = 10000
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Validate queue name."""
        if self.queue_name not in ["embeddings", "agent_tasks", "exports"]:
            raise ValueError(f"Invalid queue name: {self.queue_name}")

    @classmethod
    def create(cls, queue_name: str, max_size: int = 10000) -> "TaskQueue":
        """Create new task queue."""
        return cls(queue_name=queue_name, max_size=max_size)

    def enqueue(self, task: "QueuedTask") -> None:
        """Add task to queue."""
        if len(self.tasks) >= self.max_size:
            raise ValueError(f"Queue {self.queue_name} is full")

        # Insert task based on priority (maintain FIFO within priority)
        insert_index = len(self.tasks)
        for i, existing_task in enumerate(self.tasks):
            if task.priority.value > existing_task.priority.value:
                insert_index = i
                break

        self.tasks.insert(insert_index, task)

    def dequeue(self) -> Optional["QueuedTask"]:
        """Remove and return next task from queue."""
        if not self.tasks:
            return None

        return self.tasks.pop(0)

    def peek(self) -> Optional["QueuedTask"]:
        """Peek at next task without removing it."""
        if not self.tasks:
            return None

        return self.tasks[0]

    def size(self) -> int:
        """Get queue size."""
        return len(self.tasks)

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self.tasks) == 0

    def is_full(self) -> bool:
        """Check if queue is full."""
        return len(self.tasks) >= self.max_size

    def get_tasks_by_status(self, status: str) -> List["QueuedTask"]:
        """Get tasks by status."""
        return [task for task in self.tasks if task.status == status]

    def get_key(self) -> CacheKey:
        """Get cache key for this queue."""
        return CacheKey.queue(self.queue_name)


@dataclass
class QueuedTask:
    """
    Queued task entity.

    Represents a single task in the queue with metadata.
    """

    task_id: UUID
    task_type: str
    task_data: Dict[str, Any]
    priority: QueuePriority
    status: str = "queued"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    attempts: int = 0
    max_attempts: int = 3
    error_message: Optional[str] = None
    project_id: Optional[UUID] = None

    def __post_init__(self) -> None:
        """Validate task data."""
        if not self.task_type:
            raise ValueError("Task type cannot be empty")

    @classmethod
    def create(
        cls,
        task_type: str,
        task_data: Dict[str, Any],
        priority: QueuePriority = QueuePriority.NORMAL,
        project_id: Optional[UUID] = None,
        max_attempts: int = 3,
    ) -> "QueuedTask":
        """Create new queued task."""
        return cls(
            task_id=uuid4(),
            task_type=task_type,
            task_data=task_data,
            priority=priority,
            project_id=project_id,
            max_attempts=max_attempts,
        )

    def update_status(self, status: str, error_message: Optional[str] = None) -> None:
        """Update task status."""
        self.status = status
        self.updated_at = datetime.utcnow()
        self.error_message = error_message

    def increment_attempts(self) -> None:
        """Increment attempt count."""
        self.attempts += 1
        self.updated_at = datetime.utcnow()

    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return self.attempts < self.max_attempts and self.status in [
            "failed",
            "timeout",
        ]

    def is_failed(self) -> bool:
        """Check if task is permanently failed."""
        return self.attempts >= self.max_attempts and self.status == "failed"

    def get_status_key(self) -> CacheKey:
        """Get task status cache key."""
        return CacheKey.task_status(self.task_id)


@dataclass
class Progress:
    """
    Progress tracking entity.

    Represents progress of a long-running operation.
    """

    correlation_id: UUID
    total_steps: int
    current_step: int = 0
    message: str = ""
    step_messages: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate progress data."""
        if self.total_steps <= 0:
            raise ValueError("Total steps must be positive")
        if self.current_step < 0:
            raise ValueError("Current step cannot be negative")

    @classmethod
    def create(cls, correlation_id: UUID, total_steps: int) -> "Progress":
        """Create new progress tracker."""
        return cls(correlation_id=correlation_id, total_steps=total_steps)

    def update_step(self, step: int, message: str) -> None:
        """Update current step with message."""
        if step < 0 or step > self.total_steps:
            raise ValueError(f"Invalid step: {step}")

        self.current_step = step
        self.message = message
        self.updated_at = datetime.utcnow()

        # Store step message if not duplicate
        if not self.step_messages or self.step_messages[-1] != message:
            self.step_messages.append(message)

    def increment_step(self, message: str) -> None:
        """Increment to next step with message."""
        self.update_step(self.current_step + 1, message)

    def complete(self, message: str = "Operation completed") -> None:
        """Mark progress as completed."""
        self.current_step = self.total_steps
        self.message = message
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def fail(self, error_message: str) -> None:
        """Mark progress as failed."""
        self.error_message = error_message
        self.updated_at = datetime.utcnow()

    def get_progress_percentage(self) -> float:
        """Get progress as percentage."""
        if self.total_steps == 0:
            return 0.0
        return (self.current_step / self.total_steps) * 100

    def is_completed(self) -> bool:
        """Check if progress is completed."""
        return self.completed_at is not None

    def is_failed(self) -> bool:
        """Check if progress has failed."""
        return self.error_message is not None

    def is_active(self) -> bool:
        """Check if progress is still active."""
        return not self.is_completed() and not self.is_failed()

    def get_key(self) -> CacheKey:
        """Get cache key for this progress."""
        return CacheKey.progress(self.correlation_id)


@dataclass
class RateLimit:
    """
    Rate limiting entity.

    Represents rate limiting state for a specific identifier.
    """

    identifier: str
    limit_type: str
    window: RateLimitWindow
    limit: int
    current_count: int = 0
    window_start: datetime = field(default_factory=datetime.utcnow)
    reset_time: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Initialize rate limit."""
        if not self.reset_time:
            self.reset_time = self.window_start + timedelta(seconds=self.window.value)

    @classmethod
    def create(
        cls, identifier: str, limit_type: str, window: RateLimitWindow, limit: int
    ) -> "RateLimit":
        """Create new rate limit."""
        return cls(
            identifier=identifier, limit_type=limit_type, window=window, limit=limit
        )

    def is_window_expired(self) -> bool:
        """Check if current time window has expired."""
        return datetime.utcnow() > self.reset_time

    def reset_window(self) -> None:
        """Reset time window and count."""
        self.current_count = 0
        self.window_start = datetime.utcnow()
        self.reset_time = self.window_start + timedelta(seconds=self.window.value)

    def can_request(self) -> bool:
        """Check if request is allowed."""
        if self.is_window_expired():
            self.reset_window()

        return self.current_count < self.limit

    def record_request(self) -> None:
        """Record a request attempt."""
        if self.is_window_expired():
            self.reset_window()

        self.current_count += 1

    def get_remaining_requests(self) -> int:
        """Get remaining requests in current window."""
        if self.is_window_expired():
            return self.limit

        return max(0, self.limit - self.current_count)

    def get_reset_seconds(self) -> int:
        """Get seconds until window reset."""
        if self.is_window_expired():
            return 0

        delta = self.reset_time - datetime.utcnow()
        return max(0, int(delta.total_seconds()))

    def get_key(self) -> CacheKey:
        """Get cache key for this rate limit."""
        return CacheKey.rate_limit(self.limit_type, self.identifier, self.window)
