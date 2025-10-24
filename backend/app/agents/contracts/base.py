from __future__ import annotations

from enum import StrEnum
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, field_validator


class ExecutionStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    needs_input = "needs_input"


class AgentInput(BaseModel):
    """Base input contract for all agents.

    Example:
        >>> from uuid import uuid4
        >>> AgentInput(
        ...     project_id=uuid4(),
        ...     correlation_id=uuid4(),
        ...     language="en",
        ...     user_message="Summarize the idea",
        ... )
    """

    project_id: UUID = Field(..., description="Project ID (UUID, required)")
    correlation_id: UUID = Field(..., description="Correlation ID (UUID, required)")
    language: str = Field(
        ..., min_length=2, max_length=10, description="ISO 639-1 code"
    )
    user_message: str = Field(..., min_length=1, description="User message or prompt")
    context: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        if not value or len(value) < 2:
            raise ValueError("language must be an ISO 639-1 code (min length 2)")
        return value


class AgentOutput(BaseModel):
    """Base output contract for all agents.

    Status field uses ExecutionStatus enum values to maintain consistency
    across agent execution tracking.

    Example:
        >>> AgentOutput(
        ...     agent_type="product_manager",
        ...     status="completed",
        ...     content="All good",
        ... )
    """

    agent_type: str = Field(..., min_length=1, max_length=50)
    status: ExecutionStatus = Field(..., description="Execution status following ExecutionStatus enum")
    content: str = Field("", description="Primary textual content")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    next_agent: Optional[str] = Field(default=None, max_length=50)


__all__ = ["AgentInput", "AgentOutput", "ExecutionStatus"]
