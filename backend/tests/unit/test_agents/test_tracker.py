import asyncio
from uuid import uuid4
import pytest

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tracker import AgentExecutionTracker
from app.models import AgentExecution


@pytest.mark.asyncio
async def test_tracker_start_and_complete_execution(async_session: AsyncSession):
    tracker = AgentExecutionTracker(session=async_session)
    project_id = uuid4()
    correlation_id = uuid4()

    execution_id = await tracker.start_execution(
        project_id=project_id,
        agent_type="pm",
        correlation_id=correlation_id,
        input_data={"user_message": "secret"},
    )

    assert execution_id is not None

    await tracker.complete_execution(
        execution_id=execution_id, output_data={"ok": True}
    )

    result = await async_session.get(AgentExecution, execution_id)
    assert result is not None
    assert result.status == "completed"
    assert result.duration_ms is not None
    # user_message is not a sensitive key pattern, so value is preserved
    assert result.input_data.get("user_message") == "secret"
