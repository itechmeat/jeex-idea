"""
Qdrant instrumentation test endpoints.

Endpoints for testing and verifying Qdrant OpenTelemetry instrumentation.
Provides various vector operations to generate traces and metrics.
"""

import time
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from pydantic import BaseModel, Field
import structlog

from ...core.vector import get_vector_search_service, get_vector_repository
from ...core.qdrant_telemetry import (
    qdrant_telemetry,
    QdrantOperationType,
)
from ...services.vector.domain.entities import (
    VectorPoint,
    SearchContext,
    VectorData,
    DocumentType,
    ProjectId,
    LanguageCode,
)

logger = structlog.get_logger()
router = APIRouter()


class TestVectorSearchRequest(BaseModel):
    """Test request for vector search with configurable parameters."""

    vector_size: int = Field(
        default=1536,
        ge=1,
        le=1536,
        description="Vector dimension size (for testing: 1-1536)",
    )
    limit: int = Field(
        default=10, ge=1, le=100, description="Maximum number of results to return"
    )
    score_threshold: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum similarity score threshold"
    )
    document_type: Optional[str] = Field(
        default=None, description="Filter by document type"
    )
    importance_min: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Minimum importance score"
    )
    add_delay: float = Field(
        default=0.0,
        ge=0.0,
        le=5.0,
        description="Artificial delay for testing timeout scenarios (seconds)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "vector_size": 1536,
                "limit": 10,
                "score_threshold": 0.7,
                "document_type": "knowledge",
                "importance_min": 0.5,
                "add_delay": 0.0,
            }
        }
    }


class TestVectorUpsertRequest(BaseModel):
    """Test request for vector upsert with configurable parameters."""

    num_points: int = Field(
        default=5, ge=1, le=100, description="Number of vector points to create"
    )
    vector_size: int = Field(
        default=1536, ge=1, le=1536, description="Vector dimension size"
    )
    document_type: str = Field(
        default="test", description="Document type for test points"
    )
    importance: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Importance score for test points"
    )
    add_delay: float = Field(
        default=0.0,
        ge=0.0,
        le=5.0,
        description="Artificial delay for testing (seconds)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "num_points": 5,
                "vector_size": 1536,
                "document_type": "test",
                "importance": 1.0,
                "add_delay": 0.0,
            }
        }
    }


class TestOperationResponse(BaseModel):
    """Response schema for test operations."""

    operation: str = Field(..., description="Operation performed")
    success: bool = Field(..., description="Whether operation was successful")
    duration_ms: float = Field(..., description="Operation duration in milliseconds")
    details: Dict[str, Any] = Field(..., description="Operation details")
    telemetry_info: Dict[str, Any] = Field(..., description="Telemetry information")


@router.post("/test/search", response_model=TestOperationResponse)
async def test_vector_search(
    request: TestVectorSearchRequest,
    project_id: UUID = Query(..., description="Project ID for testing"),
    language: str = Query(default="en", description="Language code"),
    search_service=Depends(get_vector_search_service),
):
    """
    Test vector search operation with telemetry.

    Creates a test vector and performs search to generate traces and metrics.
    """
    start_time = time.time()
    operation_details = {}

    try:
        # Create search context
        context = SearchContext.create(str(project_id), language.lower())

        # Generate test vector with specified size
        test_vector = [0.1] * request.vector_size
        query_vector = VectorData(test_vector)

        # Add artificial delay if requested
        if request.add_delay > 0:
            await asyncio.sleep(request.add_delay)
            operation_details["artificial_delay_s"] = request.add_delay

        # Prepare search filters
        filters = {}
        if request.document_type:
            filters["document_type"] = DocumentType(request.document_type)
        if request.importance_min is not None:
            filters["importance_min"] = request.importance_min

        # Perform search
        results = await search_service.search(
            query_vector=query_vector,
            context=context,
            limit=request.limit,
            score_threshold=request.score_threshold,
            filters=filters,
        )

        duration = (time.time() - start_time) * 1000
        operation_details.update(
            {
                "vector_size": request.vector_size,
                "limit": request.limit,
                "score_threshold": request.score_threshold,
                "filters": filters,
                "results_count": len(results),
                "project_id": str(project_id),
                "language": language,
            }
        )

        # Add manual telemetry for verification
        with qdrant_telemetry._tracer.start_as_current_span(
            "test.vector_search"
        ) as span:
            span.set_attribute("test.operation", "vector_search")
            span.set_attribute("test.project_id", str(project_id))
            span.set_attribute("test.language", language)
            span.set_attribute("test.vector_size", request.vector_size)
            span.set_attribute("test.results_count", len(results))
            span.set_attribute("test.duration_ms", duration)

        return TestOperationResponse(
            operation="vector_search",
            success=True,
            duration_ms=duration,
            details=operation_details,
            telemetry_info={
                "operation_type": QdrantOperationType.SEARCH,
                "spans_expected": ["qdrant.search", "test.vector_search"],
                "metrics_expected": [
                    "qdrant_operations_total",
                    "qdrant_operation_duration_seconds",
                    "qdrant_search_results_count",
                ],
            },
        )

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        logger.error(
            "Test vector search failed",
            error=str(e),
            project_id=str(project_id),
            language=language,
            duration_ms=duration,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test vector search failed: {e}",
        ) from e


