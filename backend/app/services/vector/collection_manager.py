"""
Collection manager service for vector database operations.

High-level service interface for collection lifecycle management,
health monitoring, and administrative operations.
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List

import structlog
from qdrant_client import QdrantClient
from tenacity import retry, stop_after_attempt, wait_exponential

from .domain.entities import CollectionHealth, HealthStatus
from .repositories.qdrant_repository import (
    QdrantVectorRepository,
    QdrantCollectionManager,
)

logger = structlog.get_logger()


class VectorCollectionManager:
    """
    High-level collection manager service.

    Provides simplified interface for collection management operations
    with comprehensive error handling and health monitoring.
    """

    def __init__(self, qdrant_url: str, timeout: int = 30):
        """
        Initialize collection manager.

        Args:
            qdrant_url: Qdrant server URL
            timeout: Request timeout in seconds
        """
        self.client = QdrantClient(
            url=qdrant_url,
            timeout=timeout,
        )
        self.repository = QdrantVectorRepository(self.client)
        self.collection_manager = QdrantCollectionManager(self.repository)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    async def initialize(self) -> None:
        """
        Initialize the vector collection.

        Creates collection if it doesn't exist and ensures all
        required indexes are created with optimal configuration.
        """
        try:
            await self.collection_manager.initialize()
            logger.info(
                "Vector collection initialized successfully",
                collection_name=self.repository.COLLECTION_NAME,
                operation="initialize",
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize vector collection: {e}") from e

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check.

        Returns:
            Detailed health status including collection info and errors
        """
        try:
            health = await self.collection_manager.health_check()

            # Additional connectivity checks
            is_connected = await self._check_connectivity()

            if not is_connected and health.status == HealthStatus.HEALTHY:
                health.status = HealthStatus.DEGRADED
                health.errors.append("Qdrant connectivity check failed")

            return health.to_dict()

        except Exception as e:
            return {
                "collection_name": self.repository.COLLECTION_NAME,
                "status": HealthStatus.UNHEALTHY.value,
                "vector_count": 0,
                "indexed_fields": [],
                "config_status": {},
                "errors": [f"Health check failed: {e}"],
                "connectivity": False,
            }

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get collection statistics and metrics.

        Returns:
            Comprehensive statistics including configuration and usage
        """
        try:
            stats = await self.collection_manager.get_statistics()

            # Add additional metrics
            stats["connectivity"] = await self._check_connectivity()
            stats["timestamp"] = datetime.utcnow().isoformat()

            return stats

        except Exception as e:
            return {
                "error": str(e),
                "collection_name": self.repository.COLLECTION_NAME,
                "connectivity": False,
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def recreate_collection(self) -> Dict[str, Any]:
        """
        Recreate the collection (development only).

        WARNING: This will delete all existing data!

        Returns:
            Recreation status and any errors
        """
        try:
            # Get backup statistics before deletion
            stats_before = await self.get_statistics()
            vector_count = stats_before.get("collection_info", {}).get(
                "points_count", 0
            )

            # Recreate collection
            await self.collection_manager.recreate_collection()

            # Get new statistics
            stats_after = await self.get_statistics()

            return {
                "status": "success",
                "message": f"Collection recreated successfully",
                "vectors_deleted": vector_count,
                "new_collection_info": stats_after.get("collection_info", {}),
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def validate_configuration(self) -> Dict[str, Any]:
        """
        Validate collection configuration matches requirements.

        Returns:
            Validation results with any configuration issues
        """
        try:
            validation_errors = await self.repository.validate_schema()

            configuration_status = {
                "collection_exists": await self.repository.collection_exists(),
                "validation_errors": validation_errors,
                "is_valid": len(validation_errors) == 0,
                "expected_configuration": {
                    "collection_name": self.repository.COLLECTION_NAME,
                    "vector_size": self.repository.VECTOR_SIZE,
                    "hnsw_config": {
                        "m": self.repository.HNSW_M,
                        "payload_m": self.repository.HNSW_PAYLOAD_M,
                        "ef_construct": self.repository.HNSW_EF_CONSTRUCT,
                    },
                    "required_indexes": [
                        "project_id",
                        "language",
                        "type",
                        "created_at",
                        "importance",
                    ],
                },
            }

            if configuration_status["collection_exists"]:
                try:
                    info = await self.repository.get_collection_info()
                    configuration_status["actual_configuration"] = {
                        "vector_size": info.get("vector_size"),
                        "distance": info.get("distance"),
                        "points_count": info.get("points_count"),
                        "hnsw_config": info.get("hnsw_config"),
                    }
                except Exception as e:
                    configuration_status["configuration_error"] = str(e)

            return configuration_status

        except Exception as e:
            return {
                "validation_error": str(e),
                "is_valid": False,
                "collection_exists": False,
                "validation_errors": [f"Configuration validation failed: {e}"],
            }

    async def _check_connectivity(self) -> bool:
        """
        Check connectivity to Qdrant server.

        Returns:
            True if connected, False otherwise
        """
        try:
            # Simple connectivity check
            await asyncio.wait_for(
                asyncio.to_thread(self.client.get_collections), timeout=5.0
            )
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the Qdrant client connection."""
        try:
            # Qdrant client doesn't have explicit close method,
            # but we can clean up resources here if needed
            pass
        except Exception:
            pass  # Ignore errors during cleanup
