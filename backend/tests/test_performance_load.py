"""
Performance and Load Testing - Phase 4.5

Comprehensive performance testing suite covering:
1. Query performance validation (P95 < 100ms)
2. Connection pooling optimization
3. Concurrent user load testing
4. Database performance under stress
5. Performance monitoring validation
"""

import pytest
import asyncio
import time
import statistics
from typing import List, Dict, Any, Tuple
from uuid import uuid4
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import httpx

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func

from app.main import app
from app.db import get_database_session
from app.models import User, Project, DocumentVersion, AgentExecution
from app.core.config import get_settings
from app.core.monitoring import performance_monitor

logger = structlog.get_logger()
settings = get_settings()


class TestPerformanceRequirements:
    """Test performance requirements and validation."""

    @pytest.fixture(autouse=True)
    async def setup_performance_test_data(self):
        """Setup test data for performance testing."""
        async for session in get_database_session():
            try:
                # Create performance test user
                test_user = User(
                    email=f"perf-test-{uuid4()}@example.com",
                    name="Performance Test User",
                    profile_data={"test": "performance"},
                )
                session.add(test_user)
                await session.commit()
                await session.refresh(test_user)

                # Create multiple test projects
                projects = []
                for i in range(10):
                    project = Project(
                        name=f"Performance Test Project {i}",
                        language="en",
                        status="draft",
                        current_step=1,
                        meta_data={"test": "performance", "index": i},
                        created_by=test_user.id,
                    )
                    session.add(project)
                    projects.append(project)

                await session.commit()

                # Create documents for performance testing
                for i, project in enumerate(projects):
                    for doc_type in ["specification", "architecture", "planning"]:
                        for version in range(3):
                            doc = DocumentVersion(
                                project_id=project.id,
                                document_type=doc_type,
                                version=version + 1,
                                content=f"# {doc_type.title()} v{version + 1} for Project {i}\n\n"
                                + "This is performance test content. " * 20,
                                meta_data={"performance_test": True, "index": i},
                                readability_score=75.0 + (i % 25),
                                grammar_score=80.0 + (i % 20),
                                created_by=test_user.id,
                            )
                            session.add(doc)

                # Create agent executions for performance testing
                for i, project in enumerate(projects):
                    for agent_type in [
                        "product_manager",
                        "spec_expert",
                        "architect",
                        "planner",
                    ]:
                        for j in range(2):
                            execution = AgentExecution(
                                project_id=project.id,
                                agent_type=agent_type,
                                correlation_id=uuid4(),
                                input_data={"test": "performance", "iteration": j},
                                output_data={"result": f"completed iteration {j}"},
                                status="completed",
                                started_at=datetime.utcnow() - timedelta(minutes=j),
                                completed_at=datetime.utcnow(),
                            )
                            session.add(execution)

                await session.commit()
                logger.info("Performance test data setup completed")

                # Store test data for cleanup
                self.test_user_id = test_user.id
                self.test_project_ids = [p.id for p in projects]

            except Exception as e:
                await session.rollback()
                logger.error("Error setting up performance test data", error=str(e))
                raise
            break

    @pytest.mark.asyncio
    async def test_query_performance_p95_requirement(self):
        """Test that query performance meets P95 < 100ms requirement."""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            test_results = []

            # Test project listing performance
            for i in range(20):
                start_time = time.time()
                response = await client.get(f"/projects?user_id={self.test_user_id}")
                end_time = time.time()

                assert response.status_code == 200
                response_time_ms = (end_time - start_time) * 1000
                test_results.append(("project_list", response_time_ms))

            # Test document listing performance
            for project_id in self.test_project_ids[:5]:
                for i in range(5):
                    start_time = time.time()
                    response = await client.get(
                        f"/projects/{project_id}/documents?user_id={self.test_user_id}"
                    )
                    end_time = time.time()

                    assert response.status_code == 200
                    response_time_ms = (end_time - start_time) * 1000
                    test_results.append(("document_list", response_time_ms))

            # Test agent execution listing performance
            for project_id in self.test_project_ids[:5]:
                for i in range(3):
                    start_time = time.time()
                    response = await client.get(
                        f"/projects/{project_id}/agents/executions?user_id={self.test_user_id}"
                    )
                    end_time = time.time()

                    assert response.status_code == 200
                    response_time_ms = (end_time - start_time) * 1000
                    test_results.append(("agent_execution_list", response_time_ms))

            # Test individual document retrieval performance
            for project_id in self.test_project_ids[:3]:
                response = await client.get(
                    f"/projects/{project_id}/documents?user_id={self.test_user_id}"
                )
                documents = response.json()["documents"]
                if documents:
                    doc_id = documents[0]["id"]
                    for i in range(5):
                        start_time = time.time()
                        response = await client.get(
                            f"/projects/{project_id}/documents/{doc_id}?user_id={self.test_user_id}"
                        )
                        end_time = time.time()

                        assert response.status_code == 200
                        response_time_ms = (end_time - start_time) * 1000
                        test_results.append(("document_get", response_time_ms))

            # Calculate P95 for each operation type
            performance_by_type = {}
            for operation, response_time in test_results:
                if operation not in performance_by_type:
                    performance_by_type[operation] = []
                performance_by_type[operation].append(response_time)

            for operation, times in performance_by_type.items():
                times.sort()
                p95_index = int(len(times) * 0.95)
                p95_time = times[p95_index] if p95_index < len(times) else times[-1]
                avg_time = statistics.mean(times)
                max_time = max(times)

                logger.info(
                    f"Performance metrics for {operation}",
                    avg_ms=avg_time,
                    p95_ms=p95_time,
                    max_ms=max_time,
                    samples=len(times),
                )

                # Assert P95 requirement
                assert p95_time < 100, (
                    f"{operation} P95 response time {p95_time}ms exceeds 100ms limit"
                )
                assert avg_time < 50, (
                    f"{operation} average response time {avg_time}ms exceeds 50ms target"
                )

    @pytest.mark.asyncio
    async def test_connection_pool_efficiency(self):
        """Test connection pool efficiency under concurrent load."""

        async def make_request(
            client: httpx.AsyncClient, endpoint: str
        ) -> Tuple[float, int]:
            """Make a request and return response time and status code."""
            start_time = time.time()
            response = await client.get(endpoint)
            end_time = time.time()
            return (end_time - start_time) * 1000, response.status_code

        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            # Test concurrent requests to health endpoint
            concurrent_levels = [1, 5, 10, 20, 50]

            for concurrency in concurrent_levels:
                tasks = [make_request(client, "/health") for _ in range(concurrency)]

                results = await asyncio.gather(*tasks)
                response_times = [r[0] for r in results]
                status_codes = [r[1] for r in results]

                # All requests should succeed
                success_count = sum(1 for code in status_codes if code == 200)
                assert success_count == concurrency, (
                    f"Only {success_count}/{concurrency} requests succeeded at concurrency {concurrency}"
                )

                # Calculate performance metrics
                avg_time = statistics.mean(response_times)
                p95_time = sorted(response_times)[int(len(response_times) * 0.95)]

                logger.info(
                    f"Connection pool performance at concurrency {concurrency}",
                    avg_ms=avg_time,
                    p95_ms=p95_time,
                    max_ms=max(response_times),
                    min_ms=min(response_times),
                )

                # Performance should degrade gracefully
                assert avg_time < 200, (
                    f"Average response time {avg_time}ms too high at concurrency {concurrency}"
                )
                assert p95_time < 500, (
                    f"P95 response time {p95_time}ms too high at concurrency {concurrency}"
                )

    @pytest.mark.asyncio
    async def test_concurrent_user_simulation(self):
        """Simulate concurrent users accessing the system."""

        async def simulate_user_session(
            user_id: str, project_id: str
        ) -> Dict[str, Any]:
            """Simulate a user session with multiple operations."""
            async with httpx.AsyncClient(app=app, base_url="http://test") as client:
                session_metrics = {
                    "operations": 0,
                    "total_time": 0,
                    "errors": 0,
                    "start_time": time.time(),
                }

                operations = [
                    f"/projects?user_id={user_id}",
                    f"/projects/{project_id}/documents?user_id={user_id}",
                    f"/projects/{project_id}/agents/executions?user_id={user_id}",
                    f"/projects/{project_id}/agents/metrics?user_id={user_id}",
                ]

                for _ in range(5):  # 5 operation cycles per user
                    for operation in operations:
                        start_time = time.time()
                        try:
                            response = await client.get(operation)
                            end_time = time.time()

                            if response.status_code == 200:
                                session_metrics["operations"] += 1
                                session_metrics["total_time"] += end_time - start_time
                            else:
                                session_metrics["errors"] += 1

                        except Exception as e:
                            session_metrics["errors"] += 1
                            logger.warning(
                                f"User session error", user_id=user_id, error=str(e)
                            )

                session_metrics["duration"] = (
                    time.time() - session_metrics["start_time"]
                )
                return session_metrics

        # Create simulated users
        num_users = 10
        user_tasks = []

        for i in range(num_users):
            user_id = f"user-sim-{i}-{uuid4()}"
            project_id = self.test_project_ids[i % len(self.test_project_ids)]
            user_tasks.append(simulate_user_session(user_id, project_id))

        # Run concurrent user sessions
        start_time = time.time()
        user_results = await asyncio.gather(*user_tasks)
        total_simulation_time = time.time() - start_time

        # Analyze results
        total_operations = sum(result["operations"] for result in user_results)
        total_errors = sum(result["errors"] for result in user_results)
        total_response_time = sum(result["total_time"] for result in user_results)

        success_rate = (
            (total_operations / (total_operations + total_errors)) * 100
            if (total_operations + total_errors) > 0
            else 0
        )
        avg_response_time = (
            (total_response_time / total_operations) * 1000
            if total_operations > 0
            else 0
        )
        operations_per_second = total_operations / total_simulation_time

        logger.info(
            "Concurrent user simulation results",
            total_users=num_users,
            total_operations=total_operations,
            total_errors=total_errors,
            success_rate=success_rate,
            avg_response_time_ms=avg_response_time,
            operations_per_second=operations_per_second,
            simulation_duration_s=total_simulation_time,
        )

        # Performance assertions
        assert success_rate >= 95, f"Success rate {success_rate}% below 95%"
        assert avg_response_time < 100, (
            f"Average response time {avg_response_time}ms above 100ms"
        )
        assert operations_per_second >= 10, (
            f"Operations per second {operations_per_second} below 10"
        )

    @pytest.mark.asyncio
    async def test_database_performance_under_stress(self):
        """Test database performance under stress conditions."""

        async def stress_operation(
            operation_type: str, iteration: int
        ) -> Dict[str, Any]:
            """Perform a stress operation and measure performance."""
            async with httpx.AsyncClient(app=app, base_url="http://test") as client:
                start_time = time.time()

                try:
                    if operation_type == "project_list":
                        response = await client.get(
                            f"/projects?user_id={self.test_user_id}"
                        )
                    elif operation_type == "document_list":
                        project_id = self.test_project_ids[
                            iteration % len(self.test_project_ids)
                        ]
                        response = await client.get(
                            f"/projects/{project_id}/documents?user_id={self.test_user_id}"
                        )
                    elif operation_type == "metrics":
                        project_id = self.test_project_ids[
                            iteration % len(self.test_project_ids)
                        ]
                        response = await client.get(
                            f"/projects/{project_id}/agents/metrics?user_id={self.test_user_id}"
                        )
                    else:
                        response = await client.get("/health")

                    end_time = time.time()
                    success = response.status_code == 200

                    return {
                        "operation_type": operation_type,
                        "iteration": iteration,
                        "response_time_ms": (end_time - start_time) * 1000,
                        "success": success,
                        "status_code": response.status_code,
                    }

                except Exception as e:
                    end_time = time.time()
                    return {
                        "operation_type": operation_type,
                        "iteration": iteration,
                        "response_time_ms": (end_time - start_time) * 1000,
                        "success": False,
                        "error": str(e),
                    }

        # Create stress test with mixed operations
        stress_operations = []
        operation_types = ["project_list", "document_list", "metrics", "health"]

        for i in range(100):  # 100 total operations
            operation_type = operation_types[i % len(operation_types)]
            stress_operations.append(stress_operation(operation_type, i))

        # Run stress test
        start_time = time.time()
        results = await asyncio.gather(*stress_operations)
        total_stress_time = time.time() - start_time

        # Analyze results
        successful_operations = [r for r in results if r.get("success", False)]
        failed_operations = [r for r in results if not r.get("success", False)]

        if successful_operations:
            response_times = [r["response_time_ms"] for r in successful_operations]
            avg_response_time = statistics.mean(response_times)
            p95_response_time = sorted(response_times)[int(len(response_times) * 0.95)]
            max_response_time = max(response_times)

            success_rate = (len(successful_operations) / len(results)) * 100
            throughput = len(successful_operations) / total_stress_time

            logger.info(
                "Stress test results",
                total_operations=len(results),
                successful_operations=len(successful_operations),
                failed_operations=len(failed_operations),
                success_rate=success_rate,
                avg_response_time_ms=avg_response_time,
                p95_response_time_ms=p95_response_time,
                max_response_time_ms=max_response_time,
                throughput_ops_per_sec=throughput,
                total_duration_s=total_stress_time,
            )

            # Stress test assertions
            assert success_rate >= 90, (
                f"Stress test success rate {success_rate}% below 90%"
            )
            assert p95_response_time < 200, (
                f"Stress test P95 response time {p95_response_time}ms above 200ms"
            )
            assert throughput >= 5, (
                f"Stress test throughput {throughput} ops/sec below 5"
            )

        else:
            pytest.fail("All stress operations failed")

    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self):
        """Test performance monitoring integration and accuracy."""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            # Generate some activity for monitoring
            for _ in range(10):
                await client.get("/health")
                await client.get(f"/projects?user_id={self.test_user_id}")

            # Check database monitoring dashboard
            response = await client.get("/database/monitoring/dashboard")
            assert response.status_code == 200

            dashboard = response.json()
            assert "metrics" in dashboard
            assert "system_health" in dashboard
            assert "timestamp" in dashboard

            metrics = dashboard["metrics"]
            assert "database" in metrics
            assert "performance_requirements" in metrics
            assert "optimizations" in metrics

            # Check connection metrics
            response = await client.get("/database/connections/metrics")
            assert response.status_code == 200

            connection_metrics = response.json()
            assert "connection_metrics" in connection_metrics
            assert "pool_efficiency" in connection_metrics

            # Verify performance requirements are being monitored
            perf_reqs = metrics["performance_requirements"]
            assert "query_response_time_p95_ms" in perf_reqs
            assert perf_reqs["query_response_time_p95_ms"] < 100, (
                "P95 response time monitoring exceeds 100ms"
            )

            # Check that monitoring data is current
            dashboard_time = datetime.fromisoformat(
                dashboard["timestamp"].replace("Z", "+00:00")
            )
            current_time = datetime.utcnow()
            time_diff = (current_time - dashboard_time).total_seconds()

            assert time_diff < 300, f"Monitoring data is {time_diff} seconds old"

            logger.info("Performance monitoring integration validated")

    @pytest.mark.asyncio
    async def test_index_usage_optimization(self):
        """Test that database indexes are being used effectively."""
        async for session in get_database_session():
            try:
                # Test query performance with and without indexes
                # Query that should use project_id index
                start_time = time.time()
                result = await session.execute(
                    select(DocumentVersion)
                    .where(DocumentVersion.project_id == self.test_project_ids[0])
                    .limit(10)
                )
                docs = result.scalars().all()
                indexed_query_time = (time.time() - start_time) * 1000

                # Query that should use composite index on document_type and version
                start_time = time.time()
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.project_id == self.test_project_ids[0],
                        DocumentVersion.document_type == "specification",
                    )
                    .order_by(DocumentVersion.version.desc())
                    .limit(5)
                )
                docs = result.scalars().all()
                composite_index_query_time = (time.time() - start_time) * 1000

                # Query that should use agent_executions indexes
                start_time = time.time()
                result = await session.execute(
                    select(AgentExecution)
                    .where(
                        AgentExecution.project_id == self.test_project_ids[0],
                        AgentExecution.status == "completed",
                    )
                    .order_by(AgentExecution.started_at.desc())
                    .limit(5)
                )
                executions = result.scalars().all()
                agent_index_query_time = (time.time() - start_time) * 1000

                logger.info(
                    "Index usage performance",
                    indexed_query_ms=indexed_query_time,
                    composite_index_query_ms=composite_index_query_time,
                    agent_index_query_ms=agent_index_query_time,
                )

                # Assert queries are using indexes effectively (fast response times)
                assert indexed_query_time < 50, (
                    f"Project ID index query too slow: {indexed_query_time}ms"
                )
                assert composite_index_query_time < 50, (
                    f"Composite index query too slow: {composite_index_query_time}ms"
                )
                assert agent_index_query_time < 50, (
                    f"Agent execution index query too slow: {agent_index_query_time}ms"
                )

            except Exception as e:
                await session.rollback()
                raise
            break

    @pytest.mark.asyncio
    async def test_memory_and_resource_efficiency(self):
        """Test memory usage and resource efficiency."""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            # Test memory efficiency with large result sets
            start_time = time.time()
            response = await client.get(
                f"/projects?user_id={self.test_user_id}&per_page=100"
            )
            end_time = time.time()

            assert response.status_code == 200
            large_query_time = (end_time - start_time) * 1000

            # Test with smaller result sets
            start_time = time.time()
            response = await client.get(
                f"/projects?user_id={self.test_user_id}&per_page=10"
            )
            end_time = time.time()

            assert response.status_code == 200
            small_query_time = (end_time - start_time) * 1000

            # Large queries should not be significantly slower
            time_ratio = (
                large_query_time / small_query_time if small_query_time > 0 else 1
            )

            logger.info(
                "Resource efficiency metrics",
                large_query_ms=large_query_time,
                small_query_ms=small_query_time,
                time_ratio=time_ratio,
            )

            assert large_query_time < 200, f"Large query too slow: {large_query_time}ms"
            assert time_ratio < 3, (
                f"Large query is {time_ratio}x slower than small query"
            )

    async def cleanup_test_data(self):
        """Clean up performance test data."""
        async for session in get_database_session():
            try:
                # Delete test data
                if hasattr(self, "test_project_ids"):
                    for project_id in self.test_project_ids:
                        result = await session.execute(
                            select(Project).where(Project.id == project_id)
                        )
                        project = result.scalar_one_or_none()
                        if project:
                            await session.delete(project)

                if hasattr(self, "test_user_id"):
                    result = await session.execute(
                        select(User).where(User.id == self.test_user_id)
                    )
                    user = result.scalar_one_or_none()
                    if user:
                        await session.delete(user)

                await session.commit()
                logger.info("Performance test data cleanup completed")

            except Exception as e:
                await session.rollback()
                logger.error("Error cleaning up performance test data", error=str(e))
            break

    @pytest.fixture(autouse=True)
    async def cleanup_after_tests(self):
        """Clean up after all performance tests."""
        yield
        await self.cleanup_test_data()


