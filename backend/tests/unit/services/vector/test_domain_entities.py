"""
Unit tests for vector domain entities.

Tests all domain entities and value objects to ensure proper validation
and business logic enforcement.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from app.services.vector.domain.entities import (
    ProjectId,
    LanguageCode,
    ContentHash,
    VectorData,
    SearchContext,
    VectorPoint,
    SearchResult,
    DocumentType,
    CollectionHealth,
    HealthStatus,
)


class TestProjectId:
    """Test ProjectId value object."""

    def test_valid_project_id(self):
        """Test valid project ID creation."""
        project_id_str = "550e8400-e29b-41d4-a716-446655440000"
        project_id = ProjectId(project_id_str)
        assert str(project_id) == project_id_str

    def test_invalid_project_id(self):
        """Test invalid project ID raises ValueError."""
        with pytest.raises(ValueError, match="Invalid project_id format"):
            ProjectId("invalid-uuid")


class TestLanguageCode:
    """Test LanguageCode value object."""

    def test_valid_language_code(self):
        """Test valid language code creation."""
        lang = LanguageCode("en")
        assert str(lang) == "en"

        lang = LanguageCode("ru")
        assert str(lang) == "ru"

    def test_invalid_language_code(self):
        """Test invalid language code raises ValueError."""
        with pytest.raises(ValueError, match="Invalid language code format"):
            LanguageCode("invalid")

        with pytest.raises(ValueError, match="Invalid language code format"):
            LanguageCode("eng")

        with pytest.raises(ValueError, match="Invalid language code format"):
            LanguageCode("e")


class TestContentHash:
    """Test ContentHash value object."""

    def test_content_hash_creation(self):
        """Test content hash creation."""
        content = "test content"
        content_hash = ContentHash.from_content(content)
        assert isinstance(content_hash.value, str)
        assert len(content_hash.value) == 64  # SHA256 hex length

    def test_content_hash_deterministic(self):
        """Test content hash is deterministic."""
        content = "test content"
        hash1 = ContentHash.from_content(content)
        hash2 = ContentHash.from_content(content)
        assert hash1.value == hash2.value

    def test_content_hash_different_for_different_content(self):
        """Test content hash differs for different content."""
        hash1 = ContentHash.from_content("content1")
        hash2 = ContentHash.from_content("content2")
        assert hash1.value != hash2.value


class TestVectorData:
    """Test VectorData value object."""

    def test_valid_vector_data(self):
        """Test valid vector data creation."""
        vector = [0.1] * 1536
        vector_data = VectorData(vector)
        assert len(vector_data) == 1536
        assert vector_data.to_list() == vector

    def test_invalid_vector_dimension(self):
        """Test invalid vector dimension raises ValueError."""
        with pytest.raises(ValueError, match="Invalid vector dimension"):
            VectorData([0.1] * 1000)

        with pytest.raises(ValueError, match="Invalid vector dimension"):
            VectorData([0.1] * 2000)

    def test_invalid_vector_values(self):
        """Test invalid vector values raise ValueError."""
        with pytest.raises(ValueError, match="Vector values must be numbers"):
            VectorData(["invalid"] * 1536)

        with pytest.raises(
            ValueError, match="Vector values must be numbers between -1 and 1"
        ):
            VectorData([2.0] * 1536)

        with pytest.raises(
            ValueError, match="Vector values must be numbers between -1 and 1"
        ):
            VectorData([-2.0] * 1536)


class TestSearchContext:
    """Test SearchContext value object."""

    def test_valid_search_context(self):
        """Test valid search context creation."""
        context = SearchContext.create("550e8400-e29b-41d4-a716-446655440000", "en")
        assert str(context.project_id) == "550e8400-e29b-41d4-a716-446655440000"
        assert str(context.language) == "en"

    def test_invalid_search_context(self):
        """Test invalid search context raises ValueError."""
        with pytest.raises(ValueError):
            SearchContext.create("invalid-uuid", "en")

        with pytest.raises(ValueError):
            SearchContext.create("550e8400-e29b-41d4-a716-446655440000", "invalid")


class TestVectorPoint:
    """Test VectorPoint domain entity."""

    def test_valid_vector_point_creation(self):
        """Test valid vector point creation."""
        vector = VectorData([0.1] * 1536)
        point = VectorPoint(
            vector=vector,
            content="test content",
            project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
            language=LanguageCode("en"),
            document_type=DocumentType.KNOWLEDGE,
        )

        assert point.content == "test content"
        assert point.document_type == DocumentType.KNOWLEDGE
        assert point.importance == 1.0
        assert point.title is None
        assert isinstance(point.created_at, datetime)
        assert isinstance(point.updated_at, datetime)

    def test_vector_point_importance_validation(self):
        """Test importance validation."""
        vector = VectorData([0.1] * 1536)

        with pytest.raises(ValueError, match="Importance must be between 0.0 and 1.0"):
            VectorPoint(
                vector=vector,
                content="test",
                project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
                language=LanguageCode("en"),
                document_type=DocumentType.KNOWLEDGE,
                importance=1.5,
            )

        with pytest.raises(ValueError, match="Importance must be between 0.0 and 1.0"):
            VectorPoint(
                vector=vector,
                content="test",
                project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
                language=LanguageCode("en"),
                document_type=DocumentType.KNOWLEDGE,
                importance=-0.1,
            )

    def test_vector_point_metadata_reserved_fields(self):
        """Test metadata cannot contain reserved fields."""
        vector = VectorData([0.1] * 1536)

        with pytest.raises(ValueError, match="Metadata contains reserved fields"):
            VectorPoint(
                vector=vector,
                content="test",
                project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
                language=LanguageCode("en"),
                document_type=DocumentType.KNOWLEDGE,
                metadata={"project_id": "forbidden"},
            )

    def test_vector_point_auto_content_hash(self):
        """Test content hash is automatically computed."""
        vector = VectorData([0.1] * 1536)
        point = VectorPoint(
            vector=vector,
            content="test content",
            project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
            language=LanguageCode("en"),
            document_type=DocumentType.KNOWLEDGE,
        )

        assert (
            point.content_hash.value == ContentHash.from_content("test content").value
        )

    def test_vector_point_update_content(self):
        """Test content update functionality."""
        vector = VectorData([0.1] * 1536)
        point = VectorPoint(
            vector=vector,
            content="original content",
            project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
            language=LanguageCode("en"),
            document_type=DocumentType.KNOWLEDGE,
        )

        original_hash = point.content_hash.value
        original_updated_at = point.updated_at

        point.update_content("updated content")

        assert point.content == "updated content"
        assert point.content_hash.value != original_hash
        assert point.updated_at > original_updated_at

    def test_vector_point_to_qdrant_payload(self):
        """Test Qdrant payload conversion."""
        vector = VectorData([0.1] * 1536)
        point = VectorPoint(
            vector=vector,
            content="test content",
            project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
            language=LanguageCode("en"),
            document_type=DocumentType.KNOWLEDGE,
            title="Test Document",
            metadata={"source": "test"},
            importance=0.8,
        )

        payload = point.get_qdrant_payload()

        assert payload["project_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert payload["language"] == "en"
        assert payload["type"] == "knowledge"
        assert payload["content"] == "test content"
        assert payload["title"] == "Test Document"
        assert payload["metadata"] == {"source": "test"}
        assert payload["importance"] == 0.8
        assert "created_at" in payload
        assert "updated_at" in payload
        assert "content_hash" in payload


class TestSearchResult:
    """Test SearchResult domain entity."""

    def test_valid_search_result(self):
        """Test valid search result creation."""
        vector = VectorData([0.1] * 1536)
        point = VectorPoint(
            vector=vector,
            content="test",
            project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
            language=LanguageCode("en"),
            document_type=DocumentType.KNOWLEDGE,
        )

        result = SearchResult(point=point, score=0.95, rank=1)

        assert result.point == point
        assert result.score == 0.95
        assert result.rank == 1
        assert result.is_relevant

    def test_invalid_search_result_score(self):
        """Test invalid score raises ValueError."""
        vector = VectorData([0.1] * 1536)
        point = VectorPoint(
            vector=vector,
            content="test",
            project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
            language=LanguageCode("en"),
            document_type=DocumentType.KNOWLEDGE,
        )

        with pytest.raises(ValueError, match="Score must be between 0.0 and 1.0"):
            SearchResult(point=point, score=1.5, rank=1)

        with pytest.raises(ValueError, match="Score must be between 0.0 and 1.0"):
            SearchResult(point=point, score=-0.1, rank=1)

    def test_invalid_search_result_rank(self):
        """Test invalid rank raises ValueError."""
        vector = VectorData([0.1] * 1536)
        point = VectorPoint(
            vector=vector,
            content="test",
            project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
            language=LanguageCode("en"),
            document_type=DocumentType.KNOWLEDGE,
        )

        with pytest.raises(ValueError, match="Rank must be >= 1"):
            SearchResult(point=point, score=0.95, rank=0)

    def test_search_result_relevance(self):
        """Test relevance determination."""
        vector = VectorData([0.1] * 1536)
        point = VectorPoint(
            vector=vector,
            content="test",
            project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
            language=LanguageCode("en"),
            document_type=DocumentType.KNOWLEDGE,
        )

        relevant_result = SearchResult(point=point, score=0.8, rank=1)
        assert relevant_result.is_relevant

        non_relevant_result = SearchResult(point=point, score=0.3, rank=1)
        assert not non_relevant_result.is_relevant

    def test_search_result_to_dict(self):
        """Test dictionary conversion."""
        vector = VectorData([0.1] * 1536)
        point = VectorPoint(
            vector=vector,
            content="test content that is longer than 200 characters " * 10,
            project_id=ProjectId("550e8400-e29b-41d4-a716-446655440000"),
            language=LanguageCode("en"),
            document_type=DocumentType.KNOWLEDGE,
            title="Test Document",
            metadata={"source": "test"},
        )

        result = SearchResult(point=point, score=0.95, rank=1)
        result_dict = result.to_dict()

        assert "id" in result_dict
        assert result_dict["title"] == "Test Document"
        assert "content" in result_dict
        assert len(result_dict["content"]) <= 203  # Should be truncated with "..."
        assert result_dict["score"] == 0.95
        assert result_dict["rank"] == 1
        assert result_dict["metadata"] == {"source": "test"}
        assert result_dict["document_type"] == "knowledge"


class TestCollectionHealth:
    """Test CollectionHealth domain entity."""

    def test_healthy_collection(self):
        """Test healthy collection status."""
        health = CollectionHealth(
            collection_name="test_collection",
            status=HealthStatus.HEALTHY,
            vector_count=1000,
            indexed_fields=["project_id", "language"],
            config_status={"hnsw_optimized": True},
        )

        assert health.is_healthy
        assert health.to_dict()["status"] == "healthy"

    def test_unhealthy_collection(self):
        """Test unhealthy collection status."""
        health = CollectionHealth(
            collection_name="test_collection",
            status=HealthStatus.UNHEALTHY,
            vector_count=0,
            indexed_fields=[],
            config_status={},
            errors=["Collection not found"],
        )

        assert not health.is_healthy
        assert len(health.errors) == 1

    def test_degraded_collection(self):
        """Test degraded collection status."""
        health = CollectionHealth(
            collection_name="test_collection",
            status=HealthStatus.DEGRADED,
            vector_count=1000,
            indexed_fields=["project_id"],
            config_status={"hnsw_optimized": False},
        )

        assert not health.is_healthy
        assert health.status == HealthStatus.DEGRADED

    def test_collection_health_to_dict(self):
        """Test dictionary conversion."""
        health = CollectionHealth(
            collection_name="test_collection",
            status=HealthStatus.HEALTHY,
            vector_count=1000,
            indexed_fields=["project_id", "language"],
            config_status={"hnsw_optimized": True},
        )

        health_dict = health.to_dict()

        assert health_dict["collection_name"] == "test_collection"
        assert health_dict["status"] == "healthy"
        assert health_dict["vector_count"] == 1000
        assert health_dict["indexed_fields"] == ["project_id", "language"]
        assert health_dict["config_status"]["hnsw_optimized"] is True
        assert health_dict["errors"] == []
