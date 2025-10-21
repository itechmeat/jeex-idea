"""
Vector database core dependencies and configuration.

Centralized vector database client setup with OpenTelemetry integration
and performance monitoring following the project architecture.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from qdrant_client import QdrantClient
from opentelemetry import trace
from opentelemetry.metrics import Meter, Counter, Histogram
import structlog

from .config import get_settings
from ..services.vector import (
    VectorCollectionManager,
    DefaultVectorSearchService,
    QdrantVectorRepository,
)

logger = structlog.get_logger()
settings = get_settings()
tracer = trace.get_tracer(__name__)

# Initialize OpenTelemetry metrics - required by specs.md
# OpenTelemetry 1.27+ is mandatory (see docs/specs.md line 73)
try:
    from opentelemetry.metrics import get_meter_provider

    meter_provider = get_meter_provider()
    meter = meter_provider.get_meter(__name__)

    # Vector operation metrics
    vector_operations_counter = meter.create_counter(
        "vector_operations_total",
        description="Total number of vector database operations",
    )

    vector_search_latency = meter.create_histogram(
        "vector_search_duration_seconds",
        description="Vector search operation duration",
        unit="s",
    )

    vector_upsert_counter = meter.create_counter(
        "vector_upserts_total",
        description="Total number of vector upsert operations",
    )

    vector_upsert_latency = meter.create_histogram(
        "vector_upsert_duration_seconds",
        description="Vector upsert operation duration",
        unit="s",
    )

    vector_errors = meter.create_counter(
        "vector_errors_total",
        description="Total number of vector database errors",
    )

except ImportError as e:
    # OpenTelemetry metrics not available - fail fast per CLAUDE.md
    logger.error(
        "OpenTelemetry metrics import failed - required dependency missing",
        error=str(e),
        exc_info=True,
    )
    raise RuntimeError(
        "OpenTelemetry metrics are required but not available. "
        "Install OpenTelemetry metrics SDK (>=1.27) as specified in docs/specs.md. "
        "Error: " + str(e)
    ) from e
except Exception as e:
    # Meter provider not available or misconfigured - fail fast per CLAUDE.md
    logger.error(
        "OpenTelemetry meter provider initialization failed",
        error=str(e),
        exc_info=True,
    )
    raise RuntimeError(
        "OpenTelemetry meter provider is required but not properly configured. "
        "Ensure OpenTelemetry SDK is initialized before importing vector module. "
        "Error: " + str(e)
    ) from e


class VectorDatabaseManager:
    """
    Centralized vector database manager with observability.

    Manages Qdrant client lifecycle, connection pooling, and metrics.
    Provides consistent interface for all vector operations with tracing.
    """

    def __init__(self):
        """Initialize vector database manager."""
        self.client: Optional[QdrantClient] = None
        self.collection_manager: Optional[VectorCollectionManager] = None
        self.search_service: Optional[DefaultVectorSearchService] = None
        self.repository: Optional[QdrantVectorRepository] = None
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize vector database connections and services.

        Sets up Qdrant client with optimal configuration, creates collection
        manager and search service, and validates configuration.
        """
        if self._initialized:
            return

        with tracer.start_as_current_span("vector_database_initialize") as span:
            try:
                # Validate settings before initialization
                if not settings.QDRANT_URL or not settings.QDRANT_URL.strip():
                    raise ValueError("QDRANT_URL must be a non-empty string")
                if (
                    not settings.QDRANT_COLLECTION
                    or not settings.QDRANT_COLLECTION.strip()
                ):
                    raise ValueError("QDRANT_COLLECTION must be a non-empty string")
                if (
                    not isinstance(settings.QDRANT_TIMEOUT, (int, float))
                    or settings.QDRANT_TIMEOUT <= 0
                ):
                    raise ValueError("QDRANT_TIMEOUT must be a positive number")

                logger.info(
                    "Initializing vector database",
                    qdrant_url=settings.QDRANT_URL,
                    collection=settings.QDRANT_COLLECTION,
                    timeout=settings.QDRANT_TIMEOUT,
                )

                # Initialize Qdrant client
                self.client = QdrantClient(
                    url=settings.QDRANT_URL,
                    timeout=settings.QDRANT_TIMEOUT,
                )

                # Test connectivity
                await self._test_connectivity()

                # Initialize repository
                self.repository = QdrantVectorRepository(self.client)

                # Initialize collection manager
                self.collection_manager = VectorCollectionManager(
                    qdrant_url=settings.QDRANT_URL,
                    timeout=settings.QDRANT_TIMEOUT,
                )

                # Initialize collection
                await self.collection_manager.initialize()

                # Initialize search service
                self.search_service = DefaultVectorSearchService(self.repository)

                self._initialized = True
                span.set_attribute("vector.initialized", True)
                span.set_attribute("vector.collection", settings.QDRANT_COLLECTION)

                logger.info(
                    "Vector database initialized successfully",
                    collection=settings.QDRANT_COLLECTION,
                )

            except Exception as e:
                logger.error(
                    "Failed to initialize vector database",
                    error=str(e),
                    exc_info=True,
                )
                span.record_exception(e)
                span.set_attribute("vector.initialized", False)
                raise

    async def _test_connectivity(self) -> None:
        """Test Qdrant server connectivity."""
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self.client.get_collections),
                timeout=10.0,
            )
            logger.debug("Qdrant connectivity test successful")
        except Exception as e:
            logger.error(
                "Qdrant connectivity test failed",
                error=str(e),
            )
            raise ConnectionError(
                f"Cannot connect to Qdrant at {settings.QDRANT_URL}: {e}"
            ) from e

    async def cleanup(self) -> None:
        """Cleanup vector database resources."""
        if not self._initialized:
            return

        with tracer.start_as_current_span("vector_database_cleanup"):
            try:
                if self.collection_manager:
                    await self.collection_manager.close()

                if self.client:
                    # Qdrant client doesn't have explicit close
                    pass

                self._initialized = False
                logger.info("Vector database cleanup completed")

            except Exception as e:
                logger.error(
                    "Vector database cleanup failed",
                    error=str(e),
                    exc_info=True,
                )

    async def health_check(self) -> dict:
        """Perform comprehensive vector database health check."""
        if not self._initialized or not self.collection_manager:
            return {
                "status": "unhealthy",
                "error": "Vector database not initialized",
                "collection": None,
            }

        try:
            with tracer.start_as_current_span("vector_health_check"):
                health_data = await self.collection_manager.health_check()
                health_data["initialized"] = self._initialized
                return health_data

        except Exception as e:
            logger.error(
                "Vector database health check failed",
                error=str(e),
                exc_info=True,
            )
            return {
                "status": "unhealthy",
                "error": str(e),
                "collection": settings.QDRANT_COLLECTION,
                "initialized": False,
            }

    async def get_statistics(self) -> dict:
        """Get vector database statistics."""
        if not self._initialized or not self.collection_manager:
            return {
                "error": "Vector database not initialized",
                "collection": settings.QDRANT_COLLECTION,
            }

        try:
            with tracer.start_as_current_span("vector_statistics"):
                return await self.collection_manager.get_statistics()

        except Exception as e:
            logger.error(
                "Failed to get vector statistics",
                error=str(e),
                exc_info=True,
            )
            return {
                "error": str(e),
                "collection": settings.QDRANT_COLLECTION,
            }

    @property
    def is_initialized(self) -> bool:
        """Check if vector database is initialized."""
        return self._initialized

    def get_search_service(self) -> DefaultVectorSearchService:
        """
        Get vector search service.

        Returns:
            Configured vector search service

        Raises:
            RuntimeError: If vector database is not initialized
        """
        if not self._initialized or not self.search_service:
            raise RuntimeError("Vector database not initialized")
        return self.search_service

    def get_repository(self) -> QdrantVectorRepository:
        """
        Get vector repository.

        Returns:
            Configured vector repository

        Raises:
            RuntimeError: If vector database is not initialized
        """
        if not self._initialized or not self.repository:
            raise RuntimeError("Vector database not initialized")
        return self.repository


