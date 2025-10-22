"""
Qdrant OpenTelemetry Instrumentation

HTTP client instrumentation for Qdrant vector database operations.
Provides comprehensive tracing and metrics for vector search and collection operations.

This module implements:
- HTTP client instrumentation for Qdrant API calls
- Search operation spans with query parameters and result counts
- Collection operations (create, update, delete) tracing
- Performance metrics for vector search operations
- Error handling and classification for failed Qdrant operations
"""

import asyncio
import time
from typing import Dict, Any, Optional, List, Union, Callable
from contextlib import asynccontextmanager, contextmanager
from uuid import UUID

from opentelemetry import trace, metrics
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.sdk.trace import Span
from opentelemetry.propagate import inject
from opentelemetry.semconv.trace import SpanAttributes
import structlog

from .telemetry import get_tracer, get_meter

logger = structlog.get_logger()


class QdrantOperationType:
    """Qdrant operation type constants for span naming and metrics."""

    SEARCH = "qdrant.search"
    UPSERT = "qdrant.upsert"
    RETRIEVE = "qdrant.retrieve"
    DELETE = "qdrant.delete"
    COUNT = "qdrant.count"
    COLLECTION_CREATE = "qdrant.collection.create"
    COLLECTION_DELETE = "qdrant.collection.delete"
    COLLECTION_INFO = "qdrant.collection.info"
    INDEX_CREATE = "qdrant.index.create"
    HEALTH_CHECK = "qdrant.health"


class QdrantErrorClassifier:
    """Classifies Qdrant errors for appropriate error handling and metrics."""

    NETWORK_ERRORS = [
        "ConnectionError",
        "TimeoutError",
        "ConnectionRefusedError",
        "ConnectionResetError",
        "OSError",
        "socket.gaierror",
    ]

    CLIENT_ERRORS = [
        "UnexpectedResponse",
        "ValueError",
        "ValidationError",
        "TypeError",
        "KeyError",
        "AttributeError",
    ]

    SERVER_ERRORS = [
        "InternalServerError",
        "ServiceUnavailable",
        "TimeoutExpired",
        "RateLimitExceeded",
        "ResourceExhausted",
    ]

    @classmethod
    def classify_error(cls, error: Exception) -> str:
        """
        Classify error type for metrics and span attributes.

        Args:
            error: Exception instance

        Returns:
            Error classification string
        """
        error_type = type(error).__name__

        if error_type in cls.NETWORK_ERRORS:
            return "network"
        elif error_type in cls.CLIENT_ERRORS:
            return "client"
        elif error_type in cls.SERVER_ERRORS:
            return "server"
        else:
            return "unknown"


