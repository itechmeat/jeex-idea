-- JEEX Idea PostgreSQL Database Initialization
-- This script runs on container startup to create the database schema

-- Set timezone to UTC for consistent timestamp handling
SET timezone = 'UTC';

-- Create required extensions for UUID v7 support and performance
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create indexes for common query patterns
-- These indexes support the application's access patterns and will be expanded during feature development

-- Application-specific settings
-- Note: PostgreSQL performance settings configured via environment variables
-- in docker-compose.yml for better container compatibility

-- Note: PostgreSQL performance settings configured via command line flags
-- in docker-compose.yml for better container compatibility

-- Create application-specific configuration table for runtime settings
-- This allows the application to adjust configuration without ALTER SYSTEM
CREATE TABLE IF NOT EXISTS app_config (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Insert default configuration values
INSERT INTO app_config (key, value, description) VALUES
    ('log_checkpoints', 'on', 'Enable checkpoint logging'),
    ('log_connections', 'on', 'Enable connection logging'),
    ('log_disconnections', 'on', 'Enable disconnection logging'),
    ('log_lock_waits', 'on', 'Enable lock wait logging')
ON CONFLICT (key) DO NOTHING;

-- Grant necessary permissions to the application user
-- Note: In production, additional security hardening should be applied
GRANT CREATE ON DATABASE jeex_idea TO jeex_user;
GRANT ALL ON SCHEMA public TO jeex_user;

-- Initialize basic schema tables (will be expanded with Alembic migrations)
-- This provides the minimal schema needed for the application to start

-- Projects table (will be migrated with Alembic in production)
-- Commented out for now - migrations will handle schema creation
/*
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by UUID,
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Create indexes for projects table
CREATE INDEX IF NOT EXISTS idx_projects_language ON projects(language);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_created_by ON projects(created_by);
CREATE INDEX IF NOT EXISTS idx_projects_created_at ON projects(created_at);
CREATE INDEX IF NOT EXISTS idx_projects_metadata_gin ON projects USING gin(metadata);
*/

-- Log successful initialization
\echo 'JEEX Idea PostgreSQL database initialized successfully'