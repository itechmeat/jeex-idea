"""
Vector database services module.

Domain-Driven Design implementation for vector database operations
with strict project isolation and mandatory filter enforcement.
"""

from .collection_manager import VectorCollectionManager
from .search_service import (
    DefaultVectorSearchService,
    build_mandatory_filter,
    build_search_filter,
)
from .repositories.qdrant_repository import QdrantVectorRepository
from .repositories.interfaces import (
    VectorRepository,
    VectorSearchService,
    CollectionManager,
)

__all__ = [
    "VectorCollectionManager",
    "DefaultVectorSearchService",
    "build_mandatory_filter",
    "build_search_filter",
    "QdrantVectorRepository",
    "VectorRepository",
    "VectorSearchService",
    "CollectionManager",
]