@router.post("/test/upsert", response_model=TestOperationResponse)
async def test_vector_upsert(
    request: TestVectorUpsertRequest,
    project_id: UUID = Query(..., description="Project ID for testing"),
    language: str = Query(default="en", description="Language code"),
    repository=Depends(get_vector_repository),
):
    """
    Test vector upsert operation with telemetry.

    Creates test vector points and upserts them to generate traces and metrics.
    """
    start_time = time.time()
    operation_details = {}

    try:
        # Add artificial delay if requested
        if request.add_delay > 0:
            await asyncio.sleep(request.add_delay)
            operation_details["artificial_delay_s"] = request.add_delay

        # Create test vector points
        points = []
        for i in range(request.num_points):
            # Generate test vector
            vector_data = [0.1 * (i + 1) / request.num_points] * request.vector_size
            vector = VectorData(vector_data)

            # Create vector point
            point = VectorPoint(
                id=uuid4(),
                vector=vector,
                content=f"Test document {i + 1} for telemetry testing",
                title=f"Test Document {i + 1}",
                document_type=DocumentType(request.document_type),
                metadata={
                    "test": True,
                    "batch_id": str(uuid4()),
                    "index": i,
                    "vector_size": request.vector_size,
                },
                importance=request.importance,
                project_id=ProjectId(str(project_id)),
                language=LanguageCode(language.lower()),
            )
            points.append(point)

        # Perform upsert
        await repository.upsert_points(project_id, points)

        duration = (time.time() - start_time) * 1000
        operation_details.update(
            {
                "num_points": request.num_points,
                "vector_size": request.vector_size,
                "document_type": request.document_type,
                "importance": request.importance,
                "project_id": str(project_id),
                "language": language,
                "batch_ids": [
                    str(point.id) for point in points[:3]
                ],  # First 3 IDs for verification
            }
        )

        # Add manual telemetry for verification
        with qdrant_telemetry._tracer.start_as_current_span(
            "test.vector_upsert"
        ) as span:
            span.set_attribute("test.operation", "vector_upsert")
            span.set_attribute("test.project_id", str(project_id))
            span.set_attribute("test.language", language)
            span.set_attribute("test.num_points", request.num_points)
            span.set_attribute("test.vector_size", request.vector_size)
            span.set_attribute("test.duration_ms", duration)

        return TestOperationResponse(
            operation="vector_upsert",
            success=True,
            duration_ms=duration,
            details=operation_details,
            telemetry_info={
                "operation_type": QdrantOperationType.UPSERT,
                "spans_expected": ["qdrant.upsert", "test.vector_upsert"],
                "metrics_expected": [
                    "qdrant_operations_total",
                    "qdrant_operation_duration_seconds",
                    "qdrant_batch_size",
                ],
            },
        )

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        logger.error(
            "Test vector upsert failed",
            error=str(e),
            project_id=str(project_id),
            language=language,
            duration_ms=duration,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test vector upsert failed: {e}",
        ) from e


