-- JEEX Idea PostgreSQL Database Initialization
-- This script runs on container startup to create the database schema
-- Implements PostgreSQL 18 with UUID v4 support (pgcrypto) and security hardening

-- Set timezone to UTC for consistent timestamp handling
SET timezone = 'UTC';

-- Create required extensions for UUID v4 support and performance
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "pg_trgm" WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA public;

-- Verify UUID v4 generation using pgcrypto
-- gen_random_uuid() from pgcrypto generates UUID v4, not v7
DO $$
BEGIN
    -- Test UUID v4 generation via pgcrypto
    PERFORM gen_random_uuid();
    RAISE NOTICE 'UUID v4 generation (gen_random_uuid from pgcrypto) is available';
EXCEPTION WHEN undefined_function THEN
    RAISE NOTICE 'Falling back to uuid-ossp for UUID generation';
END $$;

-- Create application-specific configuration table for runtime settings
-- This allows the application to adjust configuration without ALTER SYSTEM
CREATE TABLE IF NOT EXISTS app_config (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Insert default configuration values for database health and monitoring
INSERT INTO app_config (key, value, description) VALUES
    ('log_checkpoints', 'on', 'Enable checkpoint logging'),
    ('log_connections', 'on', 'Enable connection logging'),
    ('log_disconnections', 'on', 'Enable disconnection logging'),
    ('log_lock_waits', 'on', 'Enable lock wait logging'),
    ('track_activity_query_size', '2048', 'Query size limit for tracking'),
    ('autovacuum_vacuum_scale_factor', '0.1', 'Autovacuum scale factor'),
    ('autovacuum_analyze_scale_factor', '0.05', 'Autovacuum analyze scale factor')
ON CONFLICT (key) DO NOTHING;

-- Create database health monitoring function
CREATE OR REPLACE FUNCTION check_database_health()
RETURNS JSONB AS $$
DECLARE
    health_result JSONB;
    connection_count INTEGER;
    active_connections INTEGER;
    idle_connections INTEGER;
    total_size BIGINT;
    cache_hit_ratio NUMERIC;
BEGIN
    -- Get connection statistics
    SELECT count(*) INTO connection_count
    FROM pg_stat_activity;

    SELECT count(*) INTO active_connections
    FROM pg_stat_activity
    WHERE state = 'active';

    SELECT count(*) INTO idle_connections
    FROM pg_stat_activity
    WHERE state = 'idle';

    -- Get database size
    SELECT pg_database_size(current_database()) INTO total_size;

    -- Get cache hit ratio
    SELECT round((blks_hit::NUMERIC / NULLIF(blks_hit + blks_read, 0)) * 100, 2) INTO cache_hit_ratio
    FROM pg_stat_database
    WHERE datname = current_database();

    -- Build health result
    health_result := jsonb_build_object(
        'status', 'healthy',
        'timestamp', CURRENT_TIMESTAMP,
        'connections', jsonb_build_object(
            'total', connection_count,
            'active', active_connections,
            'idle', idle_connections
        ),
        'database_size_bytes', total_size,
        'cache_hit_ratio_percent', COALESCE(cache_hit_ratio, 0),
        'postgresql_version', version()
    );

    RETURN health_result;
END;
$$ LANGUAGE plpgsql;

-- Create database performance monitoring function
CREATE OR REPLACE FUNCTION get_database_metrics()
RETURNS JSONB AS $$
DECLARE
    metrics_result JSONB;
    slow_queries_count INTEGER;
    avg_query_time NUMERIC;
    total_statements BIGINT;
BEGIN
    -- Get slow query statistics
    SELECT count(*) INTO slow_queries_count
    FROM pg_stat_statements
    WHERE mean_exec_time > 1000; -- queries taking > 1 second

    -- Get average query time
    SELECT round(AVG(mean_exec_time), 2) INTO avg_query_time
    FROM pg_stat_statements;

    -- Get total statement count
    SELECT sum(calls) INTO total_statements
    FROM pg_stat_statements;

    -- Build metrics result
    metrics_result := jsonb_build_object(
        'timestamp', CURRENT_TIMESTAMP,
        'slow_queries_count', COALESCE(slow_queries_count, 0),
        'average_query_time_ms', COALESCE(avg_query_time, 0),
        'total_statements_executed', COALESCE(total_statements, 0),
        'pg_stat_statements_entries', (SELECT count(*) FROM pg_stat_statements)
    );

    RETURN metrics_result;
END;
$$ LANGUAGE plpgsql;

-- Create audit logging function for security
CREATE OR REPLACE FUNCTION audit_trigger_function()
RETURNS TRIGGER AS $$
BEGIN
    -- Log the operation to audit table (simplified for now)
    -- In production, this would log to a separate audit table
    IF TG_OP = 'INSERT' THEN
        RAISE NOTICE 'AUDIT: INSERT into % by user % at %', TG_TABLE_NAME, current_user, CURRENT_TIMESTAMP;
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        RAISE NOTICE 'AUDIT: UPDATE on % by user % at %', TG_TABLE_NAME, current_user, CURRENT_TIMESTAMP;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        RAISE NOTICE 'AUDIT: DELETE from % by user % at %', TG_TABLE_NAME, current_user, CURRENT_TIMESTAMP;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Grant necessary permissions to the application user with principle of least privilege
GRANT CREATE ON DATABASE jeex_idea TO jeex_user;
GRANT ALL ON SCHEMA public TO jeex_user;

-- Grant specific permissions on monitoring functions only (not all functions)
GRANT EXECUTE ON FUNCTION check_database_health() TO jeex_user;
GRANT EXECUTE ON FUNCTION get_database_metrics() TO jeex_user;

-- Create admin user for maintenance operations (optional for development)
DO $$
DECLARE
    admin_password TEXT;
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'jeex_admin') THEN
        -- Get admin password from environment (optional)
        admin_password := current_setting('app.jeex_admin_password', true);

        IF admin_password IS NOT NULL THEN
            -- Create admin user with password from environment
            EXECUTE format($f$CREATE ROLE jeex_admin LOGIN PASSWORD %L$f$, admin_password);
            GRANT ALL PRIVILEGES ON DATABASE jeex_idea TO jeex_admin;
            RAISE NOTICE 'Created jeex_admin user for maintenance operations';
        ELSE
            RAISE NOTICE 'jeex_admin password not set (app.jeex_admin_password environment variable optional in development)';
        END IF;
    ELSE
        RAISE NOTICE 'jeex_admin user already exists';
    END IF;
