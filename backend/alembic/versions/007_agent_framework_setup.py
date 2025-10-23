"""Agent framework setup: ensure agent_executions duration_ms and indexes

Revision ID: 007_agent_framework_setup
Revises: db9e7a2f528c
Create Date: 2025-10-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import logging


# revision identifiers, used by Alembic.
revision = "007_agent_framework_setup"
down_revision = "db9e7a2f528c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # Add duration_ms column if not exists
    try:
        column_names = [c["name"] for c in inspector.get_columns("agent_executions")]
        if "duration_ms" not in column_names:
            op.add_column(
                "agent_executions",
                sa.Column("duration_ms", sa.Integer(), nullable=True),
            )
    except Exception:
        logging.exception("Failed to ensure duration_ms column during upgrade")
        raise

    # Helper to create index if missing
    def _ensure_index(index_name: str, columns: list[str]) -> None:
        try:
            existing = [i["name"] for i in inspector.get_indexes("agent_executions")]
            if index_name not in existing:
                op.create_index(index_name, "agent_executions", columns)
        except Exception:
            logging.exception("Failed to ensure index %s during upgrade", index_name)
            raise

    _ensure_index("idx_agent_executions_project", ["project_id", "started_at"])
    _ensure_index("idx_agent_executions_correlation", ["correlation_id"])
    _ensure_index("idx_agent_executions_status", ["status", "started_at"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # Helper to drop index if exists
    def _drop_index_if_exists(index_name: str) -> None:
        try:
            existing = [i["name"] for i in inspector.get_indexes("agent_executions")]
            if index_name in existing:
                op.drop_index(index_name, table_name="agent_executions")
        except Exception:
            logging.exception("Failed to drop index %s during downgrade", index_name)
            raise

    _drop_index_if_exists("idx_agent_executions_status")
    _drop_index_if_exists("idx_agent_executions_correlation")
    _drop_index_if_exists("idx_agent_executions_project")

    try:
        column_names = [c["name"] for c in inspector.get_columns("agent_executions")]
        if "duration_ms" in column_names:
            op.drop_column("agent_executions", "duration_ms")
    except Exception:
        logging.exception("Failed to drop column duration_ms during downgrade")
        raise
