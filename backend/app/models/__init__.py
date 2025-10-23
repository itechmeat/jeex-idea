"""
JEEX Idea Database Models

SQLAlchemy models implementing the PostgreSQL schema with project isolation.
All models enforce project_id filtering and proper relationships.
"""

from sqlalchemy import (
    UUID,
    String,
    Text,
    Integer,
    Float,
    Boolean,
    JSON,
    DateTime,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from typing import Optional, Dict, Any
import uuid


class Base(DeclarativeBase):
    """Canonical Base class for all database models."""

    pass


class TimestampMixin:
    """Mixin for timestamp fields."""

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Mixin for soft delete functionality."""

    deleted_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class User(Base, TimestampMixin):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),  # PostgreSQL 18+ UUID v7
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_data: Mapped[Dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    last_login_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="created_by_user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"


class Project(Base, TimestampMixin, SoftDeleteMixin):
    """Project model with language and status tracking."""

    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),  # PostgreSQL 18+ UUID v7
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    current_step: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    meta_data: Mapped[Dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )

    # Foreign keys
    created_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Relationships
    created_by_user: Mapped["User"] = relationship("User", back_populates="projects")
    document_versions: Mapped[list["DocumentVersion"]] = relationship(
        "DocumentVersion", back_populates="project", cascade="all, delete-orphan"
    )
    agent_executions: Mapped[list["AgentExecution"]] = relationship(
        "AgentExecution", back_populates="project", cascade="all, delete-orphan"
    )
    exports: Mapped[list["Export"]] = relationship(
        "Export", back_populates="project", cascade="all, delete-orphan"
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "current_step BETWEEN 1 AND 4", name="check_current_step_range"
        ),
        {"schema": "public"},
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name={self.name}, language={self.language})>"


class DocumentVersion(Base, TimestampMixin, SoftDeleteMixin):
    """Document version model with project isolation."""

    __tablename__ = "document_versions"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),  # PostgreSQL 18+ UUID v7
    )
    project_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta_data: Mapped[Dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    readability_score: Mapped[Optional[float]] = mapped_column(Float)
    grammar_score: Mapped[Optional[float]] = mapped_column(Float)

    # Foreign keys
    created_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project", back_populates="document_versions"
    )
    created_by_user: Mapped["User"] = relationship("User")

    # Table constraints
    __table_args__ = ({"schema": "public"},)

    def __repr__(self) -> str:
        return f"<DocumentVersion(id={self.id}, project_id={self.project_id}, type={self.document_type}, version={self.version})>"


class AgentExecution(Base, TimestampMixin):
    """Agent execution tracking model."""

    __tablename__ = "agent_executions"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),  # PostgreSQL 18+ UUID v7
    )
    project_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        server_default=func.gen_random_uuid(),  # PostgreSQL 18+ UUID v7
    )
    input_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    output_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project", back_populates="agent_executions"
    )

    def __repr__(self) -> str:
        return f"<AgentExecution(id={self.id}, project_id={self.project_id}, agent={self.agent_type}, status={self.status})>"


class Export(Base, TimestampMixin):
    """Export tracking model."""

    __tablename__ = "exports"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),  # PostgreSQL 18+ UUID v7
    )
    project_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    manifest: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Foreign keys
    created_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="exports")

    def __repr__(self) -> str:
        return f"<Export(id={self.id}, project_id={self.project_id}, status={self.status})>"
