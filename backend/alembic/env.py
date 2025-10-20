"""
Alembic environment configuration for JEEX Idea.

This module configures the Alembic migration environment with sync support
and proper model imports for autogeneration.
"""

from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy import create_engine
from alembic import context
import os
import sys

# Add the parent directory to the path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db import Base
from app.models import *  # Import all models

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Load environment variables from .env file
from dotenv import load_dotenv, find_dotenv

# Load closest .env (repo root or backend/)
load_dotenv(
    find_dotenv() or os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
)

# Build database URL from environment variables (supports ${VAR} pattern that ConfigParser doesn't)
# Priority: DATABASE_URL env var > constructed from individual vars > alembic.ini placeholder
database_url = os.getenv("DATABASE_URL")

if not database_url:
    # Construct from individual environment variables
    pg_user = os.getenv("POSTGRES_USER", "jeex_user")
    pg_password = os.getenv("POSTGRES_PASSWORD", "")
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = os.getenv("POSTGRES_PORT", "5220")
    pg_db = os.getenv("POSTGRES_DB", "jeex_idea")

    if pg_password:
        database_url = (
            f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
        )
    else:
        raise ValueError(
            "DATABASE_URL or POSTGRES_PASSWORD environment variable is required but not set"
        )

# Replace asyncpg driver with psycopg2 for migrations
database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

# Override sqlalchemy.url in config with the dynamically constructed URL
config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    # Ensure environment variables are expanded in offline mode too
    if url and "${POSTGRES_PASSWORD}" in url:
        pw = os.getenv("POSTGRES_PASSWORD", "")
        if pw:
            url = url.replace("${POSTGRES_PASSWORD}", pw)
        else:
            raise ValueError(
                "POSTGRES_PASSWORD environment variable is required but not set"
            )

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
        # Include object names in migrations for better readability
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    try:
        # Validate inputs
        configuration = config.get_section(config.config_ini_section)
        if not configuration:
            raise ValueError("Alembic configuration section not found")

        if not target_metadata:
            raise ValueError("Target metadata is required for migrations")

        database_url = configuration.get("sqlalchemy.url")
        if not database_url:
            raise ValueError("Database URL not found in configuration")

        connectable = create_engine(
            database_url,
            poolclass=pool.NullPool,
        )

        # Validate connection
        if not connectable:
            raise RuntimeError("Failed to create database engine")

        with connectable.connect() as connection:
            # Validate connection
            if not connection:
                raise RuntimeError("Failed to establish database connection")
            do_run_migrations(connection)

        connectable.dispose()
    except Exception as e:
        # Convert low-level errors to descriptive exceptions
        raise RuntimeError(f"Migration failed: {str(e)}") from e


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
