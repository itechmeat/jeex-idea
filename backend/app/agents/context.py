from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExecutionContext(BaseModel, frozen=True):
    project_id: UUID
    correlation_id: UUID
    language: str
    user_id: UUID
    stage: str
    state: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def create_context(
    project_id: UUID, user_id: UUID, stage: str, language: str
) -> ExecutionContext:
    """Create immutable execution context using existing correlation when available.

    Attempts to use correlation ID from telemetry context; if unavailable, generates a new UUID.
    """
    logger = logging.getLogger(__name__)
    try:
        from ..core.telemetry import get_correlation_id  # type: ignore

        existing = get_correlation_id()
        if not existing:
            logger.debug("No correlation_id in telemetry context, generating new UUID")
    except Exception as e:
        logger.debug(
            "Telemetry context unavailable, generating new correlation_id",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        existing = None

    return ExecutionContext(
        project_id=project_id,
        correlation_id=UUID(existing) if existing else uuid4(),
        language=language,
        user_id=user_id,
        stage=stage,
    )
