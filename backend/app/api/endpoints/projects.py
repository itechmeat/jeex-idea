"""
Projects API endpoints - Phase 4 Integration

Complete CRUD operations for projects with:
- Database integration
- Project isolation enforcement
- Transaction management
- Error handling
- Performance monitoring
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import time
import structlog

from ...db import get_database_session
from ...models import Project, User
from ...core.config import get_settings
from ...core.monitoring import performance_monitor

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()


# Pydantic schemas for API
class ProjectBase(BaseModel):
    """Base project schema with validation."""

    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    language: str = Field(
        ..., min_length=2, max_length=10, description="Project language code"
    )
    status: str = Field("draft", description="Project status")
    current_step: int = Field(1, ge=1, le=4, description="Current workflow step")
    meta_data: Dict[str, Any] = Field(
        default_factory=dict, description="Project metadata"
    )


class ProjectCreate(ProjectBase):
    """Schema for creating projects."""

    created_by: UUID = Field(..., description="User ID creating the project")


class ProjectUpdate(BaseModel):
    """Schema for updating projects."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[str] = None
    current_step: Optional[int] = Field(None, ge=1, le=4)
    meta_data: Optional[Dict[str, Any]] = None


class ProjectRead(ProjectBase):
    """Schema for reading projects."""

    id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]
    is_deleted: bool

    class Config:
        from_attributes = True


class ProjectList(BaseModel):
    """Schema for project lists with pagination."""

    projects: List[ProjectRead]
    total: int
    page: int
    per_page: int
    total_pages: int


# CRUD Operations
class ProjectRepository:
    """Repository for project CRUD operations with project isolation."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, project_data: ProjectCreate) -> Project:
        """Create a new project with proper validation."""
        start_time = time.time()

        try:
            # Validate user exists
            user_result = await self.session.execute(
                select(User).where(User.id == project_data.created_by)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Create project
            project = Project(
                name=project_data.name,
                language=project_data.language,
                status=project_data.status,
                current_step=project_data.current_step,
                meta_data=project_data.meta_data,
                created_by=project_data.created_by,
            )

            self.session.add(project)
            await self.session.flush()  # Get the ID without committing

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "project_create", duration, True
            )

            logger.info(
                "Project created",
                project_id=str(project.id),
                user_id=str(project_data.created_by),
                duration_ms=duration,
            )

            return project

        except IntegrityError as e:
            await self.session.rollback()
            raise HTTPException(status_code=400, detail="Invalid project data")
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error("Database error creating project", error=str(e))
            raise HTTPException(status_code=500, detail="Database error")

    async def get_by_id(self, project_id: UUID, user_id: UUID) -> Optional[Project]:
        """Get project by ID with user access validation."""
        start_time = time.time()

        try:
            result = await self.session.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.created_by == user_id,
                    Project.is_deleted == False,
                )
            )
            project = result.scalar_one_or_none()

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "project_get_by_id", duration, project is not None
            )

            return project

        except SQLAlchemyError as e:
            logger.error("Database error getting project", error=str(e))
            raise HTTPException(status_code=500, detail="Database error")

    async def get_user_projects(
        self,
        user_id: UUID,
        page: int = 1,
        per_page: int = 20,
        status: Optional[str] = None,
    ) -> tuple[List[Project], int]:
        """Get user's projects with pagination and filtering."""
        start_time = time.time()

        try:
            # Build query
            query = select(Project).where(
                Project.created_by == user_id, Project.is_deleted == False
            )

            if status:
                query = query.where(Project.status == status)

            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.session.execute(count_query)
            total = total_result.scalar()

            # Apply pagination
            offset = (page - 1) * per_page
            query = (
                query.order_by(Project.updated_at.desc()).offset(offset).limit(per_page)
            )

            result = await self.session.execute(query)
            projects = result.scalars().all()

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "project_list", duration, True
            )

            return list(projects), total

        except SQLAlchemyError as e:
            logger.error("Database error listing projects", error=str(e))
            raise HTTPException(status_code=500, detail="Database error")

    async def update(
        self, project_id: UUID, user_id: UUID, update_data: ProjectUpdate
    ) -> Optional[Project]:
        """Update project with user access validation."""
        start_time = time.time()

        try:
            # Check if project exists and user has access
            project = await self.get_by_id(project_id, user_id)
            if not project:
                return None

            # Update fields
            update_values = {}
            if update_data.name is not None:
                update_values["name"] = update_data.name
            if update_data.status is not None:
                update_values["status"] = update_data.status
            if update_data.current_step is not None:
                update_values["current_step"] = update_data.current_step
            if update_data.meta_data is not None:
                update_values["meta_data"] = update_data.meta_data

            if not update_values:
                return project  # No changes needed

            # Perform update
            await self.session.execute(
                update(Project).where(Project.id == project_id).values(**update_values)
            )

            await self.session.refresh(project)

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "project_update", duration, True
            )

            logger.info(
                "Project updated",
                project_id=str(project_id),
                user_id=str(user_id),
                updated_fields=list(update_values.keys()),
                duration_ms=duration,
            )

            return project

        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error("Database error updating project", error=str(e))
            raise HTTPException(status_code=500, detail="Database error")

    async def delete(self, project_id: UUID, user_id: UUID) -> bool:
        """Soft delete project with user access validation."""
        start_time = time.time()

        try:
            # Check if project exists and user has access
            project = await self.get_by_id(project_id, user_id)
            if not project:
                return False

            # Soft delete
            await self.session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(is_deleted=True, deleted_at=func.now())
            )

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "project_delete", duration, True
            )

            logger.info(
                "Project deleted",
                project_id=str(project_id),
                user_id=str(user_id),
                duration_ms=duration,
            )

            return True

        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error("Database error deleting project", error=str(e))
            raise HTTPException(status_code=500, detail="Database error")


