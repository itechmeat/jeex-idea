from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentExecution


class AgentExecutionTracker:
    """Persist agent execution lifecycle events to PostgreSQL with ACID guarantees."""

    # Class-level constants for sanitization (compiled once)
    SENSITIVE_PATTERNS = [
        re.compile(r".*password.*", re.IGNORECASE),
        re.compile(r".*token.*", re.IGNORECASE),
        re.compile(r".*secret.*", re.IGNORECASE),
        re.compile(r".*key.*", re.IGNORECASE),
        re.compile(r".*auth.*", re.IGNORECASE),
        re.compile(r".*credential.*", re.IGNORECASE),
        re.compile(r".*api[_-]?key.*", re.IGNORECASE),
    ]
    TRUNCATE_FIELDS = {"user_message", "content", "description"}
    TRUNCATE_LEN = 100

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.logger = logging.getLogger(__name__)

    async def start_execution(
        self,
        project_id: UUID,
        agent_type: str,
        correlation_id: UUID,
        input_data: dict[str, Any] | None = None,
    ) -> UUID:
        if not isinstance(agent_type, str) or not agent_type.strip():
            raise ValueError("agent_type must be a non-empty string")
        execution = AgentExecution(
            project_id=project_id,
            agent_type=agent_type,
            correlation_id=correlation_id,
            input_data=self._sanitize(input_data or {}),
            status="pending",
            started_at=datetime.now(UTC),
        )
        try:
            self.session.add(execution)
            await self.session.flush()  # Get ID without committing
            return execution.id  # type: ignore[return-value]
        except Exception:
            self.logger.exception(
                "Failed to start execution",
                extra={
                    "project_id": str(project_id),
                    "agent_type": agent_type,
                    "correlation_id": str(correlation_id),
                },
            )
            raise

    async def complete_execution(
        self,
        execution_id: UUID,
        output_data: dict[str, Any] | None,
        status: str = "completed",
    ) -> None:
        now = datetime.now(UTC)
        try:
            # First, SELECT to get started_at
            result = await self.session.execute(
                select(AgentExecution.started_at).where(
                    AgentExecution.id == execution_id
                )
            )
            started_at = result.scalar_one_or_none()

            # Calculate duration_ms if started_at exists
            duration_ms = None
            if started_at:
                duration_ms = int((now - started_at).total_seconds() * 1000)

            # Single UPDATE with all fields
            await self.session.execute(
                update(AgentExecution)
                .where(AgentExecution.id == execution_id)
                .values(
                    output_data=self._sanitize(output_data or {}),
                    status=status,
                    completed_at=now,
                    duration_ms=duration_ms,
                )
            )
        except Exception:
            self.logger.exception(
                "Failed to complete execution",
                extra={"execution_id": str(execution_id), "status": status},
            )
            raise

    async def fail_execution(self, correlation_id: UUID, error_message: str) -> None:
        if not isinstance(error_message, str) or not error_message.strip():
            raise ValueError("error_message must be a non-empty string")
        now = datetime.now(UTC)
        try:
            # First, SELECT to get execution.id and started_at
            result = await self.session.execute(
                select(AgentExecution.id, AgentExecution.started_at).where(
                    AgentExecution.correlation_id == correlation_id
                )
            )
            row = result.one_or_none()
            if not row:
                self.logger.error(
                    "Execution not found for failure update",
                    extra={"correlation_id": str(correlation_id)},
                )
                raise LookupError("Execution not found for given correlation_id")

            execution_id, started_at = row

            # Calculate duration_ms if started_at exists
            duration_ms = None
            if started_at:
                duration_ms = int((now - started_at).total_seconds() * 1000)

            # Single UPDATE with all fields including duration_ms
            await self.session.execute(
                update(AgentExecution)
                .where(AgentExecution.id == execution_id)
                .values(
                    status="failed",
                    error_message=error_message,
                    completed_at=now,
                    duration_ms=duration_ms,
                )
            )
        except Exception:
            self.logger.exception(
                "Failed to mark execution as failed",
                extra={"correlation_id": str(correlation_id)},
            )
            raise

    async def get_execution_history(
        self, project_id: UUID, limit: int = 50
    ) -> list[AgentExecution]:
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if limit > 1000:
            limit = 1000
        try:
            result = await self.session.execute(
                select(AgentExecution)
                .where(AgentExecution.project_id == project_id)
                .order_by(AgentExecution.started_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception:
            self.logger.exception(
                "Failed to fetch execution history",
                extra={"project_id": str(project_id), "limit": limit},
            )
            raise

    @staticmethod
    def _sanitize(
        data: dict[str, Any] | list[Any] | Any,
        max_depth: int = 5,
        current_depth: int = 0,
    ) -> dict[str, Any] | list[Any] | Any:
        """Recursively sanitize sensitive fields from payloads."""
        if current_depth >= max_depth:
            return "[max_depth_reached]"
        if data is None or isinstance(data, (str, int, float, bool)):
            return data

        if isinstance(data, dict):
            sanitized: dict[str, Any] = {}
            for key, value in data.items():
                if any(p.match(key) for p in AgentExecutionTracker.SENSITIVE_PATTERNS):
                    sanitized[key] = "[redacted]"
                elif key in AgentExecutionTracker.TRUNCATE_FIELDS and isinstance(
                    value, str
                ):
                    sanitized[key] = (
                        value[: AgentExecutionTracker.TRUNCATE_LEN] + "... [truncated]"
                        if len(value) > AgentExecutionTracker.TRUNCATE_LEN
                        else value
                    )
                else:
                    sanitized[key] = AgentExecutionTracker._sanitize(
                        value, max_depth=max_depth, current_depth=current_depth + 1
                    )
            return sanitized

        if isinstance(data, list):
            return [
                AgentExecutionTracker._sanitize(
                    item, max_depth=max_depth, current_depth=current_depth + 1
                )
                for item in data
            ]

        return data
