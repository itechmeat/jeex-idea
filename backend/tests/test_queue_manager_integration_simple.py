"""
Simple integration test for QueueManager project context fix

This test verifies the basic QueueManager functionality with project context.
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from app.services.queues.queue_manager import (
    QueueManager,
    TaskType,
    TaskPriority,
    TaskStatus,
    TaskData,
)


def test_queue_manager_accepts_bootstrap_project_id():
    """Test that QueueManager constructor properly accepts bootstrap_project_id."""
    bootstrap_project_id = uuid4()

    # This should not raise any exception
    queue_manager = QueueManager(bootstrap_project_id=bootstrap_project_id)

    # Verify the bootstrap project ID is stored
    assert queue_manager._bootstrap_project_id == bootstrap_project_id


def test_queue_manager_works_without_bootstrap_project_id():
    """Test that QueueManager works without bootstrap_project_id (backward compatibility)."""
    # This should not raise any exception
    queue_manager = QueueManager()

    # Verify the bootstrap project ID is None
    assert queue_manager._bootstrap_project_id is None


@patch("app.services.queues.queue_manager.redis_connection_factory")
async def test_queue_manager_enqueue_with_mock(mock_factory):
    """Test QueueManager enqueue with mocked dependencies."""
    # Setup mocks
    mock_project_client = AsyncMock()
    mock_project_client.evalsha = AsyncMock(return_value=[1, "success", 1])
    mock_factory.get_connection.return_value.__aenter__.return_value = (
        mock_project_client
    )
    mock_factory.get_admin_connection = AsyncMock()
    mock_admin_client = AsyncMock()
    mock_admin_client.script_load = AsyncMock(return_value="script_sha")
    mock_factory.get_admin_connection.return_value.__aenter__.return_value = (
        mock_admin_client
    )

    # Create queue manager
    queue_manager = QueueManager()
    project_id = uuid4()

    # Test enqueue operation
    task_id = await queue_manager.enqueue_task(
        task_type=TaskType.EMBEDDING_COMPUTATION,
        project_id=project_id,
        data={"test": "data"},
        priority=TaskPriority.NORMAL,
    )

    # Verify task ID was generated
    assert task_id is not None
    assert isinstance(task_id, UUID)

    # Verify get_connection was called with project_id
    mock_factory.get_connection.assert_called_once()
    call_args = mock_factory.get_connection.call_args[0]
    assert len(call_args) == 1
    assert call_args[0] == str(project_id)


def test_global_queue_manager_can_be_created():
    """Test that the global queue manager instance can be created successfully."""
    from app.services.queues.queue_manager import queue_manager

    # Should be able to import without errors
    assert queue_manager is not None
    assert isinstance(queue_manager, QueueManager)


def test_task_data_model_includes_project_id():
    """Test that TaskData model includes and validates project_id."""
    project_id = uuid4()

    task_data = {
        "task_type": TaskType.EMBEDDING_COMPUTATION,
        "project_id": project_id,
        "priority": TaskPriority.NORMAL,
        "data": {"test": "data"},
    }

    # Should create TaskData without errors
    task = TaskData(**task_data)

    # Verify project_id is properly set
    assert task.project_id == project_id
    assert isinstance(task.project_id, UUID)


def test_task_types_and_priorities_are_available():
    """Test that task types and priorities are properly defined."""
    # Verify task types
    assert TaskType.EMBEDDING_COMPUTATION == "embedding_computation"
    assert TaskType.AGENT_TASK == "agent_task"
    assert TaskType.DOCUMENT_EXPORT == "document_export"

    # Verify priorities
    assert TaskPriority.LOW == 1
    assert TaskPriority.NORMAL == 5
    assert TaskPriority.HIGH == 10
    assert TaskPriority.CRITICAL == 20
    assert TaskPriority.URGENT == 50

    # Verify task priorities can be compared
    assert TaskPriority.URGENT > TaskPriority.CRITICAL
    assert TaskPriority.HIGH > TaskPriority.NORMAL
    assert TaskPriority.NORMAL > TaskPriority.LOW


def test_task_status_enum():
    """Test that TaskStatus enum has all expected values."""
    expected_statuses = [
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.RETRYING,
        TaskStatus.DEAD_LETTER,
    ]

    # Verify all expected statuses exist
    for status in expected_statuses:
        assert status in TaskStatus

    # Verify values are strings
    for status in TaskStatus:
        assert isinstance(status.value, str)
