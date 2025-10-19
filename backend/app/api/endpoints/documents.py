"""
Documents API endpoints - Phase 4 Integration

Complete CRUD operations for document versions with:
- Database integration
- Project isolation enforcement
- Transaction management
- Performance monitoring
- Quality scoring
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import time
import structlog

from ...db import get_database_session
from ...models import DocumentVersion, Project, User
from ...core.config import get_settings
from ...core.monitoring import performance_monitor

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()


# Pydantic schemas for API
class DocumentBase(BaseModel):
    """Base document schema with validation."""

    document_type: str = Field(
        ..., min_length=1, max_length=50, description="Document type"
    )
    content: str = Field(..., min_length=1, description="Document content")
    meta_data: Dict[str, Any] = Field(
        default_factory=dict, description="Document metadata"
    )
    readability_score: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Readability score"
    )
    grammar_score: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Grammar score"
    )


class DocumentCreate(DocumentBase):
    """Schema for creating documents."""

    project_id: UUID = Field(..., description="Project ID")
    created_by: UUID = Field(..., description="User ID creating the document")
    version: int = Field(1, ge=1, description="Document version")


class DocumentUpdate(BaseModel):
    """Schema for updating documents."""

    content: Optional[str] = Field(None, min_length=1)
    meta_data: Optional[Dict[str, Any]] = None
    readability_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    grammar_score: Optional[float] = Field(None, ge=0.0, le=100.0)


class DocumentRead(DocumentBase):
    """Schema for reading documents."""

    id: UUID
    project_id: UUID
    created_by: UUID
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentList(BaseModel):
    """Schema for document lists with pagination."""

    documents: List[DocumentRead]
    total: int
    page: int
    per_page: int
    total_pages: int


# CRUD Operations
class DocumentRepository:
    """Repository for document CRUD operations with project isolation."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, doc_data: DocumentCreate, user_id: UUID) -> DocumentVersion:
        """Create a new document version with project isolation."""
        start_time = time.time()

        try:
            # Validate project access
            project_result = await self.session.execute(
                select(Project).where(
                    Project.id == doc_data.project_id,
                    Project.created_by == user_id,
                    Project.is_deleted == False,
                )
            )
            project = project_result.scalar_one_or_none()
            if not project:
                raise HTTPException(
                    status_code=404, detail="Project not found or access denied"
                )

            # Get next version if not specified
            if doc_data.version == 1:
                last_version_result = await self.session.execute(
                    select(func.coalesce(func.max(DocumentVersion.version), 0))
                    .where(DocumentVersion.project_id == doc_data.project_id)
                    .where(DocumentVersion.document_type == doc_data.document_type)
                )
                next_version = (last_version_result.scalar() or 0) + 1
            else:
                next_version = doc_data.version

            # Create document
            document = DocumentVersion(
                project_id=doc_data.project_id,
                document_type=doc_data.document_type,
                version=next_version,
                content=doc_data.content,
                meta_data=doc_data.meta_data,
                readability_score=doc_data.readability_score,
                grammar_score=doc_data.grammar_score,
                created_by=doc_data.created_by,
            )

            self.session.add(document)
            await self.session.flush()  # Get the ID without committing

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "document_create", duration, True
            )

            logger.info(
                "Document created",
                document_id=str(document.id),
                project_id=str(doc_data.project_id),
                version=next_version,
                type=doc_data.document_type,
                duration_ms=duration,
            )

            return document

        except IntegrityError as e:
            await self.session.rollback()
            raise HTTPException(status_code=400, detail="Invalid document data")
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error("Database error creating document", error=str(e))
            raise HTTPException(status_code=500, detail="Database error")

    async def get_by_id(
        self, document_id: UUID, project_id: UUID, user_id: UUID
    ) -> Optional[DocumentVersion]:
        """Get document by ID with project and user access validation."""
        start_time = time.time()

        try:
            # Validate project access first
            project_result = await self.session.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.created_by == user_id,
                    Project.is_deleted == False,
                )
            )
            project = project_result.scalar_one_or_none()
            if not project:
                return None

            # Get document
            result = await self.session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.id == document_id,
                    DocumentVersion.project_id == project_id,
                )
            )
            document = result.scalar_one_or_none()

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "document_get_by_id", duration, document is not None
            )

            return document

        except SQLAlchemyError as e:
            logger.error("Database error getting document", error=str(e))
            raise HTTPException(status_code=500, detail="Database error")

    async def get_project_documents(
        self,
        project_id: UUID,
        user_id: UUID,
        page: int = 1,
        per_page: int = 20,
        document_type: Optional[str] = None,
    ) -> tuple[List[DocumentVersion], int]:
        """Get project documents with pagination and filtering."""
        start_time = time.time()

        try:
            # Validate project access
            project_result = await self.session.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.created_by == user_id,
                    Project.is_deleted == False,
                )
            )
            project = project_result.scalar_one_or_none()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            # Build query
            query = select(DocumentVersion).where(
                DocumentVersion.project_id == project_id
            )

            if document_type:
                query = query.where(DocumentVersion.document_type == document_type)

            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.session.execute(count_query)
            total = total_result.scalar()

            # Apply pagination
            offset = (page - 1) * per_page
            query = (
                query.order_by(
                    DocumentVersion.document_type, DocumentVersion.version.desc()
                )
                .offset(offset)
                .limit(per_page)
            )

            result = await self.session.execute(query)
            documents = result.scalars().all()

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "document_list", duration, True
            )

            return list(documents), total

        except SQLAlchemyError as e:
            logger.error("Database error listing documents", error=str(e))
            raise HTTPException(status_code=500, detail="Database error")

    async def get_latest_version(
        self, project_id: UUID, document_type: str, user_id: UUID
    ) -> Optional[DocumentVersion]:
        """Get latest version of a document type."""
        start_time = time.time()

        try:
            # Validate project access
            project_result = await self.session.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.created_by == user_id,
                    Project.is_deleted == False,
                )
            )
            project = project_result.scalar_one_or_none()
            if not project:
                return None

            # Get latest version
            result = await self.session.execute(
                select(DocumentVersion)
                .where(
                    DocumentVersion.project_id == project_id,
                    DocumentVersion.document_type == document_type,
                )
                .order_by(DocumentVersion.version.desc())
                .limit(1)
            )
            document = result.scalar_one_or_none()

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "document_get_latest", duration, document is not None
            )

            return document

        except SQLAlchemyError as e:
            logger.error("Database error getting latest document", error=str(e))
            raise HTTPException(status_code=500, detail="Database error")

    async def update(
        self,
        document_id: UUID,
        project_id: UUID,
        user_id: UUID,
        update_data: DocumentUpdate,
    ) -> Optional[DocumentVersion]:
        """Update document with access validation."""
        start_time = time.time()

        try:
            # Check if document exists and user has access
            document = await self.get_by_id(document_id, project_id, user_id)
            if not document:
                return None

            # Update fields
            update_values = {}
            if update_data.content is not None:
                update_values["content"] = update_data.content
            if update_data.meta_data is not None:
                update_values["meta_data"] = update_data.meta_data
            if update_data.readability_score is not None:
                update_values["readability_score"] = update_data.readability_score
            if update_data.grammar_score is not None:
                update_values["grammar_score"] = update_data.grammar_score

            if not update_values:
                return document  # No changes needed

            # Perform update
            await self.session.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == document_id)
                .values(**update_values)
            )

            await self.session.refresh(document)

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "document_update", duration, True
            )

            logger.info(
                "Document updated",
                document_id=str(document_id),
                project_id=str(project_id),
                updated_fields=list(update_values.keys()),
                duration_ms=duration,
            )

            return document

        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error("Database error updating document", error=str(e))
            raise HTTPException(status_code=500, detail="Database error")

    async def delete(self, document_id: UUID, project_id: UUID, user_id: UUID) -> bool:
        """Delete document with access validation."""
        start_time = time.time()

        try:
            # Check if document exists and user has access
            document = await self.get_by_id(document_id, project_id, user_id)
            if not document:
                return False

            # Delete document
            await self.session.execute(
                delete(DocumentVersion).where(DocumentVersion.id == document_id)
            )

            # Log performance
            duration = (time.time() - start_time) * 1000
            await performance_monitor.log_query_performance(
                "document_delete", duration, True
            )

            logger.info(
                "Document deleted",
                document_id=str(document_id),
                project_id=str(project_id),
                duration_ms=duration,
            )

            return True

        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error("Database error deleting document", error=str(e))
            raise HTTPException(status_code=500, detail="Database error")


