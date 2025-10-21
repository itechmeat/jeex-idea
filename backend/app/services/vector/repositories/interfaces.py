"""
Repository interfaces for vector database operations following DDD patterns.

Repository interfaces define contracts for data access operations,
isolating domain logic from infrastructure concerns.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncGenerator
from uuid import UUID

from ..domain.entities import (
    VectorPoint,
    SearchResult,
    CollectionHealth,
    SearchContext,
    VectorData,
    DocumentType,
)


class VectorRepository(ABC):
    """
    Abstract repository interface for vector database operations.

    This interface defines the contract for all vector-related
    data access operations following the Repository pattern.
    """

    @abstractmethod
    async def initialize_collection(self) -> None:
        """
        Initialize the vector collection with proper schema and indexes.

        Creates the collection if it doesn't exist and ensures
        all required indexes are created with optimal configuration.
        """
        pass

    @abstractmethod
    async def collection_exists(self) -> bool:
        """
        Check if the vector collection exists.

        Returns:
            True if collection exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_collection_info(self) -> Dict[str, Any]:
        """
        Get detailed information about the collection.

        Returns:
            Collection metadata including configuration and statistics
        """
        pass

    @abstractmethod
    async def create_indexes(self) -> None:
        """
        Create required payload indexes for efficient filtering.

        Creates indexes for project_id, language, type, and created_at fields.
        """
        pass

    @abstractmethod
    async def validate_schema(self) -> List[str]:
        """
        Validate collection schema matches expected configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        pass

    @abstractmethod
    async def upsert_points(self, project_id: UUID, points: List[VectorPoint]) -> None:
        """
        Store or update vector points in batches with mandatory project isolation.

        CRITICAL: Implementations MUST validate that all points belong to project_id.
        This is a security-critical operation - no point should be stored without
        proper project validation.

        Args:
            project_id: UUID of the project for isolation (MANDATORY)
            points: List of vector points to store

        Raises:
            ValueError: If points validation fails or any point belongs to different project
        """
        pass

    @abstractmethod
    async def get_point_by_id(
        self, point_id: UUID, project_id: UUID
    ) -> Optional[VectorPoint]:
        """
        Retrieve a vector point by its ID with mandatory project isolation.

        CRITICAL: Implementations MUST validate project_id before retrieval.
        Only return points that belong to the specified project.

        Args:
            point_id: UUID of the point to retrieve
            project_id: UUID of the project for isolation (MANDATORY)

        Returns:
            VectorPoint if found and belongs to project, None otherwise

        Raises:
            ValueError: If project_id is missing or invalid
        """
        pass

    @abstractmethod
    async def search_similar(
        self,
        query_vector: VectorData,
        context: SearchContext,
        limit: int = 10,
        score_threshold: float = 0.0,
        document_type: Optional[DocumentType] = None,
        importance_min: Optional[float] = None,
    ) -> List[SearchResult]:
        """
        Search for similar vectors with mandatory filtering.

        CRITICAL: Implementations MUST validate that context contains project_id
        and language. All search results MUST be filtered by these fields.

        Args:
            query_vector: Query vector for similarity search
            context: Search context with project_id and language (MANDATORY)
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score threshold
            document_type: Optional document type filter
            importance_min: Optional minimum importance filter

        Returns:
            List of search results ranked by similarity

        Raises:
            ValueError: If search parameters are invalid or context is missing required fields
        """
        pass

    @abstractmethod
    async def delete_points(self, point_ids: List[UUID], project_id: UUID) -> None:
        """
        Delete vector points by their IDs with mandatory project isolation.

        CRITICAL: Implementations MUST validate project_id before deletion.
        Only delete points that belong to the specified project.

        Args:
            point_ids: List of UUIDs to delete
            project_id: UUID of the project for isolation (MANDATORY)

        Raises:
            ValueError: If project_id is missing or invalid
        """
        pass

    @abstractmethod
    async def delete_by_filter(self, context: SearchContext) -> int:
        """
        Delete points matching project and language filter.

        CRITICAL: Implementations MUST validate and enforce project_id and language
        from the provided SearchContext. This is a security-critical operation - all
        deletions must respect tenant scoping to prevent cross-project data loss.

        Args:
            context: Search context with project_id and language (MANDATORY)

        Returns:
            Number of points deleted

        Raises:
            ValueError: If context is missing required fields
        """
        pass

    @abstractmethod
    async def count_points(self, context: SearchContext) -> int:
        """
        Count points matching project and language filter.

        CRITICAL: Implementations MUST validate and enforce project_id and language
        from the provided SearchContext to ensure count operations respect multi-tenant
        isolation boundaries.

        Args:
            context: Search context with project_id and language (MANDATORY)

        Returns:
            Number of matching points

        Raises:
            ValueError: If context is missing required fields
        """
        pass

    @abstractmethod
    async def get_collection_health(self) -> CollectionHealth:
        """
        Get comprehensive health status of the collection.

        Returns:
            Collection health information including errors
        """
        pass


class CollectionManager(ABC):
    """
    Abstract interface for collection management operations.

    Handles collection lifecycle, configuration, and health monitoring.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the collection manager.

        Sets up collection, indexes, and validates configuration.
        """
        pass

    @abstractmethod
    async def health_check(self) -> CollectionHealth:
        """
        Perform comprehensive health check.

        Returns:
            Detailed health status of the collection
        """
        pass

    @abstractmethod
    async def recreate_collection(self) -> None:
        """
        Recreate the collection (development only).

        Deletes and recreates the collection with fresh configuration.
        """
        pass

    @abstractmethod
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get collection statistics and metrics.

        Returns:
            Statistics including vector count, disk usage, etc.
        """
        pass


class VectorSearchService(ABC):
    """
    Abstract interface for vector search operations.

    Provides high-level search functionality with filtering enforcement.
    """

    @abstractmethod
    async def search(
        self,
        query_vector: VectorData,
        context: SearchContext,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """
        Search for similar vectors with mandatory filtering.

        Args:
            query_vector: Query vector for similarity search
            context: Search context (project_id and language are mandatory)
            limit: Maximum number of results
            filters: Optional additional filters

        Returns:
            List of search results ranked by similarity

        Raises:
            ValueError: If context is missing required fields
        """
        pass

    @abstractmethod
    async def hybrid_search(
        self,
        query_text: str,
        query_vector: VectorData,
        context: SearchContext,
        limit: int = 10,
        text_weight: float = 0.3,
        vector_weight: float = 0.7,
    ) -> List[SearchResult]:
        """
        Perform hybrid search combining text and vector similarity.

        Args:
            query_text: Text query for keyword search
            query_vector: Query vector for similarity search
            context: Search context with project_id and language
            limit: Maximum number of results
            text_weight: Weight for text search results (0.0-1.0)
            vector_weight: Weight for vector search results (0.0-1.0)

        Returns:
            List of hybrid search results
        """
        pass
