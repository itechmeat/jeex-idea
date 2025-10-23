"""
Base Repository with Project Isolation (SEC-002 Critical)

This module implements the base repository pattern with strict project isolation
enforcement. All database operations MUST filter by project_id to prevent
cross-project data leakage.

CRITICAL RULE: project_id is ALWAYS required (UUID, never Optional, never None).
"""

from typing import Optional, Type
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeMeta
import structlog

from app.models import Base

logger = structlog.get_logger()


class BaseRepository:
    """
    Base repository with project isolation enforcement (SEC-002).

    NOTE: No generics for MVP simplicity (Variant C decision).
    Each repository subclass specifies its model type directly.

    SECURITY:
    - All queries MUST filter by project_id (SEC-002)
    - Soft delete is enforced (is_deleted = False)
    - Server-side filtering prevents client manipulation

    ZERO TOLERANCE:
    - NO fallback logic for project_id
    - NO Optional[UUID] - always required UUID
    - Errors preserve full context
    """

    def __init__(self, session: AsyncSession, model: Type[Base]):
        """
        Initialize repository with strict input validation.

        Args:
            session: AsyncSession for database operations
            model: SQLAlchemy model class

        Raises:
            TypeError: If session is not AsyncSession or model is invalid
        """
        # CRITICAL: Fail fast with explicit validation (zero tolerance rule)
        if not isinstance(session, AsyncSession):
            raise TypeError(
                f"session must be AsyncSession instance, got {type(session).__name__}"
            )

        if not model or not hasattr(model, "__tablename__"):
            raise TypeError(
                f"model must be valid SQLAlchemy model with __tablename__, got {type(model).__name__}"
            )

        self.session = session
        self.model = model

    async def get(self, id: UUID, project_id: UUID) -> Optional[Base]:
        """
        Get entity by ID with project isolation.

        Args:
            id: Entity UUID (REQUIRED)
            project_id: Project UUID for isolation (REQUIRED)

        Returns:
            Entity if found and belongs to project, None otherwise

        Raises:
            ValueError: If id or project_id is None (zero tolerance)
        """
        if id is None:
            raise ValueError("Entity id is required (cannot be None)")
        if project_id is None:
            raise ValueError("project_id is required (cannot be None)")

        try:
            stmt = select(self.model).where(
                self.model.id == id,
                self.model.project_id == project_id,  # SEC-002: Server-side filtering
                self.model.is_deleted == False,  # Exclude soft-deleted
            )
            result = await self.session.execute(stmt)
            entity = result.scalar_one_or_none()

            if entity:
                logger.debug(
                    "Repository: Entity retrieved",
                    model=self.model.__name__,
                    entity_id=str(id),
                    project_id=str(project_id),
                )

            return entity

        except Exception as e:
            logger.error(
                "Repository: Failed to get entity",
                model=self.model.__name__,
                entity_id=str(id),
                project_id=str(project_id),
                error=str(e),
                exc_info=True,
            )
            raise  # Preserve full error context

    async def list(
        self, project_id: UUID, skip: int = 0, limit: int = 100
    ) -> list[Base]:
        """
        List entities with project isolation.

        Args:
            project_id: Project UUID for isolation (REQUIRED)
            skip: Number of records to skip (pagination)
            limit: Maximum records to return (max 100)

        Returns:
            List of entities belonging to project

        Raises:
            ValueError: If project_id is None (zero tolerance)
        """
        if project_id is None:
            raise ValueError("project_id is required (cannot be None)")
        if limit > 100:
            raise ValueError("limit cannot exceed 100")
        if skip < 0:
            raise ValueError("skip must be non-negative")

        try:
            stmt = (
                select(self.model)
                .where(
                    self.model.project_id == project_id,  # SEC-002
                    self.model.is_deleted == False,
                )
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(stmt)
            entities = list(result.scalars().all())

            logger.debug(
                "Repository: Entities listed",
                model=self.model.__name__,
                project_id=str(project_id),
                count=len(entities),
                skip=skip,
                limit=limit,
            )

            return entities

        except Exception as e:
            logger.error(
                "Repository: Failed to list entities",
                model=self.model.__name__,
                project_id=str(project_id),
                error=str(e),
                exc_info=True,
            )
            raise

    async def create(self, obj: Base) -> Base:
        """
        Create new entity.

        Args:
            obj: Entity instance to create (must have project_id set)

        Returns:
            Created entity with ID populated

        Raises:
            ValueError: If obj is None or obj.project_id is None (zero tolerance)
            TypeError: If obj is not the expected type
        """
        # CRITICAL: Validate obj before accessing attributes (fail fast)
        if obj is None:
            raise ValueError("Entity object is required (cannot be None)")

        if not isinstance(obj, Base):
            raise TypeError(
                f"Entity must be SQLAlchemy model instance, got {type(obj).__name__}"
            )

        if not hasattr(obj, "project_id") or obj.project_id is None:
            raise ValueError("Entity must have project_id set (cannot be None)")

        try:
            self.session.add(obj)
            await self.session.flush()
            await self.session.refresh(obj)

            logger.info(
                "Repository: Entity created",
                model=self.model.__name__,
                entity_id=str(obj.id),
                project_id=str(obj.project_id),
            )

            return obj

        except Exception as e:
            logger.error(
                "Repository: Failed to create entity",
                model=self.model.__name__,
                project_id=str(obj.project_id) if hasattr(obj, "project_id") else None,
                error=str(e),
                exc_info=True,
            )
            raise

    async def update(self, obj: Base, project_id: UUID) -> Base:
        """
        Update existing entity with strict project isolation.

        Args:
            obj: Entity instance to update
            project_id: Project UUID for isolation validation (REQUIRED)

        Returns:
            Updated entity

        Raises:
            ValueError: If obj/obj.id/obj.project_id is None (zero tolerance)
            PermissionError: If obj.project_id doesn't match project_id (SEC-002)
        """
        # CRITICAL: Validate obj and enforce project isolation (fail fast)
        if obj is None:
            raise ValueError("Entity object is required (cannot be None)")

        if not hasattr(obj, "id") or obj.id is None:
            raise ValueError("Entity must have id set (cannot be None)")

        if not hasattr(obj, "project_id") or obj.project_id is None:
            raise ValueError("Entity must have project_id set (cannot be None)")

        if project_id is None:
            raise ValueError(
                "project_id is required for isolation check (cannot be None)"
            )

        # SEC-002: CRITICAL - Prevent cross-project data modification
        if obj.project_id != project_id:
            raise PermissionError(
                f"Cross-project access denied: entity belongs to {obj.project_id}, "
                f"requested {project_id}"
            )

        try:
            await self.session.flush()
            await self.session.refresh(obj)

            logger.info(
                "Repository: Entity updated",
                model=self.model.__name__,
                entity_id=str(obj.id),
                project_id=str(obj.project_id),
            )

            return obj

        except Exception as e:
            logger.error(
                "Repository: Failed to update entity",
                model=self.model.__name__,
                entity_id=str(obj.id) if hasattr(obj, "id") else None,
                project_id=str(project_id),
                error=str(e),
                exc_info=True,
            )
            raise

    async def delete(self, id: UUID, project_id: UUID) -> bool:
        """
        Soft delete entity with project isolation.

        Args:
            id: Entity UUID (REQUIRED)
            project_id: Project UUID for isolation (REQUIRED)

        Returns:
            True if entity was deleted, False if not found

        Raises:
            ValueError: If id or project_id is None (zero tolerance)
        """
        if id is None:
            raise ValueError("Entity id is required (cannot be None)")
        if project_id is None:
            raise ValueError("project_id is required (cannot be None)")

        try:
            obj = await self.get(id, project_id)
            if not obj:
                logger.warning(
                    "Repository: Entity not found for deletion",
                    model=self.model.__name__,
                    entity_id=str(id),
                    project_id=str(project_id),
                )
                return False

            obj.is_deleted = True
            obj.deleted_at = datetime.now(timezone.utc)
            await self.session.flush()

            logger.info(
                "Repository: Entity soft deleted",
                model=self.model.__name__,
                entity_id=str(id),
                project_id=str(project_id),
            )

            return True

        except Exception as e:
            logger.error(
                "Repository: Failed to delete entity",
                model=self.model.__name__,
                entity_id=str(id),
                project_id=str(project_id),
                error=str(e),
                exc_info=True,
            )
            raise
