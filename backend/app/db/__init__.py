"""
JEEX Idea Database Configuration

Database setup and connection management for PostgreSQL 18 with async support.
Implements project isolation patterns and connection pooling.

This module provides backward-compatible API by delegating to the optimized
DatabaseManager in core.database.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, Dict, Any
from uuid import UUID
import logging

from ..core.database import (
    database_manager,
    get_database_session as _core_get_session,
    get_database_health as _core_get_health,
    get_database_metrics as _core_get_metrics,
)

# Re-export the canonical Base from models to maintain backward compatibility
from ..models import Base

logger = logging.getLogger(__name__)


async def init_database(project_id: UUID) -> None:
    """
    Initialize database connection and create tables.

    Args:
        project_id: Required project ID for database initialization

    Delegates to DatabaseManager.initialize() for optimized connection management
    with circuit breaker, retry logic, and performance monitoring.
    """
    try:
        await database_manager.initialize(project_id)
        logger.info("Database initialized successfully for project: %s", project_id)
    except Exception as e:
        logger.exception("Failed to initialize database for project %s", project_id)
        raise


async def get_database_session(project_id: UUID) -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session with proper error handling and project isolation.

    Args:
        project_id: Required project ID for project-scoped sessions

    Yields:
        AsyncSession: Database session with transaction management
    """
    # Validate project_id is a valid UUID
    if not project_id:
        raise ValueError("project_id is required and cannot be None")

    try:
        async for session in _core_get_session(project_id):
            yield session
    except Exception as e:
        logger.exception("Failed to get database session for project %s", project_id)
        raise


async def get_database_health(project_id: UUID) -> Dict[str, Any]:
    """
    Get detailed database health information.

    Args:
        project_id: Required project ID for project-scoped health check

    Returns:
        Dict containing comprehensive health status and metrics
    """
    # Validate project_id is present and valid
    if not project_id:
        raise ValueError("project_id is required and cannot be None")

    try:
        return await _core_get_health(project_id)
    except Exception as e:
        logger.exception("Failed to get database health for project %s", project_id)
        raise


async def get_database_metrics() -> Dict[str, Any]:
    """
    Get database performance metrics.

    Returns:
        Dict containing detailed pool metrics and circuit breaker status
    """
    try:
        return await _core_get_metrics()
    except Exception as e:
        logger.exception("Failed to get database metrics")
        raise


async def close_database() -> None:
    """Close database connections and cleanup resources."""
    try:
        await database_manager.close()
        logger.info("Database connections closed")
    except Exception as e:
        logger.exception("Failed to close database connections")
        raise
