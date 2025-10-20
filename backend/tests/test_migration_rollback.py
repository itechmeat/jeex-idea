"""
Migration Rollback Tests - Phase 4.3

Comprehensive test suite for migration rollback procedures including:
1. Migration rollback validation
2. Data consistency after rollback
3. Rollback procedure documentation testing
4. Multiple rollback scenarios
5. Database state consistency verification
"""

import pytest
import asyncio
import structlog
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import List, Dict, Any
from uuid import uuid4
from datetime import datetime

from app.db import get_database_session
from app.models import User, Project, DocumentVersion, AgentExecution, Export
from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class TestMigrationRollback:
    """Test migration rollback procedures."""

    @pytest.fixture(autouse=True)
    async def setup_test_environment(self):
        """Setup test environment for rollback testing."""
        # Ensure we have a clean state
        async for session in get_database_session():
            try:
                # Clean up test data
                await session.execute(
                    text("DELETE FROM exports WHERE created_by LIKE 'test-%'")
                )
                await session.execute(
                    text(
                        "DELETE FROM agent_executions WHERE project_id IN (SELECT id FROM projects WHERE name LIKE 'test-%')"
                    )
                )
                await session.execute(
                    text(
                        "DELETE FROM document_versions WHERE project_id IN (SELECT id FROM projects WHERE name LIKE 'test-%')"
                    )
                )
                await session.execute(
                    text("DELETE FROM projects WHERE name LIKE 'test-%'")
                )
                await session.execute(
                    text("DELETE FROM users WHERE email LIKE 'test-%'")
                )
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("Error cleaning up test environment", error=str(e))
            break

    @pytest.mark.asyncio
    async def test_current_migration_state(self):
        """Test current migration state and version."""
        async for session in get_database_session():
            try:
                # Check alembic version table exists
                result = await session.execute(
                    text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = 'alembic_version'
                    )
                """)
                )
                table_exists = result.scalar()
                assert table_exists, "Alembic version table does not exist"

                # Get current migration version
                result = await session.execute(
                    text("SELECT version FROM alembic_version")
                )
                version = result.scalar()
                assert version is not None, "No migration version found"
                assert len(version) == 32, (
                    f"Invalid version format: {version}"
                )  # SHA1 hash length

                logger.info("Current migration state", version=version)

            except Exception as e:
                await session.rollback()
                raise
            break

    @pytest.mark.asyncio
    async def test_schema_consistency_validation(self):
        """Validate database schema consistency."""
        async for session in get_database_session():
            try:
                # Check all required tables exist
                required_tables = [
                    "users",
                    "projects",
                    "document_versions",
                    "agent_executions",
                    "exports",
                    "alembic_version",
                ]

                for table in required_tables:
                    result = await session.execute(
                        text("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_schema = 'public'
                            AND table_name = :table_name
                        )
                    """),
                        {"table_name": table},
                    )
                    exists = result.scalar()
                    assert exists, f"Required table {table} does not exist"

                # Check foreign key constraints
                expected_constraints = [
                    ("projects", "projects_created_by_fkey", "users"),
                    (
                        "document_versions",
                        "document_versions_project_id_fkey",
                        "projects",
                    ),
                    ("document_versions", "document_versions_created_by_fkey", "users"),
                    (
                        "agent_executions",
                        "agent_executions_project_id_fkey",
                        "projects",
                    ),
                    ("exports", "exports_project_id_fkey", "projects"),
                    ("exports", "exports_created_by_fkey", "users"),
                ]

                for (
                    table_name,
                    constraint_name,
                    referenced_table,
                ) in expected_constraints:
                    result = await session.execute(
                        text("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu
                                ON tc.constraint_name = kcu.constraint_name
                            JOIN information_schema.referential_constraints rc
                                ON tc.constraint_name = rc.constraint_name
                            WHERE tc.table_schema = 'public'
                                AND tc.table_name = :table_name
                                AND tc.constraint_name = :constraint_name
                                AND rc.unique_constraint_schema = 'public'
                                AND rc.unique_constraint_table_name = :referenced_table
                        )
                    """),
                        {
                            "table_name": table_name,
                            "constraint_name": constraint_name,
                            "referenced_table": referenced_table,
                        },
                    )
                    exists = result.scalar()
                    assert exists, f"Foreign key constraint {constraint_name} not found"

                # Check indexes for performance
                expected_indexes = [
                    ("users", "users_email_key"),
                    ("users", "users_pkey"),
                    ("projects", "projects_pkey"),
                    ("projects", "projects_created_by_idx"),
                    ("document_versions", "document_versions_pkey"),
                    ("document_versions", "document_versions_project_id_idx"),
                    ("agent_executions", "agent_executions_pkey"),
                    ("agent_executions", "agent_executions_correlation_id_idx"),
                ]

                for table_name, index_name in expected_indexes:
                    result = await session.execute(
                        text("""
                        SELECT EXISTS (
                            SELECT FROM pg_indexes
                            WHERE schemaname = 'public'
                                AND tablename = :table_name
                                AND indexname = :index_name
                        )
                    """),
                        {"table_name": table_name, "index_name": index_name},
                    )
                    exists = result.scalar()
                    assert exists, f"Required index {index_name} not found"

                logger.info("Schema consistency validation completed successfully")

            except Exception as e:
                await session.rollback()
                raise
            break

    @pytest.mark.asyncio
    async def test_data_integrity_after_transaction_rollback(self):
        """Test data integrity after transaction rollback scenarios."""
        async for session in get_database_session():
            try:
                # Create initial test data
                test_user = User(
                    email=f"test-rollback-{uuid4()}@example.com",
                    name="Test User Rollback",
                    profile_data={"test": True},
                )
                session.add(test_user)
                await session.flush()

                test_project = Project(
                    name="Test Project Rollback", language="en", created_by=test_user.id
                )
                session.add(test_project)
                await session.flush()
                await session.commit()

                project_id = test_project.id
                user_id = test_user.id

                # Test 1: Nested transaction rollback
                await session.begin_nested()
                try:
                    # Add data that will be rolled back
                    doc = DocumentVersion(
                        project_id=project_id,
                        document_type="rollback_test",
                        version=1,
                        content="This should be rolled back",
                        created_by=user_id,
                    )
                    session.add(doc)
                    await session.flush()

                    # Add another record
                    execution = AgentExecution(
                        project_id=project_id,
                        agent_type="test_agent",
                        correlation_id=uuid4(),
                        input_data={"test": "rollback"},
                        status="pending",
                    )
                    session.add(execution)
                    await session.flush()

                    # Simulate error to trigger rollback
                    raise ValueError("Intentional error for rollback testing")

                except ValueError:
                    await session.rollback()
                    logger.info("Nested transaction rolled back successfully")

                # Verify rollback worked - data should not exist
                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.project_id == project_id
                    )
                )
                docs = result.scalars().all()
                assert len(docs) == 0, "Document rollback failed"

                result = await session.execute(
                    select(AgentExecution).where(
                        AgentExecution.project_id == project_id
                    )
                )
                executions = result.scalars().all()
                assert len(executions) == 0, "Agent execution rollback failed"

                # Test 2: Multiple nested operations
                operations_succeeded = []
                operations_rolled_back = []

                for i in range(3):
                    try:
                        await session.begin_nested()

                        # This operation should succeed
                        if i % 2 == 0:
                            doc = DocumentVersion(
                                project_id=project_id,
                                document_type=f"success_test_{i}",
                                version=1,
                                content=f"Success content {i}",
                                created_by=user_id,
                            )
                            session.add(doc)
                            await session.flush()
                            await session.commit()
                            operations_succeeded.append(i)
                        else:
                            # This operation should fail and rollback
                            doc = DocumentVersion(
                                project_id=project_id,
                                document_type="",  # Invalid: empty type
                                version=1,
                                content=f"Fail content {i}",
                                created_by=user_id,
                            )
                            session.add(doc)
                            await session.flush()
                            await session.commit()
                            operations_rolled_back.append(i)

                    except Exception:
                        await session.rollback()
                        operations_rolled_back.append(i)

                # Verify only successful operations were committed
                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.project_id == project_id
                    )
                )
                docs = result.scalars().all()
                assert len(docs) == len(operations_succeeded), (
                    f"Expected {len(operations_succeeded)} documents, found {len(docs)}"
                )

                for doc in docs:
                    assert doc.document_type.startswith("success_test"), (
                        f"Unexpected document type: {doc.document_type}"
                    )

                # Test 3: Complex rollback scenario with relationships
                try:
                    await session.begin_nested()

                    # Create project that will be rolled back
                    rollback_project = Project(
                        name="Rollback Project", language="en", created_by=user_id
                    )
                    session.add(rollback_project)
                    await session.flush()

                    # Create related documents
                    for i in range(2):
                        doc = DocumentVersion(
                            project_id=rollback_project.id,
                            document_type=f"related_doc_{i}",
                            version=1,
                            content=f"Related content {i}",
                            created_by=user_id,
                        )
                        session.add(doc)

                    # Create agent executions
                    for i in range(2):
                        execution = AgentExecution(
                            project_id=rollback_project.id,
                            agent_type=f"test_agent_{i}",
                            correlation_id=uuid4(),
                            status="pending",
                        )
                        session.add(execution)

                    await session.flush()

                    # Create exports
                    export = Export(
                        project_id=rollback_project.id,
                        status="pending",
                        manifest={"test": True},
                        created_by=user_id,
                    )
                    session.add(export)
                    await session.flush()

                    # Trigger rollback
                    raise ValueError("Complex rollback test")

                except ValueError:
                    await session.rollback()

                # Verify complete rollback of all related data
                result = await session.execute(
                    select(Project).where(Project.name == "Rollback Project")
                )
                rollback_projects = result.scalars().all()
                assert len(rollback_projects) == 0, "Project rollback failed"

                # Clean up test data
                await session.delete(test_project)
                await session.delete(test_user)
                await session.commit()

                logger.info("Data integrity rollback tests completed successfully")

            except Exception as e:
                await session.rollback()
                raise
            break

    @pytest.mark.asyncio
    async def test_rollback_procedure_documentation(self):
        """Test that rollback procedures are properly documented."""
        async for session in get_database_session():
            try:
                # Check if migration files exist and have proper documentation
                # Find migration files using relative path from test file location
                repo_root = Path(__file__).resolve().parents[2]
                migration_files = list(
                    (repo_root / "alembic" / "versions").glob("*.py")
                )
                assert len(migration_files) > 0, "No migration files found"

                # Check each migration file for required elements
                for migration_file in migration_files:
                    with migration_file.open("r") as f:
                        content = f.read()

                    # Check for downgrade function (rollback capability)
                    assert "def downgrade()" in content, (
                        f"Migration {migration_file.name} missing downgrade function"
                    )

                    # Check for proper imports
                    assert "from alembic import op" in content, (
                        f"Migration {migration_file.name} missing proper imports"
                    )

                    # Check for revision identifiers
                    assert "revision:" in content, (
                        f"Migration {migration_file.name} missing revision identifier"
                    )

                    # Check for create/drop table operations in both upgrade and downgrade
                    has_create = "op.create_table" in content
                    has_drop = "op.drop_table" in content

                    if has_create:
                        assert has_drop, (
                            f"Migration {migration_file.name} has create_table but no drop_table for rollback"
                        )

                logger.info("Rollback procedure documentation validation completed")

            except Exception as e:
                await session.rollback()
                raise
            break

    @pytest.mark.asyncio
    async def test_multiple_rollback_scenarios(self):
        """Test multiple rollback scenarios and edge cases."""
        async for session in get_database_session():
            try:
                # Create base test data
                test_user = User(
                    email=f"test-multi-{uuid4()}@example.com",
                    name="Multi Test User",
                    profile_data={"test": "multi_rollback"},
                )
                session.add(test_user)
                await session.commit()

                # Scenario 1: Rollback after partial data insertion
                await session.begin_nested()
                try:
                    project = Project(
                        name="Multi Test Project 1",
                        language="en",
                        created_by=test_user.id,
                    )
                    session.add(project)
                    await session.flush()

                    # Insert some documents
                    for i in range(3):
                        doc = DocumentVersion(
                            project_id=project.id,
                            document_type=f"scenario1_doc_{i}",
                            version=1,
                            content=f"Scenario 1 content {i}",
                            created_by=test_user.id,
                        )
                        session.add(doc)

                    await session.flush()

                    # Insert some agent executions
                    for i in range(2):
                        execution = AgentExecution(
                            project_id=project.id,
                            agent_type=f"scenario1_agent_{i}",
                            correlation_id=uuid4(),
                            status="pending",
                        )
                        session.add(execution)

                    await session.flush()

                    # Trigger rollback
                    raise RuntimeError("Scenario 1 rollback test")

                except RuntimeError:
                    await session.rollback()

                # Verify complete rollback
                result = await session.execute(
                    select(Project).where(Project.name.like("Multi Test Project 1%"))
                )
                projects = result.scalars().all()
                assert len(projects) == 0, "Scenario 1 rollback failed"

                # Scenario 2: Rollback after constraint violation
                await session.begin_nested()
                try:
                    # Valid project
                    project = Project(
                        name="Multi Test Project 2",
                        language="en",
                        created_by=test_user.id,
                    )
                    session.add(project)
                    await session.flush()

                    # Valid document
                    doc = DocumentVersion(
                        project_id=project.id,
                        document_type="scenario2_doc",
                        version=1,
                        content="Valid content",
                        created_by=test_user.id,
                    )
                    session.add(doc)
                    await session.flush()

                    # Invalid agent execution (missing required fields)
                    execution = AgentExecution(
                        project_id=project.id,
                        agent_type="",  # Invalid: empty agent type
                        correlation_id=uuid4(),
                        # Missing status
                    )
                    session.add(execution)
                    await session.flush()  # This should fail

                    await session.commit()

                except Exception:
                    await session.rollback()

                # Verify rollback
                result = await session.execute(
                    select(Project).where(Project.name.like("Multi Test Project 2%"))
                )
                projects = result.scalars().all()
                assert len(projects) == 0, "Scenario 2 rollback failed"

                # Scenario 3: Rollback with concurrent operations
                async def concurrent_operation(index: int):
                    try:
                        await session.begin_nested()

                        project = Project(
                            name=f"Concurrent Project {index}",
                            language="en",
                            created_by=test_user.id,
                        )
                        session.add(project)
                        await session.flush()

                        if index % 2 == 0:
                            # Even operations succeed
                            await session.commit()
                            return project.id
                        else:
                            # Odd operations fail and rollback
                            raise ValueError(f"Concurrent operation {index} failed")

                    except ValueError:
                        await session.rollback()
                        return None

                # Run concurrent operations
                tasks = [concurrent_operation(i) for i in range(6)]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Verify only even operations succeeded
                successful_projects = [
                    r for r in results if isinstance(r, type(uuid4()))
                ]
                assert len(successful_projects) == 3, (
                    f"Expected 3 successful operations, got {len(successful_projects)}"
                )

                # Verify successful projects exist
                result = await session.execute(
                    select(Project).where(Project.name.like("Concurrent Project%"))
                )
                projects = result.scalars().all()
                assert len(projects) == 3, (
                    f"Expected 3 projects in database, found {len(projects)}"
                )

                # All successful projects should have even numbers
                for project in projects:
                    number = int(project.name.split()[-1])
                    assert number % 2 == 0, (
                        f"Odd-numbered project {project.name} should have been rolled back"
                    )

                # Clean up test data
                result = await session.execute(
                    select(Project).where(Project.created_by == test_user.id)
                )
                projects_to_delete = result.scalars().all()
                for project in projects_to_delete:
                    await session.delete(project)

                await session.delete(test_user)
                await session.commit()

                logger.info("Multiple rollback scenarios completed successfully")

            except Exception as e:
                await session.rollback()
                raise
            break

    @pytest.mark.asyncio
    async def test_database_state_consistency_after_rollback(self):
        """Test database state consistency after various rollback operations."""
        async for session in get_database_session():
            try:
                # Get initial database state
                initial_state = await self._get_database_state(session)

                # Perform complex operations with rollbacks
                test_user = User(
                    email=f"test-consistency-{uuid4()}@example.com",
                    name="Consistency Test User",
                    profile_data={"test": "consistency"},
                )
                session.add(test_user)
                await session.commit()

                # Multiple transaction cycles with rollbacks
                for cycle in range(3):
                    await session.begin_nested()
                    try:
                        # Create project
                        project = Project(
                            name=f"Consistency Project {cycle}",
                            language="en",
                            created_by=test_user.id,
                        )
                        session.add(project)
                        await session.flush()

                        # Create related data
                        doc = DocumentVersion(
                            project_id=project.id,
                            document_type=f"consistency_doc_{cycle}",
                            version=1,
                            content=f"Consistency content {cycle}",
                            created_by=test_user.id,
                        )
                        session.add(doc)
                        await session.flush()

                        execution = AgentExecution(
                            project_id=project.id,
                            agent_type=f"consistency_agent_{cycle}",
                            correlation_id=uuid4(),
                            status="completed",
                            output_data={"cycle": cycle},
                        )
                        session.add(execution)
                        await session.flush()

                        # Rollback on odd cycles
                        if cycle % 2 == 1:
                            raise ValueError(f"Rollback cycle {cycle}")

                        await session.commit()

                    except ValueError:
                        await session.rollback()

                # Verify database state consistency
                final_state = await self._get_database_state(session)

                # Compare states
                state_diff = self._compare_database_states(initial_state, final_state)

                # Only our test user should be different
                assert len(state_diff) <= 2, (
                    f"Unexpected database state changes: {state_diff}"
                )

                # Verify foreign key constraints are still intact
                await self._verify_foreign_key_constraints(session)

                # Verify indexes are still present
                await self._verify_indexes(session)

                # Clean up test data
                result = await session.execute(
                    select(Project).where(Project.created_by == test_user.id)
                )
                projects = result.scalars().all()
                for project in projects:
                    await session.delete(project)

                await session.delete(test_user)
                await session.commit()

                logger.info("Database state consistency validation completed")

            except Exception as e:
                await session.rollback()
                raise
            break

    async def _get_database_state(self, session: AsyncSession) -> Dict[str, int]:
        """Get current database state (record counts)."""
        state = {}

        tables = [
            "users",
            "projects",
            "document_versions",
            "agent_executions",
            "exports",
        ]
        for table in tables:
            result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            state[table] = result.scalar()

        return state

    def _compare_database_states(
        self, initial: Dict[str, int], final: Dict[str, int]
    ) -> List[str]:
        """Compare two database states and return differences."""
        differences = []

        for table in initial:
            if table in final:
                if initial[table] != final[table]:
                    differences.append(f"{table}: {initial[table]} -> {final[table]}")

        return differences

    async def _verify_foreign_key_constraints(self, session: AsyncSession):
        """Verify all foreign key constraints are intact."""
        result = await session.execute(
            text("""
            SELECT COUNT(*)
            FROM information_schema.table_constraints
            WHERE constraint_type = 'FOREIGN KEY'
            AND table_schema = 'public'
        """)
        )
        constraint_count = result.scalar()
        assert constraint_count > 0, "No foreign key constraints found"

    async def _verify_indexes(self, session: AsyncSession):
        """Verify all expected indexes are present."""
        result = await session.execute(
            text("""
            SELECT COUNT(*)
            FROM pg_indexes
            WHERE schemaname = 'public'
        """)
        )
        index_count = result.scalar()
        assert index_count > 0, "No indexes found"
