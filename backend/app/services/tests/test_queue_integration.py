"""
Queue Management Integration Tests

Integration tests for queue management functionality.
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta

from ..queues import queue_manager, TaskType, TaskPriority, TaskStatus
from ..queues.workers import QueueWorker, DEFAULT_TASK_HANDLERS
from ..queues.dead_letter import dead_letter_queue


class TestQueueManagementIntegration:
    """Integration tests for queue management."""

    @pytest.mark.asyncio
    async def test_end_to_end_task_processing(self):
        """Test complete task processing workflow."""
        project_id = uuid4()
        worker_id = "test_worker_e2e"

        # Enqueue a task
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION,
            project_id=project_id,
            data={"document_id": str(uuid4()), "text": "Test text for embedding"},
            priority=TaskPriority.NORMAL,
        )

        assert task_id is not None

        # Check initial status
        status = await queue_manager.get_task_status(task_id)
        assert status is None  # No status until dequeued

        # Dequeue the task
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION, worker_id=worker_id
        )

        assert task_data is not None
        assert task_data.task_id == task_id

        # Check status after dequeuing
        status = await queue_manager.get_task_status(task_id)
        assert status is not None
        assert status["status"] == TaskStatus.RUNNING.value
        assert status["worker_id"] == worker_id

        # Simulate task processing
        await asyncio.sleep(0.1)

        # Complete the task
        result = {"embedding": [0.1, 0.2, 0.3], "dimensions": 3}
        success = await queue_manager.complete_task(
            task_id=task_id, result=result, worker_id=worker_id
        )

        assert success is True

        # Check final status
        status = await queue_manager.get_task_status(task_id)
        assert status is not None
        assert status["status"] == TaskStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_task_retry_workflow(self):
        """Test task retry workflow."""
        project_id = uuid4()
        worker_id = "test_worker_retry"

        # Enqueue a task with retry configuration
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.AGENT_TASK,
            project_id=project_id,
            data={"prompt": "Test prompt"},
            max_attempts=3,
        )

        # First attempt - fail with retry
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.AGENT_TASK, worker_id=worker_id
        )

        assert task_data is not None

        # Fail the task
        error_message = "Temporary API error"
        await queue_manager.fail_task(
            task_id=task_id, error=error_message, worker_id=worker_id, retry=True
        )

        # Check status should be RETRYING
        status = await queue_manager.get_task_status(task_id)
        assert status["status"] == TaskStatus.RETRYING.value

        # Second attempt - should be able to dequeue again
        # Note: In a real system, there might be a delay before retry
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.AGENT_TASK, worker_id=worker_id
        )

        assert task_data is not None
        assert task_data.task_id == task_id

        # Check attempts increased
        status = await queue_manager.get_task_status(task_id)
        assert status["attempts"] == 2

        # Complete on second attempt
        await queue_manager.complete_task(
            task_id=task_id,
            result={"response": "Task completed successfully"},
            worker_id=worker_id,
        )

        # Final status should be COMPLETED
        status = await queue_manager.get_task_status(task_id)
        assert status["status"] == TaskStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_dead_letter_queue_integration(self):
        """Test dead letter queue integration."""
        project_id = uuid4()
        worker_id = "test_worker_dlq"

        # Enqueue a task with low retry limit
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.DOCUMENT_EXPORT,
            project_id=project_id,
            data={"export_path": "/tmp/test.pdf"},
            max_attempts=1,  # Only one attempt
        )

        # Dequeue and fail the task
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.DOCUMENT_EXPORT, worker_id=worker_id
        )

        # Fail without retry (max attempts reached)
        error_message = "Permanent export failure"
        await queue_manager.fail_task(
            task_id=task_id, error=error_message, worker_id=worker_id, retry=False
        )

        # Check task is in dead letter queue
        dlq_task = await dead_letter_queue.get_task(task_id)
        assert dlq_task is not None
        assert dlq_task.original_task_id == task_id
        assert dlq_task.error_message == error_message
        assert dlq_task.attempts == 1

        # Get dead letter queue statistics
        stats = await dead_letter_queue.get_statistics()
        assert stats["total_tasks"] >= 1

    @pytest.mark.asyncio
    async def test_priority_queue_processing(self):
        """Test priority queue processing order."""
        project_id = uuid4()
        worker_id = "test_worker_priority"

        # Enqueue tasks with different priorities
        tasks = [
            ("low", TaskPriority.LOW),
            ("critical", TaskPriority.CRITICAL),
            ("normal", TaskPriority.NORMAL),
            ("high", TaskPriority.HIGH),
            ("urgent", TaskPriority.URGENT),
        ]

        task_ids = []
        for name, priority in tasks:
            task_id = await queue_manager.enqueue_task(
                task_type=TaskType.BATCH_PROCESSING,
                project_id=project_id,
                data={"name": name},
                priority=priority,
            )
            task_ids.append((task_id, name, priority))

        # Process tasks in priority order
        processed_order = []
        for _ in range(len(tasks)):
            task_data = await queue_manager.dequeue_task(
                task_type=TaskType.BATCH_PROCESSING, worker_id=worker_id
            )

            if task_data:
                processed_order.append(task_data.data["name"])
                await queue_manager.complete_task(
                    task_id=task_data.task_id,
                    result={"processed": True},
                    worker_id=worker_id,
                )

        # Should process in priority order (highest first)
        expected_order = ["urgent", "critical", "high", "normal", "low"]
        assert processed_order == expected_order

    @pytest.mark.asyncio
    async def test_project_isolation_in_queues(self):
        """Test project isolation in queue operations."""
        project1_id = uuid4()
        project2_id = uuid4()
        worker_id = "test_worker_isolation"

        # Enqueue tasks for different projects
        task1_id = await queue_manager.enqueue_task(
            task_type=TaskType.NOTIFICATION,
            project_id=project1_id,
            data={"message": "Project 1 notification"},
        )

        task2_id = await queue_manager.enqueue_task(
            task_type=TaskType.NOTIFICATION,
            project_id=project2_id,
            data={"message": "Project 2 notification"},
        )

        # Test project-specific dequeue
        task1_data = await queue_manager.dequeue_task(
            task_type=TaskType.NOTIFICATION, worker_id=worker_id, project_id=project1_id
        )

        assert task1_data is not None
        assert task1_data.project_id == project1_id
        assert task1_data.task_id == task1_id

        # Other project's task should still be available
        task2_data = await queue_manager.dequeue_task(
            task_type=TaskType.NOTIFICATION, worker_id=worker_id, project_id=project2_id
        )

        assert task2_data is not None
        assert task2_data.project_id == project2_id
        assert task2_data.task_id == task2_id

    @pytest.mark.asyncio
    async def test_queue_statistics_monitoring(self):
        """Test queue statistics and monitoring."""
        project_id = uuid4()

        # Enqueue tasks of different types
        task_types = [
            TaskType.EMBEDDING_COMPUTATION,
            TaskType.AGENT_TASK,
            TaskType.DOCUMENT_EXPORT,
        ]
        task_ids = []

        for task_type in task_types:
            for i in range(3):  # 3 tasks per type
                task_id = await queue_manager.enqueue_task(
                    task_type=task_type, project_id=project_id, data={"batch": i}
                )
                task_ids.append(task_id)

        # Get statistics for each queue
        for task_type in task_types:
            stats = await queue_manager.get_queue_stats(task_type)
            assert stats is not None
            assert stats["total_tasks"] == 3
            assert stats["task_type"] == task_type.value

        # Get all queue statistics
        all_stats = await queue_manager.get_all_queue_stats()
        assert all_stats is not None
        assert all_stats["total_tasks"] == 9  # 3 tasks × 3 types
        assert len(all_stats["queues"]) >= len(task_types)

        # Process some tasks and check updated stats
        worker_id = "test_worker_stats"

        # Process one task
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.EMBEDDING_COMPUTATION, worker_id=worker_id
        )

        if task_data:
            await queue_manager.complete_task(
                task_id=task_data.task_id,
                result={"processed": True},
                worker_id=worker_id,
            )

        # Check updated statistics
        updated_stats = await queue_manager.get_queue_stats(
            TaskType.EMBEDDING_COMPUTATION
        )
        # Note: This would show the task as completed in a real implementation

    @pytest.mark.asyncio
    async def test_scheduled_task_processing(self):
        """Test scheduled task processing."""
        project_id = uuid4()
        worker_id = "test_worker_scheduled"

        # Schedule task for future (short delay for testing)
        scheduled_time = datetime.utcnow() + timedelta(seconds=1)
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.CLEANUP,
            project_id=project_id,
            data={"cleanup_type": "temp_files"},
            scheduled_at=scheduled_time,
        )

        # Try to dequeue immediately - should not get the task
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.CLEANUP, worker_id=worker_id
        )

        assert task_data is None  # Should not get scheduled task yet

        # Wait for scheduled time
        await asyncio.sleep(1.5)

        # Now should be able to dequeue
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.CLEANUP, worker_id=worker_id
        )

        assert task_data is not None
        assert task_data.task_id == task_id
        assert task_data.scheduled_at is not None

    @pytest.mark.asyncio
    async def test_queue_cleanup_operations(self):
        """Test queue cleanup and maintenance operations."""
        project_id = uuid4()

        # Enqueue some tasks
        task_ids = []
        for i in range(5):
            task_id = await queue_manager.enqueue_task(
                task_type=TaskType.HEALTH_CHECK,
                project_id=project_id,
                data={"check_id": i},
            )
            task_ids.append(task_id)

        # Get initial queue stats
        initial_stats = await queue_manager.get_queue_stats(TaskType.HEALTH_CHECK)
        initial_count = initial_stats["total_tasks"]

        assert initial_count == 5

        # Process some tasks
        worker_id = "test_worker_cleanup"

        for i in range(3):
            task_data = await queue_manager.dequeue_task(
                task_type=TaskType.HEALTH_CHECK, worker_id=worker_id
            )

            if task_data:
                await queue_manager.complete_task(
                    task_id=task_data.task_id,
                    result={"status": "healthy"},
                    worker_id=worker_id,
                )

        # Run cleanup (this would clean up old completed tasks)
        cleaned_count = await queue_manager.cleanup_expired_tasks(
            max_age_hours=0
        )  # Clean up everything
        # Note: In a real implementation, this would clean up tasks older than the specified age

        # Check remaining tasks
        remaining_stats = await queue_manager.get_queue_stats(TaskType.HEALTH_CHECK)
        # Note: The exact count depends on implementation details

    @pytest.mark.asyncio
    async def test_concurrent_queue_operations(self):
        """Test concurrent queue operations."""
        project_id = uuid4()

        # Enqueue tasks concurrently
        async def enqueue_batch(batch_id):
            task_ids = []
            for i in range(10):
                task_id = await queue_manager.enqueue_task(
                    task_type=TaskType.BATCH_PROCESSING,
                    project_id=project_id,
                    data={"batch_id": batch_id, "item": i},
                )
                task_ids.append(task_id)
            return task_ids

        # Create multiple concurrent batches
        batch_tasks = [enqueue_batch(i) for i in range(3)]
        all_task_ids = await asyncio.gather(*batch_tasks)

        # Flatten task IDs
        all_task_ids = [task_id for batch_ids in all_task_ids for task_id in batch_ids]

        assert len(all_task_ids) == 30  # 3 batches × 10 tasks

        # Dequeue tasks concurrently
        async def process_batch(worker_id):
            processed = []
            for _ in range(10):
                task_data = await queue_manager.dequeue_task(
                    task_type=TaskType.BATCH_PROCESSING, worker_id=worker_id
                )

                if task_data:
                    await queue_manager.complete_task(
                        task_id=task_data.task_id,
                        result={"processed": True},
                        worker_id=worker_id,
                    )
                    processed.append(task_data.task_id)
            return processed

        # Process with multiple workers concurrently
        worker_tasks = [process_batch(f"worker_{i}") for i in range(3)]
        processed_tasks = await asyncio.gather(*worker_tasks)

        # Flatten processed task IDs
        all_processed = [
            task_id for worker_tasks in processed_tasks for task_id in worker_tasks
        ]

        # All tasks should be processed
        assert len(all_processed) == 30

        # Check final queue stats
        final_stats = await queue_manager.get_queue_stats(TaskType.BATCH_PROCESSING)
        # Most tasks should be completed (queued count should be low)


class TestQueuePerformance:
    """Performance tests for queue operations."""

    @pytest.mark.asyncio
    async def test_enqueue_performance(self):
        """Test enqueue performance meets requirements (< 10ms for 95% of operations)."""
        project_id = uuid4()

        enqueue_times = []
        num_operations = 1000

        for i in range(num_operations):
            start_time = asyncio.get_event_loop().time()
            task_id = await queue_manager.enqueue_task(
                task_type=TaskType.NOTIFICATION,
                project_id=project_id,
                data={"notification_id": i},
            )
            end_time = asyncio.get_event_loop().time()

            enqueue_times.append((end_time - start_time) * 1000)  # Convert to ms
            assert task_id is not None

        # Sort to find percentiles
        enqueue_times.sort()
        p95_index = int(len(enqueue_times) * 0.95)
        p95_time = enqueue_times[p95_index]
        avg_time = sum(enqueue_times) / len(enqueue_times)

        # 95% of enqueues should be under 10ms
        assert p95_time < 10.0, (
            f"P95 enqueue time {p95_time:.2f}ms exceeds 10ms requirement"
        )

        print(f"Enqueue performance:")
        print(f"  Average: {avg_time:.2f}ms")
        print(f"  P95: {p95_time:.2f}ms")
        print(f"  Max: {max(enqueue_times):.2f}ms")

    @pytest.mark.asyncio
    async def test_dequeue_performance(self):
        """Test dequeue performance."""
        project_id = uuid4()
        worker_id = "perf_test_worker"

        # First enqueue some tasks
        task_ids = []
        for i in range(100):
            task_id = await queue_manager.enqueue_task(
                task_type=TaskType.HEALTH_CHECK,
                project_id=project_id,
                data={"check_id": i},
            )
            task_ids.append(task_id)

        # Test dequeue performance
        dequeue_times = []

        for i in range(100):
            start_time = asyncio.get_event_loop().time()
            task_data = await queue_manager.dequeue_task(
                task_type=TaskType.HEALTH_CHECK, worker_id=worker_id
            )
            end_time = asyncio.get_event_loop().time()

            dequeue_times.append((end_time - start_time) * 1000)

            if task_data:
                await queue_manager.complete_task(
                    task_id=task_data.task_id,
                    result={"status": "ok"},
                    worker_id=worker_id,
                )

        avg_time = sum(dequeue_times) / len(dequeue_times)
        max_time = max(dequeue_times)

        # Performance should be good
        assert avg_time < 5.0, f"Average dequeue time {avg_time:.2f}ms too high"
        assert max_time < 20.0, f"Max dequeue time {max_time:.2f}ms too high"

        print(f"Dequeue performance:")
        print(f"  Average: {avg_time:.2f}ms")
        print(f"  Max: {max_time:.2f}ms")

    @pytest.mark.asyncio
    async def test_high_volume_queue_operations(self):
        """Test queue performance under high volume."""
        project_id = uuid4()
        num_tasks = 1000

        # Enqueue many tasks
        enqueue_start = asyncio.get_event_loop().time()
        task_ids = []

        for i in range(num_tasks):
            task_id = await queue_manager.enqueue_task(
                task_type=TaskType.NOTIFICATION,
                project_id=project_id,
                data={"notification_id": i},
            )
            task_ids.append(task_id)

        enqueue_end = asyncio.get_event_loop().time()
        enqueue_time = (enqueue_end - enqueue_start) * 1000

        print(f"Enqueued {num_tasks} tasks in {enqueue_time:.2f}ms")
        print(f"Enqueue rate: {num_tasks / (enqueue_time / 1000):.2f} tasks/sec")

        assert len(task_ids) == num_tasks
        assert enqueue_time < 5000  # Should complete within 5 seconds

        # Process tasks with multiple workers
        async def worker_process(worker_id, start_idx, end_idx):
            processed = 0
            for i in range(start_idx, end_idx):
                task_data = await queue_manager.dequeue_task(
                    task_type=TaskType.NOTIFICATION, worker_id=worker_id
                )

                if task_data:
                    await queue_manager.complete_task(
                        task_id=task_data.task_id,
                        result={"sent": True},
                        worker_id=worker_id,
                    )
                    processed += 1
            return processed

        # Use 10 concurrent workers
        tasks_per_worker = num_tasks // 10
        worker_tasks = []

        for i in range(10):
            start_idx = i * tasks_per_worker
            end_idx = start_idx + tasks_per_worker
            if i == 9:  # Last worker gets remaining tasks
                end_idx = num_tasks

            task = worker_process(f"worker_{i}", start_idx, end_idx)
            worker_tasks.append(task)

        process_start = asyncio.get_event_loop().time()
        results = await asyncio.gather(*worker_tasks)
        process_end = asyncio.get_event_loop().time()

        process_time = (process_end - process_start) * 1000
        total_processed = sum(results)

        print(f"Processed {total_processed} tasks in {process_time:.2f}ms")
        print(f"Process rate: {total_processed / (process_time / 1000):.2f} tasks/sec")

        assert total_processed == num_tasks
        assert process_time < 10000  # Should complete within 10 seconds


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