# Global vector database manager instance
vector_database = VectorDatabaseManager()


@asynccontextmanager
async def get_vector_database() -> AsyncGenerator[VectorDatabaseManager, None]:
    """
    Get vector database manager with automatic lifecycle management.

    Context manager for vector database operations with proper initialization
    and cleanup. Use for dependency injection in FastAPI endpoints.

    Yields:
        VectorDatabaseManager: Initialized vector database manager
    """
    if not vector_database.is_initialized:
        await vector_database.initialize()

    try:
        yield vector_database
    except Exception as e:
        logger.error(
            "Vector database operation failed",
            error=str(e),
            exc_info=True,
        )
        raise


def get_vector_search_service() -> DefaultVectorSearchService:
    """
    Get vector search service for dependency injection.

    CRITICAL: Does NOT auto-initialize to prevent blocking operations in request handlers.
    The service must be initialized during application startup.

    Returns:
        Configured vector search service

    Raises:
        RuntimeError: If vector database is not initialized
    """
    if not vector_database.is_initialized:
        raise RuntimeError(
            "Vector database not initialized. Call vector_database.initialize() "
            "during application startup before using dependency injection."
        )
    return vector_database.get_search_service()


def get_vector_repository() -> QdrantVectorRepository:
    """
    Get vector repository for dependency injection.

    CRITICAL: Does NOT auto-initialize to prevent blocking operations in request handlers.
    The repository must be initialized during application startup.

    Returns:
        Configured vector repository

    Raises:
        RuntimeError: If vector database is not initialized
    """
    if not vector_database.is_initialized:
        raise RuntimeError(
            "Vector database not initialized. Call vector_database.initialize() "
            "during application startup before using dependency injection."
        )
    return vector_database.get_repository()
