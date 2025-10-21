"""
Queue Workers

Background task workers for processing queued tasks.
Provides worker pools, task execution, and health monitoring.
"""

import asyncio
import logging
import signal
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, List, Set
from uuid import UUID, uuid4

from opentelemetry import trace

from .queue_manager import queue_manager, TaskData, TaskType, TaskStatus
from .retry import ExponentialBackoffRetry
from .dead_letter import dead_letter_queue

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class QueueWorker:
    """
    Individual queue worker for processing tasks.

    Handles task execution, error handling, and retry logic.
    """

    def __init__(
        self,
        worker_id: str,
        task_types: List[TaskType],
        task_handlers: Dict[TaskType, Callable],
        max_concurrent_tasks: int = 5,
        poll_interval: float = 1.0,
        worker_timeout: int = 300,
    ):
        """
        Initialize queue worker.

        Args:
            worker_id: Unique worker identifier
            task_types: List of task types this worker can handle
            task_handlers: Mapping of task type to handler function
            max_concurrent_tasks: Maximum concurrent tasks
            poll_interval: Polling interval in seconds
            worker_timeout: Worker timeout in seconds
        """
        self.worker_id = worker_id
        self.task_types = task_types
        self.task_handlers = task_handlers
        self.max_concurrent_tasks = max_concurrent_tasks
        self.poll_interval = poll_interval
        self.worker_timeout = worker_timeout

        self._running = False
        self._current_tasks: Set[UUID] = set()
        self._task_semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._shutdown_event = asyncio.Event()
        self._stats = {
            "tasks_processed": 0,
            "tasks_failed": 0,
            "tasks_completed": 0,
            "start_time": None,
            "last_activity": None,
        }

    async def start(self) -> None:
        """Start the worker."""
        if self._running:
            return

        self._running = True
        self._stats["start_time"] = datetime.utcnow()

        logger.info(
            f"Starting worker {self.worker_id} for task types: {[t.value for t in self.task_types]}"
        )

        try:
            await self._worker_loop()
        except Exception as e:
            logger.error(f"Worker {self.worker_id} crashed: {e}")
            raise
        finally:
            await self._shutdown()

    async def stop(self, graceful_timeout: int = 30) -> None:
        """
        Stop the worker gracefully.

        Args:
            graceful_timeout: Timeout for graceful shutdown
        """
        logger.info(f"Stopping worker {self.worker_id}")

        self._running = False
        self._shutdown_event.set()

        # Wait for current tasks to complete
        if self._current_tasks:
            logger.info(f"Waiting for {len(self._current_tasks)} tasks to complete")

            try:
                await asyncio.wait_for(
                    self._wait_for_tasks_completion(), timeout=graceful_timeout
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Worker {self.worker_id} shutdown timeout, {len(self._current_tasks)} tasks still running"
                )

    async def _worker_loop(self) -> None:
        """Main worker loop."""
        while self._running:
            try:
                # Check if we can accept more tasks
                if len(self._current_tasks) >= self.max_concurrent_tasks:
                    await asyncio.sleep(self.poll_interval)
                    continue

                # Try to dequeue a task
                task_data = await self._dequeue_next_task()
                if task_data:
                    # Process task asynchronously
                    asyncio.create_task(self._process_task(task_data))
                else:
                    # No tasks available, wait before next poll
                    await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error in main loop: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _dequeue_next_task(self) -> Optional[TaskData]:
        """Dequeue next available task."""
        for task_type in self.task_types:
            try:
                task_data = await queue_manager.dequeue_task(
                    task_type=task_type,
                    worker_id=self.worker_id,
                    timeout_seconds=1,  # Non-blocking
                )
                if task_data:
                    return task_data
            except Exception as e:
                logger.warning(f"Failed to dequeue task of type {task_type.value}: {e}")

        return None

    async def _process_task(self, task_data: TaskData) -> None:
        """Process a single task."""
        task_id = task_data.task_id
        self._current_tasks.add(task_id)
        self._stats["last_activity"] = datetime.utcnow()

        with tracer.start_as_current_span("worker.process_task") as span:
            span.set_attribute("worker_id", self.worker_id)
            span.set_attribute("task_id", str(task_id))
            span.set_attribute("task_type", task_data.task_type.value)

            try:
                async with self._task_semaphore:
                    await self._execute_task(task_data)
                    self._stats["tasks_completed"] += 1

            except Exception as e:
                logger.error(f"Task {task_id} failed in worker {self.worker_id}: {e}")
                await self._handle_task_failure(task_data, str(e))
                self._stats["tasks_failed"] += 1
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

            finally:
                self._current_tasks.discard(task_id)
                self._stats["tasks_processed"] += 1

    async def _execute_task(self, task_data: TaskData) -> None:
        """Execute task with timeout and error handling."""
        handler = self.task_handlers.get(task_data.task_type)
        if not handler:
            raise ValueError(f"No handler for task type: {task_data.task_type}")

        # Execute task with timeout
        try:
            result = await asyncio.wait_for(
                handler(task_data), timeout=task_data.timeout_seconds
            )

            # Mark task as completed
            await queue_manager.complete_task(
                task_id=task_data.task_id, result=result, worker_id=self.worker_id
            )

            logger.debug(f"Task {task_data.task_id} completed successfully")

        except asyncio.TimeoutError:
            error_msg = (
                f"Task {task_data.task_id} timed out after {task_data.timeout_seconds}s"
            )
            raise Exception(error_msg)

    async def _handle_task_failure(self, task_data: TaskData, error: str) -> None:
        """Handle task failure with retry logic."""
        try:
            # Check if we should retry
            task_status = await queue_manager.get_task_status(task_data.task_id)
            current_attempts = task_status.get("attempts", 0) if task_status else 0

            if current_attempts < task_data.max_attempts:
                # Retry the task
                await queue_manager.fail_task(
                    task_id=task_data.task_id,
                    error=error,
                    worker_id=self.worker_id,
                    retry=True,
                )
                logger.info(
                    f"Task {task_data.task_id} scheduled for retry ({current_attempts + 1}/{task_data.max_attempts})"
                )
            else:
                # Move to dead letter queue
                await dead_letter_queue.add_task(
                    task_data=task_data,
                    error=error,
                    worker_id=self.worker_id,
                    attempts=current_attempts,
                )
                await queue_manager.fail_task(
                    task_id=task_data.task_id,
                    error=error,
                    worker_id=self.worker_id,
                    retry=False,
                )
                logger.warning(
                    f"Task {task_data.task_id} moved to dead letter queue after {current_attempts} attempts"
                )

        except Exception as e:
            logger.error(f"Failed to handle task failure for {task_data.task_id}: {e}")

    async def _wait_for_tasks_completion(self) -> None:
        """Wait for all current tasks to complete."""
        while self._current_tasks:
            await asyncio.sleep(0.1)

    async def _shutdown(self) -> None:
        """Perform worker shutdown cleanup."""
        logger.info(f"Worker {self.worker_id} shutdown complete")

    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics."""
        runtime = None
        if self._stats["start_time"]:
            runtime = (datetime.utcnow() - self._stats["start_time"]).total_seconds()

        return {
            "worker_id": self.worker_id,
            "running": self._running,
            "current_tasks": len(self._current_tasks),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "task_types": [t.value for t in self.task_types],
            "stats": self._stats.copy(),
            "runtime_seconds": runtime,
            "tasks_per_second": (
                self._stats["tasks_processed"] / runtime
                if runtime and runtime > 0
                else 0
            ),
        }


class WorkerPool:
    """
    Pool of queue workers with load balancing and health monitoring.

    Manages multiple workers, distributes tasks, and handles worker failures.
    """

    def __init__(
        self,
        pool_name: str,
        task_handlers: Dict[TaskType, Callable],
        workers_per_type: int = 2,
        max_concurrent_per_worker: int = 5,
    ):
        """
        Initialize worker pool.

        Args:
            pool_name: Pool identifier
            task_handlers: Mapping of task type to handler function
            workers_per_type: Number of workers per task type
            max_concurrent_per_worker: Max concurrent tasks per worker
        """
        self.pool_name = pool_name
        self.task_handlers = task_handlers
        self.workers_per_type = workers_per_type
        self.max_concurrent_per_worker = max_concurrent_per_worker

        self._workers: List[QueueWorker] = []
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._health_check_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the worker pool."""
        if self._running:
            return

        self._running = True
        logger.info(f"Starting worker pool {self.pool_name}")

        # Create workers for each task type
        for task_type, handler in self.task_handlers.items():
            for i in range(self.workers_per_type):
                worker_id = f"{self.pool_name}-{task_type.value}-{i}"
                worker = QueueWorker(
                    worker_id=worker_id,
                    task_types=[task_type],
                    task_handlers={task_type: handler},
                    max_concurrent_tasks=self.max_concurrent_per_worker,
                )
                self._workers.append(worker)

        # Start all workers
        worker_tasks = []
        for worker in self._workers:
            worker_tasks.append(asyncio.create_task(worker.start()))

        # Start health monitoring
        self._health_check_task = asyncio.create_task(self._health_monitor_loop())

        logger.info(
            f"Worker pool {self.pool_name} started with {len(self._workers)} workers"
        )

        # Wait for shutdown
        await self._shutdown_event.wait()

        # Stop all workers
        await self.stop()

    async def stop(self, graceful_timeout: int = 30) -> None:
        """
        Stop the worker pool.

        Args:
            graceful_timeout: Timeout for graceful shutdown
        """
        if not self._running:
            return

        logger.info(f"Stopping worker pool {self.pool_name}")
        self._running = False
        self._shutdown_event.set()

        # Stop health monitoring
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Stop all workers
        stop_tasks = []
        for worker in self._workers:
            stop_tasks.append(worker.stop(graceful_timeout))

        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

        logger.info(f"Worker pool {self.pool_name} stopped")

    async def _health_monitor_loop(self) -> None:
        """Monitor worker health and restart failed workers."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                # Check worker health
                unhealthy_workers = []
                for worker in self._workers:
                    stats = worker.get_stats()

                    # Check if worker is stuck (no activity for 5 minutes)
                    if (
                        stats["stats"]["last_activity"]
                        and (
                            datetime.utcnow() - stats["stats"]["last_activity"]
                        ).total_seconds()
                        > 300
                    ):
                        if stats["current_tasks"] > 0:
                            logger.warning(
                                f"Worker {worker.worker_id} appears stuck with {stats['current_tasks']} tasks"
                            )
                            unhealthy_workers.append(worker)

                # Restart unhealthy workers
                for worker in unhealthy_workers:
                    logger.warning(f"Restarting unhealthy worker {worker.worker_id}")
                    # In a real implementation, you would restart the worker
                    # For now, just log the issue

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get worker pool statistics."""
        total_stats = {
            "pool_name": self.pool_name,
            "running": self._running,
            "total_workers": len(self._workers),
            "total_current_tasks": 0,
            "total_processed": 0,
            "total_completed": 0,
            "total_failed": 0,
            "workers": [],
        }

        for worker in self._workers:
            worker_stats = worker.get_stats()
            total_stats["workers"].append(worker_stats)
            total_stats["total_current_tasks"] += worker_stats["current_tasks"]
            total_stats["total_processed"] += worker_stats["stats"]["tasks_processed"]
            total_stats["total_completed"] += worker_stats["stats"]["tasks_completed"]
            total_stats["total_failed"] += worker_stats["stats"]["tasks_failed"]

        # Calculate pool-wide metrics
        total_stats["success_rate"] = (
            total_stats["total_completed"] / total_stats["total_processed"]
            if total_stats["total_processed"] > 0
            else 0
        )

        return total_stats

    async def scale_workers(self, new_workers_per_type: int) -> None:
        """
        Scale the number of workers per task type.

        Args:
            new_workers_per_type: New number of workers per task type
        """
        if not self._running:
            raise RuntimeError("Cannot scale workers when pool is not running")

        logger.info(
            f"Scaling worker pool {self.pool_name} from {self.workers_per_type} to {new_workers_per_type} workers per type"
        )

        # TODO: Implement worker scaling logic
        # This would involve stopping excess workers or starting new ones
        self.workers_per_type = new_workers_per_type


