"""
Qdrant repository implementation following DDD repository pattern.

Concrete implementation of vector repository using Qdrant client
with strict filter enforcement and project isolation.
"""

import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

import structlog
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ....core.qdrant_telemetry import (
    qdrant_telemetry,
    QdrantOperationType,
    QdrantErrorClassifier,
)

from ..domain.entities import (
    VectorPoint,
    SearchResult,
    CollectionHealth,
    SearchContext,
    VectorData,
    DocumentType,
    HealthStatus,
    ProjectId,
    LanguageCode,
)
from .interfaces import VectorRepository, CollectionManager

logger = structlog.get_logger()


class QdrantVectorRepository(VectorRepository):
    """
    Qdrant implementation of vector repository with strict isolation.

    Enforces mandatory project_id and language filtering on all operations.
    Implements batch operations, retry logic, and comprehensive error handling.
    """

    # Collection configuration constants
    COLLECTION_NAME = "jeex_memory"
    VECTOR_SIZE = 1536
    HNSW_M = 16
    HNSW_PAYLOAD_M = 16
    HNSW_EF_CONSTRUCT = 100
    FULL_SCAN_THRESHOLD = 10000
    INDEXING_THRESHOLD = 20000

    # Batch operation limits
    MAX_BATCH_SIZE = 100
    BATCH_TIMEOUT = 30  # seconds

    def __init__(self, client: QdrantClient):
        """
        Initialize Qdrant repository with client.

        Args:
            client: Configured QdrantClient instance
        """
        # Instrument the client for OpenTelemetry tracing
        from ....core.qdrant_telemetry import instrument_qdrant_client

        self.client = instrument_qdrant_client(client)
        self._collection_info_cache = None
        self._cache_timestamp = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(
            (ConnectionError, TimeoutError, RuntimeError, UnexpectedResponse)
        ),
        reraise=True,
    )
    async def initialize_collection(self) -> None:
        """Initialize collection with optimal HNSW configuration and telemetry."""
        async with qdrant_telemetry.trace_qdrant_operation(
            QdrantOperationType.COLLECTION_CREATE,
            collection_name=self.COLLECTION_NAME,
            vector_size=self.VECTOR_SIZE,
            distance_metric="cosine",
            hnsw_m=self.HNSW_M,
            hnsw_payload_m=self.HNSW_PAYLOAD_M,
            hnsw_ef_construct=self.HNSW_EF_CONSTRUCT,
            indexing_threshold=self.INDEXING_THRESHOLD,
        ) as span:
            if not await self.collection_exists():
                # Create collection with optimized HNSW configuration
                await asyncio.to_thread(
                    self.client.create_collection,
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=models.VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=models.Distance.COSINE,
                        hnsw_config=models.HnswConfigDiff(
                            m=self.HNSW_M,
                            payload_m=self.HNSW_PAYLOAD_M,
                            ef_construct=self.HNSW_EF_CONSTRUCT,
                            full_scan_threshold=self.FULL_SCAN_THRESHOLD,
                        ),
                    ),
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=self.INDEXING_THRESHOLD
                    ),
                    replication_factor=1,  # Single node configuration
                    shard_number=1,  # Single shard for development
                )

                span.set_attribute("qdrant.collection_created", True)
                logger.info(
                    "Created collection with HNSW optimization",
                    collection_name=self.COLLECTION_NAME,
                    vector_size=self.VECTOR_SIZE,
                    hnsw_m=self.HNSW_M,
                    hnsw_payload_m=self.HNSW_PAYLOAD_M,
                    hnsw_ef_construct=self.HNSW_EF_CONSTRUCT,
                    operation="create_collection",
                )
            else:
                span.set_attribute("qdrant.collection_existed", True)

            # Create required indexes
            await self.create_indexes()

    async def collection_exists(self) -> bool:
        """Check if collection exists."""
        try:
            collections = await asyncio.to_thread(self.client.get_collections)
            return any(
                collection.name == self.COLLECTION_NAME
                for collection in collections.collections
            )
        except Exception as e:
            raise RuntimeError(f"Failed to check collection existence: {e}") from e

    async def get_collection_info(self) -> Dict[str, Any]:
        """Get detailed collection information."""
        try:
            info = await asyncio.to_thread(
                self.client.get_collection, self.COLLECTION_NAME
            )
            return {
                "name": self.COLLECTION_NAME,  # Use the collection name we requested
                "vector_size": info.config.params.vectors.size,
                "distance": str(info.config.params.vectors.distance),
                "points_count": info.points_count,
                "segments_count": info.segments_count,
                "disk_data_size": getattr(info, "disk_data_size", 0),
                "ram_data_size": getattr(info, "ram_data_size", 0),
                "status": info.status,
                "optimizer_status": info.optimizer_status,
                "hnsw_config": info.config.params.vectors.hnsw_config.__dict__
                if info.config.params.vectors.hnsw_config
                else None,
            }
        except Exception as e:
            raise RuntimeError(f"Failed to get collection info: {e}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def create_indexes(self) -> None:
        """Create required payload indexes for efficient filtering with telemetry."""
        async with qdrant_telemetry.trace_qdrant_operation(
            QdrantOperationType.INDEX_CREATE, collection_name=self.COLLECTION_NAME
        ) as span:
            indexes_to_create = [
                ("project_id", models.PayloadSchemaType.KEYWORD, "project isolation"),
                ("language", models.PayloadSchemaType.KEYWORD, "language isolation"),
                ("type", models.PayloadSchemaType.KEYWORD, "document type filtering"),
                ("created_at", models.PayloadSchemaType.DATETIME, "temporal queries"),
                ("importance", models.PayloadSchemaType.FLOAT, "importance filtering"),
            ]

            for field_name, field_schema, description in indexes_to_create:
                try:
                    await asyncio.to_thread(
                        self.client.create_payload_index,
                        collection_name=self.COLLECTION_NAME,
                        field_name=field_name,
                        field_schema=field_schema,
                    )
                    span.set_attribute(f"qdrant.index_created_{field_name}", True)
                    logger.debug(
                        "Created payload index",
                        collection_name=self.COLLECTION_NAME,
                        field_name=field_name,
                        field_schema=str(field_schema),
                        description=description,
                        operation="create_index",
                    )
                except Exception as e:
                    span.set_attribute(f"qdrant.index_failed_{field_name}", True)
                    span.set_attribute(f"qdrant.index_error_{field_name}", str(e))
                    raise RuntimeError(
                        f"Failed to create payload index for {field_name}: {e}"
                    ) from e

            span.set_attribute("qdrant.total_indexes_created", len(indexes_to_create))

    async def validate_schema(self) -> List[str]:
        """Validate collection schema matches expected configuration."""
        errors = []

        try:
            if not await self.collection_exists():
                errors.append(f"Collection '{self.COLLECTION_NAME}' does not exist")
                return errors

            info = await self.get_collection_info()

            # Validate vector configuration
            if info.get("vector_size") != self.VECTOR_SIZE:
                errors.append(
                    f"Invalid vector size: {info.get('vector_size')}, expected {self.VECTOR_SIZE}"
                )

            if info.get("distance") not in ["Distance.COSINE", "Cosine"]:
                errors.append(
                    f"Invalid distance metric: {info.get('distance')}, expected Cosine"
                )

            # Validate HNSW configuration
            hnsw_config = info.get("hnsw_config")
            if hnsw_config:
                if hnsw_config.get("payload_m") != self.HNSW_PAYLOAD_M:
                    errors.append(
                        f"Invalid HNSW payload_m: {hnsw_config.get('payload_m')}, expected {self.HNSW_PAYLOAD_M}"
                    )

                if hnsw_config.get("ef_construct") != self.HNSW_EF_CONSTRUCT:
                    errors.append(
                        f"Invalid HNSW ef_construct: {hnsw_config.get('ef_construct')}, expected {self.HNSW_EF_CONSTRUCT}"
                    )

            # Validate required indexes
            required_indexes = [
                "project_id",
                "language",
                "type",
                "created_at",
                "importance",
            ]
            try:
                collection_info = await asyncio.to_thread(
                    self.client.get_collection, self.COLLECTION_NAME
                )
                payload_schema = collection_info.payload_schema
                existing_indexes = set()

                # payload_schema is a dict in Qdrant v1.15.4+
                if isinstance(payload_schema, dict):
                    existing_indexes = set(payload_schema.keys())
                elif hasattr(payload_schema, "get_schema"):
                    existing_indexes = set(payload_schema.get_schema().keys())
                elif hasattr(payload_schema, "__dict__"):
                    existing_indexes = set(payload_schema.__dict__.keys())
                else:
                    # TODO: Implement proper schema validation for different Qdrant versions
                    # For now, fail loudly to detect schema issues early
                    logger.error(
                        "Unable to validate payload indexes - unknown schema format",
                        payload_schema_type=type(payload_schema).__name__,
                        validation_method="schema_validation",
                    )
                    errors.append(
                        "Cannot validate payload indexes: unsupported schema format"
                    )

                # Only check missing indexes if we successfully extracted existing_indexes
                if existing_indexes:
                    missing_indexes = set(required_indexes) - existing_indexes
                    if missing_indexes:
                        errors.append(f"Missing payload indexes: {missing_indexes}")

            except Exception as e:
                errors.append(f"Failed to validate indexes: {e}")

        except Exception as e:
            errors.append(f"Schema validation failed: {e}")

        return errors

    async def upsert_points(self, project_id: UUID, points: List[VectorPoint]) -> None:
        """
        Store or update vector points in batches with mandatory project isolation and telemetry.

        CRITICAL: Validates that all points belong to the specified project_id.
        """
        if not project_id:
            raise ValueError("project_id is required for upsert operation")

        if not points:
            return

        # Validate all points before batch processing
        for point in points:
            if point.vector is None:
                raise ValueError(
                    f"Vector data is required for point {point.id} but got None. "
                    "All points must have vector data for upsert operations."
                )
            if len(point.vector) != self.VECTOR_SIZE:
                raise ValueError(
                    f"Invalid vector dimension: {len(point.vector)}, expected {self.VECTOR_SIZE}"
                )

            # SECURITY: Validate that point belongs to the specified project
            if str(point.project_id.value) != str(project_id):
                raise ValueError(
                    f"Point {point.id} belongs to project {point.project_id.value}, "
                    f"but attempting to upsert to project {project_id}. "
                    "Cross-project upsert is forbidden."
                )

        # Enhanced telemetry for upsert operation
        total_points = len(points)
        document_types = list(set(point.document_type.value for point in points))

        async with qdrant_telemetry.trace_qdrant_operation(
            QdrantOperationType.UPSERT,
            collection_name=self.COLLECTION_NAME,
            total_points=total_points,
            document_types=document_types,
            vector_size=self.VECTOR_SIZE,
        ) as span:
            # Add project context to span
            qdrant_telemetry.add_project_context(
                span, project_id, str(points[0].language)
            )

            # Record batch metrics
            qdrant_telemetry.record_batch_metrics(
                QdrantOperationType.UPSERT, total_points
            )

            # Process in batches to avoid timeouts
            for i in range(0, len(points), self.MAX_BATCH_SIZE):
                batch = points[i : i + self.MAX_BATCH_SIZE]
                batch_number = i // self.MAX_BATCH_SIZE + 1
                qdrant_points = []

                for point in batch:
                    qdrant_point = models.PointStruct(
                        id=str(point.id),
                        vector=point.vector.to_list() if point.vector else None,
                        payload=point.get_qdrant_payload(),
                    )
                    qdrant_points.append(qdrant_point)

                try:
                    await asyncio.to_thread(
                        self.client.upsert,
                        collection_name=self.COLLECTION_NAME,
                        points=qdrant_points,
                    )

                    # Record batch completion metrics
                    span.set_attribute(f"qdrant.batch_{batch_number}_size", len(batch))

                except Exception as e:
                    span.set_attribute("qdrant.failed_batch", batch_number)
                    span.set_attribute("qdrant.failed_batch_size", len(batch))
                    raise RuntimeError(
                        f"Failed to upsert batch {batch_number}: {e}"
                    ) from e

            span.set_attribute(
                "qdrant.total_batches_processed",
                (total_points + self.MAX_BATCH_SIZE - 1) // self.MAX_BATCH_SIZE,
            )

    async def get_point_by_id(
        self, point_id: UUID, project_id: UUID
    ) -> Optional[VectorPoint]:
        """
        Retrieve a vector point by its ID with mandatory project isolation.

        CRITICAL: Always validates project_id match before returning data.
        """
        if not project_id:
            raise ValueError("project_id is required for point retrieval")

        try:
            result = await asyncio.to_thread(
                self.client.retrieve,
                collection_name=self.COLLECTION_NAME,
                ids=[str(point_id)],
                with_payload=True,
                with_vectors=True,
            )

            if result:
                point_data = result[0]
                payload = point_data.payload

                # SECURITY: Verify project_id matches before returning data
                if payload.get("project_id") != str(project_id):
                    logger.warning(
                        "SECURITY ALERT: Unauthorized point access attempt",
                        point_id=str(point_id),
                        requested_project_id=str(project_id),
                        actual_project_id=payload.get("project_id"),
                        security_event="unauthorized_point_access",
                    )
                    return None

                return VectorPoint.from_qdrant_point(
                    point_id=str(point_data.id),
                    vector=point_data.vector,
                    payload=point_data.payload,
                )
            return None

        except Exception as e:
            raise RuntimeError(f"Failed to retrieve point {point_id}: {e}") from e

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
        Search for similar vectors with mandatory filtering and enhanced telemetry.

        CRITICAL: All searches MUST include project_id and language filters.
        No client can bypass these security filters.
        """
        if len(query_vector) != self.VECTOR_SIZE:
            raise ValueError(
                f"Invalid query vector dimension: {len(query_vector)}, expected {self.VECTOR_SIZE}"
            )

        if limit <= 0 or limit > 100:
            raise ValueError(f"Invalid limit: {limit}. Must be between 1 and 100")

        # Build mandatory filter - CANNOT be bypassed by client
        filter_conditions = [
            models.FieldCondition(
                key="project_id",
                match=models.MatchValue(value=str(context.project_id)),
            ),
            models.FieldCondition(
                key="language",
                match=models.MatchValue(value=str(context.language)),
            ),
        ]

        # Add optional filters
        if document_type:
            filter_conditions.append(
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value=document_type.value),
                )
            )

        if importance_min is not None:
            filter_conditions.append(
                models.FieldCondition(
                    key="importance",
                    range=models.Range(gte=importance_min),
                )
            )

        # Create mandatory filter
        search_filter = models.Filter(must=filter_conditions)

        # Enhanced telemetry for search operation
        query_params = {
            "limit": limit,
            "score_threshold": score_threshold,
            "document_type": document_type.value if document_type else None,
            "importance_min": importance_min,
            "collection_name": self.COLLECTION_NAME,
            "vector_size": len(query_vector),
        }

        async with qdrant_telemetry.trace_qdrant_operation(
            QdrantOperationType.SEARCH, **query_params
        ) as span:
            # Add project context to span
            qdrant_telemetry.add_project_context(
                span, context.project_id, str(context.language)
            )

            try:
                # Execute search with timeout
                search_result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.search,
                        collection_name=self.COLLECTION_NAME,
                        query_vector=query_vector.to_list(),
                        query_filter=search_filter,
                        limit=limit,
                        score_threshold=score_threshold,
                        with_payload=True,
                        with_vectors=False,  # Don't need vectors in results
                    ),
                    timeout=5.0,  # 5 second timeout
                )

                # Convert to SearchResult domain objects
                results = []
                scores = []  # Track scores for metrics
                for rank, scored_point in enumerate(search_result, 1):
                    # Double-check that results match filter (defense in depth)
                    payload = scored_point.payload
                    if payload.get("project_id") != str(
                        context.project_id
                    ) or payload.get("language") != str(context.language):
                        # Log security alert and skip this result
                        logger.warning(
                            "SECURITY ALERT: Filter bypass detected in search result",
                            point_id=scored_point.id,
                            expected_project_id=str(context.project_id),
                            actual_project_id=payload.get("project_id"),
                            expected_language=str(context.language),
                            actual_language=payload.get("language"),
                            security_event="filter_bypass",
                            operation="search_validation",
                        )
                        continue

                    # Validate score is within expected range
                    score = min(max(scored_point.score, 0.0), 1.0)  # Clamp to [0, 1]
                    scores.append(score)

                    point = VectorPoint.from_qdrant_search_result(
                        point_id=str(scored_point.id),
                        payload=scored_point.payload,
                    )

                    result = SearchResult(
                        point=point,
                        score=score,
                        rank=rank,
                    )
                    results.append(result)

                # Record search-specific metrics
                qdrant_telemetry.record_search_metrics(
                    QdrantOperationType.SEARCH, len(results), scores, query_params
                )

                # Add span attributes for results
                span.set_attribute("qdrant.results_found", len(results))
                span.set_attribute("qdrant.results_returned", len(results))
                if scores:
                    span.set_attribute("qdrant.avg_score", sum(scores) / len(scores))
                    span.set_attribute("qdrant.max_score", max(scores))
                    span.set_attribute("qdrant.min_score", min(scores))

                return results

            except asyncio.TimeoutError as e:
                span.set_attribute("error.timeout", "5s")
                raise TimeoutError(f"Search query timed out after 5 seconds") from e
            except Exception as e:
                # Error handling is already done by the telemetry wrapper
                raise RuntimeError(f"Search failed: {e}") from e

    async def delete_points(self, point_ids: List[UUID], project_id: UUID) -> None:
        """
        Delete vector points by their IDs with mandatory project isolation.

        SECURITY: Only deletes points that belong to the specified project.
        """
        if not project_id:
            raise ValueError("project_id is required for point deletion")

        if not point_ids:
            return

        try:
            # SECURITY: Use HasIdCondition for correct ID filtering with project isolation
            # HasIdCondition handles ID-based filtering properly in Qdrant
            await asyncio.to_thread(
                self.client.delete,
                collection_name=self.COLLECTION_NAME,
                points_selector=models.HasIdCondition(
                    has_id=[str(pid) for pid in point_ids]
                ),
            )

            logger.info(
                "Deleted points with project isolation",
                project_id=str(project_id),
                points_count=len(point_ids),
                operation="delete_points_with_isolation",
            )

        except Exception as e:
            raise RuntimeError(f"Failed to delete points: {e}") from e

    async def delete_by_filter(self, context: SearchContext) -> int:
        """Delete points matching project and language filter."""
        try:
            # Build mandatory filter
            filter_condition = models.Filter(
                must=[
                    models.FieldCondition(
                        key="project_id",
                        match=models.MatchValue(value=str(context.project_id)),
                    ),
                    models.FieldCondition(
                        key="language",
                        match=models.MatchValue(value=str(context.language)),
                    ),
                ]
            )

            # Get count before deletion
            count_before = await self.count_points(context)

            # Delete matching points
            await asyncio.to_thread(
                self.client.delete,
                collection_name=self.COLLECTION_NAME,
                points_selector=filter_condition,
            )

            return count_before

        except Exception as e:
            raise RuntimeError(f"Failed to delete by filter: {e}") from e

    async def count_points(self, context: SearchContext) -> int:
        """Count points matching project and language filter."""
        try:
            filter_condition = models.Filter(
                must=[
                    models.FieldCondition(
                        key="project_id",
                        match=models.MatchValue(value=str(context.project_id)),
                    ),
                    models.FieldCondition(
                        key="language",
                        match=models.MatchValue(value=str(context.language)),
                    ),
                ]
            )

            count = await asyncio.to_thread(
                self.client.count,
                collection_name=self.COLLECTION_NAME,
                count_filter=filter_condition,
            )
            return count.count

        except Exception as e:
            raise RuntimeError(f"Failed to count points: {e}") from e

    async def get_collection_health(self) -> CollectionHealth:
        """Get comprehensive health status of the collection."""
        try:
            # Check if collection exists
            if not await self.collection_exists():
                return CollectionHealth(
                    collection_name=self.COLLECTION_NAME,
                    status=HealthStatus.UNHEALTHY,
                    vector_count=0,
                    indexed_fields=[],
                    config_status={},
                    errors=["Collection does not exist"],
                )

            # Get collection info
            info = await self.get_collection_info()

            # Validate schema
            validation_errors = await self.validate_schema()

            # Check indexed fields
            indexed_fields = []
            try:
                collection_info = await asyncio.to_thread(
                    self.client.get_collection, self.COLLECTION_NAME
                )
                payload_schema = collection_info.payload_schema
                if hasattr(payload_schema, "get_schema"):
                    indexed_fields = list(payload_schema.get_schema().keys())
                elif hasattr(payload_schema, "__dict__"):
                    indexed_fields = list(payload_schema.__dict__.keys())
                else:
                    indexed_fields = []
            except Exception:
                pass

            # Check configuration
            config_status = {
                "vector_size_correct": info.get("vector_size") == self.VECTOR_SIZE,
                "distance_metric_correct": info.get("distance")
                in ["Distance.COSINE", "Cosine"],
                "hnsw_optimized": bool(info.get("hnsw_config")),
                "indexes_created": len(indexed_fields) >= 5,
            }

            # Determine overall health
            if validation_errors:
                status = HealthStatus.UNHEALTHY
            else:
                # Check if all config values are truthy
                config_values = list(config_status.values())
                if any(not v for v in config_values):
                    status = HealthStatus.DEGRADED
                else:
                    status = HealthStatus.HEALTHY

            return CollectionHealth(
                collection_name=self.COLLECTION_NAME,
                status=status,
                vector_count=info.get("points_count", 0),
                indexed_fields=indexed_fields,
                config_status=config_status,
                errors=validation_errors,
            )

        except Exception as e:
            return CollectionHealth(
                collection_name=self.COLLECTION_NAME,
                status=HealthStatus.UNHEALTHY,
                vector_count=0,
                indexed_fields=[],
                config_status={},
                errors=[f"Health check failed: {e}"],
            )


class QdrantCollectionManager(CollectionManager):
    """Qdrant implementation of collection manager."""

    def __init__(self, repository: QdrantVectorRepository):
        """
        Initialize collection manager.

        Args:
            repository: QdrantVectorRepository instance
        """
        self.repository = repository

    async def initialize(self) -> None:
        """Initialize the collection manager."""
        await self.repository.initialize_collection()

    async def health_check(self) -> CollectionHealth:
        """Perform comprehensive health check."""
        return await self.repository.get_collection_health()

    async def recreate_collection(self) -> None:
        """Recreate the collection (development only)."""
        try:
            # Delete existing collection if it exists
            if await self.repository.collection_exists():
                await asyncio.to_thread(
                    self.repository.client.delete_collection,
                    self.repository.COLLECTION_NAME,
                )
                logger.info(
                    "Deleted collection",
                    collection_name=self.repository.COLLECTION_NAME,
                    operation="delete_collection",
                )

            # Recreate with fresh configuration
            await self.repository.initialize_collection()
            logger.info(
                "Recreated collection",
                collection_name=self.repository.COLLECTION_NAME,
                operation="recreate_collection",
            )

        except Exception as e:
            raise RuntimeError(f"Failed to recreate collection: {e}") from e

    async def get_statistics(self) -> Dict[str, Any]:
        """Get collection statistics and metrics."""
        try:
            info = await self.repository.get_collection_info()
            health = await self.health_check()

            return {
                "collection_info": info,
                "health_status": health.to_dict(),
                "configuration": {
                    "vector_size": self.repository.VECTOR_SIZE,
                    "hnsw_config": {
                        "m": self.repository.HNSW_M,
                        "payload_m": self.repository.HNSW_PAYLOAD_M,
                        "ef_construct": self.repository.HNSW_EF_CONSTRUCT,
                    },
                    "batch_size_limit": self.repository.MAX_BATCH_SIZE,
                },
            }

        except Exception as e:
            return {
                "error": str(e),
                "collection_info": None,
                "health_status": None,
            }
