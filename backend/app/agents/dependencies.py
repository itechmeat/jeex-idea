from __future__ import annotations

from fastapi import Depends
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_database_session
from .tracker import AgentExecutionTracker
from .state_manager import ExecutionStateManager
from .isolation import IsolationValidator
from .orchestrator import AgentOrchestrator


async def tracker_provider(
    project_id: UUID, session: AsyncSession = Depends(get_database_session)
) -> AgentExecutionTracker:
    """Provide AgentExecutionTracker instance.

    Args:
        project_id: Accepted to trigger upstream dependency validation in API layer;
                   intentionally unused in tracker instantiation as tracker operates
                   on execution_id which is already project-scoped.
        session: Database session.

    Returns:
        AgentExecutionTracker instance.
    """
    # project_id validated by upstream dependency; not used here
    _ = project_id
    return AgentExecutionTracker(session=session)


async def isolation_provider(
    session: AsyncSession = Depends(get_database_session),
) -> IsolationValidator:
    return IsolationValidator(session=session)


def state_manager_provider() -> ExecutionStateManager:
    return ExecutionStateManager()


async def orchestrator_provider(
    tracker: AgentExecutionTracker = Depends(tracker_provider),
    state_manager: ExecutionStateManager = Depends(state_manager_provider),
    isolation: IsolationValidator = Depends(isolation_provider),
) -> AgentOrchestrator:
    return AgentOrchestrator(
        tracker=tracker, state_manager=state_manager, isolation=isolation
    )
