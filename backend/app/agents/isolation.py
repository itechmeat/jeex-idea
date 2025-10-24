from __future__ import annotations

from typing import Any, Dict
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Project


class IsolationValidator:
    """Project and language isolation enforcement helpers."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.logger = logging.getLogger(__name__)

    async def validate_project_access(self, user_id: UUID, project_id: UUID) -> None:
        result = await self.session.execute(
            select(Project).where(
                Project.id == project_id,
                Project.created_by == user_id,
                Project.is_deleted.is_(False),
            )
        )
        if result.scalar_one_or_none() is None:
            self.logger.error(
                "Project access denied or not found",
                extra={"user_id": str(user_id), "project_id": str(project_id)},
            )
            raise PermissionError("Project not found or access denied")

    async def validate_language_consistency(
        self, project_id: UUID, language: str
    ) -> None:
        if not isinstance(language, str) or not language.strip():
            raise ValueError("language must be a non-empty string")
        result = await self.session.execute(
            select(Project.language).where(
                Project.id == project_id,
                Project.is_deleted.is_(False),
            )
        )
        db_language = result.scalar_one_or_none()
        if db_language is None:
            self.logger.error(
                "Project not found or deleted",
                extra={"project_id": str(project_id)},
            )
            raise ValueError("Project not found or deleted")
        if db_language != language:
            self.logger.error(
                "Language mismatch with project configuration",
                extra={
                    "project_id": str(project_id),
                    "provided_language": language,
                    "db_language": db_language,
                },
            )
            raise ValueError("Language mismatch with project configuration")

    @staticmethod
    def build_isolation_filter(project_id: UUID, language: str) -> Dict[str, Any]:
        """Build Qdrant payload filter enforcing project and language isolation."""
        if not isinstance(language, str) or not language.strip():
            raise ValueError("language must be a non-empty string")
        return {
            "must": [
                {"key": "project_id", "match": {"value": str(project_id)}},
                {"key": "language", "match": {"value": language}},
            ]
        }