@router.post("/test/mixed-workload", response_model=TestOperationResponse)
async def test_mixed_workload(
    background_tasks: BackgroundTasks,
    num_searches: int = Query(
        default=3, ge=1, le=10, description="Number of search operations"
    ),
    num_upserts: int = Query(
        default=2, ge=1, le=5, description="Number of upsert operations"
    ),
    project_id: UUID = Query(..., description="Project ID for testing"),
    language: str = Query(default="en", description="Language code"),
):
    """
    Test mixed workload with multiple operations.

    Executes multiple search and upsert operations concurrently to test
    telemetry performance and trace correlation.
    """
    start_time = time.time()
    operation_details = {}

    try:

        async def perform_search(operation_id: int):
            """Perform a single search operation."""
            try:
                from ...core.vector import get_vector_search_service

                search_service = get_vector_search_service()

                context = SearchContext.create(str(project_id), language.lower())
                test_vector = [0.1] * 1536
                query_vector = VectorData(test_vector)

                results = await search_service.search(
                    query_vector=query_vector,
                    context=context,
                    limit=5,
                    score_threshold=0.0,
                )

                logger.info(
                    "Mixed workload search completed",
                    operation_id=operation_id,
                    results_count=len(results),
                    project_id=str(project_id),
                )

                return {"operation_id": operation_id, "results_count": len(results)}

            except Exception as e:
                logger.error(
                    "Mixed workload search failed",
                    operation_id=operation_id,
                    error=str(e),
                    project_id=str(project_id),
                )
                return {"operation_id": operation_id, "error": str(e)}

        async def perform_upsert(operation_id: int):
            """Perform a single upsert operation."""
            try:
                from ...core.vector import get_vector_repository

                repository = get_vector_repository()

                # Create test points
                points = []
                for i in range(3):
                    vector_data = [0.1 * (operation_id + i + 1) / 10] * 1536
                    vector = VectorData(vector_data)

                    point = VectorPoint(
                        id=uuid4(),
                        vector=vector,
                        content=f"Mixed workload test {operation_id}-{i + 1}",
                        title=f"Mixed Test {operation_id}-{i + 1}",
                        document_type=DocumentType("test"),
                        metadata={"mixed_workload": True, "operation_id": operation_id},
                        importance=0.8,
                        project_id=ProjectId(str(project_id)),
                        language=LanguageCode(language.lower()),
                    )
                    points.append(point)

                await repository.upsert_points(project_id, points)

                logger.info(
                    "Mixed workload upsert completed",
                    operation_id=operation_id,
                    points_count=len(points),
                    project_id=str(project_id),
                )

                return {"operation_id": operation_id, "points_count": len(points)}

            except Exception as e:
                logger.error(
                    "Mixed workload upsert failed",
                    operation_id=operation_id,
                    error=str(e),
                    project_id=str(project_id),
                )
                return {"operation_id": operation_id, "error": str(e)}

        # Execute mixed workload
        import asyncio

        tasks = []

        # Add search tasks
        for i in range(num_searches):
            tasks.append(perform_search(f"search_{i + 1}"))

        # Add upsert tasks
        for i in range(num_upserts):
            tasks.append(perform_upsert(f"upsert_{i + 1}"))

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        successful_operations = 0
        failed_operations = 0
        search_results = 0
        upserted_points = 0

        for result in results:
            if isinstance(result, Exception):
                failed_operations += 1
            elif isinstance(result, dict):
                if "error" in result:
                    failed_operations += 1
                else:
                    successful_operations += 1
                    if "results_count" in result:
                        search_results += result["results_count"]
                    if "points_count" in result:
                        upserted_points += result["points_count"]

        duration = (time.time() - start_time) * 1000
        operation_details.update(
            {
                "total_operations": len(tasks),
                "successful_operations": successful_operations,
                "failed_operations": failed_operations,
                "num_searches": num_searches,
                "num_upserts": num_upserts,
                "total_search_results": search_results,
                "total_upserted_points": upserted_points,
                "project_id": str(project_id),
                "language": language,
            }
        )

        # Add manual telemetry for the mixed workload
        with qdrant_telemetry._tracer.start_as_current_span(
            "test.mixed_workload"
        ) as span:
            span.set_attribute("test.operation", "mixed_workload")
            span.set_attribute("test.project_id", str(project_id))
            span.set_attribute("test.language", language)
            span.set_attribute("test.total_operations", len(tasks))
            span.set_attribute("test.successful_operations", successful_operations)
            span.set_attribute("test.failed_operations", failed_operations)
            span.set_attribute("test.duration_ms", duration)

        return TestOperationResponse(
            operation="mixed_workload",
            success=failed_operations == 0,
            duration_ms=duration,
            details=operation_details,
            telemetry_info={
                "spans_expected": [
                    "test.mixed_workload",
                    *[f"qdrant.search" for _ in range(num_searches)],
                    *[f"qdrant.upsert" for _ in range(num_upserts)],
                ],
                "metrics_expected": [
                    "qdrant_operations_total",
                    "qdrant_operation_duration_seconds",
                    "qdrant_search_results_count",
                    "qdrant_batch_size",
                ],
                "trace_correlation": "All operations should share same trace_id",
            },
        )

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        logger.error(
            "Mixed workload test failed",
            error=str(e),
            project_id=str(project_id),
            language=language,
            duration_ms=duration,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Mixed workload test failed: {e}",
        ) from e


