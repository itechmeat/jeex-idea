"""
Queue Manager Tests

Unit tests for queue management functionality.
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta

from ...queue_manager import QueueManager, TaskData, TaskType, TaskPriority, TaskStatus


class TestQueueManager:
    """Test cases for QueueManager class."""

    @pytest.fixture
    async def queue_manager(self):
        """Create queue manager instance for testing."""
        manager = QueueManager()
        await manager.initialize()
        return manager

    @pytest.fixture
    def sample_task_data(self):
        """Create sample task data for testing."""
        return TaskData(
            task_type=TaskType.EMBEDDING_COMPUTATION,
            project_id=uuid4(),
            priority=TaskPriority.NORMAL,
            data={"document_id": str(uuid4()), "text": "Sample text for embedding"},
        )

    @pytest.mark.asyncio
    async def test_enqueue_task(self, queue_manager, sample_task_data):
        """Test task enqueue functionality."""
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION,
            project_id=sample_task_data.project_id,
            data=sample_task_data.data,
            priority=TaskPriority.NORMAL,
        )

        assert task_id is not None
        assert isinstance(task_id, uuid4)

    @pytest.mark.asyncio
    async def test_enqueue_with_priority(self, queue_manager):
        """Test task enqueue with different priorities."""
        project_id = uuid4()
        task_ids = []

        # Enqueue tasks with different priorities
        priorities = [
            TaskPriority.LOW,
            TaskPriority.NORMAL,
            TaskPriority.HIGH,
            TaskPriority.CRITICAL,
        ]
        for priority in priorities:
            task_id = await queue_manager.enqueue_task(
                task_type=TaskType.EMBEDDING_COMPUTATION,
                project_id=project_id,
                data={"priority": priority.value},
                priority=priority,
            )
            task_ids.append(task_id)

        assert len(task_ids) == len(priorities)
        assert all(isinstance(tid, uuid4) for tid in task_ids)

    @pytest.mark.asyncio
    async def test_dequeue_task(self, queue_manager):
        """Test task dequeue functionality."""
        project_id = uuid4()
        worker_id = "test_worker_1"

        # Enqueue a task first
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION,
            project_id=project_id,
            data={"test": "dequeue"},
            priority=TaskPriority.NORMAL,
        )

        # Dequeue the task
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION, worker_id=worker_id
        )

        assert task_data is not None
        assert task_data.task_id == task_id
        assert task_data.project_id == project_id
        assert task_data.data["test"] == "dequeue"

    @pytest.mark.asyncio
    async def test_priority_ordering(self, queue_manager):
        """Test that tasks are dequeued in priority order."""
        project_id = uuid4()
        worker_id = "test_worker_priority"

        # Enqueue tasks with different priorities
        task_data = [
            ("low", TaskPriority.LOW),
            ("critical", TaskPriority.CRITICAL),
            ("normal", TaskPriority.NORMAL),
            ("high", TaskPriority.HIGH),
        ]

        # Enqueue in random order
        import random

        random.shuffle(task_data)

        task_ids = []
        for name, priority in task_data:
            task_id = await queue_manager.enqueue_task(
                task_type=TaskType.AGENT_TASK,
                project_id=project_id,
                data={"name": name},
                priority=priority,
            )
            task_ids.append((task_id, name, priority))

        # Dequeue tasks - should come out in priority order (CRITICAL > HIGH > NORMAL > LOW)
        expected_order = ["critical", "high", "normal", "low"]
        dequeued_order = []

        for _ in range(len(expected_order)):
            task_data = await queue_manager.dequeue_task(
                task_type=TaskType.AGENT_TASK, worker_id=worker_id
            )
            if task_data:
                dequeued_order.append(task_data.data["name"])

        assert dequeued_order == expected_order

    @pytest.mark.asyncio
    async def test_complete_task(self, queue_manager):
        """Test task completion functionality."""
        project_id = uuid4()
        worker_id = "test_worker_complete"

        # Enqueue and dequeue a task
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.DOCUMENT_EXPORT,
            project_id=project_id,
            data={"export_path": "/tmp/test.pdf"},
        )

        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.DOCUMENT_EXPORT, worker_id=worker_id
        )

        # Complete the task
        result = {"status": "completed", "path": "/tmp/test.pdf"}
        success = await queue_manager.complete_task(
            task_id=task_id, result=result, worker_id=worker_id
        )

        assert success is True

        # Check task status
        status = await queue_manager.get_task_status(task_id)
        assert status is not None
        assert status["status"] == TaskStatus.COMPLETED.value
        assert status["worker_id"] == worker_id

    @pytest.mark.asyncio
    async def test_fail_task_with_retry(self, queue_manager):
        """Test task failure with retry logic."""
        project_id = uuid4()
        worker_id = "test_worker_retry"

        # Enqueue and dequeue a task
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.AGENT_TASK,
            project_id=project_id,
            data={"test": "retry"},
            max_attempts=3,
        )

        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.AGENT_TASK, worker_id=worker_id
        )

        # Fail the task with retry enabled
        error_message = "Temporary failure"
        success = await queue_manager.fail_task(
            task_id=task_id, error=error_message, worker_id=worker_id, retry=True
        )

        assert success is True

        # Check task status should be RETRYING
        status = await queue_manager.get_task_status(task_id)
        assert status is not None
        assert status["status"] == TaskStatus.RETRYING.value
        assert status["error"] == error_message

    @pytest.mark.asyncio
    async def test_fail_task_no_retry(self, queue_manager):
        """Test task failure without retry."""
        project_id = uuid4()
        worker_id = "test_worker_no_retry"

        # Enqueue and dequeue a task
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION,
            project_id=project_id,
            data={"test": "no_retry"},
            max_attempts=1,
        )

        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION, worker_id=worker_id
        )

        # Fail the task without retry
        error_message = "Permanent failure"
        success = await queue_manager.fail_task(
            task_id=task_id, error=error_message, worker_id=worker_id, retry=False
        )

        assert success is True

        # Check task status should be FAILED
        status = await queue_manager.get_task_status(task_id)
        assert status is not None
        assert status["status"] == TaskStatus.FAILED.value
        assert status["error"] == error_message

    @pytest.mark.asyncio
    async def test_cancel_task(self, queue_manager):
        """Test task cancellation."""
        project_id = uuid4()

        # Enqueue a task
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.BATCH_PROCESSING,
            project_id=project_id,
            data={"test": "cancel"},
        )

        # Cancel the task
        success = await queue_manager.cancel_task(task_id)
        assert success is True

        # Check task status
        status = await queue_manager.get_task_status(task_id)
        assert status is not None
        assert status["status"] == TaskStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_get_task_data(self, queue_manager):
        """Test retrieving task data."""
        project_id = uuid4()
        test_data = {"document_id": str(uuid4()), "action": "process"}

        # Enqueue a task
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.NOTIFICATION, project_id=project_id, data=test_data
        )

        # Get task data
        retrieved_data = await queue_manager.get_task_data(task_id)
        assert retrieved_data is not None
        assert retrieved_data.task_id == task_id
        assert retrieved_data.project_id == project_id
        assert retrieved_data.data == test_data

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, queue_manager):
        """Test getting queue statistics."""
        project_id = uuid4()

        # Enqueue some tasks
        task_types = [
            TaskType.EMBEDDING_COMPUTATION,
            TaskType.AGENT_TASK,
            TaskType.DOCUMENT_EXPORT,
        ]
        for task_type in task_types:
            await queue_manager.enqueue_task(
                task_type=task_type, project_id=project_id, data={"test": "stats"}
            )

        # Get stats for each queue
        for task_type in task_types:
            stats = await queue_manager.get_queue_stats(task_type)
            assert stats is not None
            assert "task_type" in stats
            assert stats["task_type"] == task_type.value
            assert "total_queued" in stats
            assert stats["total_queued"] >= 1

    @pytest.mark.asyncio
    async def test_get_all_queue_stats(self, queue_manager):
        """Test getting all queue statistics."""
        project_id = uuid4()

        # Enqueue tasks in different queues
        for task_type in [TaskType.EMBEDDING_COMPUTATION, TaskType.AGENT_TASK]:
            await queue_manager.enqueue_task(
                task_type=task_type, project_id=project_id, data={"test": "all_stats"}
            )

        # Get all stats
        all_stats = await queue_manager.get_all_queue_stats()
        assert all_stats is not None
        assert "queues" in all_stats
        assert "total_tasks" in all_stats
        assert all_stats["total_tasks"] >= 2

    @pytest.mark.asyncio
    async def test_scheduled_tasks(self, queue_manager):
        """Test scheduled task functionality."""
        project_id = uuid4()

        # Schedule task for future execution
        scheduled_time = datetime.utcnow() + timedelta(minutes=5)
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.CLEANUP,
            project_id=project_id,
            data={"test": "scheduled"},
            scheduled_at=scheduled_time,
        )

        assert task_id is not None

        # Get task data to verify scheduling
        task_data = await queue_manager.get_task_data(task_id)
        assert task_data is not None
        assert task_data.scheduled_at is not None
        assert task_data.scheduled_time >= scheduled_time - timedelta(seconds=1)

    @pytest.mark.asyncio
    async def test_project_isolation(self, queue_manager):
        """Test project isolation in queues."""
        project1_id = uuid4()
        project2_id = uuid4()
        worker_id = "test_worker_isolation"

        # Enqueue tasks for different projects
        task1_id = await queue_manager.enqueue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION,
            project_id=project1_id,
            data={"project": 1},
        )

        task2_id = await queue_manager.enqueue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION,
            project_id=project2_id,
            data={"project": 2},
        )

        # Dequeue with specific project ID should get that project's task
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION,
            worker_id=worker_id,
            project_id=project1_id,
        )

        assert task_data is not None
        assert task_data.project_id == project1_id
        assert task_data.data["project"] == 1


if __name__ == "__main__":
    pytest.main([__file__])
