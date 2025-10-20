"""
JEEX Idea Application Configuration

Configuration management with environment variable support.
Implements secure defaults and validation for all settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional, List
import os
from functools import lru_cache
from dotenv import load_dotenv
from urllib.parse import quote_plus

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings with validation and secure defaults."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    # Environment settings
    ENVIRONMENT: str = Field(
        default="development", description="Application environment"
    )
    PROJECT_ID: str = Field(
        default="jeex-idea", description="Project identifier for isolation"
    )

    # Database configuration - Phase 3 Optimized
    DATABASE_URL: str = Field(
        ...,
        description="Database connection URL with asyncpg driver",
    )
    DATABASE_POOL_SIZE: int = Field(
        default=20, ge=1, le=100, description="Database connection pool size (REQ-004)"
    )
    DATABASE_MAX_OVERFLOW: int = Field(
        default=30, ge=0, le=100, description="Maximum overflow connections (REQ-004)"
    )
    DATABASE_POOL_TIMEOUT: int = Field(
        default=30, ge=1, le=300, description="Connection pool timeout in seconds"
    )
    DATABASE_POOL_RECYCLE: int = Field(
        default=3600, ge=300, le=86400, description="Connection recycle time in seconds"
    )

    # Vector database configuration
    QDRANT_URL: str = Field(
        default="http://localhost:6333", description="Qdrant vector database URL"
    )
    QDRANT_COLLECTION: str = Field(
        default="jeex_memory", description="Qdrant collection name"
    )
    QDRANT_TIMEOUT: int = Field(
        default=30, ge=1, le=300, description="Qdrant request timeout"
    )

    # Redis configuration
    REDIS_URL: str = Field(
        default="redis://localhost:6379", description="Redis connection URL"
    )
    REDIS_MAX_CONNECTIONS: int = Field(
        default=10, ge=1, le=50, description="Redis connection pool size"
    )

    # API configuration
    API_HOST: str = Field(default="0.0.0.0", description="API server host")
    API_PORT: int = Field(default=8000, ge=1, le=65535, description="API server port")
    API_RELOAD: bool = Field(
        default=False, description="Enable auto-reload in development"
    )
    API_WORKERS: int = Field(
        default=1, ge=1, le=10, description="Number of worker processes"
    )

    # Security configuration
    SECRET_KEY: str = Field(
        ...,
        min_length=32,
        description="JWT secret key for authentication",
    )
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5200",
        description="CORS allowed origins (comma-separated)",
    )
    CORS_CREDENTIALS: bool = Field(default=True, description="Allow CORS credentials")

    # OpenTelemetry configuration
    OTEL_EXPORTER_OTLP_ENDPOINT: str = Field(
        default="http://localhost:4317", description="OpenTelemetry OTLP endpoint"
    )
    OTEL_SERVICE_NAME: str = Field(
        default="jeex-idea-api", description="OpenTelemetry service name"
    )
    OTEL_SERVICE_VERSION: str = Field(
        default="0.1.0", description="OpenTelemetry service version"
    )
    OTEL_RESOURCE_ATTRIBUTES: str = Field(
        default="service.name=jeex-idea-api,service.version=0.1.0,environment=development",
        description="OpenTelemetry resource attributes",
    )

    # Phase 3: Performance and Monitoring Configuration
    # Performance monitoring
    SLOW_QUERY_THRESHOLD_MS: int = Field(
        default=1000,
        ge=100,
        le=10000,
        description="Slow query threshold in milliseconds",
    )
    QUERY_TIMEOUT_SECONDS: int = Field(
        default=30, ge=5, le=300, description="Query timeout in seconds"
    )
    PERFORMANCE_MONITORING_ENABLED: bool = Field(
        default=True, description="Enable performance monitoring"
    )

    # Circuit breaker settings
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
        default=5, ge=1, le=20, description="Circuit breaker failure threshold"
    )
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Circuit breaker recovery timeout in seconds",
    )

    # Backup configuration
    BACKUP_ENABLED: bool = Field(default=True, description="Enable automated backups")
    BACKUP_RETENTION_DAYS: int = Field(
        default=30, ge=1, le=365, description="Backup retention period in days"
    )
    BACKUP_COMPRESSION: str = Field(
        default="gzip", description="Backup compression type"
    )
    BACKUP_ENCRYPTION_ENABLED: bool = Field(
        default=True, description="Enable backup encryption"
    )
    BACKUP_SCHEDULE_FULL: str = Field(
        default="0 2 * * *", description="Full backup schedule (cron)"
    )
    BACKUP_SCHEDULE_INCREMENTAL: str = Field(
        default="0 6 * * *", description="Incremental backup schedule"
    )

    # Maintenance configuration
    AUTO_VACUUM_ENABLED: bool = Field(
        default=True, description="Enable automatic VACUUM"
    )
    AUTO_ANALYZE_ENABLED: bool = Field(
        default=True, description="Enable automatic ANALYZE"
    )
    MAINTENANCE_WINDOW_START: str = Field(
        default="02:00", description="Maintenance window start time"
    )
    MAINTENANCE_WINDOW_END: str = Field(
        default="06:00", description="Maintenance window end time"
    )
    VACUUM_THRESHOLD_PERCENT: float = Field(
        default=20.0, ge=5.0, le=50.0, description="VACUUM threshold percentage"
    )
    ANALYZE_THRESHOLD_PERCENT: float = Field(
        default=10.0, ge=1.0, le=25.0, description="ANALYZE threshold percentage"
    )

    # WAL archiving
    WAL_ARCHIVING_ENABLED: bool = Field(
        default=True, description="Enable WAL archiving"
    )
    WAL_RETENTION_DAYS: int = Field(
        default=7, ge=1, le=30, description="WAL retention period in days"
    )
    WAL_ARCHIVE_DIRECTORY: str = Field(
        default="/var/lib/postgresql/wal_archive",
        description="WAL archive directory - must exist and be writable",
    )

    @field_validator("WAL_ARCHIVE_DIRECTORY")
    @classmethod
    def validate_wal_archive_directory(cls, v: str) -> str:
        """Validate WAL archive directory exists and is writable.

        Note: Only validates in production. In development, directory may not exist yet.
        """
        import os
        from pathlib import Path

        # Skip validation in test/development environments
        env = os.getenv("ENVIRONMENT", "development")
        if env in ("test", "development"):
            return v

        # In production, validate directory exists and is writable
        path = Path(v)
        if not path.exists():
            raise ValueError(
                f"WAL archive directory does not exist: {v}. "
                "Create it or set WAL_ARCHIVE_DIRECTORY to an existing path."
            )
        if not path.is_dir():
            raise ValueError(f"WAL archive path is not a directory: {v}")
        if not os.access(path, os.W_OK):
            raise ValueError(f"WAL archive directory is not writable: {v}")

        return v

    # Development and debugging
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v):
        """Validate database URL format."""
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection URL")
        return v

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v):
        """Validate environment value."""
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of: {allowed}")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of: {allowed}")
        return v.upper()

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENVIRONMENT == "production"

    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as list."""
        if isinstance(self.CORS_ORIGINS, str):
            return [
                origin.strip()
                for origin in self.CORS_ORIGINS.split(",")
                if origin.strip()
            ]
        return self.CORS_ORIGINS

    # Alias properties for backward compatibility with snake_case usage
    @property
    def environment(self) -> str:
        """Alias for ENVIRONMENT."""
        return self.ENVIRONMENT

    @property
    def debug(self) -> bool:
        """Alias for DEBUG."""
        return self.DEBUG

    @property
    def database_url(self) -> str:
        """Alias for DATABASE_URL."""
        return self.DATABASE_URL

    @property
    def database_pool_size(self) -> int:
        """Alias for DATABASE_POOL_SIZE."""
        return self.DATABASE_POOL_SIZE

    @property
    def database_max_overflow(self) -> int:
        """Alias for DATABASE_MAX_OVERFLOW."""
        return self.DATABASE_MAX_OVERFLOW

    @property
    def slow_query_threshold_ms(self) -> int:
        """Alias for SLOW_QUERY_THRESHOLD_MS."""
        return self.SLOW_QUERY_THRESHOLD_MS

    @property
    def query_timeout_seconds(self) -> int:
        """Alias for QUERY_TIMEOUT_SECONDS."""
        return self.QUERY_TIMEOUT_SECONDS

    @property
    def performance_monitoring_enabled(self) -> bool:
        """Alias for PERFORMANCE_MONITORING_ENABLED."""
        return self.PERFORMANCE_MONITORING_ENABLED

    @property
    def backup_enabled(self) -> bool:
        """Alias for BACKUP_ENABLED."""
        return self.BACKUP_ENABLED

    @property
    def backup_retention_days(self) -> int:
        """Alias for BACKUP_RETENTION_DAYS."""
        return self.BACKUP_RETENTION_DAYS

    @property
    def backup_compression(self) -> str:
        """Alias for BACKUP_COMPRESSION."""
        return self.BACKUP_COMPRESSION

    @property
    def backup_encryption_enabled(self) -> bool:
        """Alias for BACKUP_ENCRYPTION_ENABLED."""
        return self.BACKUP_ENCRYPTION_ENABLED

    @property
    def auto_vacuum_enabled(self) -> bool:
        """Alias for AUTO_VACUUM_ENABLED."""
        return self.AUTO_VACUUM_ENABLED

    @property
    def auto_analyze_enabled(self) -> bool:
        """Alias for AUTO_ANALYZE_ENABLED."""
        return self.AUTO_ANALYZE_ENABLED

    @property
    def maintenance_window_start(self) -> str:
        """Alias for MAINTENANCE_WINDOW_START."""
        return self.MAINTENANCE_WINDOW_START

    @property
    def maintenance_window_end(self) -> str:
        """Alias for MAINTENANCE_WINDOW_END."""
        return self.MAINTENANCE_WINDOW_END

    @property
    def vacuum_threshold_percent(self) -> float:
        """Alias for VACUUM_THRESHOLD_PERCENT."""
        return self.VACUUM_THRESHOLD_PERCENT

    @property
    def analyze_threshold_percent(self) -> float:
        """Alias for ANALYZE_THRESHOLD_PERCENT."""
        return self.ANALYZE_THRESHOLD_PERCENT

    @property
    def wal_archiving_enabled(self) -> bool:
        """Alias for WAL_ARCHIVING_ENABLED."""
        return self.WAL_ARCHIVING_ENABLED

    @property
    def wal_retention_days(self) -> int:
        """Alias for WAL_RETENTION_DAYS."""
        return self.WAL_RETENTION_DAYS

    @property
    def wal_archive_directory(self) -> str:
        """Alias for WAL_ARCHIVE_DIRECTORY."""
        return self.WAL_ARCHIVE_DIRECTORY

    @property
    def cors_credentials(self) -> bool:
        """Alias for CORS_CREDENTIALS."""
        return self.CORS_CREDENTIALS

    @property
    def otel_exporter_otlp_endpoint(self) -> str:
        """Alias for OTEL_EXPORTER_OTLP_ENDPOINT."""
        return self.OTEL_EXPORTER_OTLP_ENDPOINT


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Create global settings instance
settings = get_settings()
