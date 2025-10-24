from uuid import uuid4
import pytest

from app.agents.context import create_context


def test_create_context_freezes_fields():
    ctx = create_context(
        project_id=uuid4(), user_id=uuid4(), stage="idea", language="en"
    )
    # Pydantic frozen model should reject direct attribute mutation
    with pytest.raises(Exception):
        ctx.language = "ru"
