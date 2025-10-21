"""
Domain entities for vector database operations following DDD patterns.

Entities represent core business objects with identity and lifecycle.
Value objects represent immutable concepts without identity.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, List
from uuid import UUID, uuid4
import hashlib
import re


class DocumentType(str, Enum):
    """Enumeration of supported document types for vector storage."""

    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    AGENT_CONTEXT = "agent_context"


class HealthStatus(str, Enum):
    """Enumeration of service health statuses."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class ProjectId:
    """Value object representing a project identifier with validation."""

    value: str

    def __post_init__(self) -> None:
        """Validate the project ID is a valid UUID."""
        try:
            UUID(self.value)
        except ValueError as exc:
            raise ValueError(f"Invalid project_id format: {self.value}") from exc

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class LanguageCode:
    """Value object representing a language code with validation."""

    value: str

    def __post_init__(self) -> None:
        """Validate the language code is a valid ISO 639-1 code."""
        if not re.match(r"^[a-z]{2}$", self.value):
            raise ValueError(
                f"Invalid language code format: {self.value}. Must be ISO 639-1 (2 characters)."
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ContentHash:
    """Value object representing content hash for deduplication."""

    value: str

    @classmethod
    def from_content(cls, content: str) -> "ContentHash":
        """Create a content hash from text content."""
        hash_value = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return cls(value=hash_value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class VectorData:
    """Value object representing vector data with validation."""

    value: List[float]

    def __post_init__(self) -> None:
        """Validate vector dimension and values."""
        if len(self.value) != 1536:
            raise ValueError(
                f"Invalid vector dimension: {len(self.value)}. Expected: 1536"
            )

        if not all(isinstance(x, (int, float)) and -1 <= x <= 1 for x in self.value):
            raise ValueError(
                "Vector values must be numbers between -1 and 1 (normalized embeddings)"
            )

    def __len__(self) -> int:
        return len(self.value)

    def to_list(self) -> List[float]:
        """Return vector as list for Qdrant client."""
        return self.value.copy()


@dataclass(frozen=True)
class SearchContext:
    """Value object representing search context with mandatory fields."""

    project_id: ProjectId
    language: LanguageCode

    @classmethod
    def create(cls, project_id: str, language: str) -> "SearchContext":
        """Create search context with validation."""
        return cls(project_id=ProjectId(project_id), language=LanguageCode(language))


@dataclass
class VectorPoint:
    """
    Domain entity representing a vector point with rich metadata.

    This is the core aggregate root for vector operations.
    """

    vector: VectorData
    content: str
    project_id: ProjectId
    language: LanguageCode
    document_type: DocumentType
    id: UUID = field(default_factory=uuid4)
    content_hash: ContentHash = field(default_factory=lambda: ContentHash(""))
    title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    importance: float = 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Initialize derived values and validate invariants."""
        if self.content_hash.value == "":
            object.__setattr__(
                self, "content_hash", ContentHash.from_content(self.content)
            )

        # Validate importance is in valid range
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError(
                f"Importance must be between 0.0 and 1.0, got: {self.importance}"
            )

        # Validate metadata doesn't contain reserved fields
        reserved_fields = {
            "project_id",
            "language",
            "type",
            "content_hash",
            "created_at",
            "updated_at",
            "importance",
            "title",
        }
        metadata_conflicts = reserved_fields & set(self.metadata.keys())
        if metadata_conflicts:
            raise ValueError(f"Metadata contains reserved fields: {metadata_conflicts}")

    def update_content(self, new_content: str) -> None:
        """Update content and related fields."""
        self.content = new_content
        self.content_hash = ContentHash.from_content(new_content)
        self.updated_at = datetime.utcnow()

    def get_qdrant_payload(self) -> Dict[str, Any]:
        """Convert to Qdrant payload format."""
        return {
            "project_id": str(self.project_id),
            "language": str(self.language),
            "type": self.document_type.value,
            "content_hash": str(self.content_hash),
            "title": self.title,
            "metadata": self.metadata,
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_qdrant_point(
        cls, point_id: str, vector: List[float], payload: Dict[str, Any]
    ) -> "VectorPoint":
        """Create VectorPoint from Qdrant point data."""
        return cls(
            id=UUID(point_id),
            vector=VectorData(vector),
            content=payload.get("content", ""),
            content_hash=ContentHash(payload.get("content_hash", "")),
            project_id=ProjectId(payload["project_id"]),
            language=LanguageCode(payload["language"]),
            document_type=DocumentType(payload["type"]),
            title=payload.get("title"),
            metadata=payload.get("metadata", {}),
            importance=payload.get("importance", 1.0),
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
        )


@dataclass
class SearchResult:
    """Domain entity representing a search result with relevance scoring."""

    point: VectorPoint
    score: float
    rank: int

    def __post_init__(self) -> None:
        """Validate score and rank."""
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Score must be between 0.0 and 1.0, got: {self.score}")

        if self.rank < 1:
            raise ValueError(f"Rank must be >= 1, got: {self.rank}")

    @property
    def is_relevant(self) -> bool:
        """Check if result is relevant based on score threshold."""
        return self.score >= 0.5  # Configurable threshold

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": str(self.point.id),
            "title": self.point.title,
            "content": self.point.content[:200] + "..."
            if len(self.point.content) > 200
            else self.point.content,
            "score": self.score,
            "rank": self.rank,
            "metadata": self.point.metadata,
            "document_type": self.point.document_type.value,
            "created_at": self.point.created_at.isoformat(),
        }


@dataclass
class CollectionHealth:
    """Domain entity representing collection health status."""

    collection_name: str
    status: HealthStatus
    vector_count: int
    indexed_fields: List[str]
    config_status: Dict[str, bool]
    errors: List[str] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        """Check if collection is healthy."""
        return self.status == HealthStatus.HEALTHY and not self.errors

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "collection_name": self.collection_name,
            "status": self.status.value,
            "vector_count": self.vector_count,
            "indexed_fields": self.indexed_fields,
            "config_status": self.config_status,
            "errors": self.errors,
        }