# API Endpoints
@router.post("/projects", response_model=ProjectRead, status_code=201)
async def create_project(
    project_data: ProjectCreate, session: AsyncSession = Depends(get_database_session)
):
    """
    Create a new project.

    Args:
        project_data: Project creation data
        session: Database session

    Returns:
        Created project data
    """
    repo = ProjectRepository(session)
    project = await repo.create(project_data)
    return ProjectRead.model_validate(project)


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: UUID,
    user_id: UUID = Query(..., description="User ID for access validation"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Get project by ID.

    Args:
        project_id: Project UUID
        user_id: User ID for access validation
        session: Database session

    Returns:
        Project data
    """
    repo = ProjectRepository(session)
    project = await repo.get_by_id(project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectRead.model_validate(project)


@router.get("/projects", response_model=ProjectList)
async def list_projects(
    user_id: UUID = Query(..., description="User ID for access validation"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    List user's projects with pagination.

    Args:
        user_id: User ID for access validation
        page: Page number
        per_page: Items per page
        status: Optional status filter
        session: Database session

    Returns:
        Paginated project list
    """
    repo = ProjectRepository(session)
    projects, total = await repo.get_user_projects(user_id, page, per_page, status)

    total_pages = (total + per_page - 1) // per_page

    return ProjectList(
        projects=[ProjectRead.model_validate(p) for p in projects],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.put("/projects/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID,
    update_data: ProjectUpdate,
    user_id: UUID = Query(..., description="User ID for access validation"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Update project.

    Args:
        project_id: Project UUID
        update_data: Update data
        user_id: User ID for access validation
        session: Database session

    Returns:
        Updated project data
    """
    repo = ProjectRepository(session)
    project = await repo.update(project_id, user_id, update_data)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectRead.model_validate(project)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID,
    user_id: UUID = Query(..., description="User ID for access validation"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Delete project (soft delete).

    Args:
        project_id: Project UUID
        user_id: User ID for access validation
        session: Database session
    """
    repo = ProjectRepository(session)
    success = await repo.delete(project_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
