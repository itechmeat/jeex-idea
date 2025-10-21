"""
Unit tests for Cache Domain Models and Services.

Tests domain entities, value objects, and domain services
following DDD principles and business rules.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from app.domain.cache.entities import (
    ProjectCache,
    UserSession,
    TaskQueue,
    Progress,
    RateLimit,
    QueuedTask,
)
from app.domain.cache.value_objects import (
    CacheKey,
    TTL,
    CacheEntryStatus,
    CacheVersion,
    CacheTag,
    QueuePriority,
    RateLimitWindow,
    CacheMetrics,
    RateLimitConfig,
)
from app.domain.cache.domain_services import (
    CacheInvalidationService,
    SessionManagementService,
)


class TestCacheKey:
    """Test CacheKey value object."""

    def test_project_data_key(self):
        """Test project data cache key creation."""
        project_id = uuid4()
        key = CacheKey.project_data(project_id)

        assert key.value == f"project:{project_id}:data"
        assert str(key) == f"project:{project_id}:data"

    def test_user_session_key(self):
        """Test user session cache key creation."""
        session_id = uuid4()
        key = CacheKey.user_session(session_id)

        assert key.value == f"session:{session_id}"
        assert str(key) == f"session:{session_id}"

    def test_agent_config_key(self):
        """Test agent config cache key creation."""
        key = CacheKey.agent_config("business_analyst")
        assert key.value == "agent:business_analyst:config"

    def test_rate_limit_key(self):
        """Test rate limit cache key creation."""
        key = CacheKey.rate_limit("user", "user123", RateLimitWindow.HOUR)
        assert key.value == "rate_limit:user:user123:3600s"

    def test_invalid_key_empty(self):
        """Test invalid empty key."""
        with pytest.raises(ValueError, match="Cache key cannot be empty"):
            CacheKey("")

    def test_invalid_key_whitespace(self):
        """Test invalid key with whitespace."""
        with pytest.raises(ValueError, match="Cache key cannot contain whitespace"):
            CacheKey("invalid key")

    def test_invalid_key_too_long(self):
        """Test invalid key too long."""
        long_key = "a" * 251
        with pytest.raises(ValueError, match="Cache key too long"):
            CacheKey(long_key)

    def test_invalid_project_id(self):
        """Test invalid project ID format."""
        with pytest.raises(ValueError, match="Invalid project ID format"):
            CacheKey.project_data("invalid-uuid")


class TestTTL:
    """Test TTL value object."""

    def test_ttl_creation(self):
        """Test TTL creation."""
        ttl = TTL.seconds(3600)
        assert ttl.seconds == 3600
        assert str(ttl) == "3600s"

    def test_ttl_from_minutes(self):
        """Test TTL from minutes."""
        ttl = TTL.minutes(60)
        assert ttl.seconds == 3600

    def test_ttl_from_hours(self):
        """Test TTL from hours."""
        ttl = TTL.hours(2)
        assert ttl.seconds == 7200

    def test_ttl_from_days(self):
        """Test TTL from days."""
        ttl = TTL.days(1)
        assert ttl.seconds == 86400

    def test_ttl_presets(self):
        """Test TTL presets."""
        assert TTL.project_data().seconds == 3600
        assert TTL.user_session().seconds == 7200
        assert TTL.rate_limit(RateLimitWindow.MINUTE).seconds == 60
        assert TTL.rate_limit(RateLimitWindow.HOUR).seconds == 3600
        assert TTL.rate_limit(RateLimitWindow.DAY).seconds == 86400

    def test_invalid_ttl_negative(self):
        """Test invalid negative TTL."""
        with pytest.raises(ValueError, match="TTL must be positive"):
            TTL.seconds(-1)

    def test_invalid_ttl_too_large(self):
        """Test invalid TTL too large."""
        with pytest.raises(ValueError, match="TTL too large"):
            TTL.seconds(86400 * 366)  # More than 1 year


class TestCacheVersion:
    """Test CacheVersion value object."""

    def test_initial_version(self):
        """Test initial version."""
        version = CacheVersion.initial()
        assert version.value == 1
        assert str(version) == "v1"

    def test_version_increment(self):
        """Test version increment."""
        version = CacheVersion.initial()
        next_version = version.next()
        assert next_version.value == 2
        assert str(next_version) == "v2"

    def test_invalid_version_negative(self):
        """Test invalid negative version."""
        with pytest.raises(ValueError, match="Cache version cannot be negative"):
            CacheVersion(-1)


class TestCacheTag:
    """Test CacheTag value object."""

    def test_project_tag(self):
        """Test project cache tag."""
        project_id = uuid4()
        tag = CacheTag.project(project_id)
        assert tag.value == f"project:{project_id}"

    def test_user_tag(self):
        """Test user cache tag."""
        user_id = uuid4()
        tag = CacheTag.user(user_id)
        assert tag.value == f"user:{user_id}"

    def test_agent_tag(self):
        """Test agent cache tag."""
        tag = CacheTag.agent("business_analyst")
        assert tag.value == "agent:business_analyst"

    def test_invalid_tag_empty(self):
        """Test invalid empty tag."""
        with pytest.raises(ValueError, match="Cache tag cannot be empty"):
            CacheTag("")

    def test_invalid_tag_whitespace(self):
        """Test invalid tag with whitespace."""
        with pytest.raises(ValueError, match="Cache tag cannot contain whitespace"):
            CacheTag("invalid tag")

    def test_invalid_tag_too_long(self):
        """Test invalid tag too long."""
        long_tag = "a" * 51
        with pytest.raises(ValueError, match="Cache tag too long"):
            CacheTag(long_tag)


class TestProjectCache:
    """Test ProjectCache entity."""

    def test_project_cache_creation(self):
        """Test project cache creation."""
        project_id = uuid4()
        data = {"name": "Test Project", "description": "Test Description"}
        ttl = TTL.project_data()

        cache = ProjectCache.create(project_id, data, ttl)

        assert cache.project_id == project_id
        assert cache.data == data
        assert cache.version.value == 1
        assert cache.access_count == 0
        assert cache.is_expired() is False
        assert cache.get_status() == CacheEntryStatus.ACTIVE
        assert cache.has_tag(CacheTag.project(project_id))

    def test_project_cache_with_custom_version(self):
        """Test project cache with custom version."""
        project_id = uuid4()
        data = {"name": "Test Project"}
        ttl = TTL.project_data()
        version = CacheVersion(5)

        cache = ProjectCache.create(project_id, data, ttl, version)

        assert cache.version.value == 5

    def test_project_cache_access(self):
        """Test project cache access."""
        project_id = uuid4()
        data = {"name": "Test Project"}
        ttl = TTL.project_data()

        cache = ProjectCache.create(project_id, data, ttl)

        initial_access_count = cache.access_count
        initial_last_accessed = cache.last_accessed_at

        cache.access()

        assert cache.access_count == initial_access_count + 1
        assert cache.last_accessed_at > initial_last_accessed

    def test_project_cache_expiration(self):
        """Test project cache expiration."""
        project_id = uuid4()
        data = {"name": "Test Project"}
        ttl = TTL.seconds(1)

        cache = ProjectCache.create(project_id, data, ttl)
        assert cache.is_expired() is False

        # Manually set expiration time in past
        cache.expires_at = datetime.utcnow() - timedelta(seconds=1)
        assert cache.is_expired() is True
        assert cache.get_status() == CacheEntryStatus.EXPIRED

    def test_project_cache_invalidation(self):
        """Test project cache invalidation."""
        project_id = uuid4()
        data = {"name": "Test Project"}
        ttl = TTL.project_data()

        cache = ProjectCache.create(project_id, data, ttl)
        cache.invalidate()

        assert cache.is_expired() is True
        assert cache.get_status() == CacheEntryStatus.INVALIDATED

    def test_project_cache_tag_management(self):
        """Test project cache tag management."""
        project_id = uuid4()
        data = {"name": "Test Project"}
        ttl = TTL.project_data()
        custom_tag = CacheTag("custom")

        cache = ProjectCache.create(project_id, data, ttl)

        # Has project tag by default
        assert cache.has_tag(CacheTag.project(project_id))

        # Add custom tag
        cache.add_tag(custom_tag)
        assert cache.has_tag(custom_tag)

        # Don't duplicate tags
        cache.add_tag(custom_tag)
        assert cache.tags.count(custom_tag) == 1

    def test_project_cache_key(self):
        """Test project cache key generation."""
        project_id = uuid4()
        data = {"name": "Test Project"}
        ttl = TTL.project_data()

        cache = ProjectCache.create(project_id, data, ttl)
        key = cache.get_key()

        assert isinstance(key, CacheKey)
        assert key.value == f"project:{project_id}:data"


class TestUserSession:
    """Test UserSession entity."""

    def test_user_session_creation(self):
        """Test user session creation."""
        user_id = uuid4()
        user_data = {"name": "Test User", "email": "test@example.com"}
        project_access = [uuid4(), uuid4()]

        session = UserSession.create(user_id, user_data, project_access)

        assert session.user_id == user_id
        assert session.user_data == user_data
        assert session.project_access == project_access
        assert session.is_active is True
        assert session.is_valid() is True

    def test_user_session_with_custom_ttl(self):
        """Test user session with custom TTL."""
        user_id = uuid4()
        user_data = {"name": "Test User"}
        ttl = TTL.hours(4)

        session = UserSession.create(user_id, user_data, ttl=ttl)

        # Should expire in 4 hours
        expected_expires = datetime.utcnow() + timedelta(hours=4)
        time_diff = abs((session.expires_at - expected_expires).total_seconds())
        assert time_diff < 1  # Within 1 second

    def test_user_session_expiration(self):
        """Test user session expiration."""
        user_id = uuid4()
        user_data = {"name": "Test User"}
        ttl = TTL.seconds(1)

        session = UserSession.create(user_id, user_data, ttl)
        assert session.is_valid() is True

        # Set expiration in past
        session.expires_at = datetime.utcnow() - timedelta(seconds=1)
        assert session.is_expired() is True
        assert session.is_valid() is False

    def test_user_session_activity_update(self):
        """Test user session activity update."""
        user_id = uuid4()
        user_data = {"name": "Test User"}

        session = UserSession.create(user_id, user_data)
        initial_activity = session.last_activity_at

        session.update_activity()
        assert session.last_activity_at > initial_activity

    def test_user_session_extension(self):
        """Test user session TTL extension."""
        user_id = uuid4()
        user_data = {"name": "Test User"}
        ttl = TTL.hours(1)

        session = UserSession.create(user_id, user_data, ttl=ttl)
        initial_expires = session.expires_at

        # Extend by 2 more hours
        session.extend_session(TTL.hours(2))
        expected_expires = initial_expires + timedelta(hours=2)

        time_diff = abs((session.expires_at - expected_expires).total_seconds())
        assert time_diff < 1  # Within 1 second

    def test_user_session_invalidation(self):
        """Test user session invalidation."""
        user_id = uuid4()
        user_data = {"name": "Test User"}

        session = UserSession.create(user_id, user_data)
        session.invalidate()

        assert session.is_active is False
        assert session.is_valid() is False

    def test_user_session_project_access(self):
        """Test user session project access management."""
        user_id = uuid4()
        user_data = {"name": "Test User"}
        project_id = uuid4()

        session = UserSession.create(user_id, user_data)

        # Initially no access
        assert session.has_project_access(project_id) is False

        # Grant access
        session.grant_project_access(project_id)
        assert session.has_project_access(project_id) is True

        # Revoke access
        session.revoke_project_access(project_id)
        assert session.has_project_access(project_id) is False

    def test_user_session_key(self):
        """Test user session key generation."""
        user_id = uuid4()
        user_data = {"name": "Test User"}

        session = UserSession.create(user_id, user_data)
        key = session.get_key()

        assert isinstance(key, CacheKey)
        assert key.value == f"session:{session.session_id}"


class TestTaskQueue:
    """Test TaskQueue entity."""

    def test_task_queue_creation(self):
        """Test task queue creation."""
        queue = TaskQueue.create("embeddings", max_size=100)

        assert queue.queue_name == "embeddings"
        assert queue.max_size == 100
        assert queue.size() == 0
        assert queue.is_empty() is True
        assert queue.is_full() is False

    def test_invalid_queue_name(self):
        """Test invalid queue name."""
        with pytest.raises(ValueError, match="Invalid queue name"):
            TaskQueue.create("invalid_queue")

    def test_task_enqueue(self):
        """Test task enqueue."""
        queue = TaskQueue.create("agent_tasks")
        task = QueuedTask.create("test_task", {"data": "test"})

        queue.enqueue(task)

        assert queue.size() == 1
        assert queue.is_empty() is False

    def test_task_priority_ordering(self):
        """Test task priority ordering."""
        queue = TaskQueue.create("exports")

        # Create tasks with different priorities
        low_task = QueuedTask.create("low", {"priority": "low"}, QueuePriority.LOW)
        high_task = QueuedTask.create("high", {"priority": "high"}, QueuePriority.HIGH)
        normal_task = QueuedTask.create(
            "normal", {"priority": "normal"}, QueuePriority.NORMAL
        )

        # Enqueue in random order
        queue.enqueue(low_task)
        queue.enqueue(high_task)
        queue.enqueue(normal_task)

        # Should be ordered by priority (high, normal, low)
        assert queue.peek().task_id == high_task.task_id
        assert queue.dequeue().task_id == high_task.task_id
        assert queue.dequeue().task_id == normal_task.task_id
        assert queue.dequeue().task_id == low_task.task_id

    def test_task_dequeue(self):
        """Test task dequeue."""
        queue = TaskQueue.create("embeddings")
        task = QueuedTask.create("test_task", {"data": "test"})

        queue.enqueue(task)
        dequeued_task = queue.dequeue()

        assert dequeued_task.task_id == task.task_id
        assert queue.size() == 0
        assert queue.is_empty() is True

    def test_dequeue_empty_queue(self):
        """Test dequeue from empty queue."""
        queue = TaskQueue.create("embeddings")
        assert queue.dequeue() is None

    def test_queue_full(self):
        """Test queue capacity limits."""
        queue = TaskQueue.create("embeddings", max_size=2)
        task1 = QueuedTask.create("task1", {"data": "test1"})
        task2 = QueuedTask.create("task2", {"data": "test2"})
        task3 = QueuedTask.create("task3", {"data": "test3"})

        queue.enqueue(task1)
        queue.enqueue(task2)

        assert queue.is_full() is True

        with pytest.raises(ValueError, match="Queue embeddings is full"):
            queue.enqueue(task3)

    def test_get_tasks_by_status(self):
        """Test getting tasks by status."""
        queue = TaskQueue.create("agent_tasks")
        task1 = QueuedTask.create("task1", {"data": "test1"})
        task2 = QueuedTask.create("task2", {"data": "test2"})

        task2.update_status("processing")

        queue.enqueue(task1)
        queue.enqueue(task2)

        queued_tasks = queue.get_tasks_by_status("queued")
        processing_tasks = queue.get_tasks_by_status("processing")

        assert len(queued_tasks) == 1
        assert queued_tasks[0].task_id == task1.task_id
        assert len(processing_tasks) == 1
        assert processing_tasks[0].task_id == task2.task_id


class TestProgress:
    """Test Progress entity."""

    def test_progress_creation(self):
        """Test progress creation."""
        correlation_id = uuid4()
        total_steps = 5

        progress = Progress.create(correlation_id, total_steps)

        assert progress.correlation_id == correlation_id
        assert progress.total_steps == total_steps
        assert progress.current_step == 0
        assert progress.is_active() is True
        assert progress.is_completed() is False
        assert progress.is_failed() is False
        assert progress.get_progress_percentage() == 0.0

    def test_progress_invalid_steps(self):
        """Test progress with invalid steps."""
        correlation_id = uuid4()

        with pytest.raises(ValueError, match="Total steps must be positive"):
            Progress.create(correlation_id, 0)

    def test_progress_step_update(self):
        """Test progress step update."""
        correlation_id = uuid4()
        progress = Progress.create(correlation_id, 5)

        progress.update_step(2, "Processing step 2")

        assert progress.current_step == 2
        assert progress.message == "Processing step 2"
        assert progress.get_progress_percentage() == 40.0
        assert "Processing step 2" in progress.step_messages

    def test_progress_increment_step(self):
        """Test progress increment step."""
        correlation_id = uuid4()
        progress = Progress.create(correlation_id, 3)

        progress.increment_step("Step 1")
        progress.increment_step("Step 2")

        assert progress.current_step == 2
        assert progress.message == "Step 2"
        assert progress.get_progress_percentage() == 66.67  # Rounded

    def test_progress_completion(self):
        """Test progress completion."""
        correlation_id = uuid4()
        progress = Progress.create(correlation_id, 3)

        progress.increment_step("Step 1")
        progress.increment_step("Step 2")
        progress.complete("All done")

        assert progress.is_completed() is True
        assert progress.is_active() is False
        assert progress.current_step == 3
        assert progress.message == "All done"
        assert progress.completed_at is not None

    def test_progress_failure(self):
        """Test progress failure."""
        correlation_id = uuid4()
        progress = Progress.create(correlation_id, 3)

        progress.fail("Something went wrong")

        assert progress.is_failed() is True
        assert progress.is_active() is False
        assert progress.error_message == "Something went wrong"

    def test_progress_key(self):
        """Test progress key generation."""
        correlation_id = uuid4()
        progress = Progress.create(correlation_id, 3)
        key = progress.get_key()

        assert isinstance(key, CacheKey)
        assert key.value == f"progress:{correlation_id}"


class TestRateLimit:
    """Test RateLimit entity."""

    def test_rate_limit_creation(self):
        """Test rate limit creation."""
        rate_limit = RateLimit.create("user123", "user", RateLimitWindow.HOUR, 100)

        assert rate_limit.identifier == "user123"
        assert rate_limit.limit_type == "user"
        assert rate_limit.window == RateLimitWindow.HOUR
        assert rate_limit.limit == 100
        assert rate_limit.current_count == 0
        assert rate_limit.can_request() is True
        assert rate_limit.get_remaining_requests() == 100

    def test_rate_limit_requests(self):
        """Test rate limit request tracking."""
        rate_limit = RateLimit.create("user123", "user", RateLimitWindow.HOUR, 5)

        # Make 3 requests
        for i in range(3):
            assert rate_limit.can_request() is True
            rate_limit.record_request()

        assert rate_limit.current_count == 3
        assert rate_limit.get_remaining_requests() == 2

        # Make remaining requests
        rate_limit.record_request()
        rate_limit.record_request()

        assert rate_limit.can_request() is False
        assert rate_limit.get_remaining_requests() == 0

    def test_rate_limit_window_reset(self):
        """Test rate limit window reset."""
        rate_limit = RateLimit.create("user123", "user", RateLimitWindow.MINUTE, 10)

        # Exhaust limit
        for _ in range(10):
            rate_limit.record_request()

        assert rate_limit.can_request() is False

        # Reset window
        rate_limit.reset_window()

        assert rate_limit.current_count == 0
        assert rate_limit.can_request() is True
        assert rate_limit.get_remaining_requests() == 10

    def test_rate_limit_window_expiry(self):
        """Test rate limit window expiry."""
        rate_limit = RateLimit.create("user123", "user", RateLimitWindow.MINUTE, 10)

        # Set reset time in past
        rate_limit.reset_time = datetime.utcnow() - timedelta(seconds=1)

        assert rate_limit.is_window_expired() is True

        # Recording request should reset window
        rate_limit.record_request()

        assert rate_limit.current_count == 1
        assert rate_limit.is_window_expired() is False

    def test_rate_limit_key(self):
        """Test rate limit key generation."""
        rate_limit = RateLimit.create("user123", "user", RateLimitWindow.HOUR, 100)
        key = rate_limit.get_key()

        assert isinstance(key, CacheKey)
        assert key.value == "rate_limit:user:user123:3600s"

    def test_reset_time_calculation(self):
        """Test reset time calculation."""
        rate_limit = RateLimit.create("user123", "user", RateLimitWindow.MINUTE, 10)

        # Should be approximately 1 minute from now
        expected_reset = datetime.utcnow() + timedelta(seconds=60)
        time_diff = abs((rate_limit.reset_time - expected_reset).total_seconds())
        assert time_diff < 1  # Within 1 second


class TestQueuedTask:
    """Test QueuedTask entity."""

    def test_queued_task_creation(self):
        """Test queued task creation."""
        task = QueuedTask.create("embedding", {"text": "test text"})

        assert task.task_type == "embedding"
        assert task.task_data == {"text": "test text"}
        assert task.priority == QueuePriority.NORMAL
        assert task.status == "queued"
        assert task.attempts == 0
        assert task.max_attempts == 3
        assert task.can_retry() is False  # No failures yet
        assert task.is_failed() is False

    def test_queued_task_with_priority(self):
        """Test queued task with custom priority."""
        task = QueuedTask.create(
            "urgent_task",
            {"data": "urgent"},
            priority=QueuePriority.HIGH,
            max_attempts=5,
        )

        assert task.priority == QueuePriority.HIGH
        assert task.max_attempts == 5

    def test_task_status_update(self):
        """Test task status update."""
        task = QueuedTask.create("test_task", {"data": "test"})

        task.update_status("processing")
        assert task.status == "processing"

        task.update_status("completed")
        assert task.status == "completed"

    def test_task_with_error(self):
        """Test task status update with error."""
        task = QueuedTask.create("test_task", {"data": "test"})

        task.update_status("failed", "Connection error")
        assert task.status == "failed"
        assert task.error_message == "Connection error"

    def test_task_retry_logic(self):
        """Test task retry logic."""
        task = QueuedTask.create("test_task", {"data": "test"})

        # Initially can retry if fails
        task.update_status("failed", "First failure")
        task.increment_attempts()

        assert task.attempts == 1
        assert task.can_retry() is True
        assert task.is_failed() is False

        # Exhaust attempts
        task.increment_attempts()
        task.increment_attempts()
        task.increment_attempts()

        assert task.attempts == 3
        assert task.can_retry() is False
        assert task.is_failed() is True

    def test_task_status_key(self):
        """Test task status key generation."""
        task = QueuedTask.create("test_task", {"data": "test"})
        key = task.get_status_key()

        assert isinstance(key, CacheKey)
        assert key.value == f"task:{task.task_id}:status"


class TestCacheMetrics:
    """Test CacheMetrics model."""

    def test_cache_metrics_creation(self):
        """Test cache metrics creation."""
        metrics = CacheMetrics(
            operation_type="get",
            key_pattern="project:*:data",
            hit=True,
            execution_time_ms=2.5,
            data_size_bytes=1024,
            project_id=str(uuid4()),
        )

        assert metrics.operation_type == "get"
        assert metrics.key_pattern == "project:*:data"
        assert metrics.hit is True
        assert metrics.execution_time_ms == 2.5
        assert metrics.data_size_bytes == 1024

    def test_cache_metrics_with_error(self):
        """Test cache metrics with error."""
        metrics = CacheMetrics(
            operation_type="set",
            key_pattern="session:*",
            hit=False,
            execution_time_ms=150.0,
            error="Connection timeout",
        )

        assert metrics.error == "Connection timeout"

    def test_invalid_execution_time(self):
        """Test invalid execution time."""
        with pytest.raises(ValueError, match="Execution time cannot be negative"):
            CacheMetrics(
                operation_type="get", key_pattern="*", hit=True, execution_time_ms=-1.0
            )

    def test_invalid_data_size(self):
        """Test invalid data size."""
        with pytest.raises(ValueError, match="Data size cannot be negative"):
            CacheMetrics(
                operation_type="set",
                key_pattern="*",
                hit=True,
                execution_time_ms=1.0,
                data_size_bytes=-1,
            )


class TestRateLimitConfig:
    """Test RateLimitConfig model."""

    def test_rate_limit_config_creation(self):
        """Test rate limit config creation."""
        config = RateLimitConfig(
            requests_per_window=100, window_seconds=3600, burst_allowed=5
        )

        assert config.requests_per_window == 100
        assert config.window_seconds == 3600
        assert config.burst_allowed == 5
        assert config.window == RateLimitWindow.HOUR

    def test_rate_limit_config_string(self):
        """Test rate limit config string representation."""
        config = RateLimitConfig(requests_per_window=1000, window_seconds=3600)

        assert str(config) == "1000 requests per 3600s"

    def test_unsupported_window_duration(self):
        """Test unsupported window duration."""
        config = RateLimitConfig(
            requests_per_window=100,
            window_seconds=1800,  # 30 minutes not supported
        )

        with pytest.raises(ValueError, match="Unsupported window duration"):
            _ = config.window


if __name__ == "__main__":
    pytest.main([__file__])