class QdrantTelemetry:
    """
    Qdrant telemetry instrumentation manager.

    Provides comprehensive tracing and metrics for Qdrant operations
    with proper error handling and performance monitoring.
    """

    def __init__(self):
        """Initialize Qdrant telemetry manager."""
        self._tracer = get_tracer(__name__)
        self._meter = get_meter(__name__)

        # Initialize metrics
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize OpenTelemetry metrics for Qdrant operations."""
        # Operation counters
        self.operation_counter = self._meter.create_counter(
            "qdrant_operations_total",
            description="Total number of Qdrant operations",
        )

        # Operation duration histograms
        self.operation_duration = self._meter.create_histogram(
            "qdrant_operation_duration_seconds",
            description="Duration of Qdrant operations",
            unit="s",
        )

        # Search-specific metrics
        self.search_result_count = self._meter.create_histogram(
            "qdrant_search_results_count",
            description="Number of results returned from vector search",
        )

        self.search_score_histogram = self._meter.create_histogram(
            "qdrant_search_score_distribution",
            description="Distribution of similarity scores in search results",
        )

        # Error counters
        self.error_counter = self._meter.create_counter(
            "qdrant_errors_total",
            description="Total number of Qdrant errors",
        )

        # Batch size metrics
        self.batch_size_histogram = self._meter.create_histogram(
            "qdrant_batch_size",
            description="Size of batch operations",
        )

    @asynccontextmanager
    async def trace_qdrant_operation(self, operation_name: str, **attributes):
        """
        Context manager for tracing Qdrant operations.

        Args:
            operation_name: Name of the Qdrant operation
            **attributes: Additional span attributes

        Yields:
            Span for the operation
        """
        span_name = f"qdrant.{operation_name}"

        with self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            # Add standard attributes
            span.set_attribute("db.system", "qdrant")
            span.set_attribute("db.operation", operation_name)

            # Add user-provided attributes
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(str(key), str(value))

            # Record operation start
            start_time = time.time()

            try:
                yield span

                # Record success metrics
                duration = time.time() - start_time
                self.operation_counter.add(
                    1, {"operation": operation_name, "status": "success"}
                )
                self.operation_duration.record(
                    duration, {"operation": operation_name, "status": "success"}
                )

                span.set_status(Status(StatusCode.OK))

            except Exception as e:
                # Record error metrics and span attributes
                duration = time.time() - start_time
                error_type = QdrantErrorClassifier.classify_error(e)

                self.operation_counter.add(
                    1,
                    {
                        "operation": operation_name,
                        "status": "error",
                        "error_type": error_type,
                    },
                )
                self.operation_duration.record(
                    duration,
                    {
                        "operation": operation_name,
                        "status": "error",
                        "error_type": error_type,
                    },
                )

                self.error_counter.add(
                    1,
                    {
                        "operation": operation_name,
                        "error_type": error_type,
                        "error_class": type(e).__name__,
                    },
                )

                # Set span error attributes
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.set_attribute("error.type", error_type)
                span.set_attribute("error.class", type(e).__name__)
                span.set_attribute("error.message", str(e))

                # Record exception in span
                span.record_exception(e)

                # Re-raise exception
                raise

    def record_search_metrics(
        self,
        operation_name: str,
        result_count: int,
        scores: List[float],
        query_params: Dict[str, Any],
    ) -> None:
        """
        Record search-specific metrics.

        Args:
            operation_name: Name of the search operation
            result_count: Number of results returned
            scores: List of similarity scores
            query_params: Query parameters used
        """
        # Record result count
        self.search_result_count.record(
            result_count,
            {
                "operation": operation_name,
                "limit": query_params.get("limit", 0),
                "score_threshold": query_params.get("score_threshold", 0.0),
            },
        )

        # Record score distribution
        for score in scores:
            self.search_score_histogram.record(score, {"operation": operation_name})

    def record_batch_metrics(self, operation_name: str, batch_size: int) -> None:
        """
        Record batch operation metrics.

        Args:
            operation_name: Name of the batch operation
            batch_size: Size of the batch
        """
        self.batch_size_histogram.record(batch_size, {"operation": operation_name})

    def add_project_context(self, span: Span, project_id: UUID, language: str) -> None:
        """
        Add project context attributes to span.

        Args:
            span: OpenTelemetry span
            project_id: Project ID for isolation
            language: Language code
        """
        span.set_attribute("project.id", str(project_id))
        span.set_attribute("project.language", language)
        span.set_attribute("db.namespace", f"project_{project_id}")


# Global telemetry instance
qdrant_telemetry = QdrantTelemetry()


def instrument_qdrant_client(qdrant_client):
    """
    Instrument Qdrant client with OpenTelemetry tracing.

    Wraps Qdrant client methods to add comprehensive tracing and metrics.

    Args:
        qdrant_client: QdrantClient instance to instrument

    Returns:
        Instrumented QdrantClient wrapper
    """

    class InstrumentedQdrantClient:
        """Qdrant client wrapper with OpenTelemetry instrumentation."""

        def __init__(self, client):
            """Initialize instrumented client wrapper."""
            self._client = client

        async def search(
            self,
            collection_name: str,
            query_vector: List[float],
            query_filter: Optional[Any] = None,
            limit: int = 10,
            score_threshold: Optional[float] = None,
            with_payload: bool = True,
            with_vectors: bool = False,
            **kwargs,
        ):
            """Instrumented search operation."""
            async with qdrant_telemetry.trace_qdrant_operation(
                QdrantOperationType.SEARCH,
                collection_name=collection_name,
                vector_size=len(query_vector),
                limit=limit,
                score_threshold=score_threshold,
                with_payload=with_payload,
                with_vectors=with_vectors,
            ) as span:
                # Execute search
                result = await asyncio.to_thread(
                    self._client.search,
                    collection_name=collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                    score_threshold=score_threshold,
                    with_payload=with_payload,
                    with_vectors=with_vectors,
                    **kwargs,
                )

                # Extract project context from filter if available
                if query_filter and hasattr(query_filter, "must"):
                    for condition in query_filter.must:
                        if hasattr(condition, "key") and condition.key == "project_id":
                            if hasattr(condition, "match") and hasattr(
                                condition.match, "value"
                            ):
                                span.set_attribute("project.id", condition.match.value)
                        elif hasattr(condition, "key") and condition.key == "language":
                            if hasattr(condition, "match") and hasattr(
                                condition.match, "value"
                            ):
                                span.set_attribute(
                                    "project.language", condition.match.value
                                )

                # Record search metrics
                scores = [point.score for point in result]
                qdrant_telemetry.record_search_metrics(
                    QdrantOperationType.SEARCH,
                    len(result),
                    scores,
                    {"limit": limit, "score_threshold": score_threshold or 0.0},
                )

                # Add result attributes
                span.set_attribute("qdrant.result_count", len(result))
                if scores:
                    span.set_attribute("qdrant.avg_score", sum(scores) / len(scores))
                    span.set_attribute("qdrant.max_score", max(scores))
                    span.set_attribute("qdrant.min_score", min(scores))

                return result

        async def upsert(self, collection_name: str, points: List[Any], **kwargs):
            """Instrumented upsert operation."""
            async with qdrant_telemetry.trace_qdrant_operation(
                QdrantOperationType.UPSERT,
                collection_name=collection_name,
                points_count=len(points),
            ) as span:
                # Extract project context from first point payload
                if points and hasattr(points[0], "payload"):
                    payload = points[0].payload
                    if "project_id" in payload:
                        span.set_attribute("project.id", payload["project_id"])
                    if "language" in payload:
                        span.set_attribute("project.language", payload["language"])

                # Record batch metrics
                qdrant_telemetry.record_batch_metrics(
                    QdrantOperationType.UPSERT, len(points)
                )

                # Execute upsert
                result = await asyncio.to_thread(
                    self._client.upsert,
                    collection_name=collection_name,
                    points=points,
                    **kwargs,
                )

                return result

        async def retrieve(
            self,
            collection_name: str,
            ids: List[str],
            with_payload: bool = True,
            with_vectors: bool = False,
            **kwargs,
        ):
            """Instrumented retrieve operation."""
            async with qdrant_telemetry.trace_qdrant_operation(
                QdrantOperationType.RETRIEVE,
                collection_name=collection_name,
                ids_count=len(ids),
                with_payload=with_payload,
                with_vectors=with_vectors,
            ) as span:
                result = await asyncio.to_thread(
                    self._client.retrieve,
                    collection_name=collection_name,
                    ids=ids,
                    with_payload=with_payload,
                    with_vectors=with_vectors,
                    **kwargs,
                )

                span.set_attribute("qdrant.result_count", len(result))
                return result

        async def delete(self, collection_name: str, points_selector: Any, **kwargs):
            """Instrumented delete operation."""
            # Try to determine number of points being deleted
            points_count = "unknown"
            if hasattr(points_selector, "has_id"):
                points_count = len(points_selector.has_id)
            elif hasattr(points_selector, "must"):
                points_count = "filter"

            async with qdrant_telemetry.trace_qdrant_operation(
                QdrantOperationType.DELETE,
                collection_name=collection_name,
                points_count=points_count,
            ) as span:
                result = await asyncio.to_thread(
                    self._client.delete,
                    collection_name=collection_name,
                    points_selector=points_selector,
                    **kwargs,
                )

                return result

        async def count(
            self, collection_name: str, count_filter: Optional[Any] = None, **kwargs
        ):
            """Instrumented count operation."""
            async with qdrant_telemetry.trace_qdrant_operation(
                QdrantOperationType.COUNT,
                collection_name=collection_name,
                has_filter=count_filter is not None,
            ) as span:
                result = await asyncio.to_thread(
                    self._client.count,
                    collection_name=collection_name,
                    count_filter=count_filter,
                    **kwargs,
                )

                span.set_attribute("qdrant.count", result.count)
                return result

        async def get_collection(self, collection_name: str, **kwargs):
            """Instrumented get collection operation."""
            async with qdrant_telemetry.trace_qdrant_operation(
                QdrantOperationType.COLLECTION_INFO, collection_name=collection_name
            ) as span:
                result = await asyncio.to_thread(
                    self._client.get_collection,
                    collection_name=collection_name,
                    **kwargs,
                )

                # Add collection info to span
                if hasattr(result, "points_count"):
                    span.set_attribute("qdrant.points_count", result.points_count)
                if hasattr(result, "segments_count"):
                    span.set_attribute("qdrant.segments_count", result.segments_count)

                return result

        async def get_collections(self, **kwargs):
            """Instrumented get collections operation."""
            async with qdrant_telemetry.trace_qdrant_operation(
                QdrantOperationType.COLLECTION_INFO, operation="list_collections"
            ) as span:
                result = await asyncio.to_thread(self._client.get_collections, **kwargs)

                span.set_attribute("qdrant.collections_count", len(result.collections))
                return result

        async def create_collection(
            self, collection_name: str, vectors_config: Any, **kwargs
        ):
            """Instrumented create collection operation."""
            async with qdrant_telemetry.trace_qdrant_operation(
                QdrantOperationType.COLLECTION_CREATE, collection_name=collection_name
            ) as span:
                # Add vector config info
                if hasattr(vectors_config, "size"):
                    span.set_attribute("qdrant.vector_size", vectors_config.size)
                if hasattr(vectors_config, "distance"):
                    span.set_attribute("qdrant.distance", str(vectors_config.distance))

                result = await asyncio.to_thread(
                    self._client.create_collection,
                    collection_name=collection_name,
                    vectors_config=vectors_config,
                    **kwargs,
                )

                return result

        async def delete_collection(self, collection_name: str, **kwargs):
            """Instrumented delete collection operation."""
            async with qdrant_telemetry.trace_qdrant_operation(
                QdrantOperationType.COLLECTION_DELETE, collection_name=collection_name
            ) as span:
                result = await asyncio.to_thread(
                    self._client.delete_collection,
                    collection_name=collection_name,
                    **kwargs,
                )

                return result

        async def create_payload_index(
            self, collection_name: str, field_name: str, field_schema: Any, **kwargs
        ):
            """Instrumented create payload index operation."""
            async with qdrant_telemetry.trace_qdrant_operation(
                QdrantOperationType.INDEX_CREATE,
                collection_name=collection_name,
                field_name=field_name,
                field_schema=str(field_schema),
            ) as span:
                result = await asyncio.to_thread(
                    self._client.create_payload_index,
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                    **kwargs,
                )

                return result

        # Delegate all other methods to the original client
        def __getattr__(self, name):
            """Delegate any other method calls to the original client."""
            return getattr(self._client, name)

    return InstrumentedQdrantClient(qdrant_client)


# Export main classes and functions
__all__ = [
    "QdrantOperationType",
    "QdrantErrorClassifier",
    "QdrantTelemetry",
    "qdrant_telemetry",
    "instrument_qdrant_client",
]
