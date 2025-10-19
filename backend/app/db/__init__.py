"""
JEEX Idea Database Configuration

Database setup and connection management for PostgreSQL 18 with async support.
Implements project isolation patterns and connection pooling.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import logging
from typing import AsyncGenerator

from ..core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# Global engine and session factory
engine = None
AsyncSessionLocal = None


async def init_database() -> None:
    """Initialize database connection and create tables."""
    global engine, AsyncSessionLocal

    settings = get_settings()

    # Create async engine with optimized settings
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        pool_recycle=3600,  # Recycle connections after 1 hour
        connect_args={
            "command_timeout": 60,
            "server_settings": {
                "application_name": "jeex_idea_api",
                "jit": "off",  # Disable JIT for better performance in OLTP workloads
            },
        },
    )

    # Create session factory
    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Test database connection
    await test_database_connection()

    logger.info("Database initialized successfully")


async def test_database_connection() -> None:
    """Test database connection and health."""
    try:
        async with engine.begin() as conn:
            # Test basic connectivity
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

            # Test PostgreSQL version
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            logger.info(f"Connected to PostgreSQL: {version}")

            # Test health check function
            result = await conn.execute(text("SELECT simple_health_check()"))
            health = result.scalar()
            logger.info(f"Database health check: {health}")

    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        raise


async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session with proper error handling."""
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def get_database_health() -> dict:
    """Get detailed database health information."""
    if engine is None:
        raise RuntimeError("Database not initialized")

    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT detailed_health_check()"))
            health_data = result.scalar()
            return health_data
    except Exception as e:
        logger.error(f"Failed to get database health: {e}")
        return {"status": "error", "error": str(e), "timestamp": None}


async def get_database_metrics() -> dict:
    """Get database performance metrics."""
    if engine is None:
        raise RuntimeError("Database not initialized")

    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT get_database_metrics()"))
            metrics = result.scalar()
            return metrics
    except Exception as e:
        logger.error(f"Failed to get database metrics: {e}")
        return {"status": "error", "error": str(e), "timestamp": None}


async def close_database() -> None:
    """Close database connections."""
    global engine, AsyncSessionLocal

    if engine:
        await engine.dispose()
        engine = None
        AsyncSessionLocal = None
        logger.info("Database connections closed")
