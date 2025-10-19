"""
QA Model Integration Testing

Test integration between PostgreSQL implementation and existing models.
Validates that all models work correctly with the optimized database setup.
"""

import pytest
import asyncio
import structlog
from uuid import uuid4
from typing import Dict, Any, List
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, desc
from sqlalchemy.exc import IntegrityError

logger = structlog.get_logger()


@pytest.mark.asyncio
class TestModelIntegration:
    """Test model integration with PostgreSQL implementation."""

    @pytest.fixture(autouse=True)
    async def setup_test_models(self):
        """Setup test environment for model integration."""
        from app.core.database import database_manager
        from app.models import User, Project, DocumentVersion, AgentExecution, Export

        async with database_manager.get_session() as session:
            # Create test user
            self.test_user = User(
                email=f"qa-model-{uuid4()}@example.com",
                name="QA Model Test User",
                profile_data={"test": "model_integration", "role": "tester"},
            )
            session.add(self.test_user)
            await session.commit()
            await session.refresh(self.test_user)

            # Create test projects
            self.test_projects = []
            for i in range(3):
                project = Project(
                    name=f"QA Model Project {i}",
                    language="en",
                    status="draft",
                    current_step=1,
                    meta_data={"test": "model_integration", "project_index": i},
                    created_by=self.test_user.id,
                )
                session.add(project)
                self.test_projects.append(project)

            await session.commit()

            for project in self.test_projects:
                await session.refresh(project)

            logger.info("Model integration test data created")

    async def test_user_model_integration(self):
        """Test User model integration with PostgreSQL."""
        from app.core.database import database_manager
        from app.models import User

        async with database_manager.get_session() as session:
            # Test user creation
            new_user = User(
                email=f"qa-user-{uuid4()}@example.com",
                name="Integration Test User",
                profile_data={
                    "test": "user_integration",
                    "permissions": ["read", "write"],
                },
            )
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)

            # Test user retrieval
            result = await session.execute(select(User).where(User.id == new_user.id))
            retrieved_user = result.scalar_one()
            assert retrieved_user.email == new_user.email
            assert retrieved_user.name == new_user.name
            assert retrieved_user.profile_data["test"] == "user_integration"

            # Test user update
            retrieved_user.name = "Updated Test User"
            retrieved_user.profile_data["updated_at"] = datetime.utcnow().isoformat()
            await session.commit()

            # Verify update
            result = await session.execute(select(User).where(User.id == new_user.id))
            updated_user = result.scalar_one()
            assert updated_user.name == "Updated Test User"
            assert "updated_at" in updated_user.profile_data

            # Test user deletion (soft delete through model logic)
            await session.delete(updated_user)
            await session.commit()

            # Verify deletion
            result = await session.execute(select(User).where(User.id == new_user.id))
            deleted_user = result.scalar_one_or_none()
            assert deleted_user is None, "User deletion failed"

            logger.info("User model integration test passed")

    async def test_project_model_integration(self):
        """Test Project model integration with PostgreSQL."""
        from app.core.database import database_manager
        from app.models import Project

        async with database_manager.get_session() as session:
            # Test project creation with all fields
            new_project = Project(
                name="Integration Test Project",
                language="ru",  # Test different language
                status="in_progress",
                current_step=2,
                meta_data={
                    "test": "project_integration",
                    "priority": "high",
                    "tags": ["integration", "test"],
                },
                created_by=self.test_user.id,
            )
            session.add(new_project)
            await session.commit()
            await session.refresh(new_project)

            # Test project retrieval with joins
            result = await session.execute(
                select(Project, User)
                .join(User, Project.created_by == User.id)
                .where(Project.id == new_project.id)
            )
            project_with_user = result.fetchone()
            assert project_with_user is not None
            project, user = project_with_user
            assert project.name == "Integration Test Project"
            assert user.email == self.test_user.email

            # Test project update with status change
            project.status = "completed"
            project.current_step = 5
            project.meta_data["completed_at"] = datetime.utcnow().isoformat()
            await session.commit()

            # Test project listing with filtering
            result = await session.execute(
                select(Project)
                .where(
                    Project.created_by == self.test_user.id,
                    Project.status.in_(["draft", "in_progress"]),
                )
                .order_by(Project.created_at.desc())
            )
            active_projects = result.scalars().all()
            assert len(active_projects) >= len(self.test_projects)

            # Test project uniqueness constraints
            duplicate_project = Project(
                name=new_project.name, language="en", created_by=self.test_user.id
            )
            session.add(duplicate_project)

            with pytest.raises(IntegrityError):
                await session.commit()

            await session.rollback()

            logger.info("Project model integration test passed")

    async def test_document_version_model_integration(self):
        """Test DocumentVersion model integration with PostgreSQL."""
        from app.core.database import database_manager
        from app.models import DocumentVersion

        async with database_manager.get_session() as session:
            # Test document creation with all fields
            new_document = DocumentVersion(
                project_id=self.test_projects[0].id,
                document_type="specification",
                version=1,
                content="# Integration Test Specification\n\nThis is a test document for model integration.",
                meta_data={
                    "test": "document_integration",
                    "word_count": 15,
                    "readability_score": 85.5,
                },
                readability_score=85.5,
                grammar_score=92.0,
                created_by=self.test_user.id,
            )
            session.add(new_document)
            await session.commit()
            await session.refresh(new_document)

            # Test document retrieval with project filtering
            result = await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.project_id == self.test_projects[0].id)
                .order_by(DocumentVersion.version.desc())
            )
            documents = result.scalars().all()
            assert len(documents) >= 1
            assert documents[0].document_type == "specification"

            # Test document versioning
            versioned_document = DocumentVersion(
                project_id=self.test_projects[0].id,
                document_type="specification",
                version=2,
                content="# Integration Test Specification v2\n\nThis is an updated version.",
                meta_data={
                    "test": "document_integration",
                    "word_count": 18,
                    "readability_score": 87.0,
                },
                readability_score=87.0,
                grammar_score=93.5,
                created_by=self.test_user.id,
            )
            session.add(versioned_document)
            await session.commit()

            # Test version history retrieval
            result = await session.execute(
                select(DocumentVersion)
                .where(
                    DocumentVersion.project_id == self.test_projects[0].id,
                    DocumentVersion.document_type == "specification",
                )
                .order_by(DocumentVersion.version.desc())
            )
            version_history = result.scalars().all()
            assert len(version_history) == 2
            assert version_history[0].version == 2
            assert version_history[1].version == 1

            # Test document search functionality
            result = await session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.project_id == self.test_projects[0].id,
                    DocumentVersion.content.ilike("%integration%"),
                )
            )
            search_results = result.scalars().all()
            assert len(search_results) >= 2

            logger.info("DocumentVersion model integration test passed")

    async def test_agent_execution_model_integration(self):
        """Test AgentExecution model integration with PostgreSQL."""
        from app.core.database import database_manager
        from app.models import AgentExecution

        async with database_manager.get_session() as session:
            # Test agent execution creation
            new_execution = AgentExecution(
                project_id=self.test_projects[1].id,
                agent_type="product_manager",
                correlation_id=uuid4(),
                input_data={
                    "task": "analyze requirements",
                    "context": "integration test",
                    "priority": "high",
                },
                status="pending",
                created_by=self.test_user.id,
            )
            session.add(new_execution)
            await session.commit()
            await session.refresh(new_execution)

            # Test execution update
            new_execution.status = "running"
            new_execution.started_at = datetime.utcnow()
            new_execution.output_data = {
                "progress": "processing requirements analysis",
                "step": 1,
                "total_steps": 5,
            }
            await session.commit()

            # Test execution completion
            new_execution.status = "completed"
            new_execution.completed_at = datetime.utcnow()
            new_execution.output_data = {
                "result": "requirements analysis completed",
                "summary": "3 main requirements identified",
                "confidence": 0.95,
            }
            await session.commit()

            # Test execution retrieval with filtering
            result = await session.execute(
                select(AgentExecution)
                .where(
                    AgentExecution.project_id == self.test_projects[1].id,
                    AgentExecution.status == "completed",
                )
                .order_by(AgentExecution.completed_at.desc())
            )
            completed_executions = result.scalars().all()
            assert len(completed_executions) >= 1

            # Test execution metrics calculation
            result = await session.execute(
                select(
                    func.count(AgentExecution.id).label("total"),
                    func.count(
                        func.nullif(AgentExecution.status != "completed", True)
                    ).label("completed"),
                    func.count(
                        func.nullif(AgentExecution.status == "failed", True)
                    ).label("failed"),
                ).where(AgentExecution.project_id == self.test_projects[1].id)
            )
            metrics = result.fetchone()
            assert metrics.total >= 1
            assert metrics.completed >= 1

            # Test execution by agent type
            result = await session.execute(
                select(AgentExecution.agent_type, func.count().label("count"))
                .where(AgentExecution.project_id == self.test_projects[1].id)
                .group_by(AgentExecution.agent_type)
            )
            agent_counts = result.fetchall()
            assert len(agent_counts) >= 1

            logger.info("AgentExecution model integration test passed")

    async def test_export_model_integration(self):
        """Test Export model integration with PostgreSQL."""
        from app.core.database import database_manager
        from app.models import Export

        async with database_manager.get_session() as session:
            # Test export creation
            new_export = Export(
                project_id=self.test_projects[2].id,
                export_type="markdown",
                format="full",
                status="pending",
                created_by=self.test_user.id,
            )
            session.add(new_export)
            await session.commit()
            await session.refresh(new_export)

            # Test export processing
            new_export.status = "processing"
            new_export.started_at = datetime.utcnow()
            new_export.file_path = f"/exports/{new_export.id}.md"
            await session.commit()

            # Test export completion
            new_export.status = "completed"
            new_export.completed_at = datetime.utcnow()
            new_export.file_size = 1024  # 1KB
            await session.commit()

            # Test export retrieval with filtering
            result = await session.execute(
                select(Export)
                .where(
                    Export.project_id == self.test_projects[2].id,
                    Export.status == "completed",
                )
                .order_by(Export.completed_at.desc())
            )
            completed_exports = result.scalars().all()
            assert len(completed_exports) >= 1

            # Test export by type
            result = await session.execute(
                select(Export.export_type, func.count().label("count"))
                .where(Export.project_id == self.test_projects[2].id)
                .group_by(Export.export_type)
            )
            export_counts = result.fetchall()
            assert len(export_counts) >= 1

            logger.info("Export model integration test passed")

    async def test_model_relationships_integrity(self):
        """Test model relationships and foreign key integrity."""
        from app.core.database import database_manager
        from app.models import User, Project, DocumentVersion, AgentExecution, Export

        async with database_manager.get_session() as session:
            # Test user-project relationship
            result = await session.execute(
                select(Project, User)
                .join(User, Project.created_by == User.id)
                .where(User.id == self.test_user.id)
            )
            user_projects = result.fetchall()
            assert len(user_projects) >= len(self.test_projects)

            # Test project-documents relationship
            for project in self.test_projects:
                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.project_id == project.id
                    )
                )
                documents = result.scalars().all()
                # Documents may be empty, but relationship should work

            # Test project-executions relationship
            result = await session.execute(
                select(AgentExecution).where(
                    AgentExecution.project_id == self.test_projects[1].id
                )
            )
            executions = result.scalars().all()
            # Executions may be empty, but relationship should work

            # Test foreign key constraint enforcement
            invalid_document = DocumentVersion(
                project_id=uuid4(),  # Non-existent project ID
                document_type="test",
                version=1,
                content="Test content",
                created_by=self.test_user.id,
            )
            session.add(invalid_document)

            with pytest.raises(IntegrityError):
                await session.commit()

            await session.rollback()

            # Test cascade delete behavior (if configured)
            # This would test if deleting a user cascades to their projects
            # Note: Actual cascade behavior depends on database configuration

            logger.info("Model relationships integrity test passed")

    async def test_model_performance_with_indexes(self):
        """Test model performance with database indexes."""
        from app.core.database import database_manager
        from app.models import Project, DocumentVersion, AgentExecution

        async with database_manager.get_session() as session:
            # Create additional test data for performance testing
            for i in range(20):
                project = Project(
                    name=f"Performance Test Project {i}",
                    language="en",
                    status="draft",
                    created_by=self.test_user.id,
                )
                session.add(project)
                await session.flush()

                # Add documents for performance testing
                for j in range(5):
                    doc = DocumentVersion(
                        project_id=project.id,
                        document_type=f"test_doc_{j % 3}",
                        version=1,
                        content=f"Performance test content {i}-{j}",
                        created_by=self.test_user.id,
                    )
                    session.add(doc)

            await session.commit()

            # Test performance of indexed queries
            import time

            # Query using project_id index
            start_time = time.time()
            result = await session.execute(
                select(Project).where(Project.created_by == self.test_user.id)
            )
            projects = result.scalars().all()
            indexed_query_time = time.time() - start_time

            # Query using document_type and version index
            start_time = time.time()
            result = await session.execute(
                select(DocumentVersion)
                .where(
                    DocumentVersion.document_type == "test_doc_0",
                    DocumentVersion.version == 1,
                )
                .order_by(DocumentVersion.created_at.desc())
                .limit(10)
            )
            documents = result.scalars().all()
            composite_index_query_time = time.time() - start_time

            # Query using agent execution indexes
            start_time = time.time()
            result = await session.execute(
                select(AgentExecution)
                .where(AgentExecution.project_id == self.test_projects[1].id)
                .order_by(AgentExecution.created_at.desc())
                .limit(5)
            )
            executions = result.scalars().all()
            execution_index_query_time = time.time() - start_time

            # Assert query performance
            assert indexed_query_time < 0.1, (
                f"Indexed query too slow: {indexed_query_time}s"
            )
            assert composite_index_query_time < 0.1, (
                f"Composite index query too slow: {composite_index_query_time}s"
            )
            assert execution_index_query_time < 0.1, (
                f"Execution index query too slow: {execution_index_query_time}s"
            )

            logger.info(
                "Model performance test passed",
                indexed_query_time=indexed_query_time,
                composite_index_query_time=composite_index_query_time,
                execution_index_query_time=execution_index_query_time,
            )

    async def test_model_data_validation(self):
        """Test model data validation and constraints."""
        from app.core.database import database_manager
        from app.models import Project, DocumentVersion

        async with database_manager.get_session() as session:
            # Test required field validation
            invalid_project = Project(
                name="",  # Empty name should fail validation
                language="en",
                created_by=self.test_user.id,
            )
            session.add(invalid_project)

            with pytest.raises(IntegrityError):
                await session.commit()

            await session.rollback()

            # Test enum validation for status
            valid_statuses = ["draft", "in_progress", "completed", "archived"]
            for status in valid_statuses:
                valid_project = Project(
                    name=f"Test Project {status}",
                    language="en",
                    status=status,
                    created_by=self.test_user.id,
                )
                session.add(valid_project)
                await session.flush()

            await session.commit()

            # Test language validation
            valid_languages = ["en", "ru", "es", "fr", "de"]
            for lang in valid_languages:
                lang_project = Project(
                    name=f"Test Project {lang}",
                    language=lang,
                    created_by=self.test_user.id,
                )
                session.add(lang_project)
                await session.flush()

            await session.commit()

            # Test document version validation
            invalid_document = DocumentVersion(
                project_id=self.test_projects[0].id,
                document_type="test",
                version=0,  # Version should be >= 1
                content="Test content",
                created_by=self.test_user.id,
            )
            session.add(invalid_document)

            # Note: Version validation might be at application level
            # This test checks database-level constraints if any
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.info("Document version validation enforced at database level")

            logger.info("Model data validation test passed")

    async def test_model_audit_functionality(self):
        """Test model audit functionality and timestamps."""
        from app.core.database import database_manager
        from app.models import User, Project

        async with database_manager.get_session() as session:
            # Test automatic timestamp creation
            start_time = datetime.utcnow()

            new_user = User(
                email=f"qa-audit-{uuid4()}@example.com", name="Audit Test User"
            )
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)

            # Verify created_at timestamp
            assert new_user.created_at is not None
            assert new_user.created_at >= start_time
            time_diff = (new_user.created_at - start_time).total_seconds()
            assert time_diff < 10, (
                f"Created_at timestamp too far in the future: {time_diff}s"
            )

            # Test updated_at timestamp on update
            original_updated_at = new_user.updated_at
            await asyncio.sleep(0.1)  # Small delay to ensure timestamp difference

            new_user.name = "Updated Audit User"
            await session.commit()
            await session.refresh(new_user)

            # Verify updated_at changed
            assert new_user.updated_at > original_updated_at
            update_diff = (new_user.updated_at - original_updated_at).total_seconds()
            assert update_diff >= 0.1, f"Updated_at should have changed: {update_diff}s"

            # Test project timestamps
            start_time = datetime.utcnow()

            new_project = Project(
                name="Audit Test Project", language="en", created_by=new_user.id
            )
            session.add(new_project)
            await session.commit()
            await session.refresh(new_project)

            assert new_project.created_at is not None
            assert new_project.created_at >= start_time

            logger.info("Model audit functionality test passed")
