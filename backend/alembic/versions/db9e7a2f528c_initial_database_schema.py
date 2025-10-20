"""initial_database_schema

Revision ID: db9e7a2f528c
Revises:
Create Date: 2025-10-19 00:04:30.686141

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "db9e7a2f528c"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create pgcrypto extension for UUID generation
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    # Create users table
    op.create_table(
        "users",
        sa.Column(
            "id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("profile_data", postgresql.JSONB(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # Create projects table
    op.create_table(
        "projects",
        sa.Column(
            "id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column(
            "current_step", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "language",
            sa.String(length=10),
            nullable=False,
            server_default=sa.text("'en'"),
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "current_step BETWEEN 1 AND 4", name="check_current_step_range"
        ),
    )
    op.create_index(
        op.f("ix_projects_created_at"), "projects", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_projects_created_by"), "projects", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_projects_user_status"),
        "projects",
        ["created_by", "status", "updated_at"],
        unique=False,
    )

    # Create document_versions table
    op.create_table(
        "document_versions",
        sa.Column(
            "id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("readability_score", sa.Float(), nullable=True),
        sa.Column("grammar_score", sa.Float(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_versions_project_id"),
        "document_versions",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_versions_created_by"),
        "document_versions",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_documents_project_type"),
        "document_versions",
        ["project_id", "document_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_documents_project_version"),
        "document_versions",
        ["project_id", "version"],
        unique=False,
    )
    op.create_index(
        op.f("ix_documents_created"), "document_versions", ["created_at"], unique=False
    )
    op.create_index(
        "idx_documents_unique_version",
        "document_versions",
        ["project_id", "document_type", "version"],
        unique=True,
    )

    # Create agent_executions table
    op.create_table(
        "agent_executions",
        sa.Column(
            "id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("agent_type", sa.String(length=50), nullable=False),
        sa.Column(
            "correlation_id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("input_data", postgresql.JSONB(), nullable=True),
        sa.Column("output_data", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_executions_project_id"),
        "agent_executions",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_executions_correlation_id"),
        "agent_executions",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_executions_project"),
        "agent_executions",
        ["project_id", "started_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_executions_project_status"),
        "agent_executions",
        ["project_id", "status", "started_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_executions_status"),
        "agent_executions",
        ["status", "started_at"],
        unique=False,
    )

    # Create exports table
    op.create_table(
        "exports",
        sa.Column(
            "id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "download_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_exports_project_id"), "exports", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_exports_created_by"), "exports", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_exports_expires"),
        "exports",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("status = 'completed'"),
    )

    # Create JSONB indexes for metadata searches
    op.create_index(
        "idx_users_metadata",
        "users",
        ["profile_data"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_projects_metadata",
        "projects",
        ["metadata"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_documents_metadata",
        "document_versions",
        ["metadata"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_exports_metadata",
        "exports",
        ["manifest"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_agent_input",
        "agent_executions",
        ["input_data"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_agent_output",
        "agent_executions",
        ["output_data"],
        unique=False,
        postgresql_using="gin",
    )

    # Create trigger function for updated_at timestamp
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    # Create triggers for all tables with updated_at
    op.execute("""
        CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_document_versions_updated_at BEFORE UPDATE ON document_versions
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_agent_executions_updated_at BEFORE UPDATE ON agent_executions
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_exports_updated_at BEFORE UPDATE ON exports
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    # Drop pgcrypto extension
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto";')

    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS update_users_updated_at ON users")
    op.execute("DROP TRIGGER IF EXISTS update_projects_updated_at ON projects")
    op.execute(
        "DROP TRIGGER IF EXISTS update_document_versions_updated_at ON document_versions"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS update_agent_executions_updated_at ON agent_executions"
    )
    op.execute("DROP TRIGGER IF EXISTS update_exports_updated_at ON exports")

    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # Drop JSONB indexes
    op.drop_index(op.f("idx_agent_output"), table_name="agent_executions")
    op.drop_index(op.f("idx_agent_input"), table_name="agent_executions")
    op.drop_index(
        op.f("ix_agent_executions_correlation_id"), table_name="agent_executions"
    )
    op.drop_index(op.f("idx_exports_metadata"), table_name="exports")
    op.drop_index(op.f("idx_documents_metadata"), table_name="document_versions")
    op.drop_index(op.f("idx_projects_metadata"), table_name="projects")
    op.drop_index(op.f("idx_users_metadata"), table_name="users")

    # Drop tables
    op.drop_table("exports")
    op.drop_table("agent_executions")
    op.drop_table("document_versions")
    op.drop_table("projects")
    op.drop_table("users")
