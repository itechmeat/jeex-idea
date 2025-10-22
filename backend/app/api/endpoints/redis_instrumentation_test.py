"""
Redis Instrumentation Test Endpoints

Test endpoints for verifying Redis instrumentation functionality.
These endpoints provide controlled Redis operations to validate
tracing, metrics collection, and monitoring features.

Implements Task 2.2 test requirements:
- Redis client instrumentation test endpoints
- Cache hit/miss ratio verification
- Operation latency measurement
- Memory usage monitoring validation
- Connection pool metrics testing
"""

import asyncio
import time
import logging
import uuid
from typing import Dict, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field

import structlog
from ...infrastructure.redis.instrumented_redis_service import (
    instrumented_redis_service,
)
from ...core.redis_instrumentation import redis_instrumentation

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/test/redis", tags=["redis-instrumentation-test"])


# Pydantic models for test requests/responses
class RedisTestRequest(BaseModel):
    """Redis test operation request."""

    operation: str = Field(..., description="Redis operation to test")
    key_prefix: str = Field("test", description="Key prefix for test operations")
    count: int = Field(10, ge=1, le=1000, description="Number of operations to perform")
    project_id: UUID = Field(
        ..., description="Required project ID for isolation testing"
    )


class RedisTestResponse(BaseModel):
    """Redis test operation response."""

    success: bool
    operations_completed: int
    total_duration_ms: float
    average_duration_ms: float
    error_count: int
    errors: List[str]
    instrumentation_data: Dict[str, Any]


class CacheTestRequest(BaseModel):
    """Cache performance test request."""

    total_keys: int = Field(100, ge=10, le=10000, description="Total keys to create")
    hit_rate_target: float = Field(0.7, ge=0.0, le=1.0, description="Target hit rate")
    project_id: UUID = Field(..., description="Required project ID for isolation")


class LatencyTestRequest(BaseModel):
    """Latency test request."""

    command: str = Field("GET", description="Redis command to test")
    iterations: int = Field(1000, ge=10, le=100000, description="Number of iterations")
    key_size: int = Field(
        100, ge=10, le=10240, description="Size of key/value in bytes"
    )
    project_id: UUID = Field(..., description="Required project ID for isolation")


