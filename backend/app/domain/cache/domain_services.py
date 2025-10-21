"""
Cache Domain Services

Business logic services for cache domain operations.
Orchestrates domain entities and repositories to implement business use cases.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Set
from uuid import UUID

from ..cache.entities import ProjectCache, UserSession, Progress, RateLimit, QueuedTask
from ..cache.value_objects import (
    CacheKey,
    TTL,
    CacheTag,
    RateLimitWindow,
    CacheMetrics,
    RateLimitConfig,
)
from ..cache.repository_interfaces import (
    ProjectCacheRepository,
    UserSessionRepository,
    ProgressRepository,
    RateLimitRepository,
    CacheHealthRepository,
)
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class CacheInvalidationService:
    """
    Domain service for cache invalidation strategies.

    Implements business logic for intelligent cache invalidation.
    """

    def __init__(
        self,
        project_cache_repo: ProjectCacheRepository,
        user_session_repo: UserSessionRepository,
        progress_repo: ProgressRepository,
    ):
        self.project_cache_repo = project_cache_repo
        self.user_session_repo = user_session_repo
        self.progress_repo = progress_repo

    async def invalidate_project_caches(
        self, project_id: UUID, reason: str = "project_update"
    ) -> int:
        """
        Invalidate all caches related to a project.

        Args:
            project_id: Project ID to invalidate caches for
            reason: Reason for invalidation (for logging)

        Returns:
            Number of cache entries invalidated
        """
        with tracer.start_as_current_span("cache.invalidate_project") as span:
            span.set_attribute("project_id", str(project_id))
            span.set_attribute("reason", reason)

            invalidated_count = 0

            try:
                # Invalidate project data cache
                invalidated_count += (
                    await self.project_cache_repo.invalidate_by_project_id(project_id)
                )

                # Invalidate by project tag
                project_tag = CacheTag.project(project_id)
                invalidated_count += await self.project_cache_repo.invalidate_by_tag(
                    project_tag
                )

                # Invalidate user sessions that have access to this project
                sessions = await self.user_session_repo.find_active_by_user_id(
                    UUID(int=0)
                )  # Would need user_id
                for session in sessions:
                    if session.has_project_access(project_id):
                        await self.user_session_repo.delete(session.session_id)
                        invalidated_count += 1

                # Invalidate related progress trackers
                progress_entries = await self.progress_repo.find_expired(
                    max_age_hours=24
                )
                for progress in progress_entries:
                    # Check if progress is related to project (would need correlation data)
                    await self.progress_repo.delete(progress.correlation_id)
                    invalidated_count += 1

                span.set_attribute("invalidated_count", invalidated_count)
                logger.info(
                    f"Invalidated {invalidated_count} cache entries for project {project_id}",
                    extra={
                        "project_id": str(project_id),
                        "reason": reason,
                        "count": invalidated_count,
                    },
                )

                return invalidated_count

            except Exception as e:
                logger.error(
                    f"Failed to invalidate caches for project {project_id}: {e}"
                )
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def invalidate_by_tags(
        self, tags: List[CacheTag], reason: str = "tag_invalidation"
    ) -> int:
        """
        Invalidate caches by multiple tags.

        Args:
            tags: List of cache tags to invalidate
            reason: Reason for invalidation

        Returns:
            Number of cache entries invalidated
        """
        with tracer.start_as_current_span("cache.invalidate_by_tags") as span:
            span.set_attribute("tag_count", len(tags))
            span.set_attribute("reason", reason)

            invalidated_count = 0

            try:
                for tag in tags:
                    count = await self.project_cache_repo.invalidate_by_tag(tag)
                    invalidated_count += count

                span.set_attribute("invalidated_count", invalidated_count)
                logger.info(
                    f"Invalidated {invalidated_count} cache entries by tags",
                    extra={
                        "tags": [str(tag) for tag in tags],
                        "count": invalidated_count,
                    },
                )

                return invalidated_count

            except Exception as e:
                logger.error(f"Failed to invalidate caches by tags: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def cleanup_expired_entries(self, max_age_hours: int = 24) -> Dict[str, int]:
        """
        Clean up expired cache entries.

        Args:
            max_age_hours: Maximum age for cleanup

        Returns:
            Dictionary with cleanup counts by type
        """
        with tracer.start_as_current_span("cache.cleanup_expired") as span:
            span.set_attribute("max_age_hours", max_age_hours)

            cleanup_counts = {
                "project_caches": 0,
                "user_sessions": 0,
                "progress_trackers": 0,
            }

            try:
                # Clean up expired project caches
                expired_caches = await self.project_cache_repo.find_expired()
                for cache in expired_caches:
                    await self.project_cache_repo.delete(cache.get_key())
                    cleanup_counts["project_caches"] += 1

                # Clean up expired user sessions
                cleanup_counts[
                    "user_sessions"
                ] = await self.user_session_repo.cleanup_expired()

                # Clean up expired progress trackers
                cleanup_counts[
                    "progress_trackers"
                ] = await self.progress_repo.cleanup_expired(max_age_hours)

                total_cleaned = sum(cleanup_counts.values())
                span.set_attribute("total_cleaned", total_cleaned)
                span.set_attributes(
                    {f"cleaned_{k}": v for k, v in cleanup_counts.items()}
                )

                logger.info(
                    f"Cleaned up {total_cleaned} expired cache entries",
                    extra=cleanup_counts,
                )

                return cleanup_counts

            except Exception as e:
                logger.error(f"Failed to cleanup expired cache entries: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise


class SessionManagementService:
    """
    Domain service for user session management.

    Implements business logic for session lifecycle and security.
    """

    def __init__(
        self,
        session_repo: UserSessionRepository,
        project_cache_repo: ProjectCacheRepository,
        default_ttl: TTL = TTL.user_session(),
    ):
        self.session_repo = session_repo
        self.project_cache_repo = project_cache_repo
        self.default_ttl = default_ttl

    async def create_session(
        self,
        user_id: UUID,
        user_data: Dict[str, Any],
        project_access: Optional[List[UUID]] = None,
        ttl: Optional[TTL] = None,
    ) -> UserSession:
        """
        Create new user session.

        Args:
            user_id: User ID
            user_data: User session data
            project_access: List of projects user can access
            ttl: Session TTL (uses default if not provided)

        Returns:
            Created session entity
        """
        with tracer.start_as_current_span("session.create") as span:
            span.set_attribute("user_id", str(user_id))
            span.set_attribute("project_count", len(project_access or []))

            try:
                # Invalidate existing sessions for user (single session policy)
                await self.session_repo.invalidate_all_for_user(user_id)

                # Create new session
                session = UserSession.create(
                    user_id=user_id,
                    user_data=user_data,
                    project_access=project_access or [],
                    ttl=ttl or self.default_ttl,
                )

                # Save session
                await self.session_repo.save(session)

                span.set_attribute("session_id", str(session.session_id))
                logger.info(
                    f"Created new session for user {user_id}",
                    extra={
                        "user_id": str(user_id),
                        "session_id": str(session.session_id),
                        "project_count": len(session.project_access),
                    },
                )

                return session

            except Exception as e:
                logger.error(f"Failed to create session for user {user_id}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def validate_session(self, session_id: UUID) -> Optional[UserSession]:
        """
        Validate and update session.

        Args:
            session_id: Session ID to validate

        Returns:
            Valid session or None if invalid
        """
        with tracer.start_as_current_span("session.validate") as span:
            span.set_attribute("session_id", str(session_id))

            try:
                session = await self.session_repo.find_by_session_id(session_id)

                if not session:
                    logger.warning(f"Session not found: {session_id}")
                    return None

                if not session.is_valid():
                    logger.warning(f"Session invalid: {session_id}")
                    # Clean up invalid session
                    await self.session_repo.delete(session_id)
                    return None

                # Update activity and extend TTL
                session.update_activity()
                session.extend_session(self.default_ttl)
                await self.session_repo.save(session)

                span.set_attribute("user_id", str(session.user_id))
                span.set_attribute("activity_count", session.access_count)

                return session

            except Exception as e:
                logger.error(f"Failed to validate session {session_id}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def revoke_session(self, session_id: UUID, reason: str = "logout") -> bool:
        """
        Revoke user session.

        Args:
            session_id: Session ID to revoke
            reason: Reason for revocation

        Returns:
            True if session was revoked
        """
        with tracer.start_as_current_span("session.revoke") as span:
            span.set_attribute("session_id", str(session_id))
            span.set_attribute("reason", reason)

            try:
                session = await self.session_repo.find_by_session_id(session_id)

                if not session:
                    return False

                session.invalidate()
                await self.session_repo.save(session)

                logger.info(
                    f"Revoked session {session_id} for user {session.user_id}",
                    extra={
                        "session_id": str(session_id),
                        "user_id": str(session.user_id),
                        "reason": reason,
                    },
                )

                return True

            except Exception as e:
                logger.error(f"Failed to revoke session {session_id}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def revoke_all_user_sessions(
        self, user_id: UUID, reason: str = "security"
    ) -> int:
        """
        Revoke all sessions for a user.

        Args:
            user_id: User ID
            reason: Reason for revocation

        Returns:
            Number of sessions revoked
        """
        with tracer.start_as_current_span("session.revoke_all_user") as span:
            span.set_attribute("user_id", str(user_id))
            span.set_attribute("reason", reason)

            try:
                count = await self.session_repo.invalidate_all_for_user(user_id)

                logger.info(
                    f"Revoked {count} sessions for user {user_id}",
                    extra={"user_id": str(user_id), "count": count, "reason": reason},
                )

                span.set_attribute("revoked_count", count)
                return count

            except Exception as e:
                logger.error(f"Failed to revoke all sessions for user {user_id}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def grant_project_access(self, session_id: UUID, project_id: UUID) -> bool:
        """
        Grant project access to session.

        Args:
            session_id: Session ID
            project_id: Project ID to grant access to

        Returns:
            True if access was granted
        """
        with tracer.start_as_current_span("session.grant_project_access") as span:
            span.set_attribute("session_id", str(session_id))
            span.set_attribute("project_id", str(project_id))

            try:
                session = await self.session_repo.find_by_session_id(session_id)

                if not session or not session.is_valid():
                    return False

                session.grant_project_access(project_id)
                await self.session_repo.save(session)

                logger.info(
                    f"Granted project access to session {session_id}",
                    extra={
                        "session_id": str(session_id),
                        "user_id": str(session.user_id),
                        "project_id": str(project_id),
                    },
                )

                return True

            except Exception as e:
                logger.error(
                    f"Failed to grant project access to session {session_id}: {e}"
                )
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise


class RateLimitingService:
    """
    Domain service for rate limiting operations.

    Implements business logic for rate limiting strategies.
    """

    def __init__(self, rate_limit_repo: RateLimitRepository):
        self.rate_limit_repo = rate_limit_repo

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
        with tracer.start_as_current_span("rate_limit.check") as span:
            span.set_attribute("identifier", identifier)
            span.set_attribute("limit_type", limit_type)
            span.set_attribute("limit", config.requests_per_window)
            span.set_attribute("window", config.window_seconds)

            try:
                # Check and increment rate limit
                allowed = await self.rate_limit_repo.check_and_increment(
                    identifier=identifier,
                    limit_type=limit_type,
                    window=config.window,
                    limit=config.requests_per_window,
                )

                # Get current state
                current_count = await self.rate_limit_repo.get_current_count(
                    identifier, limit_type, config.window
                )
                remaining = await self.rate_limit_repo.get_remaining_requests(
                    identifier, limit_type, config.window, config.requests_per_window
                )
                reset_time = await self.rate_limit_repo.get_reset_time(
                    identifier, limit_type, config.window
                )
                reset_seconds = 0

                if reset_time:
                    reset_seconds = max(
                        0, int((reset_time - datetime.utcnow()).total_seconds())
                    )

                result = {
                    "allowed": allowed,
                    "current_count": current_count,
                    "remaining_requests": remaining,
                    "reset_seconds": reset_seconds,
                    "reset_time": reset_time.isoformat() if reset_time else None,
                    "limit": config.requests_per_window,
                    "window": config.window_seconds,
                    "identifier": identifier,
                    "limit_type": limit_type,
                }

                span.set_attribute("allowed", allowed)
                span.set_attribute("current_count", current_count)
                span.set_attribute("remaining", remaining)

                if not allowed:
                    logger.warning(
                        f"Rate limit exceeded for {limit_type}:{identifier}",
                        extra=result,
                    )

                return result

            except Exception as e:
                logger.error(f"Failed to check rate limit for {identifier}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def reset_rate_limit(
        self, identifier: str, limit_type: str, window: RateLimitWindow
    ) -> bool:
        """
        Reset rate limit for identifier.

        Args:
            identifier: Rate limit identifier
            limit_type: Type of rate limit
            window: Time window

        Returns:
            True if rate limit was reset
        """
        with tracer.start_as_current_span("rate_limit.reset") as span:
            span.set_attribute("identifier", identifier)
            span.set_attribute("limit_type", limit_type)
            span.set_attribute("window", window.value)

            try:
                success = await self.rate_limit_repo.reset_window(
                    identifier, limit_type, window
                )

                if success:
                    logger.info(
                        f"Reset rate limit for {limit_type}:{identifier}:{window.value}",
                        extra={
                            "identifier": identifier,
                            "limit_type": limit_type,
                            "window": window.value,
                        },
                    )

                span.set_attribute("success", success)
                return success

            except Exception as e:
                logger.error(f"Failed to reset rate limit for {identifier}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

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
        with tracer.start_as_current_span("rate_limit.status") as span:
            span.set_attribute("identifier", identifier)
            span.set_attribute("limit_type", limit_type)
            span.set_attribute("window", window.value)

            try:
                current_count = await self.rate_limit_repo.get_current_count(
                    identifier, limit_type, window
                )
                remaining = await self.rate_limit_repo.get_remaining_requests(
                    identifier, limit_type, window, limit
                )
                reset_time = await self.rate_limit_repo.get_reset_time(
                    identifier, limit_type, window
                )
                reset_seconds = 0

                if reset_time:
                    reset_seconds = max(
                        0, int((reset_time - datetime.utcnow()).total_seconds())
                    )

                status = {
                    "current_count": current_count,
                    "remaining_requests": remaining,
                    "reset_seconds": reset_seconds,
                    "reset_time": reset_time.isoformat() if reset_time else None,
                    "limit": limit,
                    "window": window.value,
                    "identifier": identifier,
                    "limit_type": limit_type,
                    "allowed": current_count < limit,
                }

                span.set_attribute("current_count", current_count)
                span.set_attribute("remaining", remaining)
                span.set_attribute("allowed", status["allowed"])

                return status

            except Exception as e:
                logger.error(f"Failed to get rate limit status for {identifier}: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise


class CacheHealthService:
    """
    Domain service for cache health monitoring.

    Implements business logic for health checks and metrics.
    """

    def __init__(self, health_repo: CacheHealthRepository):
        self.health_repo = health_repo

    async def perform_comprehensive_health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive cache health check.

        Returns:
            Detailed health status
        """
        with tracer.start_as_current_span("cache.health_check") as span:
            try:
                # Get individual health components
                memory_usage = await self.health_repo.get_memory_usage()
                connection_info = await self.health_repo.get_connection_info()
                operation_stats = await self.health_repo.get_operation_stats()
                basic_health = await self.health_repo.perform_health_check()
                key_distribution = await self.health_repo.get_key_distribution()

                # Determine overall health status
                overall_status = "healthy"
                issues = []

                # Check memory usage
                memory_percentage = memory_usage.get("usage_percentage", 0)
                if memory_percentage > 90:
                    overall_status = "critical"
                    issues.append(f"High memory usage: {memory_percentage:.1f}%")
                elif memory_percentage > 80:
                    overall_status = "warning"
                    issues.append(f"Elevated memory usage: {memory_percentage:.1f}%")

                # Check connection health
                if connection_info.get("status") != "healthy":
                    overall_status = "unhealthy"
                    issues.append("Connection issues detected")

                # Check basic health
                if basic_health.get("status") != "healthy":
                    overall_status = "unhealthy"
                    issues.append("Basic health check failed")

                # Combine results
                health_status = {
                    "status": overall_status,
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "cache",
                    "issues": issues,
                    "memory": memory_usage,
                    "connections": connection_info,
                    "operations": operation_stats,
                    "key_distribution": key_distribution,
                    "basic_health": basic_health,
                }

                span.set_attribute("status", overall_status)
                span.set_attribute("issue_count", len(issues))

                if overall_status != "healthy":
                    logger.warning(
                        f"Cache health check returned {overall_status}",
                        extra={"status": overall_status, "issues": issues},
                    )

                return health_status

            except Exception as e:
                logger.error(f"Failed to perform cache health check: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

                return {
                    "status": "unhealthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "cache",
                    "error": str(e),
                }

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for cache operations.

        Returns:
            Performance metrics
        """
        with tracer.start_as_current_span("cache.performance_metrics") as span:
            try:
                # Get slow operations
                slow_operations = await self.health_repo.get_slow_operations(
                    threshold_ms=100.0
                )

                # Get operation statistics
                operation_stats = await self.health_repo.get_operation_stats()

                # Get memory usage
                memory_usage = await self.health_repo.get_memory_usage()

                # Get key distribution
                key_distribution = await self.health_repo.get_key_distribution()

                # Calculate performance metrics
                metrics = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "slow_operations": {
                        "count": len(slow_operations),
                        "operations": slow_operations[:10],  # Top 10 slowest
                    },
                    "operation_stats": operation_stats,
                    "memory_usage": memory_usage,
                    "key_distribution": key_distribution,
                    "performance_indicators": {
                        "slow_operation_count": len(slow_operations),
                        "memory_usage_percentage": memory_usage.get(
                            "usage_percentage", 0
                        ),
                        "total_keys": sum(key_distribution.values()),
                        "key_pattern_diversity": len(key_distribution),
                    },
                }

                span.set_attribute("slow_operation_count", len(slow_operations))
                span.set_attribute(
                    "memory_percentage", memory_usage.get("usage_percentage", 0)
                )

                return metrics

            except Exception as e:
                logger.error(f"Failed to get cache performance metrics: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise
