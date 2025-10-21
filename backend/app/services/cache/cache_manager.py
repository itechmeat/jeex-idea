"""
Cache Manager Service

High-level cache management service that orchestrates domain entities,
repositories, and services for cache operations.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from uuid import UUID

from opentelemetry import trace

from ...constants import SYSTEM_PROJECT_ID

from ...domain.cache.entities import ProjectCache, UserSession, Progress
from ...domain.cache.value_objects import (
    CacheKey,
    TTL,
    CacheTag,
    RateLimitWindow,
    CacheMetrics,
    RateLimitConfig,
)
from ...domain.cache.domain_services import (
    CacheInvalidationService,
    SessionManagementService,
    RateLimitingService,
    CacheHealthService,
)
from ...infrastructure.repositories.cache_repository import cache_repository
from ...infrastructure.redis.exceptions import RedisException
from ...infrastructure.redis.redis_service import redis_service

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class CacheManager:
    """
    High-level cache management service.

    Provides unified interface for all cache operations including
    project data caching, user sessions, rate limiting, and progress tracking.
    """

    def __init__(self):
        self.repository = cache_repository
        # Initialize services with actual repository instances
        project_cache_repo = self.repository.project_cache
        user_session_repo = self.repository.user_session
        progress_repo = self.repository.progress
        rate_limit_repo = self.repository.rate_limit
        health_repo = self.repository.health

        self.invalidation_service = CacheInvalidationService(
            project_cache_repo,
            user_session_repo,
            progress_repo,
        )
        self.session_service = SessionManagementService(
            user_session_repo, project_cache_repo
        )
        self.rate_limit_service = RateLimitingService(rate_limit_repo)
        self.health_service = CacheHealthService(health_repo)

    async def initialize(self) -> None:
        """Initialize cache manager and underlying connections."""
        try:
            await self.repository.initialize()
            logger.info("Cache manager initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize cache manager: {e}")
            raise

    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        with tracer.start_as_current_span("cache_manager.health_check") as span:
            try:
                health_status = (
                    await self.health_service.perform_comprehensive_health_check()
                )

                # Add cache manager specific information
                health_status.update(
                    {
                        "cache_manager": {
                            "initialized": True,
                            "services": {
                                "invalidation": "active",
                                "session_management": "active",
                                "rate_limiting": "active",
                                "health_monitoring": "active",
                            },
                            "repositories": {
                                "project_cache": "active",
                                "user_session": "active",
                                "task_queue": "active",
                                "progress": "active",
                                "rate_limit": "active",
                                "health": "active",
                            },
                        }
                    }
                )

                return health_status

            except Exception as e:
                logger.error(f"Cache manager health check failed: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

                return {
                    "status": "unhealthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "cache_manager": {"initialized": False, "error": str(e)},
                }

    # Project Cache Operations

    async def cache_project_data(
        self,
        project_id: UUID,
        data: Dict[str, Any],
        ttl: Optional[TTL] = None,
        tags: Optional[List[CacheTag]] = None,
    ) -> bool:
        """
        Cache project data with optional TTL and tags.

        Args:
            project_id: Project ID
            data: Project data to cache
            ttl: Time to live (uses default project TTL if not provided)
            tags: Additional cache tags

        Returns:
            True if data was cached successfully
        """
        with tracer.start_as_current_span("cache_manager.cache_project_data") as span:
            span.set_attribute("project_id", str(project_id))
            span.set_attribute("data_size", len(str(data)))

            try:
                cache_ttl = ttl or TTL.project_data()
                cache = ProjectCache.create(project_id, data, cache_ttl)

                # Add custom tags
                if tags:
                    for tag in tags:
                        cache.add_tag(tag)

                await self.repository.project_cache.save(cache)

                logger.debug(
                    f"Cached project data for {project_id}",
                    extra={"project_id": str(project_id), "ttl": cache_ttl.seconds},
                )

                return True

            except Exception as e:
                logger.error(f"Failed to cache project data for {project_id}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                return False

    async def get_project_data(self, project_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get cached project data.

        Args:
            project_id: Project ID

        Returns:
            Cached project data or None if not found/expired
        """
        with tracer.start_as_current_span("cache_manager.get_project_data") as span:
            span.set_attribute("project_id", str(project_id))

            try:
                cache = await self.repository.project_cache.find_by_project_id(
                    project_id
                )

                if cache:
                    span.set_attribute("cache_hit", True)
                    span.set_attribute("cache_version", cache.version.value)
                    return cache.data
                else:
                    span.set_attribute("cache_hit", False)
                    return None

            except Exception as e:
                logger.error(f"Failed to get cached project data for {project_id}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                return None

    async def invalidate_project_cache(
        self, project_id: UUID, reason: str = "manual"
    ) -> int:
        """
        Invalidate all cache entries for a project.

        Args:
            project_id: Project ID to invalidate
            reason: Reason for invalidation

        Returns:
            Number of cache entries invalidated
        """
        with tracer.start_as_current_span(
            "cache_manager.invalidate_project_cache"
        ) as span:
            span.set_attribute("project_id", str(project_id))
            span.set_attribute("reason", reason)

            try:
                count = await self.invalidation_service.invalidate_project_caches(
                    project_id, reason
                )

                logger.info(
                    f"Invalidated {count} cache entries for project {project_id}",
                    extra={
                        "project_id": str(project_id),
                        "count": count,
                        "reason": reason,
                    },
                )

                return count

            except Exception as e:
                logger.error(
                    f"Failed to invalidate project cache for {project_id}: {e}"
                )
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                return 0

    async def cache_project_context(
        self, project_id: UUID, context: Dict[str, Any], ttl: Optional[TTL] = None
    ) -> bool:
        """
        Cache project context data.

        Args:
            project_id: Project ID
            context: Project context data
            ttl: Time to live

        Returns:
            True if context was cached successfully
        """
        try:
            # Use project cache with context-specific key pattern
            cache_ttl = ttl or TTL.project_data()
            key = CacheKey.project_context(project_id)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                context_data = {
                    "project_id": str(project_id),
                    "context": context,
                    "created_at": datetime.utcnow().isoformat(),
                    "expires_at": (
                        datetime.utcnow() + timedelta(seconds=cache_ttl.seconds)
                    ).isoformat(),
                }

                await redis_client.setex(
                    key.value, cache_ttl.seconds, json.dumps(context_data, default=str)
                )

            return True

        except Exception as e:
            logger.error(f"Failed to cache project context for {project_id}: {e}")
            return False

    async def get_project_context(self, project_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get cached project context.

        Args:
            project_id: Project ID

        Returns:
            Cached project context or None if not found/expired
        """
        try:
            key = CacheKey.project_context(project_id)

            async with redis_service.get_connection(str(project_id)) as redis_client:
                context_data = await redis_client.get(key.value)

                if context_data:
                    data = json.loads(context_data)
                    return data.get("context")

            return None

        except Exception as e:
            logger.error(f"Failed to get cached project context for {project_id}: {e}")
            return None

    # User Session Operations

    async def create_user_session(
        self,
        user_id: UUID,
        user_data: Dict[str, Any],
        project_access: Optional[List[UUID]] = None,
        ttl: Optional[TTL] = None,
    ) -> Optional[UserSession]:
        """
        Create new user session.

        Args:
            user_id: User ID
            user_data: User session data
            project_access: List of projects user can access
            ttl: Session TTL

        Returns:
            Created session or None if failed
        """
        with tracer.start_as_current_span("cache_manager.create_user_session") as span:
            span.set_attribute("user_id", str(user_id))
            span.set_attribute("project_count", len(project_access or []))

            try:
                session = await self.session_service.create_session(
                    user_id=user_id,
                    user_data=user_data,
                    project_access=project_access,
                    ttl=ttl,
                )

                return session

            except Exception as e:
                logger.error(f"Failed to create user session for {user_id}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                return None

    async def validate_user_session(self, session_id: UUID) -> Optional[UserSession]:
        """
        Validate and return user session.

        Args:
            session_id: Session ID to validate

        Returns:
            Valid session or None if invalid/not found
        """
        with tracer.start_as_current_span(
            "cache_manager.validate_user_session"
        ) as span:
            span.set_attribute("session_id", str(session_id))

            try:
                session = await self.session_service.validate_session(session_id)
                return session

            except Exception as e:
                logger.error(f"Failed to validate user session {session_id}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                return None

    async def revoke_user_session(
        self, session_id: UUID, reason: str = "logout"
    ) -> bool:
        """
        Revoke user session.

        Args:
            session_id: Session ID to revoke
            reason: Reason for revocation

        Returns:
            True if session was revoked
        """
        with tracer.start_as_current_span("cache_manager.revoke_user_session") as span:
            span.set_attribute("session_id", str(session_id))
            span.set_attribute("reason", reason)

            try:
                return await self.session_service.revoke_session(session_id, reason)

            except Exception as e:
                logger.error(f"Failed to revoke user session {session_id}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                return False

    async def grant_project_access(self, session_id: UUID, project_id: UUID) -> bool:
        """
        Grant project access to user session.

        Args:
            session_id: Session ID
            project_id: Project ID to grant access to

        Returns:
            True if access was granted
        """
        try:
            return await self.session_service.grant_project_access(
                session_id, project_id
            )

        except Exception as e:
            logger.error(f"Failed to grant project access to session {session_id}: {e}")
            return False

    # Rate Limiting Operations

    async def check_rate_limit(
        self, identifier: str, limit_type: str, config: RateLimitConfig
    ) -> Dict[str, Any]:
        """
        Check rate limit for identifier.

        Args:
            identifier: Rate limit identifier (user ID, IP, etc.)
            limit_type: Type of rate limit (user, project, ip)
            config: Rate limit configuration

        Returns:
            Rate limit check result
        """
        with tracer.start_as_current_span("cache_manager.check_rate_limit") as span:
            span.set_attribute("identifier", identifier)
            span.set_attribute("limit_type", limit_type)
            span.set_attribute("limit", config.requests_per_window)

            try:
                result = await self.rate_limit_service.check_rate_limit(
                    identifier, limit_type, config
                )

                if not result["allowed"]:
                    logger.warning(
                        f"Rate limit exceeded for {limit_type}:{identifier}",
                        extra=result,
                    )

                return result

            except Exception as e:
                logger.error(f"Failed to check rate limit for {identifier}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

                # Fail open - allow request if rate limiting fails
                return {
                    "allowed": True,
                    "current_count": 0,
                    "remaining_requests": config.requests_per_window,
                    "reset_seconds": config.window_seconds,
                    "limit": config.requests_per_window,
                    "window": config.window_seconds,
                    "identifier": identifier,
                    "limit_type": limit_type,
                    "error": "Rate limiting service unavailable",
                }

    async def get_rate_limit_status(
        self, identifier: str, limit_type: str, window: RateLimitWindow, limit: int
    ) -> Dict[str, Any]:
        """
        Get current rate limit status without incrementing.

        Args:
            identifier: Rate limit identifier
            limit_type: Type of rate limit
            window: Time window
            limit: Rate limit threshold

        Returns:
            Current rate limit status
        """
        try:
            return await self.rate_limit_service.get_rate_limit_status(
                identifier, limit_type, window, limit
            )

        except Exception as e:
            logger.error(f"Failed to get rate limit status for {identifier}: {e}")
            return {
                "current_count": 0,
                "remaining_requests": limit,
                "reset_seconds": 0,
                "limit": limit,
                "window": window.value,
                "identifier": identifier,
                "limit_type": limit_type,
                "allowed": True,
                "error": "Rate limiting service unavailable",
            }

    # Progress Tracking Operations

    async def start_progress_tracking(
        self, correlation_id: UUID, total_steps: int
    ) -> bool:
        """
        Start progress tracking for operation.

        Args:
            correlation_id: Operation correlation ID
            total_steps: Total number of steps

        Returns:
            True if progress tracking started successfully
        """
        try:
            progress = Progress.create(correlation_id, total_steps)
            await self.repository.progress.save(progress)

            logger.debug(f"Started progress tracking for {correlation_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to start progress tracking for {correlation_id}: {e}")
            return False

    async def update_progress(
        self, correlation_id: UUID, step: int, message: str
    ) -> bool:
        """
        Update progress for operation.

        Args:
            correlation_id: Operation correlation ID
            step: Current step number
            message: Progress message

        Returns:
            True if progress updated successfully
        """
        try:
            return await self.repository.progress.update_progress(
                correlation_id, step, message
            )

        except Exception as e:
            logger.error(f"Failed to update progress for {correlation_id}: {e}")
            return False

    async def increment_progress(self, correlation_id: UUID, message: str) -> bool:
        """
        Increment progress by one step.

        Args:
            correlation_id: Operation correlation ID
            message: Progress message

        Returns:
            True if progress updated successfully
        """
        try:
            progress = await self.repository.progress.find_by_correlation_id(
                correlation_id
            )
            if progress:
                return await self.repository.progress.update_progress(
                    correlation_id, progress.current_step + 1, message
                )
            return False

        except Exception as e:
            logger.error(f"Failed to increment progress for {correlation_id}: {e}")
            return False

    async def complete_progress(
        self, correlation_id: UUID, message: str = "Operation completed"
    ) -> bool:
        """
        Mark progress as completed.

        Args:
            correlation_id: Operation correlation ID
            message: Completion message

        Returns:
            True if progress completed successfully
        """
        try:
            return await self.repository.progress.complete_progress(
                correlation_id, message
            )

        except Exception as e:
            logger.error(f"Failed to complete progress for {correlation_id}: {e}")
            return False

    async def fail_progress(self, correlation_id: UUID, error_message: str) -> bool:
        """
        Mark progress as failed.

        Args:
            correlation_id: Operation correlation ID
            error_message: Error message

        Returns:
            True if progress marked as failed
        """
        try:
            return await self.repository.progress.fail_progress(
                correlation_id, error_message
            )

        except Exception as e:
            logger.error(f"Failed to fail progress for {correlation_id}: {e}")
            return False

    async def get_progress(self, correlation_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get current progress for operation.

        Args:
            correlation_id: Operation correlation ID

        Returns:
            Progress data or None if not found
        """
        try:
            progress = await self.repository.progress.find_by_correlation_id(
                correlation_id
            )

            if progress:
                return {
                    "correlation_id": str(progress.correlation_id),
                    "total_steps": progress.total_steps,
                    "current_step": progress.current_step,
                    "message": progress.message,
                    "percentage": progress.get_progress_percentage(),
                    "started_at": progress.started_at.isoformat(),
                    "updated_at": progress.updated_at.isoformat(),
                    "completed_at": progress.completed_at.isoformat()
                    if progress.completed_at
                    else None,
                    "is_completed": progress.is_completed(),
                    "is_failed": progress.is_failed(),
                    "is_active": progress.is_active(),
                    "error_message": progress.error_message,
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get progress for {correlation_id}: {e}")
            return None

    # Maintenance and Cleanup Operations

    async def cleanup_expired_entries(self, max_age_hours: int = 24) -> Dict[str, int]:
        """
        Clean up expired cache entries.

        Args:
            max_age_hours: Maximum age for cleanup

        Returns:
            Dictionary with cleanup counts by type
        """
        with tracer.start_as_current_span("cache_manager.cleanup_expired") as span:
            span.set_attribute("max_age_hours", max_age_hours)

            try:
                cleanup_counts = (
                    await self.invalidation_service.cleanup_expired_entries(
                        max_age_hours
                    )
                )

                total_cleaned = sum(cleanup_counts.values())
                logger.info(
                    f"Cleaned up {total_cleaned} expired cache entries",
                    extra=cleanup_counts,
                )

                span.set_attribute("total_cleaned", total_cleaned)
                return cleanup_counts

            except Exception as e:
                logger.error(f"Failed to cleanup expired cache entries: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                return {}

    async def get_cache_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive cache statistics.

        Returns:
            Cache statistics including memory, operations, and distributions
        """
        try:
            return await self.repository.get_metrics()

        except Exception as e:
            logger.error(f"Failed to get cache statistics: {e}")
            return {"timestamp": datetime.utcnow().isoformat(), "error": str(e)}

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for monitoring.

        Returns:
            Performance metrics including slow operations and memory usage
        """
        try:
            return await self.health_service.get_performance_metrics()

        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return {"timestamp": datetime.utcnow().isoformat(), "error": str(e)}

    # Utility Operations

    async def cache_agent_config(
        self, agent_type: str, config: Dict[str, Any], ttl: Optional[TTL] = None
    ) -> bool:
        """
        Cache agent configuration.

        Args:
            agent_type: Type of agent
            config: Agent configuration
            ttl: Time to live

        Returns:
            True if config was cached successfully
        """
        try:
            cache_ttl = ttl or TTL.hours(1)  # Default 1 hour for agent configs
            key = CacheKey.agent_config(agent_type)

            config_data = {
                "agent_type": agent_type,
                "config": config,
                "cached_at": datetime.utcnow().isoformat(),
                "ttl": cache_ttl.seconds,
            }

            async with redis_service.get_connection(
                str(SYSTEM_PROJECT_ID)
            ) as redis_client:
                await redis_client.setex(
                    key.value, cache_ttl.seconds, json.dumps(config_data, default=str)
                )

            logger.debug(f"Cached agent config for {agent_type}")
            return True

        except Exception as e:
            logger.error(f"Failed to cache agent config for {agent_type}: {e}")
            return False

    async def get_agent_config(self, agent_type: str) -> Optional[Dict[str, Any]]:
        """
        Get cached agent configuration.

        Args:
            agent_type: Type of agent

        Returns:
            Cached agent configuration or None if not found
        """
        try:
            key = CacheKey.agent_config(agent_type)

            async with redis_service.get_connection(
                str(SYSTEM_PROJECT_ID)
            ) as redis_client:
                config_data = await redis_client.get(key.value)

                if config_data:
                    data = json.loads(config_data)
                    return data.get("config")

            return None

        except Exception as e:
            logger.error(f"Failed to get cached agent config for {agent_type}: {e}")
            return None

    async def close(self) -> None:
        """Close cache manager and cleanup resources."""
        try:
            await self.repository.close()
            logger.info("Cache manager closed successfully")

        except Exception as e:
            logger.error(f"Failed to close cache manager: {e}")


# Global cache manager instance
cache_manager = CacheManager()