# API Endpoints
@router.post(
    "/projects/{project_id}/documents", response_model=DocumentRead, status_code=201
)
async def create_document(
    project_id: UUID,
    doc_data: DocumentCreate,
    user_id: UUID = Query(..., description="User ID for access validation"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Create a new document version.

    Args:
        project_id: Project UUID
        doc_data: Document creation data
        user_id: User ID for access validation
        session: Database session

    Returns:
        Created document data
    """
    # Ensure project_id matches
    doc_data.project_id = project_id

    repo = DocumentRepository(session)
    document = await repo.create(doc_data, user_id)
    return DocumentRead.model_validate(document)


@router.get(
    "/projects/{project_id}/documents/{document_id}", response_model=DocumentRead
)
async def get_document(
    project_id: UUID,
    document_id: UUID,
    user_id: UUID = Query(..., description="User ID for access validation"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Get document by ID.

    Args:
        project_id: Project UUID
        document_id: Document UUID
        user_id: User ID for access validation
        session: Database session

    Returns:
        Document data
    """
    repo = DocumentRepository(session)
    document = await repo.get_by_id(document_id, project_id, user_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentRead.model_validate(document)


@router.get("/projects/{project_id}/documents", response_model=DocumentList)
async def list_documents(
    project_id: UUID,
    user_id: UUID = Query(..., description="User ID for access validation"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    List project documents with pagination.

    Args:
        project_id: Project UUID
        user_id: User ID for access validation
        page: Page number
        per_page: Items per page
        document_type: Optional document type filter
        session: Database session

    Returns:
        Paginated document list
    """
    repo = DocumentRepository(session)
    documents, total = await repo.get_project_documents(
        project_id, user_id, page, per_page, document_type
    )

    total_pages = (total + per_page - 1) // per_page

    return DocumentList(
        documents=[DocumentRead.model_validate(d) for d in documents],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/projects/{project_id}/documents/latest", response_model=DocumentRead)
async def get_latest_document(
    project_id: UUID,
    document_type: str = Query(..., description="Document type"),
    user_id: UUID = Query(..., description="User ID for access validation"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Get latest version of a document type.

    Args:
        project_id: Project UUID
        document_type: Document type
        user_id: User ID for access validation
        session: Database session

    Returns:
        Latest document data
    """
    repo = DocumentRepository(session)
    document = await repo.get_latest_version(project_id, document_type, user_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentRead.model_validate(document)


@router.put(
    "/projects/{project_id}/documents/{document_id}", response_model=DocumentRead
)
async def update_document(
    project_id: UUID,
    document_id: UUID,
    update_data: DocumentUpdate,
    user_id: UUID = Query(..., description="User ID for access validation"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Update document.

    Args:
        project_id: Project UUID
        document_id: Document UUID
        update_data: Update data
        user_id: User ID for access validation
        session: Database session

    Returns:
        Updated document data
    """
    repo = DocumentRepository(session)
    document = await repo.update(document_id, project_id, user_id, update_data)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentRead.model_validate(document)


@router.delete("/projects/{project_id}/documents/{document_id}", status_code=204)
async def delete_document(
    project_id: UUID,
    document_id: UUID,
    user_id: UUID = Query(..., description="User ID for access validation"),
    session: AsyncSession = Depends(get_database_session),
):
    """
    Delete document.

    Args:
        project_id: Project UUID
        document_id: Document UUID
        user_id: User ID for access validation
        session: Database session
    """
    repo = DocumentRepository(session)
    success = await repo.delete(document_id, project_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