# Default task handlers (to be implemented by application)
class DefaultTaskHandlers:
    """Default task handlers for common task types."""

    @staticmethod
    async def handle_embedding_computation(task_data: TaskData) -> Dict[str, Any]:
        """Handle embedding computation task."""
        # TODO: Implement embedding computation
        await asyncio.sleep(1)  # Simulate work
        return {"status": "completed", "embeddings_count": 42}

    @staticmethod
    async def handle_agent_task(task_data: TaskData) -> Dict[str, Any]:
        """Handle agent task."""
        # TODO: Implement agent task processing
        await asyncio.sleep(2)  # Simulate work
        return {"status": "completed", "agent_response": "Task completed"}

    @staticmethod
    async def handle_document_export(task_data: TaskData) -> Dict[str, Any]:
        """Handle document export task."""
        # TODO: Implement document export
        await asyncio.sleep(3)  # Simulate work
        return {"status": "completed", "export_path": "/tmp/export.pdf"}

    @staticmethod
    async def handle_batch_processing(task_data: TaskData) -> Dict[str, Any]:
        """Handle batch processing task."""
        # TODO: Implement batch processing
        await asyncio.sleep(5)  # Simulate work
        return {"status": "completed", "processed_items": 100}

    @staticmethod
    async def handle_notification(task_data: TaskData) -> Dict[str, Any]:
        """Handle notification task."""
        # TODO: Implement notification sending
        await asyncio.sleep(0.5)  # Simulate work
        return {"status": "completed", "notification_id": str(uuid4())}

    @staticmethod
    async def handle_cleanup(task_data: TaskData) -> Dict[str, Any]:
        """Handle cleanup task."""
        # TODO: Implement cleanup operations
        await asyncio.sleep(2)  # Simulate work
        return {"status": "completed", "cleaned_items": 50}

    @staticmethod
    async def handle_health_check(task_data: TaskData) -> Dict[str, Any]:
        """Handle health check task."""
        # TODO: Implement health check
        await asyncio.sleep(0.1)  # Simulate work
        return {"status": "completed", "health": "ok"}


# Create default task handler mapping
DEFAULT_TASK_HANDLERS = {
    TaskType.EMBEDDING_COMPUTATION: DefaultTaskHandlers.handle_embedding_computation,
    TaskType.AGENT_TASK: DefaultTaskHandlers.handle_agent_task,
    TaskType.DOCUMENT_EXPORT: DefaultTaskHandlers.handle_document_export,
    TaskType.BATCH_PROCESSING: DefaultTaskHandlers.handle_batch_processing,
    TaskType.NOTIFICATION: DefaultTaskHandlers.handle_notification,
    TaskType.CLEANUP: DefaultTaskHandlers.handle_cleanup,
    TaskType.HEALTH_CHECK: DefaultTaskHandlers.handle_health_check,
}