class TestLoadTestingScenarios:
    """Advanced load testing scenarios."""

    @pytest.mark.asyncio
    async def test_burst_traffic_handling(self):
        """Test system behavior under burst traffic patterns."""

        async def simulate_traffic_burst(
            burst_size: int, burst_id: int
        ) -> Dict[str, Any]:
            """Simulate a traffic burst."""
            async with httpx.AsyncClient(app=app, base_url="http://test") as client:
                start_time = time.time()
                results = []

                for i in range(burst_size):
                    request_start = time.time()
                    try:
                        response = await client.get("/health")
                        request_end = time.time()

                        results.append(
                            {
                                "success": response.status_code == 200,
                                "response_time_ms": (request_end - request_start)
                                * 1000,
                                "burst_id": burst_id,
                                "request_id": i,
                            }
                        )

                    except Exception as e:
                        results.append(
                            {
                                "success": False,
                                "error": str(e),
                                "burst_id": burst_id,
                                "request_id": i,
                            }
                        )

                burst_duration = time.time() - start_time
                successful_requests = [r for r in results if r.get("success", False)]

                return {
                    "burst_id": burst_id,
                    "burst_size": burst_size,
                    "burst_duration_s": burst_duration,
                    "successful_requests": len(successful_requests),
                    "failed_requests": len(results) - len(successful_requests),
                    "requests_per_second": len(successful_requests) / burst_duration
                    if burst_duration > 0
                    else 0,
                    "avg_response_time_ms": statistics.mean(
                        [r["response_time_ms"] for r in successful_requests]
                    )
                    if successful_requests
                    else 0,
                }

        # Simulate multiple traffic bursts
        burst_configs = [
            (20, 1),  # 20 requests, burst 1
            (50, 2),  # 50 requests, burst 2
            (100, 3),  # 100 requests, burst 3
            (50, 4),  # 50 requests, burst 4
            (20, 5),  # 20 requests, burst 5
        ]

        # Run bursts with small delays between them
        all_results = []
        for burst_size, burst_id in burst_configs:
            burst_result = await simulate_traffic_burst(burst_size, burst_id)
            all_results.append(burst_result)

            # Small delay between bursts
            await asyncio.sleep(0.5)

        # Analyze burst handling
        total_requests = sum(r["burst_size"] for r in all_results)
        total_successful = sum(r["successful_requests"] for r in all_results)
        total_failed = sum(r["failed_requests"] for r in all_results)

        overall_success_rate = (
            (total_successful / total_requests) * 100 if total_requests > 0 else 0
        )
        avg_response_time = statistics.mean(
            [
                r["avg_response_time_ms"]
                for r in all_results
                if r["avg_response_time_ms"] > 0
            ]
        )

        logger.info(
            "Burst traffic test results",
            total_requests=total_requests,
            total_successful=total_successful,
            total_failed=total_failed,
            overall_success_rate=overall_success_rate,
            avg_response_time_ms=avg_response_time,
            burst_results=all_results,
        )

        # Assert system handles bursts well
        assert overall_success_rate >= 95, (
            f"Burst test success rate {overall_success_rate}% below 95%"
        )
        assert avg_response_time < 150, (
            f"Burst test avg response time {avg_response_time}ms above 150ms"
        )

        for result in all_results:
            assert result["successful_requests"] / result["burst_size"] >= 0.9, (
                f"Burst {result['burst_id']} success rate below 90%"
            )
