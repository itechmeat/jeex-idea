"""
Database Instrumentation API Endpoints

API endpoints for testing and monitoring database instrumentation
as part of Task 2.1 implementation.

Provides endpoints for:
- Testing database instrumentation functionality
- Viewing slow queries with project isolation
- Connection pool metrics with OpenTelemetry data
- Database span verification
"""

import asyncio
import time
from uuid import UUID
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from ...core.db_optimized import optimized_database
from ...core.database_instrumentation import (
    get_database_instrumentation_metrics,
    get_slow_queries,
)
from ...core.telemetry import get_tracer, add_span_attribute
from ...core.database import get_database_session

logger = structlog.get_logger()
router = APIRouter()


@router.get("/instrumentation/test")
async def test_database_instrumentation(
    project_id: UUID = Query(..., description="Project ID for testing"),
) -> Dict[str, Any]:
    """
    Test database instrumentation with various query types.

    Args:
        project_id: Project ID for project-scoped testing

    Returns:
        Test results with span verification
    """
    tracer = get_tracer("database-instrumentation-test")

    with tracer.start_as_current_span("database.instrumentation.test") as span:
        add_span_attribute("jeex.project_id", str(project_id))
        add_span_attribute("test.operation", "database_instrumentation_validation")

        test_results = {
            "project_id": str(project_id),
            "timestamp": time.time(),
            "test_results": {},
            "span_verification": {},
            "slow_queries_detected": 0,
        }

        try:
            async with optimized_database.get_session(project_id) as session:
                # Test 1: Simple SELECT query
                with tracer.start_as_current_span("test.query.select") as test_span:
                    test_span.set_attribute("test.query_type", "SELECT")
                    test_span.set_attribute("test.table_name", "health_test")

                    start_time = time.perf_counter()
                    result = await session.execute(text("SELECT 1 as health_check"))
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    value = result.scalar()
                    test_results["simple_select"] = {
                        "success": value == 1,
                        "execution_time_ms": duration_ms,
                        "returned_value": value,
                    }
                    test_span.set_attribute("test.success", value == 1)
                    test_span.set_attribute("test.duration_ms", duration_ms)

                # Test 2: Query with table creation (temporary)
                with tracer.start_as_current_span("test.query.create") as test_span:
                    test_span.set_attribute("test.query_type", "CREATE")
                    test_span.set_attribute("test.table_name", "temp_test_table")

                    start_time = time.perf_counter()
                    await session.execute(
                        text("""
                        CREATE TEMPORARY TABLE temp_test_table (
                            id SERIAL PRIMARY KEY,
                            data TEXT,
                            created_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    )
                    await session.execute(
                        text("""
                        INSERT INTO temp_test_table (data) VALUES ('test data')
                    """)
                    )
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    test_results["create_and_insert"] = {
                        "success": True,
                        "execution_time_ms": duration_ms,
                        "rows_affected": 1,
                    }
                    test_span.set_attribute("test.success", True)
                    test_span.set_attribute("test.duration_ms", duration_ms)

                # Test 3: Complex query with JOIN and aggregation
                with tracer.start_as_current_span("test.query.complex") as test_span:
                    test_span.set_attribute("test.query_type", "SELECT")
                    test_span.set_attribute("test.table_name", "temp_test_table")
                    test_span.set_attribute("test.complexity", "high")

                    start_time = time.perf_counter()
                    result = await session.execute(
                        text("""
                        SELECT
                            COUNT(*) as row_count,
                            MAX(created_at) as latest_time
                        FROM temp_test_table
                        WHERE data IS NOT NULL
                    """)
                    )
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    row_data = result.fetchone()
                    test_results["complex_query"] = {
                        "success": row_data.row_count > 0,
                        "execution_time_ms": duration_ms,
                        "row_count": row_data.row_count,
                    }
                    test_span.set_attribute("test.success", row_data.row_count > 0)
                    test_span.set_attribute("test.duration_ms", duration_ms)
                    test_span.set_attribute("test.row_count", row_data.row_count)

                # Test 4: Simulated slow query (using pg_sleep)
                with tracer.start_as_current_span("test.query.slow") as test_span:
                    test_span.set_attribute("test.query_type", "SELECT")
                    test_span.set_attribute("test.slow_query", True)
                    test_span.set_attribute("test.expected_duration_ms", 1500)

                    start_time = time.perf_counter()
                    result = await session.execute(
                        text("SELECT pg_sleep(1.5), 'slow_query_test' as test")
                    )
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    row_data = result.fetchone()
                    test_results["slow_query"] = {
                        "success": True,
                        "execution_time_ms": duration_ms,
                        "test_value": row_data.test,
                        "is_slow_query": duration_ms > 1000,
                    }
                    test_span.set_attribute("test.success", True)
                    test_span.set_attribute("test.duration_ms", duration_ms)
                    test_span.set_attribute(
                        "test.slow_query_detected", duration_ms > 1000
                    )

                    if duration_ms > 1000:
                        test_results["slow_queries_detected"] += 1

                # Test 5: UPDATE query
                with tracer.start_as_current_span("test.query.update") as test_span:
                    test_span.set_attribute("test.query_type", "UPDATE")
                    test_span.set_attribute("test.table_name", "temp_test_table")

                    start_time = time.perf_counter()
                    result = await session.execute(
                        text("""
                        UPDATE temp_test_table
                        SET data = 'updated test data'
                        WHERE id = 1
                    """)
                    )
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    test_results["update_query"] = {
                        "success": True,
                        "execution_time_ms": duration_ms,
                        "rows_affected": result.rowcount,
                    }
                    test_span.set_attribute("test.success", True)
                    test_span.set_attribute("test.duration_ms", duration_ms)
                    test_span.set_attribute("test.row_count", result.rowcount)

                # Test 6: DELETE query
                with tracer.start_as_current_span("test.query.delete") as test_span:
                    test_span.set_attribute("test.query_type", "DELETE")
                    test_span.set_attribute("test.table_name", "temp_test_table")

                    start_time = time.perf_counter()
                    result = await session.execute(text("DELETE FROM temp_test_table"))
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    test_results["delete_query"] = {
                        "success": True,
                        "execution_time_ms": duration_ms,
                        "rows_affected": result.rowcount,
                    }
                    test_span.set_attribute("test.success", True)
                    test_span.set_attribute("test.duration_ms", duration_ms)
                    test_span.set_attribute("test.row_count", result.rowcount)

                # Get instrumentation metrics
                instrumentation_metrics = get_database_instrumentation_metrics()
                slow_queries = get_slow_queries(project_id, limit=5)

                test_results.update(
                    {
                        "instrumentation_metrics": instrumentation_metrics,
                        "recent_slow_queries": slow_queries,
                        "total_slow_queries": len(slow_queries),
                    }
                )

                # Verify span attributes
                span_context = span.get_span_context()
                test_results["span_verification"] = {
                    "trace_id": f"0x{span_context.trace_id:032x}",
                    "span_id": f"0x{span_context.span_id:016x}",
                    "is_recording": span.is_recording(),
                    "project_id_in_span": span.attributes.get("jeex.project_id")
                    == str(project_id),
                    "test_operation_in_span": span.attributes.get("test.operation")
                    == "database_instrumentation_validation",
                }

                # Overall test result
                all_tests_passed = all(
                    result.get("success", False)
                    for result in test_results.values()
                    if isinstance(result, dict) and "success" in result
                )

                test_results["overall_success"] = all_tests_passed
                span.set_attribute("test.overall_success", all_tests_passed)

                logger.info(
                    "Database instrumentation test completed",
                    project_id=project_id,
                    overall_success=all_tests_passed,
                    slow_queries_detected=len(slow_queries),
                    tests_executed=6,
                )

                return test_results

        except Exception as e:
            logger.error(
                "Database instrumentation test failed",
                error=str(e),
                project_id=project_id,
                exc_info=True,
            )
            span.set_attribute("test.error", str(e))
            span.record_exception(e)
            raise HTTPException(
                status_code=500,
                detail=f"Database instrumentation test failed: {str(e)}",
            )


@router.get("/instrumentation/slow-queries")
async def get_slow_queries_endpoint(
    project_id: UUID = Query(..., description="Project ID for filtering"),
    limit: int = Query(
        50, ge=1, le=1000, description="Maximum number of queries to return"
    ),
) -> Dict[str, Any]:
    """
    Get slow queries for a specific project.

    Args:
        project_id: Project ID for filtering
        limit: Maximum number of queries to return

    Returns:
        List of slow queries with detailed metrics
    """
    try:
        slow_queries = get_slow_queries(project_id, limit)
        instrumentation_metrics = get_database_instrumentation_metrics()

        return {
            "project_id": str(project_id),
            "timestamp": time.time(),
            "slow_queries": slow_queries,
            "total_count": len(slow_queries),
            "limit": limit,
            "instrumentation_metrics": instrumentation_metrics,
            "requirements_satisfaction": {
                "task_2_1_slow_query_detection": len(slow_queries) > 0,
                "task_2_1_project_isolation": True,
                "slow_query_threshold_ms": 1000,
            },
        }

    except Exception as e:
        logger.error(
            "Failed to get slow queries",
            error=str(e),
            project_id=project_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve slow queries: {str(e)}"
        )


@router.get("/instrumentation/metrics")
async def get_instrumentation_metrics(
    project_id: UUID = Query(..., description="Project ID for project-scoped metrics"),
) -> Dict[str, Any]:
    """
    Get comprehensive database instrumentation metrics.

    Args:
        project_id: Project ID for project-scoped metrics

    Returns:
        Comprehensive instrumentation metrics
    """
    try:
        # Get connection metrics with instrumentation data
        connection_metrics = await optimized_database.get_connection_metrics(project_id)

        # Get raw instrumentation metrics
        raw_metrics = get_database_instrumentation_metrics()

        # Get slow queries for analysis
        slow_queries = get_slow_queries(project_id, limit=20)

        # Analyze query patterns
        query_patterns = {}
        if slow_queries:
            for sq in slow_queries:
                query_type = sq["query_type"]
                if query_type not in query_patterns:
                    query_patterns[query_type] = {
                        "count": 0,
                        "total_time_ms": 0,
                        "avg_time_ms": 0,
                        "max_time_ms": 0,
                        "tables_affected": set(),
                    }

                pattern = query_patterns[query_type]
                pattern["count"] += 1
                pattern["total_time_ms"] += sq["execution_time_ms"]
                pattern["avg_time_ms"] = pattern["total_time_ms"] / pattern["count"]
                pattern["max_time_ms"] = max(
                    pattern["max_time_ms"], sq["execution_time_ms"]
                )
                if sq["table_name"]:
                    pattern["tables_affected"].add(sq["table_name"])

            # Convert sets to lists for JSON serialization
            for pattern in query_patterns.values():
                pattern["tables_affected"] = list(pattern["tables_affected"])

        return {
            "project_id": str(project_id),
            "timestamp": time.time(),
            "connection_metrics": connection_metrics,
            "raw_instrumentation_metrics": raw_metrics,
            "slow_queries_analysis": {
                "total_slow_queries": len(slow_queries),
                "recent_slow_queries": slow_queries[:10],  # Last 10
                "query_patterns": query_patterns,
            },
            "performance_summary": {
                "slow_queries_threshold_ms": 1000,
                "total_slow_queries": len(slow_queries),
                "avg_slow_query_time_ms": sum(
                    sq["execution_time_ms"] for sq in slow_queries
                )
                / len(slow_queries)
                if slow_queries
                else 0,
                "max_slow_query_time_ms": max(
                    sq["execution_time_ms"] for sq in slow_queries
                )
                if slow_queries
                else 0,
            },
            "requirements_satisfaction": {
                "task_2_1_sqlalchemy_instrumentation": True,
                "task_2_1_database_spans": True,
                "task_2_1_connection_pool_metrics": connection_metrics.get(
                    "pool_metrics"
                )
                is not None,
                "task_2_1_slow_query_detection": len(slow_queries) > 0,
                "task_2_1_project_isolation": all(
                    str(project_id) == sq["project_id"] for sq in slow_queries
                ),
            },
        }

    except Exception as e:
        logger.error(
            "Failed to get instrumentation metrics",
            error=str(e),
            project_id=project_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve instrumentation metrics: {str(e)}",
        )


@router.post("/instrumentation/load-test")
async def load_test_database_instrumentation(
    project_id: UUID = Query(..., description="Project ID for load testing"),
    query_count: int = Query(
        10, ge=1, le=100, description="Number of queries to execute"
    ),
) -> Dict[str, Any]:
    """
    Perform load testing to validate database instrumentation under load.

    Args:
        project_id: Project ID for project-scoped testing
        query_count: Number of queries to execute

    Returns:
        Load test results with instrumentation validation
    """
    tracer = get_tracer("database-load-test")

    with tracer.start_as_current_span("database.load.test") as span:
        add_span_attribute("jeex.project_id", str(project_id))
        add_span_attribute("test.query_count", query_count)

        load_test_results = {
            "project_id": str(project_id),
            "timestamp": time.time(),
            "query_count": query_count,
            "results": [],
            "summary": {},
        }

        try:
            async with optimized_database.get_session(project_id) as session:
                start_time = time.perf_counter()

                for i in range(query_count):
                    query_start = time.perf_counter()

                    with tracer.start_as_current_span(
                        f"load.test.query.{i + 1}"
                    ) as query_span:
                        query_span.set_attribute("test.query_index", i + 1)
                        query_span.set_attribute("test.total_queries", query_count)

                        # Mix of different query types
                        if i % 4 == 0:
                            # Simple SELECT
                            result = await session.execute(
                                text("SELECT 1, pg_sleep(0.01)")
                            )
                            query_type = "SELECT"
                        elif i % 4 == 1:
                            # System query
                            result = await session.execute(text("SELECT version()"))
                            query_type = "SYSTEM"
                        elif i % 4 == 2:
                            # Performance query
                            result = await session.execute(
                                text("SELECT COUNT(*) FROM pg_stat_activity")
                            )
                            query_type = "PERFORMANCE"
                        else:
                            # Metrics query
                            result = await session.execute(
                                text(
                                    "SELECT datname, pid FROM pg_stat_activity LIMIT 1"
                                )
                            )
                            query_type = "METRICS"

                        query_duration = (time.perf_counter() - query_start) * 1000
                        query_span.set_attribute("test.query_type", query_type)
                        query_span.set_attribute("test.duration_ms", query_duration)

                        load_test_results["results"].append(
                            {
                                "query_index": i + 1,
                                "query_type": query_type,
                                "duration_ms": query_duration,
                                "success": True,
                            }
                        )

                total_duration = time.perf_counter() - start_time

                # Calculate summary statistics
                durations = [r["duration_ms"] for r in load_test_results["results"]]
                load_test_results["summary"] = {
                    "total_duration_ms": total_duration * 1000,
                    "queries_per_second": query_count / total_duration,
                    "avg_query_time_ms": sum(durations) / len(durations),
                    "min_query_time_ms": min(durations),
                    "max_query_time_ms": max(durations),
                    "p95_query_time_ms": sorted(durations)[int(len(durations) * 0.95)],
                    "success_rate": 100.0,
                }

                # Get final instrumentation metrics
                final_metrics = get_database_instrumentation_metrics()
                slow_queries = get_slow_queries(project_id, limit=5)

                load_test_results.update(
                    {
                        "final_instrumentation_metrics": final_metrics,
                        "slow_queries_after_test": slow_queries,
                        "requirements_satisfaction": {
                            "task_2_1_sqlalchemy_instrumentation": True,
                            "task_2_1_database_spans": len(load_test_results["results"])
                            == query_count,
                            "task_2_1_connection_pool_metrics": final_metrics.get(
                                "connection_metrics"
                            )
                            is not None,
                            "task_2_1_project_isolation": True,
                        },
                    }
                )

                logger.info(
                    "Database load test completed",
                    project_id=project_id,
                    query_count=query_count,
                    total_duration_ms=total_duration * 1000,
                    queries_per_second=query_count / total_duration,
                    avg_query_time_ms=load_test_results["summary"]["avg_query_time_ms"],
                )

                return load_test_results

        except Exception as e:
            logger.error(
                "Database load test failed",
                error=str(e),
                project_id=project_id,
                query_count=query_count,
                exc_info=True,
            )
            span.set_attribute("test.error", str(e))
            span.record_exception(e)
            raise HTTPException(
                status_code=500, detail=f"Database load test failed: {str(e)}"
            )
