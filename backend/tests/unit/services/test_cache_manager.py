"""
Unit tests for Cache Manager Service.

Tests the high-level cache management service that orchestrates
domain entities, repositories, and services.
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.cache.cache_manager import CacheManager
from app.domain.cache.entities import ProjectCache, UserSession, Progress
from app.domain.cache.value_objects import (
    CacheKey,
    TTL,
    CacheTag,
    RateLimitWindow,
    RateLimitConfig,
)


class TestCacheManager:
    """Test CacheManager service."""

    @pytest.fixture
    def cache_manager(self):
        """Create cache manager instance."""
        return CacheManager()

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        repo = AsyncMock()
        repo.initialize = AsyncMock()
        repo.close = AsyncMock()
        repo.get_metrics = AsyncMock(return_value={"test": "metrics"})
        return repo

    @pytest.fixture
    def sample_project_data(self):
        """Sample project data for testing."""
        return {
            "id": str(uuid4()),
            "name": "Test Project",
            "description": "Test Description",
            "documents": ["doc1", "doc2"],
            "metadata": {"created_by": "test_user"},
        }

    @pytest.fixture
    def sample_user_data(self):
        """Sample user data for testing."""
        return {
            "id": str(uuid4()),
            "name": "Test User",
            "email": "test@example.com",
            "roles": ["user", "admin"],
        }

    @pytest.mark.asyncio
    async def test_initialize(self, cache_manager):
        """Test cache manager initialization."""
        with patch.object(cache_manager.repository, "initialize") as mock_init:
            await cache_manager.initialize()
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check(self, cache_manager):
        """Test comprehensive health check."""
        mock_health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "memory": {"usage_percentage": 45.0},
            "connections": {"status": "healthy"},
        }

        with patch.object(
            cache_manager.health_service,
            "perform_comprehensive_health_check",
            return_value=mock_health_status,
        ) as mock_health:
            result = await cache_manager.health_check()

            mock_health.assert_called_once()
            assert result["status"] == "healthy"
            assert "cache_manager" in result
            assert result["cache_manager"]["services"]["invalidation"] == "active"

    @pytest.mark.asyncio
    async def test_cache_project_data(self, cache_manager, sample_project_data):
        """Test caching project data."""
        project_id = uuid4()
        ttl = TTL.hours(2)

        with patch.object(cache_manager.repository.project_cache, "save") as mock_save:
            await cache_manager.cache_project_data(project_id, sample_project_data, ttl)

            mock_save.assert_called_once()
            # Verify the saved cache entity
            saved_cache = mock_save.call_args[0][0]
            assert isinstance(saved_cache, ProjectCache)
            assert saved_cache.project_id == project_id
            assert saved_cache.data == sample_project_data

    @pytest.mark.asyncio
    async def test_cache_project_data_with_tags(
        self, cache_manager, sample_project_data
    ):
        """Test caching project data with custom tags."""
        project_id = uuid4()
        custom_tags = [CacheTag("custom"), CacheTag("test")]

        with patch.object(cache_manager.repository.project_cache, "save") as mock_save:
            await cache_manager.cache_project_data(
                project_id, sample_project_data, tags=custom_tags
            )

            saved_cache = mock_save.call_args[0][0]
            assert saved_cache.has_tag(CacheTag.project(project_id))
            assert saved_cache.has_tag(CacheTag("custom"))
            assert saved_cache.has_tag(CacheTag("test"))

    @pytest.mark.asyncio
    async def test_get_project_data_hit(self, cache_manager, sample_project_data):
        """Test getting cached project data (cache hit)."""
        project_id = uuid4()
        mock_cache = MagicMock()
        mock_cache.data = sample_project_data
        mock_cache.version.value = 2

        with patch.object(
            cache_manager.repository.project_cache,
            "find_by_project_id",
            return_value=mock_cache,
        ) as mock_find:
            result = await cache_manager.get_project_data(project_id)

            mock_find.assert_called_once_with(project_id)
            assert result == sample_project_data

    @pytest.mark.asyncio
    async def test_get_project_data_miss(self, cache_manager):
        """Test getting cached project data (cache miss)."""
        project_id = uuid4()

        with patch.object(
            cache_manager.repository.project_cache,
            "find_by_project_id",
            return_value=None,
        ) as mock_find:
            result = await cache_manager.get_project_data(project_id)

            mock_find.assert_called_once_with(project_id)
            assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_project_cache(self, cache_manager):
        """Test invalidating project cache."""
        project_id = uuid4()
        reason = "project_updated"

        with patch.object(
            cache_manager.invalidation_service,
            "invalidate_project_caches",
            return_value=3,
        ) as mock_invalidate:
            count = await cache_manager.invalidate_project_cache(project_id, reason)

            mock_invalidate.assert_called_once_with(project_id, reason)
            assert count == 3

    @pytest.mark.asyncio
    async def test_cache_project_context(self, cache_manager):
        """Test caching project context."""
        project_id = uuid4()
        context = {"current_step": 2, "agent": "business_analyst"}

        with patch("redis.asyncio.Redis.setex") as mock_setex:
            mock_redis = AsyncMock()
            mock_redis.setex = mock_setex

            with patch(
                "app.services.cache.cache_manager.redis_service.get_connection",
                return_value=mock_redis,
            ):
                result = await cache_manager.cache_project_context(project_id, context)

                mock_setex.assert_called_once()
                assert result is True

    @pytest.mark.asyncio
    async def test_get_project_context(self, cache_manager):
        """Test getting cached project context."""
        project_id = uuid4()
        context_data = json.dumps(
            {
                "project_id": str(project_id),
                "context": {"current_step": 2, "agent": "business_analyst"},
                "created_at": datetime.utcnow().isoformat(),
            }
        )

        with patch("redis.asyncio.Redis.get", return_value=context_data) as mock_get:
            mock_redis = AsyncMock()
            mock_redis.get = mock_get

            with patch(
                "app.services.cache.cache_manager.redis_service.get_connection",
                return_value=mock_redis,
            ):
                result = await cache_manager.get_project_context(project_id)

                mock_get.assert_called_once()
                assert result == {"current_step": 2, "agent": "business_analyst"}

    @pytest.mark.asyncio
    async def test_create_user_session(self, cache_manager, sample_user_data):
        """Test creating user session."""
        user_id = uuid4()
        project_access = [uuid4(), uuid4()]
        mock_session = MagicMock()
        mock_session.session_id = uuid4()

        with patch.object(
            cache_manager.session_service, "create_session", return_value=mock_session
        ) as mock_create:
            session = await cache_manager.create_user_session(
                user_id, sample_user_data, project_access
            )

            mock_create.assert_called_once()
            assert session == mock_session

    @pytest.mark.asyncio
    async def test_validate_user_session(self, cache_manager):
        """Test validating user session."""
        session_id = uuid4()
        mock_session = MagicMock()
        mock_session.user_id = uuid4()

        with patch.object(
            cache_manager.session_service, "validate_session", return_value=mock_session
        ) as mock_validate:
            session = await cache_manager.validate_user_session(session_id)

            mock_validate.assert_called_once_with(session_id)
            assert session == mock_session

    @pytest.mark.asyncio
    async def test_revoke_user_session(self, cache_manager):
        """Test revoking user session."""
        session_id = uuid4()
        reason = "user_logout"

        with patch.object(
            cache_manager.session_service, "revoke_session", return_value=True
        ) as mock_revoke:
            result = await cache_manager.revoke_user_session(session_id, reason)

            mock_revoke.assert_called_once_with(session_id, reason)
            assert result is True

    @pytest.mark.asyncio
    async def test_grant_project_access(self, cache_manager):
        """Test granting project access to session."""
        session_id = uuid4()
        project_id = uuid4()

        with patch.object(
            cache_manager.session_service, "grant_project_access", return_value=True
        ) as mock_grant:
            result = await cache_manager.grant_project_access(session_id, project_id)

            mock_grant.assert_called_once_with(session_id, project_id)
            assert result is True

    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed(self, cache_manager):
        """Test rate limit check (allowed)."""
        identifier = "user123"
        config = RateLimitConfig(requests_per_window=100, window_seconds=3600)
        mock_result = {
            "allowed": True,
            "current_count": 5,
            "remaining_requests": 95,
            "reset_seconds": 1800,
            "limit": 100,
            "window": 3600,
        }

        with patch.object(
            cache_manager.rate_limit_service,
            "check_rate_limit",
            return_value=mock_result,
        ) as mock_check:
            result = await cache_manager.check_rate_limit("user", identifier, config)

            mock_check.assert_called_once_with(identifier, "user", config)
            assert result["allowed"] is True
            assert result["remaining_requests"] == 95

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self, cache_manager):
        """Test rate limit check (exceeded)."""
        identifier = "user123"
        config = RateLimitConfig(requests_per_window=100, window_seconds=3600)
        mock_result = {
            "allowed": False,
            "current_count": 100,
            "remaining_requests": 0,
            "reset_seconds": 300,
            "limit": 100,
            "window": 3600,
        }

        with patch.object(
            cache_manager.rate_limit_service,
            "check_rate_limit",
            return_value=mock_result,
        ) as mock_check:
            result = await cache_manager.check_rate_limit("user", identifier, config)

            mock_check.assert_called_once_with(identifier, "user", config)
            assert result["allowed"] is False
            assert result["remaining_requests"] == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_service_error(self, cache_manager):
        """Test rate limit check with service error (fail open)."""
        identifier = "user123"
        config = RateLimitConfig(requests_per_window=100, window_seconds=3600)

        with patch.object(
            cache_manager.rate_limit_service,
            "check_rate_limit",
            side_effect=Exception("Service unavailable"),
        ) as mock_check:
            result = await cache_manager.check_rate_limit("user", identifier, config)

            mock_check.assert_called_once()
            # Should fail open - allow request
            assert result["allowed"] is True
            assert result["error"] == "Rate limiting service unavailable"

    @pytest.mark.asyncio
    async def test_get_rate_limit_status(self, cache_manager):
        """Test getting rate limit status."""
        identifier = "user123"
        window = RateLimitWindow.HOUR
        limit = 100
        mock_result = {
            "current_count": 25,
            "remaining_requests": 75,
            "reset_seconds": 1200,
            "limit": 100,
            "window": 3600,
            "allowed": True,
        }

        with patch.object(
            cache_manager.rate_limit_service,
            "get_rate_limit_status",
            return_value=mock_result,
        ) as mock_status:
            result = await cache_manager.get_rate_limit_status(
                "user", identifier, window, limit
            )

            mock_status.assert_called_once_with(identifier, "user", window, limit)
            assert result["current_count"] == 25
            assert result["remaining_requests"] == 75

    @pytest.mark.asyncio
    async def test_start_progress_tracking(self, cache_manager):
        """Test starting progress tracking."""
        correlation_id = uuid4()
        total_steps = 5

        with patch.object(cache_manager.repository.progress, "save") as mock_save:
            result = await cache_manager.start_progress_tracking(
                correlation_id, total_steps
            )

            mock_save.assert_called_once()
            saved_progress = mock_save.call_args[0][0]
            assert saved_progress.correlation_id == correlation_id
            assert saved_progress.total_steps == total_steps
            assert saved_progress.current_step == 0
            assert result is True

    @pytest.mark.asyncio
    async def test_update_progress(self, cache_manager):
        """Test updating progress."""
        correlation_id = uuid4()
        step = 2
        message = "Processing business analyst response"

        with patch.object(
            cache_manager.repository.progress, "update_progress", return_value=True
        ) as mock_update:
            result = await cache_manager.update_progress(correlation_id, step, message)

            mock_update.assert_called_once_with(correlation_id, step, message)
            assert result is True

    @pytest.mark.asyncio
    async def test_increment_progress(self, cache_manager):
        """Test incrementing progress."""
        correlation_id = uuid4()
        message = "Next step completed"
        mock_progress = MagicMock()
        mock_progress.current_step = 2

        with patch.object(
            cache_manager.repository.progress,
            "find_by_correlation_id",
            return_value=mock_progress,
        ) as mock_find:
            with patch.object(
                cache_manager.repository.progress, "update_progress", return_value=True
            ) as mock_update:
                result = await cache_manager.increment_progress(correlation_id, message)

                mock_find.assert_called_once_with(correlation_id)
                mock_update.assert_called_once_with(correlation_id, 3, message)
                assert result is True

    @pytest.mark.asyncio
    async def test_complete_progress(self, cache_manager):
        """Test completing progress."""
        correlation_id = uuid4()
        message = "Operation completed successfully"

        with patch.object(
            cache_manager.repository.progress, "complete_progress", return_value=True
        ) as mock_complete:
            result = await cache_manager.complete_progress(correlation_id, message)

            mock_complete.assert_called_once_with(correlation_id, message)
            assert result is True

    @pytest.mark.asyncio
    async def test_fail_progress(self, cache_manager):
        """Test failing progress."""
        correlation_id = uuid4()
        error_message = "Processing failed due to error"

        with patch.object(
            cache_manager.repository.progress, "fail_progress", return_value=True
        ) as mock_fail:
            result = await cache_manager.fail_progress(correlation_id, error_message)

            mock_fail.assert_called_once_with(correlation_id, error_message)
            assert result is True

    @pytest.mark.asyncio
    async def test_get_progress(self, cache_manager):
        """Test getting progress."""
        correlation_id = uuid4()
        mock_progress = MagicMock()
        mock_progress.correlation_id = correlation_id
        mock_progress.total_steps = 5
        mock_progress.current_step = 3
        mock_progress.message = "Processing step 3"
        mock_progress.get_progress_percentage.return_value = 60.0
        mock_progress.started_at = datetime.utcnow()
        mock_progress.updated_at = datetime.utcnow()
        mock_progress.completed_at = None
        mock_progress.is_completed.return_value = False
        mock_progress.is_failed.return_value = False
        mock_progress.is_active.return_value = True
        mock_progress.error_message = None

        with patch.object(
            cache_manager.repository.progress,
            "find_by_correlation_id",
            return_value=mock_progress,
        ) as mock_find:
            result = await cache_manager.get_progress(correlation_id)

            mock_find.assert_called_once_with(correlation_id)
            assert result["correlation_id"] == str(correlation_id)
            assert result["total_steps"] == 5
            assert result["current_step"] == 3
            assert result["percentage"] == 60.0
            assert result["is_active"] is True
            assert result["is_completed"] is False

    @pytest.mark.asyncio
    async def test_cleanup_expired_entries(self, cache_manager):
        """Test cleaning up expired entries."""
        max_age_hours = 24
        mock_cleanup_counts = {
            "project_caches": 10,
            "user_sessions": 5,
            "progress_trackers": 3,
        }

        with patch.object(
            cache_manager.invalidation_service,
            "cleanup_expired_entries",
            return_value=mock_cleanup_counts,
        ) as mock_cleanup:
            result = await cache_manager.cleanup_expired_entries(max_age_hours)

            mock_cleanup.assert_called_once_with(max_age_hours)
            assert result == mock_cleanup_counts

    @pytest.mark.asyncio
    async def test_get_cache_statistics(self, cache_manager):
        """Test getting cache statistics."""
        mock_stats = {
            "timestamp": datetime.utcnow().isoformat(),
            "memory": {"usage_percentage": 45.0},
            "operations": {"total_commands": 10000},
            "key_distribution": {"project:": 50, "session:": 20},
        }

        with patch.object(
            cache_manager.repository, "get_metrics", return_value=mock_stats
        ) as mock_metrics:
            result = await cache_manager.get_cache_statistics()

            mock_metrics.assert_called_once()
            assert result == mock_stats

    @pytest.mark.asyncio
    async def test_get_performance_metrics(self, cache_manager):
        """Test getting performance metrics."""
        mock_metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "slow_operations": {"count": 2, "operations": []},
            "memory_usage": {"usage_percentage": 45.0},
            "performance_indicators": {"slow_operation_count": 2},
        }

        with patch.object(
            cache_manager.health_service,
            "get_performance_metrics",
            return_value=mock_metrics,
        ) as mock_metrics:
            result = await cache_manager.get_performance_metrics()

            mock_metrics.assert_called_once()
            assert result == mock_metrics

    @pytest.mark.asyncio
    async def test_cache_agent_config(self, cache_manager):
        """Test caching agent configuration."""
        agent_type = "business_analyst"
        config = {"model": "gpt-4", "temperature": 0.7, "max_tokens": 2000}

        with patch("redis.asyncio.Redis.setex") as mock_setex:
            mock_redis = AsyncMock()
            mock_redis.setex = mock_setex

            with patch(
                "app.services.cache.cache_manager.redis_service.get_connection",
                return_value=mock_redis,
            ):
                result = await cache_manager.cache_agent_config(agent_type, config)

                mock_setex.assert_called_once()
                assert result is True

    @pytest.mark.asyncio
    async def test_get_agent_config(self, cache_manager):
        """Test getting cached agent configuration."""
        agent_type = "business_analyst"
        config_data = json.dumps(
            {
                "agent_type": agent_type,
                "config": {"model": "gpt-4", "temperature": 0.7},
                "cached_at": datetime.utcnow().isoformat(),
            }
        )

        with patch("redis.asyncio.Redis.get", return_value=config_data) as mock_get:
            mock_redis = AsyncMock()
            mock_redis.get = mock_get

            with patch(
                "app.services.cache.cache_manager.redis_service.get_connection",
                return_value=mock_redis,
            ):
                result = await cache_manager.get_agent_config(agent_type)

                mock_get.assert_called_once()
                assert result == {"model": "gpt-4", "temperature": 0.7}

    @pytest.mark.asyncio
    async def test_close(self, cache_manager):
        """Test closing cache manager."""
        with patch.object(cache_manager.repository, "close") as mock_close:
            await cache_manager.close()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling_in_health_check(self, cache_manager):
        """Test error handling in health check."""
        with patch.object(
            cache_manager.health_service,
            "perform_comprehensive_health_check",
            side_effect=Exception("Health check failed"),
        ) as mock_health:
            result = await cache_manager.health_check()

            mock_health.assert_called_once()
            assert result["status"] == "unhealthy"
            assert "error" in result

    @pytest.mark.asyncio
    async def test_error_handling_in_cache_project_data(
        self, cache_manager, sample_project_data
    ):
        """Test error handling in cache project data."""
        project_id = uuid4()

        with patch.object(
            cache_manager.repository.project_cache,
            "save",
            side_effect=Exception("Save failed"),
        ) as mock_save:
            result = await cache_manager.cache_project_data(
                project_id, sample_project_data
            )

            mock_save.assert_called_once()
            assert result is False

    @pytest.mark.asyncio
    async def test_error_handling_in_check_rate_limit(self, cache_manager):
        """Test error handling in check rate limit with different exception types."""
        identifier = "user123"
        config = RateLimitConfig(requests_per_window=100, window_seconds=3600)

        # Test with different exception types to ensure fail-open behavior
        for exception in [
            ConnectionError("Connection failed"),
            TimeoutError("Timeout"),
            ValueError("Invalid data"),
        ]:
            with patch.object(
                cache_manager.rate_limit_service,
                "check_rate_limit",
                side_effect=exception,
            ) as mock_check:
                result = await cache_manager.check_rate_limit(
                    "user", identifier, config
                )

                mock_check.assert_called_once()
                # Should always fail open regardless of exception type
                assert result["allowed"] is True
                assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__])
