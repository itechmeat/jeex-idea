"""
Agents API endpoints - Phase 4 Integration

Agent execution tracking and management with:
- Database integration
- Project isolation enforcement
- Transaction management
- Performance monitoring
- Correlation tracking
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, case
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime, timedelta
import time
import structlog
import asyncio

from ...db import get_database_session
from ...models import AgentExecution, Project, User
from ...core.config import get_settings
from ...core.monitoring import performance_monitor

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()


# Pydantic schemas for API
class AgentBase(BaseModel):
    """Base agent execution schema."""

    agent_type: str = Field(..., min_length=1, max_length=50, description="Agent type")
    input_data: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Input data for agent"
    )


class AgentExecutionCreate(AgentBase):
    """Schema for creating agent executions."""

    project_id: UUID = Field(..., description="Project ID")
    created_by: UUID = Field(..., description="User ID initiating execution")


class AgentExecutionUpdate(BaseModel):
    """Schema for updating agent executions."""

    status: Optional[str] = Field(None, description="Execution status")
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class AgentExecutionRead(BaseModel):
    """Schema for reading agent executions."""

    id: UUID
    project_id: UUID
    agent_type: str
    correlation_id: UUID
    input_data: Optional[Dict[str, Any]]
    output_data: Optional[Dict[str, Any]]
    status: str
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentExecutionList(BaseModel):
    """Schema for agent execution lists with pagination."""

    executions: List[AgentExecutionRead]
    total: int
    page: int
    per_page: int
    total_pages: int


class AgentMetrics(BaseModel):
    """Schema for agent performance metrics."""

    total_executions: int
    successful_executions: int
    failed_executions: int
    average_execution_time_seconds: float
    success_rate: float
    executions_by_agent_type: Dict[str, int]
    recent_executions: List[AgentExecutionRead]


# CRUD Operations
class AgentExecutionRepository:
    """Repository for agent execution CRUD operations with project isolation."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, execution_data: AgentExecutionCreate, user_id: UUID
    ) -> AgentExecution:
        """Create a new agent execution with project isolation."""
        start_time = time.time()

        try:
            # Validate project access
            project_result = await self.session.execute(
                select(Project).where(
                    Project.id == execution_data.project_id,
                    Project.created_by == user_id,
                    Project.is_deleted == False,
                )
            )
            project = project_result.scalar_one_or_none()
            if not project:
                raise HTTPException(
                    status_code=404, detail="Project not found or access denied"
                )

            # Create agent execution
            execution = AgentExecution(
                project_id=execution_data.project_id,
                agent_type=execution_data.agent_type,
                correlation_id=uuid4(),
                input_data=execution_data.input_data,
                status="pending",
                started_at=datetime.utcnow(),
            )

            self.session.add(execution)
            await self.session.flush()  # Get the ID without committing

            # Commit the transaction
            await self.session.commit()

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "agent_execution_create", duration, True
            )

            logger.info(
                "Agent execution created",
                execution_id=str(execution.id),
                project_id=str(execution_data.project_id),
                agent_type=execution_data.agent_type,
                correlation_id=str(execution.correlation_id),
                duration_ms=duration,
            )

            return execution

        except IntegrityError as e:
            await self.session.rollback()
            raise HTTPException(status_code=400, detail="Invalid agent execution data")
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.exception("Database error creating agent execution")
            raise HTTPException(status_code=500, detail="Database error") from e

    async def get_by_id(
        self, execution_id: UUID, project_id: UUID, user_id: UUID
    ) -> Optional[AgentExecution]:
        """Get agent execution by ID with project and user access validation."""
        start_time = time.time()

        try:
            # Validate project access first
            project_result = await self.session.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.created_by == user_id,
                    Project.is_deleted == False,
                )
            )
            project = project_result.scalar_one_or_none()
            if not project:
                return None

            # Get execution
            result = await self.session.execute(
                select(AgentExecution).where(
                    AgentExecution.id == execution_id,
                    AgentExecution.project_id == project_id,
                )
            )
            execution = result.scalar_one_or_none()

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "agent_execution_get_by_id", duration, execution is not None
            )

            return execution

        except SQLAlchemyError as e:
            logger.exception("Database error getting agent execution")
            raise HTTPException(status_code=500, detail="Database error") from e

    async def get_project_executions(
        self,
        project_id: UUID,
        user_id: UUID,
        page: int = 1,
        per_page: int = 20,
        agent_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> tuple[List[AgentExecution], int]:
        """Get project agent executions with pagination and filtering."""
        start_time = time.time()

        try:
            # Validate project access
            project_result = await self.session.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.created_by == user_id,
                    Project.is_deleted == False,
                )
            )
            project = project_result.scalar_one_or_none()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            # Build query
            query = select(AgentExecution).where(
                AgentExecution.project_id == project_id
            )

            if agent_type:
                query = query.where(AgentExecution.agent_type == agent_type)
            if status:
                query = query.where(AgentExecution.status == status)

            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.session.execute(count_query)
            total = total_result.scalar()

            # Apply pagination
            offset = (page - 1) * per_page
            query = (
                query.order_by(AgentExecution.started_at.desc())
                .offset(offset)
                .limit(per_page)
            )

            result = await self.session.execute(query)
            executions = result.scalars().all()

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "agent_execution_list", duration, True
            )

            return list(executions), total

        except SQLAlchemyError as e:
            logger.exception("Database error listing agent executions")
            raise HTTPException(status_code=500, detail="Database error") from e

    async def update(
        self,
        execution_id: UUID,
        project_id: UUID,
        user_id: UUID,
        update_data: AgentExecutionUpdate,
    ) -> Optional[AgentExecution]:
        """Update agent execution with access validation."""
        start_time = time.time()

        try:
            # Check if execution exists and user has access
            execution = await self.get_by_id(execution_id, project_id, user_id)
            if not execution:
                return None

            # Update fields
            update_values = {}
            if update_data.status is not None:
                update_values["status"] = update_data.status
                # Set completed_at if status is final
                if update_data.status in ["completed", "failed", "cancelled"]:
                    update_values["completed_at"] = datetime.utcnow()
            if update_data.output_data is not None:
                update_values["output_data"] = update_data.output_data
            if update_data.error_message is not None:
                update_values["error_message"] = update_data.error_message

            if not update_values:
                return execution  # No changes needed

            # Perform update
            await self.session.execute(
                update(AgentExecution)
                .where(AgentExecution.id == execution_id)
                .values(**update_values)
            )

            # Commit the transaction
            await self.session.commit()

            await self.session.refresh(execution)

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "agent_execution_update", duration, True
            )

            logger.info(
                "Agent execution updated",
                execution_id=str(execution_id),
                project_id=str(project_id),
                updated_fields=list(update_values.keys()),
                duration_ms=duration,
            )

            return execution

        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.exception("Database error updating agent execution")
            raise HTTPException(status_code=500, detail="Database error") from e

    async def get_metrics(
        self, project_id: UUID, user_id: UUID, days: int = 30
    ) -> Dict[str, Any]:
        """Get agent execution metrics for a project."""
        start_time = time.time()

        try:
            # Validate project access
            project_result = await self.session.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.created_by == user_id,
                    Project.is_deleted == False,
                )
            )
            project = project_result.scalar_one_or_none()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Get metrics
            metrics_query = select(
                func.count(AgentExecution.id).label("total_executions"),
                func.sum(
                    case((AgentExecution.status == "completed", 1), else_=0)
                ).label("successful_executions"),
                func.sum(case((AgentExecution.status == "failed", 1), else_=0)).label(
                    "failed_executions"
                ),
                func.avg(
                    func.extract(
                        "epoch",
                        func.coalesce(AgentExecution.completed_at, datetime.utcnow())
                        - AgentExecution.started_at,
                    )
                ).label("avg_execution_time"),
            ).where(
                AgentExecution.project_id == project_id,
                AgentExecution.started_at >= start_date,
            )

            metrics_result = await self.session.execute(metrics_query)
            metrics = metrics_result.first()

            # Get executions by agent type
            type_query = (
                select(
                    AgentExecution.agent_type,
                    func.count(AgentExecution.id).label("count"),
                )
                .where(
                    AgentExecution.project_id == project_id,
                    AgentExecution.started_at >= start_date,
                )
                .group_by(AgentExecution.agent_type)
            )

            type_result = await self.session.execute(type_query)
            executions_by_type = dict(type_result.all())

            # Get recent executions
            recent_query = (
                select(AgentExecution)
                .where(AgentExecution.project_id == project_id)
                .order_by(AgentExecution.started_at.desc())
                .limit(10)
            )

            recent_result = await self.session.execute(recent_query)
            recent_executions = recent_result.scalars().all()

            # Calculate success rate
            success_rate = 0.0
            if metrics.total_executions > 0:
                success_rate = (
                    metrics.successful_executions / metrics.total_executions
                ) * 100

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "agent_execution_metrics", duration, True
            )

            return {
                "total_executions": metrics.total_executions or 0,
                "successful_executions": metrics.successful_executions or 0,
                "failed_executions": metrics.failed_executions or 0,
                "average_execution_time_seconds": float(
                    metrics.avg_execution_time or 0
                ),
                "success_rate": success_rate,
                "executions_by_agent_type": executions_by_type,
                "recent_executions": list(recent_executions),
            }

        except SQLAlchemyError as e:
            logger.exception("Database error getting agent metrics")
            raise HTTPException(status_code=500, detail="Database error") from e


