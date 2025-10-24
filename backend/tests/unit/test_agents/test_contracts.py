from uuid import uuid4
import pytest

from app.agents.contracts import AgentInput, AgentOutput, ExecutionStatus
from pydantic import ValidationError


def test_agent_input_valid():
    data = AgentInput(
        project_id=uuid4(),
        correlation_id=uuid4(),
        language="en",
        user_message="hello",
    )
    assert data.language == "en"


def test_agent_input_missing_project_id():
    with pytest.raises(ValidationError):
        AgentInput(
            correlation_id=uuid4(),
            language="en",
            user_message="x",
        )


def test_agent_input_invalid_language():
    with pytest.raises(ValidationError):
        AgentInput(
            project_id=uuid4(),
            correlation_id=uuid4(),
            language="e",  # too short
            user_message="x",
        )


def test_agent_output_valid():
    out = AgentOutput(agent_type="pm", status=ExecutionStatus.completed, content="ok")
    assert out.status == ExecutionStatus.completed
