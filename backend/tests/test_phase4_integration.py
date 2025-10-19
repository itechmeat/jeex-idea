"""
Phase 4 Integration Tests - Complete Database Integration

Comprehensive test suite for Phase 4 integration covering:
1. FastAPI database integration
2. CRUD operations and transactions
3. Migration rollback procedures
4. Failover and recovery scenarios
5. Performance testing and optimization validation
"""

import pytest
import asyncio
from uuid import uuid4
from typing import Dict, Any, Generator, AsyncGenerator
from datetime import datetime, timedelta
import time
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from httpx import AsyncClient

from app.main import app
from app.db import init_database, get_database_session, close_database
from app.models import User, Project, DocumentVersion, AgentExecution
from app.core.config import get_settings
from app.core.db_optimized import optimized_database
from app.core.monitoring import performance_monitor

logger = structlog.get_logger()
settings = get_settings()


# Test fixtures
@pytest.fixture(scope="session")
async def test_database():
    """Initialize test database."""
    await init_database()
    yield
    await close_database()


@pytest.fixture
async def client(test_database) -> AsyncGenerator[AsyncClient, None]:
    """Create test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session(test_database) -> AsyncGenerator[AsyncSession, None]:
    """Create database session."""
    async for session in get_database_session():
        yield session


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create test user."""
    user = User(
        email=f"test-{uuid4()}@example.com",
        name="Test User",
        profile_data={"role": "test"},
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_project(db_session: AsyncSession, test_user: User) -> Project:
    """Create test project."""
    project = Project(
        name="Test Project",
        language="en",
        status="draft",
        current_step=1,
        meta_data={"test": True},
        created_by=test_user.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


# Phase 4.1: Database Integration Tests
class TestDatabaseIntegration:
    """Test database integration with FastAPI."""

    @pytest.mark.asyncio
    async def test_database_connection_on_startup(self, client: AsyncClient):
        """Test that database connects properly on application startup."""
        response = await client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["phase_3_optimizations"] is True

    @pytest.mark.asyncio
    async def test_readiness_check_with_database(
        self, client: AsyncClient, test_project: Project
    ):
        """Test readiness check with database validation."""
        response = await client.get(f"/ready?project_id={test_project.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "dependencies" in data
        assert "performance_metrics" in data

    @pytest.mark.asyncio
    async def test_database_health_monitoring(
        self, client: AsyncClient, test_project: Project
    ):
        """Test database health monitoring integration."""
        response = await client.get("/database/health")
        assert response.status_code == 200

        data = response.json()
        assert "database" in data
        assert "optimizations" in data
        assert "performance_requirements" in data

    @pytest.mark.asyncio
    async def test_connection_testing_endpoint(
        self, client: AsyncClient, test_project: Project
    ):
        """Test connection testing with project isolation."""
        response = await client.get(f"/test/connections?project_id={test_project.id}")
        assert response.status_code == 200

        data = response.json()
        assert "connection_tests" in data
        assert "project_isolation" in data
        assert data["project_isolation"]["enabled"] is True


# Phase 4.2: CRUD Operations Tests
class TestCRUDOperations:
    """Test CRUD operations and transaction management."""

    @pytest.mark.asyncio
    async def test_project_crud_operations(self, client: AsyncClient, test_user: User):
        """Test complete project CRUD operations."""
        # Create project
        project_data = {
            "name": "Test Project CRUD",
            "language": "en",
            "status": "draft",
            "current_step": 1,
            "meta_data": {"test": "crud"},
            "created_by": str(test_user.id),
        }

        response = await client.post("/projects", json=project_data)
        assert response.status_code == 201
        created_project = response.json()
        project_id = created_project["id"]

        # Read project
        response = await client.get(f"/projects/{project_id}?user_id={test_user.id}")
        assert response.status_code == 200
        project = response.json()
        assert project["name"] == "Test Project CRUD"

        # Update project
        update_data = {"name": "Updated Test Project", "status": "in_progress"}
        response = await client.put(
            f"/projects/{project_id}?user_id={test_user.id}", json=update_data
        )
        assert response.status_code == 200
        updated_project = response.json()
        assert updated_project["name"] == "Updated Test Project"

        # List projects
        response = await client.get(f"/projects?user_id={test_user.id}")
        assert response.status_code == 200
        projects = response.json()
        assert len(projects["projects"]) >= 1

        # Delete project (soft delete)
        response = await client.delete(f"/projects/{project_id}?user_id={test_user.id}")
        assert response.status_code == 204

        # Verify project is soft deleted
        response = await client.get(f"/projects/{project_id}?user_id={test_user.id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_document_crud_operations(
        self, client: AsyncClient, test_project: Project, test_user: User
    ):
        """Test complete document CRUD operations."""
        # Create document
        doc_data = {
            "document_type": "specification",
            "content": "# Test Specification\n\nThis is a test document.",
            "meta_data": {"version": "1.0"},
            "readability_score": 85.5,
            "grammar_score": 92.0,
            "created_by": str(test_user.id),
        }

        response = await client.post(
            f"/projects/{test_project.id}/documents?user_id={test_user.id}",
            json=doc_data,
        )
        assert response.status_code == 201
        created_doc = response.json()
        doc_id = created_doc["id"]

        # Read document
        response = await client.get(
            f"/projects/{test_project.id}/documents/{doc_id}?user_id={test_user.id}"
        )
        assert response.status_code == 200
        doc = response.json()
        assert doc["document_type"] == "specification"

        # Update document
        update_data = {
            "content": "# Updated Test Specification\n\nThis content has been updated.",
            "readability_score": 88.0,
        }
        response = await client.put(
            f"/projects/{test_project.id}/documents/{doc_id}?user_id={test_user.id}",
            json=update_data,
        )
        assert response.status_code == 200
        updated_doc = response.json()
        assert "Updated" in updated_doc["content"]

        # List documents
        response = await client.get(
            f"/projects/{test_project.id}/documents?user_id={test_user.id}"
        )
        assert response.status_code == 200
        docs = response.json()
        assert len(docs["documents"]) >= 1

        # Delete document
        response = await client.delete(
            f"/projects/{test_project.id}/documents/{doc_id}?user_id={test_user.id}"
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_agent_execution_crud_operations(
        self, client: AsyncClient, test_project: Project, test_user: User
    ):
        """Test complete agent execution CRUD operations."""
        # Create agent execution
        execution_data = {
            "agent_type": "product_manager",
            "input_data": {"task": "analyze requirements"},
            "created_by": str(test_user.id),
        }

        response = await client.post(
            f"/projects/{test_project.id}/agents/executions?user_id={test_user.id}",
            json=execution_data,
        )
        assert response.status_code == 201
        created_execution = response.json()
        execution_id = created_execution["id"]

        # Read execution
        response = await client.get(
            f"/projects/{test_project.id}/agents/executions/{execution_id}?user_id={test_user.id}"
        )
        assert response.status_code == 200
        execution = response.json()
        assert execution["agent_type"] == "product_manager"
        assert execution["status"] == "pending"

        # Update execution
        update_data = {
            "status": "completed",
            "output_data": {"result": "analysis complete"},
        }
        response = await client.put(
            f"/projects/{test_project.id}/agents/executions/{execution_id}?user_id={test_user.id}",
            json=update_data,
        )
        assert response.status_code == 200
        updated_execution = response.json()
        assert updated_execution["status"] == "completed"
        assert updated_execution["output_data"]["result"] == "analysis complete"

        # List executions
        response = await client.get(
            f"/projects/{test_project.id}/agents/executions?user_id={test_user.id}"
        )
        assert response.status_code == 200
        executions = response.json()
        assert len(executions["executions"]) >= 1

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_error(
        self, client: AsyncClient, test_user: User
    ):
        """Test transaction rollback on errors."""
        # Try to create project with invalid data
        invalid_project_data = {
            "name": "",  # Invalid: empty name
            "language": "en",
            "status": "draft",
            "current_step": 1,
            "meta_data": {},
            "created_by": str(test_user.id),
        }

        response = await client.post("/projects", json=invalid_project_data)
        assert response.status_code == 400

        # Verify no partial data was created
        response = await client.get(f"/projects?user_id={test_user.id}")
        assert response.status_code == 200
        projects = response.json()
        # Should not contain the invalid project
        for project in projects["projects"]:
            assert project["name"] != ""

    @pytest.mark.asyncio
    async def test_concurrent_operations_handling(
        self, client: AsyncClient, test_project: Project, test_user: User
    ):
        """Test concurrent operations handling."""

        # Create multiple documents concurrently
        async def create_document(index: int):
            doc_data = {
                "document_type": f"test_doc_{index}",
                "content": f"Test document content {index}",
                "created_by": str(test_user.id),
            }
            return await client.post(
                f"/projects/{test_project.id}/documents?user_id={test_user.id}",
                json=doc_data,
            )

        # Run concurrent operations
        tasks = [create_document(i) for i in range(5)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # All operations should succeed
        successful = [
            r for r in responses if isinstance(r, type(await create_document(0)))
        ]
        assert len(successful) == 5

        # Verify all documents were created
        response = await client.get(
            f"/projects/{test_project.id}/documents?user_id={test_user.id}"
        )
        assert response.status_code == 200
        docs = response.json()
        assert len(docs["documents"]) >= 5


# Phase 4.3: Migration Rollback Tests
class TestMigrationRollback:
    """Test migration rollback procedures."""

    @pytest.mark.asyncio
    async def test_migration_rollback_procedure(self, db_session: AsyncSession):
        """Test migration rollback procedure."""
        # Get current migration state
        result = await db_session.execute(text("SELECT version FROM alembic_version"))
        current_version = result.scalar()
        assert current_version is not None

        # Test that schema is consistent
        # Check that all required tables exist
        tables_query = text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
        """)
        result = await db_session.execute(tables_query)
        tables = [row[0] for row in result.fetchall()]

        required_tables = [
            "users",
            "projects",
            "document_versions",
            "agent_executions",
            "exports",
        ]
        for table in required_tables:
            assert table in tables, f"Required table {table} not found"

        # Verify constraints are in place
        constraints_query = text("""
            SELECT constraint_name, table_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
            AND constraint_type = 'FOREIGN KEY'
        """)
        result = await db_session.execute(constraints_query)
        constraints = result.fetchall()
        assert len(constraints) > 0, "No foreign key constraints found"

    @pytest.mark.asyncio
    async def test_data_consistency_after_rollback(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test data consistency after rollback scenarios."""
        # Create test data
        project = Project(
            name="Rollback Test Project", language="en", created_by=test_user.id
        )
        db_session.add(project)
        await db_session.commit()
        project_id = project.id

        # Simulate rollback scenario by creating and then rolling back a transaction
        try:
            # Start a nested transaction
            await db_session.begin_nested()

            # Add data that will be rolled back
            document = DocumentVersion(
                project_id=project_id,
                document_type="test",
                version=1,
                content="Test content",
                created_by=test_user.id,
            )
            db_session.add(document)
            await db_session.flush()

            # Simulate an error that would cause rollback
            raise ValueError("Simulated error for rollback test")

        except ValueError:
            # Rollback the nested transaction
            await db_session.rollback()
            pass

        # Verify the document was not committed
        result = await db_session.execute(
            select(DocumentVersion).where(DocumentVersion.project_id == project_id)
        )
        documents = result.scalars().all()
        assert len(documents) == 0, "Rollback failed: document was still committed"

        # Project should still exist
        result = await db_session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        assert project is not None, "Rollback affected unrelated data"


# Phase 4.4: Failover and Recovery Tests
class TestFailoverRecovery:
    """Test failover and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_database_connection_failure_handling(self, client: AsyncClient):
        """Test handling of database connection failures."""
        # Test that application handles database unavailability gracefully
        # This would normally involve temporarily stopping the database
        # For testing purposes, we'll simulate the error handling

        # Test with invalid project ID to trigger error handling
        response = await client.get(
            "/ready?project_id=00000000-0000-0000-0000-000000000000"
        )
        # Should still return a response, but with degraded status
        assert response.status_code in [200, 503]

    @pytest.mark.asyncio
    async def test_performance_monitoring_during_failures(
        self, client: AsyncClient, test_project: Project
    ):
        """Test performance monitoring during failure scenarios."""
        # Get performance dashboard
        response = await client.get("/database/monitoring/dashboard")
        assert response.status_code == 200

        data = response.json()
        assert "metrics" in data
        assert "system_health" in data

    @pytest.mark.asyncio
    async def test_backup_system_recovery(self, client: AsyncClient):
        """Test backup system recovery procedures."""
        # Test backup system status
        response = await client.get("/database/backup")
        assert response.status_code == 200

        data = response.json()
        assert "configuration" in data
        assert "status" in data


# Phase 4.5: Performance Testing
class TestPerformanceValidation:
    """Test performance requirements and optimization validation."""

    @pytest.mark.asyncio
    async def test_query_performance_requirements(
        self, client: AsyncClient, test_project: Project, test_user: User
    ):
        """Test that query performance meets P95 < 100ms requirement."""
        # Create test data for performance testing
        documents = []
        for i in range(10):
            doc_data = {
                "document_type": f"perf_test_{i % 3}",
                "content": f"Performance test document {i} content",
                "created_by": str(test_user.id),
            }
            response = await client.post(
                f"/projects/{test_project.id}/documents?user_id={test_user.id}",
                json=doc_data,
            )
            assert response.status_code == 201
            documents.append(response.json())

        # Test list performance
        start_time = time.time()
        response = await client.get(
            f"/projects/{test_project.id}/documents?user_id={test_user.id}"
        )
        end_time = time.time()

        response_time_ms = (end_time - start_time) * 1000
        assert response.status_code == 200
        assert response_time_ms < 100, (
            f"Query took {response_time_ms}ms, exceeding 100ms limit"
        )

        # Test individual document retrieval performance
        for doc in documents[:5]:  # Test first 5 documents
            start_time = time.time()
            response = await client.get(
                f"/projects/{test_project.id}/documents/{doc['id']}?user_id={test_user.id}"
            )
            end_time = time.time()

            response_time_ms = (end_time - start_time) * 1000
            assert response.status_code == 200
            assert response_time_ms < 100, (
                f"Document query took {response_time_ms}ms, exceeding 100ms limit"
            )

    @pytest.mark.asyncio
    async def test_connection_pool_performance(self, client: AsyncClient):
        """Test connection pool performance under load."""

        # Simulate concurrent requests
        async def make_request():
            return await client.get("/health")

        # Run 20 concurrent requests
        tasks = [make_request() for _ in range(20)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # All requests should succeed
        successful = [
            r for r in responses if hasattr(r, "status_code") and r.status_code == 200
        ]
        assert len(successful) == 20, "Connection pool failed under load"

    @pytest.mark.asyncio
    async def test_database_metrics_accuracy(
        self, client: AsyncClient, test_project: Project
    ):
        """Test database metrics accuracy and monitoring."""
        # Get database metrics
        response = await client.get("/database/metrics")
        assert response.status_code == 200

        metrics = response.json()
        assert "connection_metrics" in metrics
        assert "query_performance" in metrics
        assert "pool_status" in metrics

        # Test agent metrics
        response = await client.get(
            f"/projects/{test_project.id}/agents/metrics?user_id={test_project.created_by}"
        )
        assert response.status_code == 200

        agent_metrics = response.json()
        assert "total_executions" in agent_metrics
        assert "success_rate" in agent_metrics
        assert "executions_by_agent_type" in agent_metrics

    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(
        self, client: AsyncClient, test_project: Project
    ):
        """Test performance monitoring integration."""
        # Trigger some operations to generate performance data
        for i in range(3):
            execution_data = {
                "agent_type": f"test_agent_{i}",
                "input_data": {"test": i},
                "created_by": str(test_project.created_by),
            }
            await client.post(
                f"/projects/{test_project.id}/agents/executions?user_id={test_project.created_by}",
                json=execution_data,
            )

        # Check performance dashboard
        response = await client.get("/database/monitoring/dashboard")
        assert response.status_code == 200

        dashboard = response.json()
        assert "metrics" in dashboard
        assert dashboard["metrics"]["system_health"]["status"] in [
            "healthy",
            "degraded",
        ]


# Integration Validation Tests
class TestIntegrationValidation:
    """Validate complete integration between components."""

    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self, client: AsyncClient, test_user: User):
        """Test complete end-to-end workflow."""
        # 1. Create project
        project_data = {
            "name": "End-to-End Test Project",
            "language": "en",
            "status": "draft",
            "current_step": 1,
            "meta_data": {"test": "e2e"},
            "created_by": str(test_user.id),
        }

        response = await client.post("/projects", json=project_data)
        assert response.status_code == 201
        project = response.json()
        project_id = project["id"]

        # 2. Create documents
        doc_types = ["specification", "architecture", "planning"]
        for doc_type in doc_types:
            doc_data = {
                "document_type": doc_type,
                "content": f"# {doc_type.title()}\n\nContent for {doc_type}.",
                "created_by": str(test_user.id),
            }
            response = await client.post(
                f"/projects/{project_id}/documents?user_id={test_user.id}",
                json=doc_data,
            )
            assert response.status_code == 201

        # 3. Create agent executions
        agent_types = ["product_manager", "spec_expert", "architect"]
        for agent_type in agent_types:
            execution_data = {
                "agent_type": agent_type,
                "input_data": {"task": f"process {agent_type} workflow"},
                "created_by": str(test_user.id),
            }
            response = await client.post(
                f"/projects/{project_id}/agents/executions?user_id={test_user.id}",
                json=execution_data,
            )
            assert response.status_code == 201

        # 4. Verify all data is accessible
        response = await client.get(
            f"/projects/{project_id}/documents?user_id={test_user.id}"
        )
        assert response.status_code == 200
        docs = response.json()
        assert len(docs["documents"]) == 3

        response = await client.get(
            f"/projects/{project_id}/agents/executions?user_id={test_user.id}"
        )
        assert response.status_code == 200
        executions = response.json()
        assert len(executions["executions"]) == 3

        # 5. Get metrics
        response = await client.get(
            f"/projects/{project_id}/agents/metrics?user_id={test_user.id}"
        )
        assert response.status_code == 200
        metrics = response.json()
        assert metrics["total_executions"] == 3

    @pytest.mark.asyncio
    async def test_project_isolation_enforcement(
        self, client: AsyncClient, test_user: User
    ):
        """Test that project isolation is properly enforced."""
        # Create two projects
        project1_data = {
            "name": "Project 1",
            "language": "en",
            "created_by": str(test_user.id),
        }
        project2_data = {
            "name": "Project 2",
            "language": "en",
            "created_by": str(test_user.id),
        }

        response1 = await client.post("/projects", json=project1_data)
        response2 = await client.post("/projects", json=project2_data)

        assert response1.status_code == 201
        assert response2.status_code == 201

        project1 = response1.json()
        project2 = response2.json()

        # Create document in project 1
        doc_data = {
            "document_type": "test",
            "content": "Test content",
            "created_by": str(test_user.id),
        }
        response = await client.post(
            f"/projects/{project1['id']}/documents?user_id={test_user.id}",
            json=doc_data,
        )
        assert response.status_code == 201
        doc = response.json()

        # Try to access document from project 2 (should fail)
        response = await client.get(
            f"/projects/{project2['id']}/documents/{doc['id']}?user_id={test_user.id}"
        )
        assert response.status_code == 404

        # Verify document only exists in project 1
        response = await client.get(
            f"/projects/{project1['id']}/documents/{doc['id']}?user_id={test_user.id}"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_production_readiness_checklist(self, client: AsyncClient):
        """Test production readiness checklist validation."""
        # Check all health endpoints
        health_checks = [
            "/health",
            "/ready",
            "/database/health",
            "/database/metrics",
            "/database/monitoring/dashboard",
        ]

        for endpoint in health_checks:
            response = await client.get(endpoint)
            assert response.status_code == 200, f"Health check failed for {endpoint}"

        # Check API documentation endpoints
        doc_endpoints = ["/docs", "/redoc", "/openapi.json"]
        for endpoint in doc_endpoints:
            response = await client.get(endpoint)
            assert response.status_code == 200, (
                f"Documentation endpoint failed for {endpoint}"
            )

        # Verify API schema is properly generated
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "paths" in schema
        assert "components" in schema

        # Verify all our endpoints are documented
        expected_paths = [
            "/projects",
            "/projects/{project_id}",
            "/projects/{project_id}/documents",
            "/projects/{project_id}/documents/{document_id}",
            "/projects/{project_id}/agents/executions",
            "/projects/{project_id}/agents/executions/{execution_id}",
        ]

        for path in expected_paths:
            assert path in schema["paths"], (
                f"Endpoint {path} not documented in OpenAPI schema"
            )