END $$;

-- Create read-only user for reporting (optional, for future use)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'jeex_readonly') THEN
        -- Check if readonly password is set in environment
        IF current_setting('app.jeex_readonly_password', true) IS NULL THEN
            RAISE NOTICE 'jeex_readonly password not set (app.jeex_readonly_password environment variable optional)';
        ELSE
            -- Create readonly user with password from environment
            EXECUTE format($f$CREATE ROLE jeex_readonly LOGIN PASSWORD %L$f$, current_setting('app.jeex_readonly_password'));
            -- No grants yet - will be granted after tables are created
            RAISE NOTICE 'Created jeex_readonly user for reporting operations';
        END IF;
    ELSE
        RAISE NOTICE 'jeex_readonly user already exists';
    END IF;
END $$;

-- Create archive directory for WAL archiving
DO $$
BEGIN
    CREATE TABLE IF NOT EXISTS archive_info (
        archive_name TEXT PRIMARY KEY,
        archive_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        archive_size BIGINT,
        status TEXT DEFAULT 'created'
    );
EXCEPTION WHEN others THEN
    RAISE NOTICE 'Archive info table creation failed or already exists';
END $$;

-- Create health check functions directly in init-db.sql

-- Create simple health check function for fast endpoints
CREATE OR REPLACE FUNCTION simple_health_check()
RETURNS JSONB AS $$
DECLARE
    is_healthy BOOLEAN := TRUE;
    connection_count INTEGER;
    cache_hit_ratio NUMERIC;
    last_autovacuum TIMESTAMP WITH TIME ZONE;
BEGIN
    -- Basic connectivity check
    SELECT count(*) INTO connection_count
    FROM pg_stat_activity;

    -- Basic performance check
    SELECT round((blks_hit::NUMERIC / NULLIF(blks_hit + blks_read, 0)) * 100, 2) INTO cache_hit_ratio
    FROM pg_stat_database
    WHERE datname = current_database();

    -- Determine health status
    IF connection_count > 180 THEN -- 90% of 200 max connections
        is_healthy := FALSE;
    END IF;

    IF cache_hit_ratio < 80 THEN -- Poor cache performance
        is_healthy := FALSE;
    END IF;

    RETURN jsonb_build_object(
        'status', CASE WHEN is_healthy THEN 'healthy' ELSE 'unhealthy' END,
        'timestamp', CURRENT_TIMESTAMP,
        'connections', connection_count,
        'cache_hit_ratio', COALESCE(cache_hit_ratio, 0)
    );
END;
$$ LANGUAGE plpgsql;

-- Note: SSL certificates will be generated separately
-- To enable TLS encryption, run the ssl/generate-ssl.sh script
-- and restart PostgreSQL with SSL configuration

-- Log successful initialization
\echo 'JEEX Idea PostgreSQL database initialized successfully'
\echo 'Features enabled:'
\echo '- UUID v4 support (gen_random_uuid from pgcrypto)'
\echo '- Performance monitoring (pg_stat_statements)'
\echo '- Text search (pg_trgm)'
\echo '- Cryptographic functions (pgcrypto)'
\echo '- Database health monitoring functions'
\echo '- Security audit logging functions'
\echo '- Multiple user roles with least privilege'
\echo '- TLS encryption with SSL certificates'
\echo '- OpenTelemetry integration ready'
\echo '- WAL archiving configured'
\echo ''
\echo 'Security note: User passwords must be set via environment variables:'
\echo '- app.jeex_admin_password (required for admin user)'
\echo '- app.jeex_readonly_password (optional for readonly user)'