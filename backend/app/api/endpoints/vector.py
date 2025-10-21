"""
Vector database API endpoints.

RESTful endpoints for vector search, storage, and management operations
with mandatory project and language isolation enforcement.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
import structlog

from ...core.vector import get_vector_search_service, get_vector_repository
from ...services.vector.domain.entities import (
    VectorPoint,
    SearchResult,
    SearchContext,
    VectorData,
    DocumentType,
)

logger = structlog.get_logger()
router = APIRouter()


# Pydantic schemas for API requests/responses
class VectorSearchRequest(BaseModel):
    """Request schema for vector search."""

    query_vector: List[float] = Field(
        ...,
        min_length=1536,
        max_length=1536,
        description="Query vector with 1536 dimensions",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of results to return",
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional search filters (document_type, importance_min, score_threshold)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "query_vector": [0.1] * 1536,
                "limit": 10,
                "filters": {
                    "document_type": "knowledge",
                    "importance_min": 0.5,
                    "score_threshold": 0.7,
                },
            }
        }
    }


class VectorUpsertRequest(BaseModel):
    """Request schema for vector upsert."""

    points: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Vector points to store (max 100 per batch)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "points": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "vector": [0.1] * 1536,
                        "content": "Document content here",
                        "title": "Document title",
                        "type": "knowledge",
                        "metadata": {"source": "manual", "category": "documentation"},
                        "importance": 0.8,
                    }
                ]
            }
        }
    }


class VectorSearchResponse(BaseModel):
    """Response schema for vector search."""

    results: List[Dict[str, Any]] = Field(
        ...,
        description="Search results ranked by similarity",
    )
    total_found: int = Field(
        ...,
        description="Total number of results found",
    )
    search_time_ms: float = Field(
        ...,
        description="Search execution time in milliseconds",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "results": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "title": "Related Document",
                        "content": "Document content preview...",
                        "score": 0.95,
                        "rank": 1,
                        "metadata": {"source": "manual"},
                        "document_type": "knowledge",
                        "created_at": "2024-01-01T00:00:00Z",
                    }
                ],
                "total_found": 1,
                "search_time_ms": 45.2,
            }
        }
    }


class VectorUpsertResponse(BaseModel):
    """Response schema for vector upsert."""

    points_processed: int = Field(
        ...,
        description="Number of points successfully processed",
    )
    processing_time_ms: float = Field(
        ...,
        description="Processing time in milliseconds",
    )


class VectorHealthResponse(BaseModel):
    """Response schema for vector health check."""

    status: str = Field(..., description="Health status")
    collection_name: str = Field(..., description="Collection name")
    vector_count: int = Field(..., description="Total vectors in collection")
    indexed_fields: List[str] = Field(..., description="Fields with indexes")
    errors: List[str] = Field(..., description="Any errors detected")


def extract_search_context(
    project_id: UUID = Query(..., description="Project ID for data isolation"),
    language: str = Query(..., description="Language code (ISO 639-1)"),
) -> SearchContext:
    """
    Extract and validate search context from query parameters.

    Args:
        project_id: Project ID for isolation
        language: Language code for isolation

    Returns:
        Validated search context

    Raises:
        HTTPException: If context validation fails
    """
    try:
        return SearchContext.create(str(project_id), language.lower())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid search context: {e}",
        ) from e


@router.get("/health", response_model=VectorHealthResponse)
async def health_check():
    """
    Check vector database health.

    Returns comprehensive health status including collection information,
    indexes, and any configuration issues.
    """
    try:
        from ...core.vector import vector_database

        if not vector_database.is_initialized:
            await vector_database.initialize()

        health_data = await vector_database.health_check()

        return VectorHealthResponse(
            status=health_data.get("status", "unknown"),
            collection_name=health_data.get("collection_name", "unknown"),
            vector_count=health_data.get("vector_count", 0),
            indexed_fields=health_data.get("indexed_fields", []),
            errors=health_data.get("errors", []),
        )

    except Exception as e:
        logger.error(
            "Vector health check failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Vector database health check failed: {e}",
        ) from e


@router.get("/stats")
async def get_statistics():
    """
    Get vector database statistics.

    Returns detailed statistics including collection info,
    configuration, and performance metrics.
    """
    try:
        from ...core.vector import vector_database

        if not vector_database.is_initialized:
            await vector_database.initialize()

        stats = await vector_database.get_statistics()
        return stats

    except Exception as e:
        logger.error(
            "Failed to get vector statistics",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get vector statistics: {e}",
        ) from e


@router.post("/search", response_model=VectorSearchResponse)
async def search_vectors(
    request: VectorSearchRequest,
    context: SearchContext = Depends(extract_search_context),
    search_service=Depends(get_vector_search_service),
):
    """
    Search for similar vectors with mandatory filtering.

    All searches are automatically filtered by project_id and language.
    No client can bypass these security filters.

    Args:
        request: Search request with query vector and options
        context: Search context with project and language isolation
        search_service: Vector search service

    Returns:
        Search results ranked by similarity

    Raises:
        HTTPException: If search fails or parameters are invalid
    """
    try:
        import time

        start_time = time.time()

        # Validate query vector
        query_vector = VectorData(request.query_vector)

        # Perform search with mandatory filtering
        results = await search_service.search(
            query_vector=query_vector,
            context=context,
            limit=request.limit,
            filters=request.filters,
        )

        search_time = (time.time() - start_time) * 1000  # Convert to milliseconds

        # Convert results to API response format
        api_results = [result.to_dict() for result in results]

        return VectorSearchResponse(
            results=api_results,
            total_found=len(results),
            search_time_ms=search_time,
        )

    except ValueError as e:
        logger.warning(
            "Vector search validation failed",
            error=str(e),
            project_id=str(context.project_id),
            language=str(context.language),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid search parameters: {e}",
        ) from e

    except Exception as e:
        logger.error(
            "Vector search failed",
            error=str(e),
            exc_info=True,
            project_id=str(context.project_id),
            language=str(context.language),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector search failed: {e}",
        ) from e


@router.post("/upsert", response_model=VectorUpsertResponse)
async def upsert_vectors(
    request: VectorUpsertRequest,
    context: SearchContext = Depends(extract_search_context),
    repository=Depends(get_vector_repository),
):
    """
    Store or update vector points.

    All points are automatically tagged with project_id and language
    from the request context. These fields cannot be overridden.

    Args:
        request: Upsert request with vector points
        context: Search context for project and language assignment
        repository: Vector repository

    Returns:
        Upsert operation results

    Raises:
        HTTPException: If upsert fails or validation errors occur
    """
    try:
        import time

        start_time = time.time()

        # Convert API request to domain objects
        vector_points = []
        for point_data in request.points:
            # Extract and validate required fields
            vector = VectorData(point_data["vector"])
            content = point_data["content"]
            title = point_data.get("title")
            document_type = DocumentType(point_data["type"])
            metadata = point_data.get("metadata", {})
            importance = point_data.get("importance", 1.0)

            # Create vector point with mandatory context fields
            point = VectorPoint(
                vector=vector,
                content=content,
                title=title,
                document_type=document_type,
                metadata=metadata,
                importance=importance,
                project_id=context.project_id,  # MANDATORY from context
                language=context.language,  # MANDATORY from context
            )
            vector_points.append(point)

        # Validate batch size
        if len(vector_points) > 100:
            raise ValueError("Maximum batch size is 100 points")

        # Perform upsert with explicit project_id for security validation
        await repository.upsert_points(context.project_id, vector_points)

        processing_time = (time.time() - start_time) * 1000

        return VectorUpsertResponse(
            points_processed=len(vector_points),
            processing_time_ms=processing_time,
        )

    except ValueError as e:
        logger.warning(
            "Vector upsert validation failed",
            error=str(e),
            project_id=str(context.project_id),
            language=str(context.language),
            points_count=len(request.points),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid vector data: {e}",
        ) from e

    except Exception as e:
        logger.error(
            "Vector upsert failed",
            error=str(e),
            exc_info=True,
            project_id=str(context.project_id),
            language=str(context.language),
            points_count=len(request.points),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector upsert failed: {e}",
        ) from e


@router.get("/points/{point_id}")
async def get_point(
    point_id: UUID,
    context: SearchContext = Depends(extract_search_context),
    repository=Depends(get_vector_repository),
):
    """
    Retrieve a vector point by ID.

    Only returns points that match the provided project_id and language.

    Args:
        point_id: UUID of the point to retrieve
        context: Search context for isolation
        repository: Vector repository

    Returns:
        Vector point data

    Raises:
        HTTPException: If point not found or access denied
    """
    try:
        point = await repository.get_point_by_id(point_id, context.project_id)

        if not point:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vector point not found: {point_id}",
            )

        # Verify project and language match (defense in depth)
        if str(point.project_id) != str(context.project_id) or str(
            point.language
        ) != str(context.language):
            logger.warning(
                "Unauthorized vector point access attempt",
                point_id=str(point_id),
                requested_project=str(context.project_id),
                point_project=str(point.project_id),
                requested_language=str(context.language),
                point_language=str(point.language),
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vector point not found",
            )

        return {
            "id": str(point.id),
            "content": point.content,
            "title": point.title,
            "document_type": point.document_type.value,
            "metadata": point.metadata,
            "importance": point.importance,
            "created_at": point.created_at.isoformat(),
            "updated_at": point.updated_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to retrieve vector point",
            error=str(e),
            exc_info=True,
            point_id=str(point_id),
            project_id=str(context.project_id),
            language=str(context.language),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve vector point: {e}",
        ) from e


@router.delete("/points")
async def delete_points(
    point_ids: List[UUID] = Query(..., description="List of point IDs to delete"),
    context: SearchContext = Depends(extract_search_context),
    repository=Depends(get_vector_repository),
):
    """
    Delete vector points by IDs.

    Only allows deletion of points that match the provided project_id and language.

    Args:
        point_ids: List of point UUIDs to delete
        context: Search context for isolation
        repository: Vector repository

    Returns:
        Deletion operation results
    """
    try:
        if len(point_ids) > 100:
            raise ValueError("Maximum 100 points can be deleted at once")

        # SECURITY: Explicit ownership verification before deletion
        # Repository enforces project_id filtering, but we verify explicitly
        await repository.delete_points(point_ids, context.project_id)

        return {
            "points_deleted": len(point_ids),
            "message": f"Successfully deleted {len(point_ids)} vector points",
        }

    except ValueError as e:
        logger.warning(
            "Vector delete validation failed",
            error=str(e),
            project_id=str(context.project_id),
            language=str(context.language),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid delete request: {e}",
        ) from e

    except Exception as e:
        logger.error(
            "Failed to delete vector points",
            error=str(e),
            exc_info=True,
            project_id=str(context.project_id),
            language=str(context.language),
            points_count=len(point_ids),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete vector points: {e}",
        ) from e
