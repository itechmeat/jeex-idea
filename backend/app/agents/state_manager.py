from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ..infrastructure.redis.redis_service import redis_service
from .context import ExecutionContext

STATE_TTL_SECONDS = int(os.getenv("AGENT_STATE_TTL_SECONDS", "86400"))


class ExecutionStateManager:
    """Manage execution state in Redis with project isolation and TTL."""

    def __init__(self) -> None:
        self.ttl_seconds = STATE_TTL_SECONDS

    def _key(self, project_id: UUID, correlation_id: UUID) -> str:
        return f"agent:execution:{project_id}:{correlation_id}"

    async def create_state(self, context: ExecutionContext, stage: str) -> None:
        payload = {
            "project_id": str(context.project_id),
            "correlation_id": str(context.correlation_id),
            "language": context.language,
            "stage": stage,
            "current_agent": "product_manager",
            "status": "running",
            "progress": 0,
            "started_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        from redis.asyncio import Redis

        async def _set(conn: Redis, key: str, value: str, ex: int) -> bool:
            return await conn.set(key, value, ex=ex)

        await redis_service.execute_with_retry(
            operation="state.create",
            func=_set,
            key=self._key(context.project_id, context.correlation_id),
            value=json.dumps(payload),
            ex=self.ttl_seconds,
            project_id=str(context.project_id),
        )

    async def update_state(
        self, project_id: UUID, correlation_id: UUID, current_agent: str, progress: int
    ) -> None:
        from redis.asyncio import Redis

        # Clamp progress to 0-100 range
        progress = max(0, min(100, int(progress)))

        async def _get(conn: Redis, key: str) -> str | None:
            return await conn.get(key)

        raw = await redis_service.execute_with_retry(
            operation="state.get",
            func=_get,
            key=self._key(project_id, correlation_id),
            project_id=str(project_id),
        )
        if not raw:
            return
        state = json.loads(raw)
        state["current_agent"] = current_agent
        state["progress"] = progress
        state["updated_at"] = datetime.now(UTC).isoformat()

        async def _set(conn: Redis, key: str, value: str, ex: int) -> bool:
            return await conn.set(key, value, ex=ex)

        await redis_service.execute_with_retry(
            operation="state.update",
            func=_set,
            key=self._key(project_id, correlation_id),
            value=json.dumps(state),
            ex=self.ttl_seconds,
            project_id=str(project_id),
        )

    async def get_state(
        self, project_id: UUID, correlation_id: UUID
    ) -> dict[str, Any] | None:
        from redis.asyncio import Redis

        async def _get(conn: Redis, key: str) -> str | None:
            return await conn.get(key)

        raw = await redis_service.execute_with_retry(
            operation="state.get",
            func=_get,
            key=self._key(project_id, correlation_id),
            project_id=str(project_id),
        )
        return json.loads(raw) if raw else None

    async def cleanup(self, project_id: UUID, correlation_id: UUID) -> None:
        from redis.asyncio import Redis

        async def _delete(conn: Redis, key: str) -> int:
            return await conn.delete(key)

        await redis_service.execute_with_retry(
            operation="state.cleanup",
            func=_delete,
            key=self._key(project_id, correlation_id),
            project_id=str(project_id),
        )