@router.post("/operations/basic", response_model=RedisTestResponse)
async def test_basic_operations(request: RedisTestRequest):
    """
    Test basic Redis operations with instrumentation.

    Performs the specified Redis operation multiple times to validate
    instrumentation, tracing, and metrics collection.
    """
    try:
        start_time = time.time()
        operations_completed = 0
        error_count = 0
        errors = []

        project_id = request.project_id

        async with instrumented_redis_service.get_connection(
            project_id
        ) as redis_client:
            # Perform operations based on type
            for i in range(request.count):
                try:
                    if request.operation.upper() == "SET":
                        key = f"{request.key_prefix}:set:{i}"
                        value = f"test_value_{i}"
                        await redis_client.set(key, value)

                    elif request.operation.upper() == "GET":
                        # First set a value to get
                        key = f"{request.key_prefix}:get:{i}"
                        await redis_client.set(key, f"test_value_{i}")
                        await redis_client.get(key)

                    elif request.operation.upper() == "DELETE":
                        # First set a value to delete
                        key = f"{request.key_prefix}:del:{i}"
                        await redis_client.set(key, f"test_value_{i}")
                        await redis_client.delete(key)

                    elif request.operation.upper() == "INCR":
                        key = f"{request.key_prefix}:incr:{i}"
                        await redis_client.incr(key)

                    elif request.operation.upper() == "HSET":
                        key = f"{request.key_prefix}:hash:{i}"
                        await redis_client.hset(key, "field1", f"value_{i}")

                    elif request.operation.upper() == "HGET":
                        key = f"{request.key_prefix}:hash:{i}"
                        await redis_client.hset(key, "field1", f"value_{i}")
                        await redis_client.hget(key, "field1")

                    elif request.operation.upper() == "LPUSH":
                        key = f"{request.key_prefix}:list:{i}"
                        await redis_client.lpush(key, f"item_{i}")

                    elif request.operation.upper() == "LRANGE":
                        key = f"{request.key_prefix}:list:{i}"
                        await redis_client.lpush(key, f"item_{i}")
                        await redis_client.lrange(key, 0, -1)

                    else:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unsupported operation: {request.operation}",
                        )

                    operations_completed += 1

                except Exception as e:
                    error_count += 1
                    errors.append(f"Operation {i}: {str(e)}")
                    logger.error(
                        f"Redis test operation failed", operation=i, error=str(e)
                    )

        total_duration = (time.time() - start_time) * 1000
        average_duration = total_duration / max(1, operations_completed)

        # Get instrumentation data
        instrumentation_data = (
            await instrumented_redis_service.get_comprehensive_metrics(project_id)
        )

        return RedisTestResponse(
            success=error_count == 0,
            operations_completed=operations_completed,
            total_duration_ms=total_duration,
            average_duration_ms=average_duration,
            error_count=error_count,
            errors=errors,
            instrumentation_data=instrumentation_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Basic Redis operations test failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")


@router.post("/cache/performance", response_model=Dict[str, Any])
async def test_cache_performance(request: CacheTestRequest):
    """
    Test cache performance and hit/miss ratios.

    Creates a set of keys and measures cache hit/miss ratios to validate
    cache performance monitoring and instrumentation.
    """
    try:
        project_id = request.project_id
        hit_count = 0
        miss_count = 0

        async with instrumented_redis_service.get_connection(
            project_id
        ) as redis_client:
            # Phase 1: Populate cache
            logger.info(
                "Populating cache with test data", total_keys=request.total_keys
            )
            populate_start = time.time()

            for i in range(request.total_keys):
                key = f"cache_test:{i}"
                value = f"cached_value_{i}" * 10  # Larger value
                await redis_client.set(key, value, ex=300)  # 5 minute TTL

            populate_duration = (time.time() - populate_start) * 1000

            # Phase 2: Access keys to generate hits
            logger.info("Testing cache hits")
            hit_test_start = time.time()

            # Calculate number of accesses for target hit rate
            hit_accesses = int(request.total_keys * request.hit_rate_target)
            miss_accesses = request.total_keys - hit_accesses

            # Perform cache hits (access existing keys)
            for i in range(hit_accesses):
                key = f"cache_test:{i % request.total_keys}"
                result = await redis_client.get(key)
                if result is not None:
                    hit_count += 1
                else:
                    miss_count += 1

            # Perform cache misses (access non-existent keys)
            for i in range(miss_accesses):
                key = f"cache_test:nonexistent:{i}"
                result = await redis_client.get(key)
                if result is None:
                    miss_count += 1
                else:
                    hit_count += 1

            access_duration = (time.time() - hit_test_start) * 1000

            # Phase 3: Get instrumentation data
            instrumentation_data = (
                await instrumented_redis_service.get_comprehensive_metrics(project_id)
            )
            cache_performance = redis_instrumentation.get_cache_performance_summary()

            # Calculate actual hit rate
            total_accesses = hit_count + miss_count
            actual_hit_rate = hit_count / total_accesses if total_accesses > 0 else 0

            result = {
                "test_parameters": {
                    "total_keys": request.total_keys,
                    "target_hit_rate": request.hit_rate_target,
                    "total_accesses": total_accesses,
                },
                "performance_metrics": {
                    "populate_duration_ms": populate_duration,
                    "access_duration_ms": access_duration,
                    "total_duration_ms": populate_duration + access_duration,
                },
                "cache_results": {
                    "hits": hit_count,
                    "misses": miss_count,
                    "actual_hit_rate": actual_hit_rate,
                    "target_achieved": abs(actual_hit_rate - request.hit_rate_target)
                    < 0.1,
                },
                "instrumentation_cache_data": cache_performance,
                "instrumentation_full_data": instrumentation_data,
                "project_id": str(project_id),
            }

            logger.info(
                "Cache performance test completed",
                total_keys=request.total_keys,
                hit_rate=actual_hit_rate,
                target_rate=request.hit_rate_target,
            )

            return result

    except Exception as e:
        logger.error("Cache performance test failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Cache test failed: {str(e)}")


@router.post("/latency/measurement", response_model=Dict[str, Any])
async def test_operation_latency(request: LatencyTestRequest):
    """
    Test Redis operation latency measurements.

    Executes a Redis command multiple times to measure latency and validate
    latency metrics collection in the instrumentation.
    """
    try:
        project_id = request.project_id
        latencies = []
        errors = []

        # Generate test data of specified size
        test_value = "x" * request.key_size

        async with instrumented_redis_service.get_connection(
            project_id
        ) as redis_client:
            logger.info(
                "Starting latency test",
                command=request.command,
                iterations=request.iterations,
                key_size=request.key_size,
            )

            # Prepare test key
            test_key = f"latency_test:{uuid.uuid4()}"

            # For GET operations, first set a value
            if request.command.upper() == "GET":
                await redis_client.set(test_key, test_value)

            # Execute iterations
            for i in range(request.iterations):
                try:
                    start_time = time.time()

                    if request.command.upper() == "SET":
                        await redis_client.set(f"{test_key}:{i}", test_value)
                    elif request.command.upper() == "GET":
                        await redis_client.get(test_key)
                    elif request.command.upper() == "DELETE":
                        await redis_client.delete(f"{test_key}:{i}")
                    elif request.command.upper() == "INCR":
                        await redis_client.incr(f"{test_key}:counter")
                    elif request.command.upper() == "HSET":
                        await redis_client.hset(test_key, f"field_{i}", test_value)
                    elif request.command.upper() == "HGET":
                        await redis_client.hset(test_key, "test_field", test_value)
                        await redis_client.hget(test_key, "test_field")
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unsupported latency test command: {request.command}",
                        )

                    latency_ms = (time.time() - start_time) * 1000
                    latencies.append(latency_ms)

                except Exception as e:
                    errors.append(f"Iteration {i}: {str(e)}")

        # Calculate latency statistics
        if latencies:
            latencies.sort()
            count = len(latencies)
            stats = {
                "count": count,
                "average_ms": sum(latencies) / count,
                "min_ms": min(latencies),
                "max_ms": max(latencies),
                "p50_ms": latencies[count // 2],
                "p95_ms": latencies[int(count * 0.95)],
                "p99_ms": latencies[int(count * 0.99)],
                "error_count": len(errors),
            }
        else:
            stats = {
                "count": 0,
                "average_ms": 0,
                "min_ms": 0,
                "max_ms": 0,
                "p50_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
                "error_count": len(errors),
            }

        # Get instrumentation latency data
        instrumentation_latencies = (
            await redis_instrumentation.get_command_latency_stats()
        )
        command_stats = instrumentation_latencies.get(request.command.upper(), {})

        result = {
            "test_parameters": {
                "command": request.command,
                "iterations": request.iterations,
                "key_size_bytes": request.key_size,
            },
            "measured_latency": stats,
            "instrumentation_latency": command_stats,
            "errors": errors[:10],  # Limit to first 10 errors
            "project_id": str(project_id),
        }

        logger.info(
            "Latency test completed",
            command=request.command,
            iterations=request.iterations,
            avg_latency_ms=stats["average_ms"],
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Latency test failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Latency test failed: {str(e)}")


@router.get("/memory/usage", response_model=Dict[str, Any])
async def test_memory_usage_monitoring(
    project_id: UUID = Query(..., description="Required project ID for isolation"),
):
    """
    Test Redis memory usage monitoring and INFO command parsing.

    Creates data to consume memory and validates that memory statistics
    are properly collected and reported by the instrumentation.
    """
    try:
        test_project_id = project_id

        async with instrumented_redis_service.get_connection(
            test_project_id
        ) as redis_client:
            # Get initial memory stats
            initial_memory = await redis_instrumentation.collect_redis_info(
                redis_client
            )

            # Create test data to consume memory
            logger.info("Creating test data to consume memory")
            data_creation_start = time.time()

            test_keys = []
            batch_size = 100
            batches = 10

            for batch in range(batches):
                batch_keys = []
                for i in range(batch_size):
                    key = f"memory_test:{batch}:{i}"
                    # Create larger values to consume measurable memory
                    value = "x" * 1024  # 1KB per value
                    await redis_client.set(key, value, ex=3600)  # 1 hour TTL
                    batch_keys.append(key)
                test_keys.extend(batch_keys)

                # Small delay between batches
                await asyncio.sleep(0.01)

            data_creation_duration = (time.time() - data_creation_start) * 1000

            # Get memory stats after data creation
            post_creation_memory = await redis_instrumentation.collect_redis_info(
                redis_client
            )

            # Get comprehensive metrics
            metrics = await instrumented_redis_service.get_comprehensive_metrics(
                test_project_id
            )

            # Calculate memory consumption
            memory_consumed = (
                post_creation_memory.used_memory - initial_memory.used_memory
            )
            memory_per_key = memory_consumed / len(test_keys) if test_keys else 0

            result = {
                "test_parameters": {
                    "keys_created": len(test_keys),
                    "value_size_bytes": 1024,
                    "batches": batches,
                    "batch_size": batch_size,
                },
                "memory_analysis": {
                    "initial_memory_mb": initial_memory.used_memory / 1024 / 1024,
                    "post_creation_memory_mb": post_creation_memory.used_memory
                    / 1024
                    / 1024,
                    "memory_consumed_mb": memory_consumed / 1024 / 1024,
                    "memory_per_key_bytes": memory_per_key,
                    "fragmentation_ratio": post_creation_memory.memory_fragmentation_ratio,
                },
                "redis_info_stats": {
                    "used_memory_rss_mb": post_creation_memory.used_memory_rss
                    / 1024
                    / 1024,
                    "used_memory_peak_mb": post_creation_memory.used_memory_peak
                    / 1024
                    / 1024,
                    "used_memory_overhead_mb": post_creation_memory.used_memory_overhead
                    / 1024
                    / 1024,
                    "allocator_allocated_mb": post_creation_memory.allocator_allocated
                    / 1024
                    / 1024,
                    "allocator_active_mb": post_creation_memory.allocator_active
                    / 1024
                    / 1024,
                    "maxmemory_policy": post_creation_memory.maxmemory_policy,
                },
                "instrumentation_data": metrics,
                "data_creation_duration_ms": data_creation_duration,
                "project_id": str(test_project_id),
            }

            logger.info(
                "Memory usage test completed",
                keys_created=len(test_keys),
                memory_consumed_mb=memory_consumed / 1024 / 1024,
            )

            return result

    except Exception as e:
        logger.error("Memory usage test failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Memory test failed: {str(e)}")


@router.get("/connection/pool/status", response_model=Dict[str, Any])
async def test_connection_pool_monitoring(
    project_id: UUID = Query(..., description="Project ID for isolation"),
):
    """
    Test connection pool monitoring and metrics collection.

    Performs multiple connection operations to validate connection pool
    monitoring and error rate tracking.
    """
    try:
        test_project_id = project_id

        # Get initial connection stats
        initial_stats = await instrumented_redis_service.get_comprehensive_metrics(
            test_project_id
        )

        # Perform connection-intensive operations
        logger.info("Testing connection pool with concurrent operations")
        concurrent_operations = 20
        operations_per_connection = 10

        async def perform_connection_operations(conn_id: int):
            async with instrumented_redis_service.get_connection(
                test_project_id
            ) as redis_client:
                for i in range(operations_per_connection):
                    try:
                        key = f"connection_test:{conn_id}:{i}"
                        await redis_client.set(key, f"value_{conn_id}_{i}")
                        await redis_client.get(key)
                        await redis_client.delete(key)
                    except Exception as e:
                        logger.warning(
                            f"Connection operation failed",
                            conn_id=conn_id,
                            error=str(e),
                        )

        # Execute concurrent operations
        start_time = time.time()
        tasks = [perform_connection_operations(i) for i in range(concurrent_operations)]
        await asyncio.gather(*tasks)
        total_duration = (time.time() - start_time) * 1000

        # Get final connection stats
        final_stats = await instrumented_redis_service.get_comprehensive_metrics(
            test_project_id
        )

        # Get error rate statistics
        error_stats = redis_instrumentation.get_error_rate_stats()

        result = {
            "test_parameters": {
                "concurrent_connections": concurrent_operations,
                "operations_per_connection": operations_per_connection,
                "total_operations": concurrent_operations * operations_per_connection,
            },
            "performance_metrics": {
                "total_duration_ms": total_duration,
                "operations_per_second": (
                    concurrent_operations * operations_per_connection
                )
                / (total_duration / 1000),
            },
            "connection_pool_analysis": {
                "initial_stats": initial_stats.get("connection_pool", {}),
                "final_stats": final_stats.get("connection_pool", {}),
            },
            "error_analysis": error_stats,
            "cache_performance": redis_instrumentation.get_cache_performance_summary(),
            "project_id": str(test_project_id),
        }

        logger.info(
            "Connection pool test completed",
            concurrent_operations=concurrent_operations,
            total_duration_ms=total_duration,
        )

        return result

    except Exception as e:
        logger.error("Connection pool test failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Connection pool test failed: {str(e)}"
        )


@router.get("/instrumentation/status", response_model=Dict[str, Any])
async def get_instrumentation_status(
    project_id: UUID = Path(..., description="Required project ID for isolation"),
):
    """
    Get current instrumentation status and metrics.

    Returns the current state of Redis instrumentation including
    collected metrics, error rates, and system health for the specified project.

    Args:
        project_id: Required project ID for data isolation
    """
    try:
        # Get comprehensive instrumentation status
        cache_performance = redis_instrumentation.get_cache_performance_summary()
        error_stats = redis_instrumentation.get_error_rate_stats()
        latency_stats = await redis_instrumentation.get_command_latency_stats()

        # Get base service status
        base_health = await instrumented_redis_service.health_check()

        result = {
            "instrumentation_status": {
                "cache_performance": cache_performance,
                "error_rates": error_stats,
                "command_latencies": latency_stats,
                "recent_operations_count": len(
                    redis_instrumentation._recent_operations
                ),
            },
            "service_health": base_health,
            "metrics_collection": {
                "background_collection_running": redis_instrumentation._running,
                "total_operations_tracked": redis_instrumentation._total_operations,
                "total_errors_tracked": redis_instrumentation._total_errors,
            },
            "timestamp": time.time(),
        }

        return result

    except Exception as e:
        logger.error("Failed to get instrumentation status", error=str(e))
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")


@router.post("/cleanup")
async def cleanup_test_data(
    project_id: UUID = Query(..., description="Required project ID for cleanup scope"),
):
    """
    Clean up test data created during instrumentation tests.

    Removes all keys with test prefixes to clean up the Redis instance
    after testing activities.
    """
    try:
        cleanup_project_id = project_id
        keys_deleted = 0

        async with instrumented_redis_service.get_connection(
            cleanup_project_id
        ) as redis_client:
            # Find and delete test keys
            test_patterns = [
                "cache_test:*",
                "latency_test:*",
                "memory_test:*",
                "connection_test:*",
                "test:*",
            ]

            for pattern in test_patterns:
                cursor = 0
                while True:
                    cursor, keys = await redis_client.scan(
                        cursor=cursor, match=pattern, count=100
                    )
                    if keys:
                        deleted = await redis_client.delete(*keys)
                        keys_deleted += deleted
                    if cursor == 0:
                        break

        result = {
            "cleanup_completed": True,
            "keys_deleted": keys_deleted,
            "project_id": str(cleanup_project_id),
            "timestamp": time.time(),
        }

        logger.info("Test data cleanup completed", keys_deleted=keys_deleted)
        return result

    except Exception as e:
        logger.error("Test data cleanup failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")
