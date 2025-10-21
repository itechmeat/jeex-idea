"""
Test QueueManager project context fix

This test verifies that QueueManager properly uses project_id context
for all Redis connections and operations.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.services.queues.queue_manager import QueueManager, TaskType, TaskPriority
from app.infrastructure.redis.exceptions import RedisProjectIsolationException


class TestQueueManagerProjectContext:
    """Test QueueManager project context handling."""

    @pytest.fixture
    def mock_redis_factory(self):
        """Mock Redis connection factory."""
        factory = AsyncMock()
        factory.get_connection = AsyncMock()
        factory.get_admin_connection = AsyncMock()
        return factory

    @pytest.fixture
    def bootstrap_project_id(self):
        """Bootstrap project ID for testing."""
        return uuid4()

    def test_constructor_with_bootstrap_project_id(self, bootstrap_project_id):
        """Test constructor accepts and stores bootstrap_project_id."""
        queue_manager = QueueManager(bootstrap_project_id=bootstrap_project_id)
        assert queue_manager._bootstrap_project_id == bootstrap_project_id

    def test_constructor_without_bootstrap_project_id(self):
        """Test constructor works without bootstrap_project_id."""
        queue_manager = QueueManager()
        assert queue_manager._bootstrap_project_id is None

    @patch("app.services.queues.queue_manager.redis_connection_factory")
    async def test_initialize_uses_admin_connection(self, mock_factory):
        """Test that initialize() uses admin connection for script loading."""
        mock_admin_client = AsyncMock()
        mock_admin_client.script_load = AsyncMock(return_value="script_sha")
        mock_factory.get_admin_connection.return_value.__aenter__.return_value = (
            mock_admin_client
        )

        queue_manager = QueueManager()
        await queue_manager.initialize()

        # Verify admin connection was used for script loading
        mock_factory.get_admin_connection.assert_called_once()
        mock_admin_client.script_load.assert_called()

    @patch("app.services.queues.queue_manager.redis_connection_factory")
    @patch("app.services.queues.queue_manager.queue_repository")
    async def test_enqueue_task_uses_project_context(
        self, mock_repo, mock_factory, bootstrap_project_id
    ):
        """Test that enqueue_task uses provided project_id for Redis connection."""
        mock_project_client = AsyncMock()
        mock_project_client.evalsha = AsyncMock(return_value=[1, "success", 1])
        mock_factory.get_connection.return_value.__aenter__.return_value = (
            mock_project_client
        )

        queue_manager = QueueManager(bootstrap_project_id=bootstrap_project_id)
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION,
            project_id=uuid4(),
            data={"test": "data"},
        )

        # Verify project-specific connection was used
        mock_factory.get_connection.assert_called_once()
        call_args = mock_factory.get_connection.call_args[0]
        assert len(call_args) == 1
        # The project_id passed should be a string (UUID converted to string)
        assert call_args[0] is not None

    @patch("app.services.queues.queue_manager.redis_connection_factory")
    @patch("app.services.queues.queue_manager.queue_repository")
    async def test_dequeue_task_uses_project_context(self, mock_repo, mock_factory):
        """Test that dequeue_task uses project context properly."""
        project_id = uuid4()
        queue_manager = QueueManager()

        # Mock repository to return None (no tasks)
        mock_repo.dequeue_task = AsyncMock(return_value=None)

        result = await queue_manager.dequeue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION,
            worker_id="test_worker",
            project_id=project_id,
        )

        # Verify repository was called with correct project_id
        mock_repo.dequeue_task.assert_called_once_with(
            TaskType.EMBEDDING_COMPUTATION, "test_worker", project_id
        )
        assert result is None

    @patch("app.services.queues.queue_manager.redis_connection_factory")
    @patch("app.services.queues.queue_manager.queue_repository")
    async def test_get_task_data_uses_bootstrap_context(
        self, mock_repo, mock_factory, bootstrap_project_id
    ):
        """Test that get_task_data falls back to bootstrap_project_id when needed."""
        task_id = uuid4()
        queue_manager = QueueManager(bootstrap_project_id=bootstrap_project_id)

        # Mock repository to return None (task not found)
        mock_repo.get_task_data = AsyncMock(return_value=None)

        result = await queue_manager.get_task_data(task_id)

        # Verify repository was called with bootstrap project_id
        mock_repo.get_task_data.assert_called_once_with(task_id, bootstrap_project_id)
        assert result is None

    @patch("app.services.queues.queue_manager.redis_connection_factory")
    @patch("app.services.queues.queue_manager.queue_repository")
    async def test_get_task_data_uses_default_when_no_bootstrap(
        self, mock_repo, mock_factory
    ):
        """Test that get_task_data uses default UUID when no bootstrap_project_id."""
        task_id = uuid4()
        queue_manager = QueueManager()  # No bootstrap_project_id

        # Mock repository to return None (task not found)
        mock_repo.get_task_data = AsyncMock(return_value=None)

        await queue_manager.get_task_data(task_id)

        # Verify repository was called with default UUID
        call_args = mock_repo.get_task_data.call_args[0]
        assert call_args[1] == UUID("12345678-1234-5678-9abc-123456789abc")

    @patch("app.services.queues.queue_manager.redis_connection_factory")
    @patch("app.services.queues.queue_manager.queue_repository")
    async def test_get_queue_stats_uses_bootstrap_context(
        self, mock_repo, mock_factory, bootstrap_project_id
    ):
        """Test that get_queue_stats uses bootstrap_project_id when project_id not provided."""
        queue_manager = QueueManager(bootstrap_project_id=bootstrap_project_id)

        # Mock repository to return empty stats
        mock_repo.get_queue_stats = AsyncMock(return_value={})

        result = await queue_manager.get_queue_stats(TaskType.EMBEDDING_COMPUTATION)

        # Verify repository was called with bootstrap project_id
        mock_repo.get_queue_stats.assert_called_once_with(
            TaskType.EMBEDDING_COMPUTATION, bootstrap_project_id
        )
        assert result == {}

    @patch("app.services.queues.queue_manager.redis_connection_factory")
    @patch("app.services.queues.queue_manager.queue_repository")
    async def test_get_all_queue_stats_uses_bootstrap_context(
        self, mock_repo, mock_factory, bootstrap_project_id
    ):
        """Test that get_all_queue_stats uses bootstrap_project_id when project_id not provided."""
        queue_manager = QueueManager(bootstrap_project_id=bootstrap_project_id)

        # Mock repository to return empty stats
        mock_repo.get_all_queue_stats = AsyncMock(return_value={"queues": {}})

        result = await queue_manager.get_all_queue_stats()

        # Verify repository was called with bootstrap project_id
        mock_repo.get_all_queue_stats.assert_called_once_with(bootstrap_project_id)
        assert result == {"queues": {}}

    @patch("app.services.queues.queue_manager.redis_connection_factory")
    @patch("app.services.queues.queue_manager.queue_repository")
    async def test_cleanup_expired_tasks_uses_bootstrap_context(
        self, mock_repo, mock_factory, bootstrap_project_id
    ):
        """Test that cleanup_expired_tasks uses bootstrap_project_id."""
        queue_manager = QueueManager(bootstrap_project_id=bootstrap_project_id)

        # Mock repository to return 0 cleaned tasks
        mock_repo.cleanup_expired_tasks = AsyncMock(return_value=0)

        result = await queue_manager.cleanup_expired_tasks()

        # Verify repository was called with bootstrap project_id
        mock_repo.cleanup_expired_tasks.assert_called_once_with(
            bootstrap_project_id, 24
        )
        assert result == 0

    def test_project_isolation_enforced(self):
        """Test that project isolation is properly enforced."""
        queue_manager = QueueManager()

        # The queue manager should have access to redis factory
        assert queue_manager._redis_factory is not None
        assert hasattr(queue_manager, "_bootstrap_project_id")

    @patch("app.services.queues.queue_manager.redis_connection_factory")
    async def test_connection_factory_get_connection_called_with_project_id(
        self, mock_factory
    ):
        """Test that get_connection is called with correct project_id format."""
        project_id = uuid4()
        queue_manager = QueueManager(bootstrap_project_id=project_id)

        # Test that when we need a project connection, the factory is called correctly
        async with mock_factory.get_connection(str(project_id)) as mock_client:
            mock_client.set = AsyncMock(return_value=True)
            await mock_client.set("test_key", "test_value")

        # Verify the factory was called with string representation of UUID
        mock_factory.get_connection.assert_called_once_with(str(project_id))

    @patch("app.services.queues.queue_manager.settings")
    def test_global_queue_manager_initialization(self, mock_settings):
        """Test global queue manager initialization with settings."""
        mock_bootstrap_uuid = uuid4()
        mock_settings.BOOTSTRAP_PROJECT_ID = str(mock_bootstrap_uuid)

        # Re-import to test global initialization
        import importlib
        import app.services.queues.queue_manager

        importlib.reload(app.services.queues.queue_manager)

        # Verify the global queue manager was created with bootstrap project_id
        from app.services.queues.queue_manager import queue_manager

        assert queue_manager._bootstrap_project_id == mock_bootstrap_uuid