@router.get("/test/telemetry-info", response_model=Dict[str, Any])
async def get_telemetry_info():
    """
    Get information about available telemetry instrumentation.

    Returns details about expected spans, metrics, and attributes for testing.
    """
    return {
        "available_operations": {
            "search": {
                "operation_type": QdrantOperationType.SEARCH,
                "span_name": "qdrant.search",
                "expected_attributes": [
                    "db.system",
                    "db.operation",
                    "collection_name",
                    "vector_size",
                    "limit",
                    "score_threshold",
                    "project.id",
                    "project.language",
                    "qdrant.results_found",
                    "qdrant.avg_score",
                ],
                "expected_metrics": [
                    "qdrant_operations_total",
                    "qdrant_operation_duration_seconds",
                    "qdrant_search_results_count",
                    "qdrant_search_score_distribution",
                ],
            },
            "upsert": {
                "operation_type": QdrantOperationType.UPSERT,
                "span_name": "qdrant.upsert",
                "expected_attributes": [
                    "db.system",
                    "db.operation",
                    "collection_name",
                    "total_points",
                    "document_types",
                    "vector_size",
                    "project.id",
                    "project.language",
                    "qdrant.total_batches_processed",
                ],
                "expected_metrics": [
                    "qdrant_operations_total",
                    "qdrant_operation_duration_seconds",
                    "qdrant_batch_size",
                ],
            },
            "collection_create": {
                "operation_type": QdrantOperationType.COLLECTION_CREATE,
                "span_name": "qdrant.collection.create",
                "expected_attributes": [
                    "db.system",
                    "db.operation",
                    "collection_name",
                    "vector_size",
                    "distance_metric",
                    "hnsw_m",
                    "qdrant.collection_created",
                ],
                "expected_metrics": [
                    "qdrant_operations_total",
                    "qdrant_operation_duration_seconds",
                ],
            },
            "index_create": {
                "operation_type": QdrantOperationType.INDEX_CREATE,
                "span_name": "qdrant.index.create",
                "expected_attributes": [
                    "db.system",
                    "db.operation",
                    "collection_name",
                    "qdrant.index_created_project_id",
                    "qdrant.index_created_language",
                    "qdrant.total_indexes_created",
                ],
                "expected_metrics": [
                    "qdrant_operations_total",
                    "qdrant_operation_duration_seconds",
                ],
            },
        },
        "error_classifications": {
            "network": [
                "ConnectionError",
                "TimeoutError",
                "ConnectionRefusedError",
                "ConnectionResetError",
                "OSError",
                "socket.gaierror",
            ],
            "client": [
                "UnexpectedResponse",
                "ValueError",
                "ValidationError",
                "TypeError",
                "KeyError",
                "AttributeError",
            ],
            "server": [
                "InternalServerError",
                "ServiceUnavailable",
                "TimeoutExpired",
                "RateLimitExceeded",
                "ResourceExhausted",
            ],
        },
        "testing_endpoints": {
            "test_search": "POST /api/vector/test/search",
            "test_upsert": "POST /api/vector/test/upsert",
            "test_mixed_workload": "POST /api/vector/test/mixed-workload",
            "telemetry_info": "GET /api/vector/test/telemetry-info",
        },
    }


# Import for asyncio
import asyncio
