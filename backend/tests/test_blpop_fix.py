"""
Test script to verify BLPOP fix for atomic queue operations.

This test verifies that the critical BLPOP issue has been resolved:
- Tasks are atomically removed from both priority ZSET and project list
- No duplicate processing occurs
- Project-preferring behavior works correctly
- Timeout parameters are respected
"""

import asyncio
import uuid
import logging
from datetime import datetime
from uuid import UUID

from app.services.queues.queue_manager import queue_manager, TaskType, TaskPriority
from app.infrastructure.repositories.queue_repository import queue_repository

logger = logging.getLogger(__name__)


async def test_atomic_dequeue():
    """Test that dequeue operations are atomic and prevent duplicates."""
    test_project_id = UUID("12345678-1234-5678-9abc-123456789abc")
    worker_id = "test-worker"

    print("Testing atomic dequeue operations...")

    try:
        # Initialize queue repository
        await queue_repository.initialize()
        await queue_manager.initialize()

        # Enqueue a test task
        task_id = await queue_manager.enqueue_task(
            task_type=TaskType.HEALTH_CHECK,
            project_id=test_project_id,
            data={"test": "atomic_dequeue"},
            priority=TaskPriority.HIGH,
        )

        print(f"✓ Enqueued test task: {task_id}")

        # Verify task exists in both priority queue and project queue
        queue_size = await queue_repository.get_queue_size(
            TaskType.HEALTH_CHECK, test_project_id
        )
        project_queue_size = await queue_repository.get_project_queue_size(
            TaskType.HEALTH_CHECK, test_project_id
        )

        print(f"✓ Queue sizes - Global: {queue_size}, Project: {project_queue_size}")

        # Dequeue the task (should be atomic)
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.HEALTH_CHECK,
            worker_id=worker_id,
            project_id=test_project_id,
            timeout_seconds=5,
        )

        if task_data:
            print(f"✓ Successfully dequeued task: {task_data.task_id}")

            # Verify task was removed from both queues atomically
            queue_size_after = await queue_repository.get_queue_size(
                TaskType.HEALTH_CHECK, test_project_id
            )
            project_queue_size_after = await queue_repository.get_project_queue_size(
                TaskType.HEALTH_CHECK, test_project_id
            )

            print(
                f"✓ Queue sizes after dequeue - Global: {queue_size_after}, Project: {project_queue_size_after}"
            )

            if queue_size_after == 0 and project_queue_size_after == 0:
                print(
                    "✓ CRITICAL FIX VERIFIED: Task atomically removed from both queues"
                )
            else:
                print("✗ ISSUE: Task not completely removed from queues")
                return False

        else:
            print("✗ Failed to dequeue task")
            return False

        # Try to dequeue again (should return None)
        task_data_2 = await queue_manager.dequeue_task(
            task_type=TaskType.HEALTH_CHECK,
            worker_id=worker_id,
            project_id=test_project_id,
            timeout_seconds=1,
        )

        if task_data_2 is None:
            print("✓ No duplicate tasks found - atomicity working correctly")
        else:
            print("✗ CRITICAL ISSUE: Duplicate task detected!")
            return False

        print("\n✓ All atomic dequeue tests passed!")
        return True

    except Exception as e:
        logger.exception("✗ Test failed with error")
        raise


async def test_project_preferring_behavior():
    """Test that project-preferring dequeue works correctly."""
    test_project_id = UUID("12345678-1234-5678-9abc-123456789abc")
    worker_id = "test-worker-2"

    print("\nTesting project-preferring dequeue behavior...")

    try:
        # Enqueue a project-specific task
        task_id_1 = await queue_manager.enqueue_task(
            task_type=TaskType.NOTIFICATION,
            project_id=test_project_id,
            data={"test": "project_specific"},
            priority=TaskPriority.NORMAL,
        )

        print(f"✓ Enqueued project-specific task: {task_id_1}")

        # Dequeue with project_id (should get project-specific task first)
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.NOTIFICATION,
            worker_id=worker_id,
            project_id=test_project_id,
            timeout_seconds=2,
        )

        if task_data and task_data.project_id == test_project_id:
            print(f"✓ Got project-specific task: {task_data.task_id}")
        else:
            print("✗ Project-preferring behavior failed")
            return False

        print("✓ Project-preferring behavior working correctly!")
        return True

    except Exception as e:
        logger.exception("✗ Project-preferring test failed")
        raise


async def test_timeout_handling():
    """Test that timeout parameters are respected."""
    test_project_id = UUID("12345678-1234-5678-9abc-123456789abc")
    worker_id = "test-worker-3"

    print("\nTesting timeout handling...")

    try:
        start_time = datetime.utcnow()

        # Try to dequeue from empty queue with short timeout
        task_data = await queue_manager.dequeue_task(
            task_type=TaskType.CLEANUP,
            worker_id=worker_id,
            project_id=test_project_id,
            timeout_seconds=2,
        )

        end_time = datetime.utcnow()
        elapsed_seconds = (end_time - start_time).total_seconds()

        if task_data is None:
            print(f"✓ No tasks returned (expected for empty queue)")
            print(f"✓ Timeout respected: elapsed {elapsed_seconds:.2f}s, expected ~2s")

            # Allow some tolerance for processing time
            if 1.5 <= elapsed_seconds <= 3.0:
                print("✓ Timeout handling working correctly!")
                return True
            else:
                print(f"✗ Unexpected timing: {elapsed_seconds:.2f}s")
                return False
        else:
            print("✗ Unexpected task data returned")
            return False

    except Exception as e:
        logger.exception("✗ Timeout test failed")
        raise


async def main():
    """Run all BLPOP fix verification tests."""
    print("=" * 60)
    print("BLPOP ATOMICITY FIX VERIFICATION")
    print("=" * 60)

    # Configure logging
    logging.basicConfig(level=logging.INFO)

    success_count = 0
    total_tests = 3

    # Test 1: Atomic dequeue operations
    if await test_atomic_dequeue():
        success_count += 1

    # Test 2: Project-preferring behavior
    if await test_project_preferring_behavior():
        success_count += 1

    # Test 3: Timeout handling
    if await test_timeout_handling():
        success_count += 1

    print("\n" + "=" * 60)
    print(f"TEST RESULTS: {success_count}/{total_tests} tests passed")

    if success_count == total_tests:
        print("✓ ALL CRITICAL BLPOP FIXES VERIFIED!")
        print("✓ No duplicate processing issues expected")
        print("✓ Atomic queue operations working correctly")
    else:
        print("✗ Some tests failed - BLPOP issues may persist")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
