"""
Project Repository

Specialized repository for Project model with user-based access control.
Implements project isolation and user ownership validation.
"""

from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.models import Project
from .base import BaseRepository

logger = structlog.get_logger()


class ProjectRepository(BaseRepository):
    """
    Project-specific repository with user-based access control.

    NOTE: Projects are special - they ARE the project_id, so some methods
    differ from standard BaseRepository pattern.
    """

    def __init__(self, session: AsyncSession):
        """Initialize project repository."""
        super().__init__(session, Project)

    async def get_by_user(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> list[Project]:
        """
        Get all projects for a user.

        Args:
            user_id: User UUID (REQUIRED)
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of user's projects

        Raises:
            ValueError: If user_id is None (zero tolerance)
        """
        if user_id is None:
            raise ValueError("user_id is required (cannot be None)")
        if limit > 100:
            raise ValueError("limit cannot exceed 100")
        if skip < 0:
            raise ValueError("skip must be non-negative")

        try:
            stmt = (
                select(Project)
                .where(Project.created_by == user_id, Project.is_deleted == False)
                .offset(skip)
                .limit(limit)
                .order_by(Project.updated_at.desc())
            )

            result = await self.session.execute(stmt)
            projects = list(result.scalars().all())

            logger.debug(
                "ProjectRepository: User projects retrieved",
                user_id=str(user_id),
                count=len(projects),
                skip=skip,
                limit=limit,
            )

            return projects

        except Exception as e:
            logger.error(
                "ProjectRepository: Failed to get user projects",
                user_id=str(user_id),
                error=str(e),
                exc_info=True,
            )
            raise

    async def get_by_id_and_user(
        self, project_id: UUID, user_id: UUID
    ) -> Optional[Project]:
        """
        Get project by ID with user ownership validation.

        Args:
            project_id: Project UUID (REQUIRED)
            user_id: User UUID for ownership check (REQUIRED)

        Returns:
            Project if found and owned by user, None otherwise

        Raises:
            ValueError: If project_id or user_id is None (zero tolerance)
        """
        if project_id is None:
            raise ValueError("project_id is required (cannot be None)")
        if user_id is None:
            raise ValueError("user_id is required (cannot be None)")

        try:
            stmt = select(Project).where(
                Project.id == project_id,
                Project.created_by == user_id,
                Project.is_deleted == False,
            )

            result = await self.session.execute(stmt)
            project = result.scalar_one_or_none()

            if project:
                logger.debug(
                    "ProjectRepository: Project retrieved",
                    project_id=str(project_id),
                    user_id=str(user_id),
                )
            else:
                logger.warning(
                    "ProjectRepository: Project not found or access denied",
                    project_id=str(project_id),
                    user_id=str(user_id),
                )

            return project

        except Exception as e:
            logger.error(
                "ProjectRepository: Failed to get project",
                project_id=str(project_id),
                user_id=str(user_id),
                error=str(e),
                exc_info=True,
            )
            raise
