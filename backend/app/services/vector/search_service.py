"""
Vector search service with mandatory filter enforcement.

Implements the VectorSearchService interface with strict security controls.
All search operations are filtered by project_id AND language - no exceptions.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID

from qdrant_client import QdrantClient

from .domain.entities import (
    SearchResult,
    SearchContext,
    VectorData,
    DocumentType,
)
from .repositories.interfaces import VectorSearchService, VectorRepository


class DefaultVectorSearchService(VectorSearchService):
    """
    Default implementation of vector search service.

    Enforces mandatory project_id and language filtering on all search operations.
    Provides hybrid search capabilities and comprehensive error handling.
    """

    def __init__(self, repository: VectorRepository):
        """
        Initialize vector search service.

        Args:
            repository: Vector repository implementation

        Raises:
            ValueError: If repository is None
        """
        if not repository:
            raise ValueError("repository must not be None")
        self.repository = repository

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
            filters: Optional additional filters (document_type, importance_min, etc.)

        Returns:
            List of search results ranked by similarity

        Raises:
            ValueError: If context is missing required fields or invalid parameters
        """
        # Validate mandatory context - CANNOT be bypassed
        if not context:
            raise ValueError("SearchContext is required")
        if not context.project_id:
            raise ValueError(
                "SearchContext.project_id is required for project isolation"
            )
        if not context.language:
            raise ValueError(
                "SearchContext.language is required for language isolation"
            )

        # Parse additional filters
        document_type = None
        importance_min = None
        score_threshold = 0.0

        if filters:
            if "document_type" in filters:
                try:
                    document_type = DocumentType(filters["document_type"])
                except ValueError as e:
                    raise ValueError(
                        f"Invalid document_type filter: {filters['document_type']}"
                    ) from e

            if "importance_min" in filters:
                importance_min = filters["importance_min"]
                if (
                    not isinstance(importance_min, (int, float))
                    or not 0.0 <= importance_min <= 1.0
                ):
                    raise ValueError(
                        f"Invalid importance_min filter: {importance_min}. Must be between 0.0 and 1.0"
                    )

            if "score_threshold" in filters:
                score_threshold = filters["score_threshold"]
                if (
                    not isinstance(score_threshold, (int, float))
                    or not 0.0 <= score_threshold <= 1.0
                ):
                    raise ValueError(
                        f"Invalid score_threshold: {score_threshold}. Must be between 0.0 and 1.0"
                    )

        # Validate limit
        if limit <= 0 or limit > 50:
            raise ValueError(f"Invalid limit: {limit}. Must be between 1 and 50")

        # Delegate to repository with enforced filters
        return await self.repository.search_similar(
            query_vector=query_vector,
            context=context,
            limit=limit,
            score_threshold=score_threshold,
            document_type=document_type,
            importance_min=importance_min,
        )

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

        TODO(JEEX): Implement true hybrid search combining text + vector similarity
        Current implementation is incomplete and ignores query_text parameter.
        Production hybrid search should:
        1. Perform text-based keyword search (BM25/full-text)
        2. Perform vector similarity search
        3. Combine scores using text_weight and vector_weight
        4. Merge and re-rank results
        For now, this uses vector-only search with simplified scoring adjustment.

        Args:
            query_text: Text query for keyword search (currently ignored - see TODO)
            query_vector: Query vector for similarity search
            context: Search context with project_id and language
            limit: Maximum number of results
            text_weight: Weight for text search results (0.0-1.0)
            vector_weight: Weight for vector search results (0.0-1.0)

        Returns:
            List of hybrid search results
        """
        # Validate weights
        if not (0.0 <= text_weight <= 1.0) or not (0.0 <= vector_weight <= 1.0):
            raise ValueError("Weights must be between 0.0 and 1.0")

        if abs(text_weight + vector_weight - 1.0) > 0.01:
            raise ValueError("Weights must sum to 1.0")

        # For now, prioritize vector search with slight text influence
        # In a full implementation, this would include text-based search
        vector_results = await self.search(
            query_vector=query_vector,
            context=context,
            limit=limit,
        )

        # Apply weight-based scoring adjustment (simplified)
        for result in vector_results:
            # Adjust score based on weights (simplified hybrid scoring)
            # In production, this would combine actual text search scores
            adjusted_score = (
                result.score * vector_weight + (1 - result.score) * text_weight
            )
            result.score = min(max(adjusted_score, 0.0), 1.0)  # Clamp to [0, 1]

        return vector_results


def build_mandatory_filter(project_id: UUID, language: str) -> Dict[str, Any]:
    """
    Build mandatory search filter with validation.

    Args:
        project_id: Project ID (UUID) to filter by
        language: Language code to filter by

    Returns:
        Filter configuration dictionary

    Raises:
        ValueError: If project_id or language are invalid
    """
    from .domain.entities import ProjectId, LanguageCode

    # Validate project_id format (UUID already validated by type system)
    try:
        ProjectId(str(project_id))
    except ValueError as e:
        raise ValueError(f"Invalid project_id: {e}") from e

    # Validate language format
    try:
        LanguageCode(language)
    except ValueError as e:
        raise ValueError(f"Invalid language: {e}") from e

    return {
        "must": [
            {"key": "project_id", "match": {"value": str(project_id)}},
            {"key": "language", "match": {"value": language}},
        ]
    }


def build_search_filter(
    project_id: UUID,
    language: str,
    document_type: Optional[str] = None,
    importance_min: Optional[float] = None,
    created_after: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build comprehensive search filter with optional refinements.

    Args:
        project_id: Project ID (UUID) to filter by
        language: Language code to filter by
        document_type: Optional document type filter
        importance_min: Optional minimum importance filter
        created_after: Optional created date filter (ISO 8601)

    Returns:
        Comprehensive filter configuration

    Raises:
        ValueError: If any filter parameters are invalid
    """
    # Start with mandatory filters
    filter_config = build_mandatory_filter(project_id, language)

    # Add optional filters
    if document_type:
        if document_type not in [dt.value for dt in DocumentType]:
            raise ValueError(f"Invalid document_type: {document_type}")
        filter_config["must"].append({"key": "type", "match": {"value": document_type}})

    if importance_min is not None:
        if (
            not isinstance(importance_min, (int, float))
            or not 0.0 <= importance_min <= 1.0
        ):
            raise ValueError(
                f"Invalid importance_min: {importance_min}. Must be between 0.0 and 1.0"
            )
        filter_config["must"].append(
            {"key": "importance", "range": {"gte": importance_min}}
        )

    if created_after:
        # Validate ISO 8601 format
        try:
            from datetime import datetime

            datetime.fromisoformat(created_after.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(
                f"Invalid created_after date format: {created_after}. Must be ISO 8601"
            ) from e
        filter_config["must"].append(
            {"key": "created_at", "range": {"gte": created_after}}
        )

    return filter_config
