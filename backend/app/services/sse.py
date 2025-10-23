"""
Server-Sent Events (SSE) Streaming Service (REQ-006)

Implements basic SSE streaming for long-running operations with:
- Redis pub/sub for event distribution
- Project isolation (all events scoped to project_id)
- Keepalive to prevent connection timeouts
- Graceful connection cleanup

Variant C: Basic implementation without advanced backpressure handling.
"""

import asyncio
import json
from typing import AsyncGenerator, Optional
from uuid import UUID
import structlog

from redis.asyncio import Redis
from app.infrastructure.redis.connection_factory import redis_connection_factory

logger = structlog.get_logger()


class SSEService:
    """
    Basic Server-Sent Events streaming service (Variant C - no advanced backpressure).

    Uses Redis pub/sub for event distribution with project isolation.

    SECURITY:
    - All events MUST be scoped to project_id (SEC-002)
    - Channel names include project_id to prevent cross-project leaks

    ZERO TOLERANCE:
    - project_id is ALWAYS required (UUID, never Optional)
    - operation_id is ALWAYS required for tracking
    """

    def __init__(self, redis: Redis):
        """
        Initialize SSE service.

        Args:
            redis: Redis client (REQUIRED)

        Raises:
            TypeError: If redis is not Redis instance (zero tolerance)
        """
        # CRITICAL: Fail fast with explicit validation (zero tolerance rule)
        if not isinstance(redis, Redis):
            raise TypeError(f"redis must be Redis instance, got {type(redis).__name__}")

        self._redis = redis
        self.connection_timeout = 300  # 5 minutes
        self.keepalive_interval = 30  # 30 seconds

    async def _get_redis(self) -> Redis:
        """
        Get Redis client instance.

        Returns:
            Redis client (no fallback - explicit dependency)
        """
        return self._redis

    async def stream_progress(
        self, project_id: UUID, operation_id: str
    ) -> AsyncGenerator[str, None]:
        """
        Stream progress events for long-running operation.

        Yields SSE formatted events. Connection automatically closes after
        timeout or when operation completes.

        Args:
            project_id: Project UUID for isolation (REQUIRED)
            operation_id: Operation identifier for tracking (REQUIRED)

        Yields:
            SSE formatted event strings

        Raises:
            ValueError: If project_id or operation_id is None (zero tolerance)
        """
        if project_id is None:
            raise ValueError("project_id is required (cannot be None)")
        if not operation_id:
            raise ValueError("operation_id is required (cannot be empty)")

        # SEC-002: Channel name MUST include project_id
        channel_name = f"progress:{project_id}:{operation_id}"
        redis = await self._get_redis()
        pubsub = redis.pubsub()

        try:
            await pubsub.subscribe(channel_name)
            logger.info(
                "SSE: Subscribed to progress channel",
                project_id=str(project_id),
                operation_id=operation_id,
                channel=channel_name,
            )

            last_keepalive = asyncio.get_running_loop().time()

            while True:
                try:
                    # Check for messages with timeout
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True), timeout=1.0
                    )

                    if message and message["type"] == "message":
                        data = message["data"].decode("utf-8")

                        # Check for completion event
                        try:
                            event_data = json.loads(data)
                            if event_data.get("status") in (
                                "completed",
                                "failed",
                                "cancelled",
                            ):
                                logger.info(
                                    "SSE: Operation completed, closing stream",
                                    project_id=str(project_id),
                                    operation_id=operation_id,
                                    status=event_data.get("status"),
                                )
                                yield f"data: {data}\n\n"
                                break
                        except json.JSONDecodeError:
                            pass

                        yield f"data: {data}\n\n"
                        last_keepalive = asyncio.get_running_loop().time()

                    # Send keepalive if no activity
                    current_time = asyncio.get_running_loop().time()
                    if current_time - last_keepalive > self.keepalive_interval:
                        yield ": keepalive\n\n"
                        last_keepalive = current_time

                except asyncio.TimeoutError:
                    # Check if connection timeout exceeded
                    current_time = asyncio.get_running_loop().time()
                    if current_time - last_keepalive > self.connection_timeout:
                        logger.info(
                            "SSE: Connection timeout, closing stream",
                            project_id=str(project_id),
                            operation_id=operation_id,
                            timeout=self.connection_timeout,
                        )
                        break
                    continue

        except asyncio.CancelledError:
            logger.info(
                "SSE: Stream cancelled by client",
                project_id=str(project_id),
                operation_id=operation_id,
            )
            raise

        except Exception as e:
            logger.error(
                "SSE: Stream error",
                project_id=str(project_id),
                operation_id=operation_id,
                error=str(e),
                exc_info=True,
            )
            raise

        finally:
            try:
                await pubsub.unsubscribe(channel_name)
                await pubsub.close()
                logger.info(
                    "SSE: Unsubscribed from progress channel",
                    project_id=str(project_id),
                    operation_id=operation_id,
                )
            except Exception as e:
                logger.warning(
                    "SSE: Error during cleanup",
                    project_id=str(project_id),
                    operation_id=operation_id,
                    error=str(e),
                )

    async def publish_event(
        self, project_id: UUID, operation_id: str, event: dict
    ) -> None:
        """
        Publish event to Redis for SSE streaming.

        Args:
            project_id: Project UUID for isolation (REQUIRED)
            operation_id: Operation identifier (REQUIRED)
            event: Event data dictionary

        Raises:
            ValueError: If project_id or operation_id is None (zero tolerance)
        """
        if project_id is None:
            raise ValueError("project_id is required (cannot be None)")
        if not operation_id:
            raise ValueError("operation_id is required (cannot be empty)")
        if not event:
            raise ValueError("event is required (cannot be empty)")

        try:
            # SEC-002: Channel name MUST include project_id
            channel_name = f"progress:{project_id}:{operation_id}"
            redis = await self._get_redis()

            # Add metadata to event
            event_with_metadata = {
                **event,
                "project_id": str(project_id),
                "operation_id": operation_id,
            }

            await redis.publish(channel_name, json.dumps(event_with_metadata))

            logger.debug(
                "SSE: Event published",
                project_id=str(project_id),
                operation_id=operation_id,
                event_type=event.get("type", "unknown"),
            )

        except Exception as e:
            logger.error(
                "SSE: Failed to publish event",
                project_id=str(project_id),
                operation_id=operation_id,
                error=str(e),
                exc_info=True,
            )
            raise


# Global SSE service instance will be initialized during app startup
# with explicit Redis dependency (no fallback - fail fast)
sse_service: Optional[SSEService] = None


def initialize_sse_service(redis: Redis) -> SSEService:
    """
    Initialize global SSE service with Redis dependency.

    Args:
        redis: Redis client (REQUIRED)

    Returns:
        Initialized SSEService instance

    Raises:
        TypeError: If redis is invalid
    """
    global sse_service
    sse_service = SSEService(redis=redis)
    logger.info("SSE service initialized with explicit Redis dependency")
    return sse_service


def get_sse_service() -> SSEService:
    """
    Get initialized SSE service.

    Returns:
        SSEService instance

    Raises:
        RuntimeError: If service not initialized (fail fast)
    """
    if sse_service is None:
        raise RuntimeError(
            "SSE service not initialized. Call initialize_sse_service() during app startup."
        )
    return sse_service


__all__ = [
    "SSEService",
    "sse_service",
    "initialize_sse_service",
    "get_sse_service",
]
