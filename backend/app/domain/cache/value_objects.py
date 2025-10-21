"""
Cache Value Objects

Immutable value objects for cache domain following DDD principles.
Provides type safety and business logic encapsulation for cache operations.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Union, Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field, validator


class CacheEntryStatus(str, Enum):
    """Cache entry status enumeration."""

    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    EVICTED = "evicted"


class QueuePriority(int, Enum):
    """Task queue priority levels."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class RateLimitWindow(str, Enum):
    """Rate limiting time windows."""

    MINUTE = "60s"
    HOUR = "3600s"
    DAY = "86400s"


@dataclass(frozen=True)
class CacheKey:
    """
    Immutable cache key value object.

    Enforces key naming conventions and provides validation.
    """

    value: str

    # Cache key patterns
    PROJECT_DATA_PATTERN = re.compile(r"^project:[a-f0-9-]{36}:data$")
    PROJECT_CONTEXT_PATTERN = re.compile(r"^project:[a-f0-9-]{36}:context$")
    USER_SESSION_PATTERN = re.compile(r"^session:[a-f0-9-]{36}$")
    AGENT_CONFIG_PATTERN = re.compile(r"^agent:[a-z_]+:config$")
    RATE_LIMIT_PATTERN = re.compile(
        r"^rate_limit:(user|project|ip):[a-f0-9\-\.]+:(60|3600|86400)$"
    )
    QUEUE_PATTERN = re.compile(r"^queue:(embeddings|agent_tasks|exports)$")
    TASK_STATUS_PATTERN = re.compile(r"^task:[a-f0-9-]{36}:status$")
    PROGRESS_PATTERN = re.compile(r"^progress:[a-f0-9-]{36}$")

    def __post_init__(self) -> None:
        """Validate cache key format."""
        if not self.value:
            raise ValueError("Cache key cannot be empty")

        if len(self.value) > 250:
            raise ValueError("Cache key too long (max 250 characters)")

        # Validate no whitespace in key
        if any(char.isspace() for char in self.value):
            raise ValueError("Cache key cannot contain whitespace")

    @classmethod
    def project_data(cls, project_id: Union[str, UUID]) -> "CacheKey":
        """Create project data cache key."""
        project_str = str(project_id)
        if not re.match(r"^[a-f0-9-]{36}$", project_str):
            raise ValueError("Invalid project ID format")
        return cls(f"project:{project_str}:data")

    @classmethod
    def project_context(cls, project_id: Union[str, UUID]) -> "CacheKey":
        """Create project context cache key."""
        project_str = str(project_id)
        if not re.match(r"^[a-f0-9-]{36}$", project_str):
            raise ValueError("Invalid project ID format")
        return cls(f"project:{project_str}:context")

    @classmethod
    def user_session(cls, session_id: Union[str, UUID]) -> "CacheKey":
        """Create user session cache key."""
        session_str = str(session_id)
        if not re.match(r"^[a-f0-9-]{36}$", session_str):
            raise ValueError("Invalid session ID format")
        return cls(f"session:{session_str}")

    @classmethod
    def agent_config(cls, agent_type: str) -> "CacheKey":
        """Create agent configuration cache key."""
        if not re.match(r"^[a-z_]+$", agent_type):
            raise ValueError("Invalid agent type format")
        return cls(f"agent:{agent_type}:config")

    @classmethod
    def rate_limit(
        cls, limit_type: str, identifier: str, window: RateLimitWindow
    ) -> "CacheKey":
        """Create rate limit cache key."""
        if limit_type not in ["user", "project", "ip"]:
            raise ValueError("Invalid rate limit type")
        # Extract numeric seconds from window.value (e.g., "60s" -> "60")
        seconds = window.value.rstrip('s')
        return cls(f"rate_limit:{limit_type}:{identifier}:{seconds}")

    @classmethod
    def queue(cls, queue_name: str) -> "CacheKey":
        """Create queue cache key."""
        if queue_name not in ["embeddings", "agent_tasks", "exports"]:
            raise ValueError("Invalid queue name")
        return cls(f"queue:{queue_name}")

    @classmethod
    def task_status(cls, task_id: Union[str, UUID]) -> "CacheKey":
        """Create task status cache key."""
        task_str = str(task_id)
        if not re.match(r"^[a-f0-9-]{36}$", task_str):
            raise ValueError("Invalid task ID format")
        return cls(f"task:{task_str}:status")

    @classmethod
    def progress(cls, correlation_id: Union[str, UUID]) -> "CacheKey":
        """Create progress tracking cache key."""
        correlation_str = str(correlation_id)
        if not re.match(r"^[a-f0-9-]{36}$", correlation_str):
            raise ValueError("Invalid correlation ID format")
        return cls(f"progress:{correlation_str}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TTL:
    """
    Time To Live value object for cache expiration.

    Provides type-safe TTL configuration with validation.
    """

    seconds: int

    def __post_init__(self) -> None:
        """Validate TTL value."""
        if self.seconds <= 0:
            raise ValueError("TTL must be positive")
        if self.seconds > 86400 * 365:  # Max 1 year
            raise ValueError("TTL too large (max 1 year)")

    @classmethod
    def seconds(cls, seconds: int) -> "TTL":
        """Create TTL from seconds."""
        return cls(seconds)

    @classmethod
    def minutes(cls, minutes: int) -> "TTL":
        """Create TTL from minutes."""
        return cls(minutes * 60)

    @classmethod
    def hours(cls, hours: int) -> "TTL":
        """Create TTL from hours."""
        return cls(hours * 3600)

    @classmethod
    def days(cls, days: int) -> "TTL":
        """Create TTL from days."""
        return cls(days * 86400)

    # Common TTL presets
    @classmethod
    def project_data(cls) -> "TTL":
        """Project data TTL (1 hour)."""
        return cls.hours(1)

    @classmethod
    def user_session(cls) -> "TTL":
        """User session TTL (2 hours)."""
        return cls.hours(2)

    @classmethod
    def rate_limit(cls, window: RateLimitWindow) -> "TTL":
        """Rate limit TTL based on window."""
        if window == RateLimitWindow.MINUTE:
            return cls.minutes(1)
        elif window == RateLimitWindow.HOUR:
            return cls.hours(1)
        elif window == RateLimitWindow.DAY:
            return cls.days(1)
        else:
            raise ValueError(f"Unsupported RateLimitWindow: {window}")

    @classmethod
    def task_status(cls) -> "TTL":
        """Task status TTL (24 hours)."""
        return cls.days(1)

    @classmethod
    def progress(cls) -> "TTL":
        """Progress tracking TTL (30 minutes)."""
        return cls.minutes(30)

    def __str__(self) -> str:
        return f"{self.seconds}s"


class CacheMetrics(BaseModel):
    """Cache operation metrics for monitoring."""

    operation_type: str = Field(..., description="Type of cache operation")
    key_pattern: str = Field(..., description="Pattern of the cache key")
    hit: bool = Field(..., description="Whether operation was a cache hit")
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")
    data_size_bytes: Optional[int] = Field(
        None, description="Size of cached data in bytes"
    )
    project_id: Optional[str] = Field(
        None, description="Project ID for isolation tracking"
    )
    error: Optional[str] = Field(None, description="Error message if operation failed")

    @validator("execution_time_ms")
    def validate_execution_time(cls, v):
        if v < 0:
            raise ValueError("Execution time cannot be negative")
        return v

    @validator("data_size_bytes")
    def validate_data_size(cls, v):
        if v is not None and v < 0:
            raise ValueError("Data size cannot be negative")
        return v


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    requests_per_window: int = Field(
        ..., gt=0, description="Number of requests allowed"
    )
    window_seconds: int = Field(..., gt=0, description="Time window in seconds")
    burst_allowed: int = Field(1, ge=1, description="Burst capacity")

    @property
    def window(self) -> RateLimitWindow:
        """Get rate limit window enum."""
        if self.window_seconds == 60:
            return RateLimitWindow.MINUTE
        elif self.window_seconds == 3600:
            return RateLimitWindow.HOUR
        elif self.window_seconds == 86400:
            return RateLimitWindow.DAY
        else:
            raise ValueError(f"Unsupported window duration: {self.window_seconds}")

    def __str__(self) -> str:
        return f"{self.requests_per_window} requests per {self.window_seconds}s"


@dataclass(frozen=True)
class CacheVersion:
    """
    Cache version value object for cache invalidation.

    Provides version tracking to prevent stale data serving.
    """

    value: int

    def __post_init__(self) -> None:
        """Validate version value."""
        if self.value < 0:
            raise ValueError("Cache version cannot be negative")

    @classmethod
    def initial(cls) -> "CacheVersion":
        """Create initial cache version."""
        return cls(1)

    def next(self) -> "CacheVersion":
        """Get next version."""
        return CacheVersion(self.value + 1)

    def __str__(self) -> str:
        return f"v{self.value}"


@dataclass(frozen=True)
class CacheTag:
    """
    Cache tag value object for cache invalidation groups.

    Allows invalidating multiple cache entries by tag.
    """

    value: str

    def __post_init__(self) -> None:
        """Validate tag value."""
        if not self.value:
            raise ValueError("Cache tag cannot be empty")
        if len(self.value) > 50:
            raise ValueError("Cache tag too long (max 50 characters)")
        if any(char.isspace() for char in self.value):
            raise ValueError("Cache tag cannot contain whitespace")

    @classmethod
    def project(cls, project_id: Union[str, UUID]) -> "CacheTag":
        """Create project-specific cache tag."""
        return CacheTag(f"project:{project_id}")

    @classmethod
    def user(cls, user_id: Union[str, UUID]) -> "CacheTag":
        """Create user-specific cache tag."""
        return CacheTag(f"user:{user_id}")

    @classmethod
    def agent(cls, agent_type: str) -> "CacheTag":
        """Create agent-specific cache tag."""
        return CacheTag(f"agent:{agent_type}")

    def __str__(self) -> str:
        return self.value
