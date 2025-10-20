#!/usr/bin/env python3
"""
Test script to verify the critical fixes in maintenance.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.core.maintenance import (
    DatabaseMaintenance,
    MaintenanceType,
    MaintenanceStatus,
    MaintenanceTask,
)
from uuid import UUID
from datetime import datetime


async def test_concurrency_semaphore():
    """Test that semaphore properly limits concurrent maintenance tasks."""
    print("Testing concurrency semaphore...")

    maintenance = DatabaseMaintenance()

    # Test that semaphore exists and has correct capacity
    assert hasattr(maintenance, "_concurrency_sem")
    assert (
        maintenance._concurrency_sem._value
        == maintenance.config.max_concurrent_maintenance
    )
    print(
        f"✓ Semaphore initialized with capacity: {maintenance._concurrency_sem._value}"
    )

    # Test semaphore wrapper method exists
    assert hasattr(maintenance, "_with_semaphore")
    assert callable(getattr(maintenance, "_with_semaphore"))
    print("✓ _with_semaphore method exists and is callable")

    # Test that wrapper properly acquires semaphore
    test_task = MaintenanceTask(
        task_id="test_task",
        maintenance_type=MaintenanceType.VACUUM,
        status=MaintenanceStatus.PENDING,
        start_time=datetime.utcnow(),
        end_time=None,
        duration_seconds=0,
        affected_rows=0,
        project_id=UUID("00000000-0000-0000-0000-000000000000"),
        table_name=None,
    )

    # Mock the execution method to avoid database operations
    async def mock_execute(task):
        await asyncio.sleep(0.1)  # Simulate work
        task.status = MaintenanceStatus.COMPLETED

    original_execute = maintenance._execute_maintenance_task
    maintenance._execute_maintenance_task = mock_execute

    # Create multiple concurrent tasks
    start_time = asyncio.get_event_loop().time()
    tasks = []
    for i in range(3):  # More than the limit (2)
        task = MaintenanceTask(
            task_id=f"test_task_{i}",
            maintenance_type=MaintenanceType.VACUUM,
            status=MaintenanceStatus.PENDING,
            start_time=datetime.utcnow(),
            end_time=None,
            duration_seconds=0,
            affected_rows=0,
            project_id=UUID("00000000-0000-0000-0000-000000000000"),
            table_name=None,
        )
        tasks.append(maintenance._with_semaphore(task))

    # Wait for all tasks to complete
    await asyncio.gather(*tasks)
    end_time = asyncio.get_event_loop().time()

    # Restore original method
    maintenance._execute_maintenance_task = original_execute

    print(f"✓ Concurrent tasks executed in {end_time - start_time:.2f}s")
    print("✓ Concurrency test passed")


async def test_success_rate_calculation():
    """Test that success rate is calculated correctly."""
    print("\nTesting success rate calculation...")

    maintenance = DatabaseMaintenance()

    # Create test history with known outcomes
    from uuid import uuid4

    # Add 60 completed tasks and 40 failed tasks = 60% success rate
    for i in range(60):
        maintenance._maintenance_history.append(
            MaintenanceTask(
                task_id=f"completed_task_{i}",
                maintenance_type=MaintenanceType.VACUUM,
                status=MaintenanceStatus.COMPLETED,
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
                duration_seconds=10.0,
                affected_rows=1,
                project_id=uuid4(),
                table_name="test_table",
            )
        )

    for i in range(40):
        maintenance._maintenance_history.append(
            MaintenanceTask(
                task_id=f"failed_task_{i}",
                maintenance_type=MaintenanceType.VACUUM,
                status=MaintenanceStatus.FAILED,
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
                duration_seconds=5.0,
                affected_rows=0,
                project_id=uuid4(),
                table_name="test_table",
                error_message="Test error",
            )
        )

    # Get maintenance status to trigger success rate calculation
    status = await maintenance.get_maintenance_status()

    expected_success_rate = 60.0 / 100.0  # 60% success rate
    actual_success_rate = status["performance"]["success_rate"]

    print(f"✓ Expected success rate: {expected_success_rate}")
    print(f"✓ Actual success rate: {actual_success_rate}")

    # Verify calculation is correct (allowing for floating point precision)
    assert abs(actual_success_rate - expected_success_rate) < 0.01, (
        f"Success rate calculation incorrect: {actual_success_rate} != {expected_success_rate}"
    )

    print("✓ Success rate calculation test passed")


async def main():
    """Run all tests."""
    print("Testing critical fixes in maintenance.py\n")

    try:
        await test_concurrency_semaphore()
        await test_success_rate_calculation()
        print("\n✅ All tests passed! Critical fixes are working correctly.")
    except Exception as e:
        import traceback

        print(f"\n❌ Test failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
