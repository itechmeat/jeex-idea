"""
Test for Dead Letter Queue fixes to verify critical issues are resolved
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.queues.dead_letter import DeadLetterQueue, DeadLetterTask
from app.services.queues.queue_manager import TaskData, TaskType, TaskPriority


class TestDeadLetterQueueFixes:
    """Test critical fixes in dead letter queue."""

    @pytest.fixture
    def sample_task_data(self):
        """Create sample task data for testing."""
        return TaskData(
            task_id=uuid4(),
            task_type=TaskType.EMBEDDING_COMPUTATION,
            project_id=uuid4(),
            data={"text": "sample text", "chunks": ["chunk1", "chunk2"]},
            priority=TaskPriority.NORMAL,
            max_attempts=3,
            metadata={"source": "test"},
        )

    @pytest.fixture
    def dead_letter_queue(self):
        """Create dead letter queue instance."""
        return DeadLetterQueue()

    @pytest.mark.asyncio
    async def test_project_id_required_in_all_methods(
        self, dead_letter_queue, sample_task_data
    ):
        """Test that project_id is required parameter in all methods."""

        # Test get_task requires project_id
        with pytest.raises(ValueError, match="project_id is required"):
            await dead_letter_queue.get_task(None, uuid4())

        # Test list_tasks requires project_id
        with pytest.raises(ValueError, match="project_id is required"):
            await dead_letter_queue.list_tasks(None)

        # Test retry_task requires project_id
        with pytest.raises(ValueError, match="project_id is required"):
            await dead_letter_queue.retry_task(None, uuid4())

        # Test remove_task requires project_id
        with pytest.raises(ValueError, match="project_id is required"):
            await dead_letter_queue.remove_task(None, uuid4())

        # Test get_statistics requires project_id
        with pytest.raises(ValueError, match="project_id is required"):
            await dead_letter_queue.get_statistics(None)

        # Test process_auto_retries requires project_id
        with pytest.raises(ValueError, match="project_id is required"):
            await dead_letter_queue.process_auto_retries(None)

        # Test cleanup_old_tasks requires project_id
        with pytest.raises(ValueError, match="project_id is required"):
            await dead_letter_queue.cleanup_old_tasks(None)

    @pytest.mark.asyncio
    async def test_project_isolation_in_key_patterns(
        self, dead_letter_queue, sample_task_data
    ):
        """Test that all keys include project prefix."""
        project_id = uuid4()
        task_id = uuid4()

        # Mock Redis connection factory
        mock_redis = AsyncMock()
        mock_connection_factory = AsyncMock()
        mock_connection_factory.get_connection.return_value.__aenter__.return_value = (
            mock_redis
        )

        dead_letter_queue._redis_factory = mock_connection_factory

        # Test get_task key pattern
        await dead_letter_queue.get_task(project_id, task_id)
        expected_key = f"proj:{project_id}:dead_letter_queue:task:{task_id}"
        mock_redis.get.assert_called_with(expected_key)

        # Test remove_task key pattern
        mock_redis.reset_mock()
        await dead_letter_queue.remove_task(project_id, task_id)
        mock_redis.delete.assert_called_with(expected_key)

    @pytest.mark.asyncio
    async def test_scan_iter_usage_instead_of_keys(
        self, dead_letter_queue, sample_task_data
    ):
        """Test that scan_iter is used instead of blocking KEYS command."""
        project_id = uuid4()

        # Mock Redis connection factory with scan_iter
        mock_redis = AsyncMock()
        mock_redis.scan_iter.return_value = []
        mock_connection_factory = AsyncMock()
        mock_connection_factory.get_connection.return_value.__aenter__.return_value = (
            mock_redis
        )

        dead_letter_queue._redis_factory = mock_connection_factory

        # Test list_tasks uses scan_iter
        await dead_letter_queue.list_tasks(project_id=project_id, limit=100)
        pattern = f"proj:{project_id}:dead_letter_queue:task:*"
        mock_redis.scan_iter.assert_called_with(match=pattern)

        # Test get_statistics uses scan_iter
        mock_redis.reset_mock()
        mock_redis.scan_iter.return_value = []
        await dead_letter_queue.get_statistics(project_id)
        mock_redis.scan_iter.assert_called_with(match=pattern)

    @pytest.mark.asyncio
    async def test_context_manager_usage(self, dead_letter_queue, sample_task_data):
        """Test that Redis operations are properly inside async with blocks."""
        project_id = uuid4()
        task_id = uuid4()

        # Mock Redis connection factory
        mock_redis = AsyncMock()
        mock_connection_factory = AsyncMock()
        mock_connection_factory.get_connection.return_value.__aenter__.return_value = (
            mock_redis
        )

        dead_letter_queue._redis_factory = mock_connection_factory

        # Test list_tasks properly uses context managers
        await dead_letter_queue.list_tasks(project_id=project_id, limit=100)

        # Verify get_connection was called
        assert mock_connection_factory.get_connection.call_count >= 1

        # Test get_statistics properly uses context managers
        mock_connection_factory.reset_mock()
        mock_redis.scan_iter.return_value = []
        await dead_letter_queue.get_statistics(project_id)

        # Verify get_connection was called
        assert mock_connection_factory.get_connection.call_count >= 1

    @pytest.mark.asyncio
    async def test_project_isolation_verification(
        self, dead_letter_queue, sample_task_data
    ):
        """Test project isolation verification in task retrieval."""
        project_id = uuid4()
        task_id = uuid4()
        wrong_project_id = uuid4()

        # Create a task belonging to wrong_project_id
        dead_letter_task = DeadLetterTask(
            original_task_id=task_id,
            task_type=TaskType.EMBEDDING_COMPUTATION,
            project_id=wrong_project_id,  # Different project
            original_data={"test": "data"},
            error_message="Test error",
            error_type="TestError",
            attempts=1,
            first_failed_at=datetime.utcnow(),
            last_failed_at=datetime.utcnow(),
        )

        # Mock Redis connection factory
        mock_redis = AsyncMock()
        mock_redis.get.return_value = dead_letter_task.model_dump_json()
        mock_connection_factory = AsyncMock()
        mock_connection_factory.get_connection.return_value.__aenter__.return_value = (
            mock_redis
        )

        dead_letter_queue._redis_factory = mock_connection_factory

        # Test get_task returns None for wrong project
        result = await dead_letter_queue.get_task(project_id, task_id)
        assert result is None

        # Test list_tasks skips tasks from wrong project
        mock_connection_factory.reset_mock()
        mock_redis.scan_iter.return_value = [
            f"proj:{project_id}:dead_letter_queue:task:{task_id}"
        ]
        mock_redis.get.return_value = dead_letter_task.model_dump_json()

        tasks = await dead_letter_queue.list_tasks(project_id, limit=100)
        assert len(tasks) == 0  # Should be empty due to project mismatch

    @pytest.mark.asyncio
    async def test_project_id_in_connections(self, dead_letter_queue, sample_task_data):
        """Test that get_connection is called with str(project_id)."""
        project_id = uuid4()

        # Mock Redis connection factory
        mock_redis = AsyncMock()
        mock_connection_factory = AsyncMock()
        mock_connection_factory.get_connection.return_value.__aenter__.return_value = (
            mock_redis
        )

        dead_letter_queue._redis_factory = mock_connection_factory

        # Test various methods use project_id in get_connection
        await dead_letter_queue.get_task(project_id, uuid4())
        mock_connection_factory.get_connection.assert_called_with(str(project_id))

        mock_connection_factory.reset_mock()
        await dead_letter_queue.remove_task(project_id, uuid4())
        mock_connection_factory.get_connection.assert_called_with(str(project_id))

        mock_connection_factory.reset_mock()
        await dead_letter_queue.list_tasks(project_id)
        mock_connection_factory.get_connection.assert_called_with(str(project_id))

        mock_connection_factory.reset_mock()
        await dead_letter_queue.get_statistics(project_id)
        mock_connection_factory.get_connection.assert_called_with(str(project_id))

    @pytest.mark.asyncio
    async def test_pydantic_model_validate_json(
        self, dead_letter_queue, sample_task_data
    ):
        """Test that model_validate_json is used instead of parse_raw."""
        project_id = uuid4()
        task_id = uuid4()

        # Create dead letter task
        dead_letter_task = DeadLetterTask(
            original_task_id=task_id,
            task_type=TaskType.EMBEDDING_COMPUTATION,
            project_id=project_id,
            original_data={"test": "data"},
            error_message="Test error",
            error_type="TestError",
            attempts=1,
            first_failed_at=datetime.utcnow(),
            last_failed_at=datetime.utcnow(),
        )

        # Mock Redis connection factory
        mock_redis = AsyncMock()
        mock_redis.get.return_value = dead_letter_task.model_dump_json()
        mock_connection_factory = AsyncMock()
        mock_connection_factory.get_connection.return_value.__aenter__.return_value = (
            mock_redis
        )

        dead_letter_queue._redis_factory = mock_connection_factory

        # Test get_task works with model_validate_json
        result = await dead_letter_queue.get_task(project_id, task_id)
        assert result is not None
        assert result.project_id == project_id
        assert result.original_task_id == task_id

    @pytest.mark.asyncio
    async def test_add_task_uses_project_isolation(
        self, dead_letter_queue, sample_task_data
    ):
        """Test that add_task method properly stores with project isolation."""

        # Mock the private methods
        with (
            patch.object(dead_letter_queue, "_store_dead_letter_task") as mock_store,
            patch.object(dead_letter_queue, "_update_stats") as mock_stats,
            patch.object(dead_letter_queue, "_send_alert") as mock_alert,
        ):
            await dead_letter_queue.add_task(
                sample_task_data,
                error="Test error",
                worker_id="test_worker",
                attempts=1,
                category="retry_exhausted",
                severity="medium",
            )

            # Verify _store_dead_letter_task was called
            mock_store.assert_called_once()

            # Get the stored task and verify it has correct project_id
            call_args = mock_store.call_args[0][
                0
            ]  # First positional argument (the task)
            assert call_args.project_id == sample_task_data.project_id