# API Endpoints
@router.post(
    "/projects/{project_id}/agents/executions",
    response_model=AgentExecutionRead,
    status_code=201,
)
async def create_agent_execution(
    project_id: UUID,
    execution_data: AgentExecutionCreate,
    user_id: UUID = Query(..., description="User ID for access validation"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Create a new agent execution.

    Args:
        project_id: Project UUID
        execution_data: Agent execution data
        user_id: User ID for access validation
        session: Database session

    Returns:
        Created agent execution data
    """
    # Ensure project_id matches
    execution_data.project_id = project_id

    repo = AgentExecutionRepository(session)
    execution = await repo.create(execution_data, user_id)
    return AgentExecutionRead.model_validate(execution)


@router.get(
    "/projects/{project_id}/agents/executions/{execution_id}",
    response_model=AgentExecutionRead,
)
async def get_agent_execution(
    project_id: UUID,
    execution_id: UUID,
    user_id: UUID = Query(..., description="User ID for access validation"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Get agent execution by ID.

    Args:
        project_id: Project UUID
        execution_id: Agent execution UUID
        user_id: User ID for access validation
        session: Database session

    Returns:
        Agent execution data
    """
    repo = AgentExecutionRepository(session)
    execution = await repo.get_by_id(execution_id, project_id, user_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Agent execution not found")
    return AgentExecutionRead.model_validate(execution)


@router.get(
    "/projects/{project_id}/agents/executions", response_model=AgentExecutionList
)
async def list_agent_executions(
    project_id: UUID,
    user_id: UUID = Query(..., description="User ID for access validation"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    List project agent executions with pagination.

    Args:
        project_id: Project UUID
        user_id: User ID for access validation
        page: Page number
        per_page: Items per page
        agent_type: Optional agent type filter
        status: Optional status filter
        session: Database session

    Returns:
        Paginated agent execution list
    """
    repo = AgentExecutionRepository(session)
    executions, total = await repo.get_project_executions(
        project_id, user_id, page, per_page, agent_type, status
    )

    total_pages = (total + per_page - 1) // per_page

    return AgentExecutionList(
        executions=[AgentExecutionRead.model_validate(e) for e in executions],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.put(
    "/projects/{project_id}/agents/executions/{execution_id}",
    response_model=AgentExecutionRead,
)
async def update_agent_execution(
    project_id: UUID,
    execution_id: UUID,
    update_data: AgentExecutionUpdate,
    user_id: UUID = Query(..., description="User ID for access validation"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Update agent execution.

    Args:
        project_id: Project UUID
        execution_id: Agent execution UUID
        update_data: Update data
        user_id: User ID for access validation
        session: Database session

    Returns:
        Updated agent execution data
    """
    repo = AgentExecutionRepository(session)
    execution = await repo.update(execution_id, project_id, user_id, update_data)
    if not execution:
        raise HTTPException(status_code=404, detail="Agent execution not found")
    return AgentExecutionRead.model_validate(execution)


@router.get("/projects/{project_id}/agents/metrics", response_model=AgentMetrics)
async def get_agent_metrics(
    project_id: UUID,
    user_id: UUID = Query(..., description="User ID for access validation"),
    days: int = Query(30, ge=1, le=365, description="Number of days for metrics"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Get agent execution metrics for a project.

    Args:
        project_id: Project UUID
        user_id: User ID for access validation
        days: Number of days for metrics calculation
        session: Database session

    Returns:
        Agent execution metrics
    """
    repo = AgentExecutionRepository(session)
    metrics = await repo.get_metrics(project_id, user_id, days)

    return AgentMetrics(
        total_executions=metrics["total_executions"],
        successful_executions=metrics["successful_executions"],
        failed_executions=metrics["failed_executions"],
        average_execution_time_seconds=metrics["average_execution_time_seconds"],
        success_rate=metrics["success_rate"],
        executions_by_agent_type=metrics["executions_by_agent_type"],
        recent_executions=[
            AgentExecutionRead.model_validate(e) for e in metrics["recent_executions"]
        ],
    )
