-- JEEX Idea PostgreSQL Health Check Script
-- This script provides comprehensive database health monitoring
-- Integrated with OpenTelemetry for metrics collection

-- Set timezone for consistent reporting
SET timezone = 'UTC';

-- Create health check function with detailed diagnostics
CREATE OR REPLACE FUNCTION detailed_health_check()
RETURNS JSONB AS $$
DECLARE
    health_result JSONB;
    overall_status TEXT := 'healthy';
    warnings JSONB := '[]'::jsonb;
    errors JSONB := '[]'::jsonb;

    -- Database metrics
    connection_count INTEGER;
    active_connections INTEGER;
    idle_connections INTEGER;
    max_connections INTEGER;
    connection_utilization NUMERIC;

    -- Performance metrics
    cache_hit_ratio NUMERIC;
    avg_query_time NUMERIC;
    slow_queries_count INTEGER;
    total_statements BIGINT;

    -- Database size and growth
    database_size BIGINT;
    database_size_mb NUMERIC;

    -- WAL metrics
    wal_size BIGINT;
    wal_count INTEGER;
    archive_status TEXT;

    -- Autovacuum status
    autovacuum_running INTEGER;
    last_autovacuum TIMESTAMP WITH TIME ZONE;

    -- Replication status (if applicable)
    replication_lag NUMERIC;
    is_replica BOOLEAN;

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

    SELECT setting::integer INTO max_connections
    FROM pg_settings
    WHERE name = 'max_connections';

    -- Calculate connection utilization
    connection_utilization := (connection_count::NUMERIC / max_connections::NUMERIC) * 100;

    -- Check connection thresholds
    IF connection_utilization > 90 THEN
        overall_status := 'degraded';
        errors := errors || jsonb_build_object(
            'type', 'connection_utilization_high',
            'message', format('Connection utilization is %.2f%% (threshold: 90%%)', connection_utilization),
            'severity', 'critical'
        );
    ELSIF connection_utilization > 75 THEN
        overall_status := 'degraded';
        warnings := warnings || jsonb_build_object(
            'type', 'connection_utilization_elevated',
            'message', format('Connection utilization is %.2f%% (threshold: 75%%)', connection_utilization),
            'severity', 'warning'
        );
    END IF;

    -- Get performance metrics
    SELECT round((blks_hit::NUMERIC / (blks_hit + blks_read)) * 100, 2) INTO cache_hit_ratio
    FROM pg_stat_database
    WHERE datname = current_database();

    -- Get query performance from pg_stat_statements
    SELECT
        count(*) INTO slow_queries_count,
        COALESCE(round(AVG(mean_exec_time), 2), 0) INTO avg_query_time,
        COALESCE(sum(calls), 0) INTO total_statements
    FROM pg_stat_statements;

    -- Check cache hit ratio
    IF cache_hit_ratio < 90 THEN
        overall_status := 'degraded';
        warnings := warnings || jsonb_build_object(
            'type', 'cache_hit_ratio_low',
            'message', format('Cache hit ratio is %.2f%% (threshold: 90%%)', cache_hit_ratio),
            'severity', 'warning'
        );
    END IF;

    -- Check slow queries
    IF slow_queries_count > 10 THEN
        overall_status := 'degraded';
        errors := errors || jsonb_build_object(
            'type', 'slow_queries_high',
            'message', format('Found %d slow queries (>1s average) (threshold: 10)', slow_queries_count),
            'severity', 'critical'
        );
    ELSIF slow_queries_count > 5 THEN
        overall_status := 'degraded';
        warnings := warnings || jsonb_build_object(
            'type', 'slow_queries_elevated',
            'message', format('Found %d slow queries (>1s average) (threshold: 5)', slow_queries_count),
            'severity', 'warning'
        );
    END IF;

    -- Get database size
    SELECT pg_database_size(current_database()) INTO database_size;
    database_size_mb := database_size / (1024.0 * 1024.0);

    -- Get WAL metrics
    SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0') INTO wal_size;
    SELECT count(*) INTO wal_count
    FROM pg_stat_wal_receiver;

    -- Check autovacuum status
    SELECT count(*) INTO autovacuum_running
    FROM pg_stat_activity
    WHERE query LIKE 'autovacuum:%';

    -- Check replication status
    SELECT pg_is_in_recovery() INTO is_replica;

    IF is_replica THEN
        -- We're a replica, check replication lag
        SELECT pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()) INTO replication_lag;

        IF replication_lag > 1024 * 1024 * 100 THEN -- 100MB lag
            overall_status := 'degraded';
            warnings := warnings || jsonb_build_object(
                'type', 'replication_lag_high',
                'message', format('Replication lag is %.2f MB', replication_lag / (1024.0 * 1024.0)),
                'severity', 'warning'
            );
        END IF;
    END IF;

    -- Build comprehensive health result
    health_result := jsonb_build_object(
        'status', overall_status,
        'timestamp', CURRENT_TIMESTAMP,
        'postgresql_version', version(),
        'instance_id', current_setting('data_directory'),

        -- Connection metrics
        'connections', jsonb_build_object(
            'total', connection_count,
            'active', active_connections,
            'idle', idle_connections,
            'max_allowed', max_connections,
            'utilization_percent', round(connection_utilization, 2)
        ),

        -- Performance metrics
        'performance', jsonb_build_object(
            'cache_hit_ratio_percent', COALESCE(cache_hit_ratio, 0),
            'average_query_time_ms', avg_query_time,
            'slow_queries_count', COALESCE(slow_queries_count, 0),
            'total_statements_executed', total_statements
        ),

        -- Database metrics
        'database', jsonb_build_object(
            'size_bytes', database_size,
            'size_mb', round(database_size_mb, 2),
            'name', current_database()
        ),

        -- WAL and replication
        'wal', jsonb_build_object(
            'current_size_bytes', wal_size,
            'is_replica', is_replica,
            'replication_lag_bytes', COALESCE(replication_lag, 0)
        ),

        -- Autovacuum status
        'autovacuum', jsonb_build_object(
            'running_workers', autovacuum_running
        ),

        -- Health issues
        'warnings', warnings,
        'errors', errors,

        -- OpenTelemetry metrics
        'otel_metrics', jsonb_build_object(
            'database.connections.active', active_connections,
            'database.connections.utilization', round(connection_utilization, 2),
            'database.cache.hit_ratio', COALESCE(cache_hit_ratio, 0),
            'database.queries.avg_time_ms', avg_query_time,
            'database.queries.slow_count', COALESCE(slow_queries_count, 0),
            'database.size_bytes', database_size,
            'database.wal.size_bytes', wal_size,
            'database.autovacuum.workers', autovacuum_running
        )
    );

    RETURN health_result;
END;
$$ LANGUAGE plpgsql;

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
    SELECT round((blks_hit::NUMERIC / (blks_hit + blks_read)) * 100, 2) INTO cache_hit_ratio
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

-- Grant execution permissions to application user
GRANT EXECUTE ON FUNCTION detailed_health_check() TO jeex_user;
GRANT EXECUTE ON FUNCTION simple_health_check() TO jeex_user;
GRANT EXECUTE ON FUNCTION check_database_health() TO jeex_user;
GRANT EXECUTE ON FUNCTION get_database_metrics() TO jeex_user;

-- Create monitoring view for OpenTelemetry integration
CREATE OR REPLACE VIEW current_database_status AS
SELECT
    CURRENT_TIMESTAMP as check_time,
    detailed_health_check() as health_data,
    simple_health_check() as basic_health;

-- Grant view access
GRANT SELECT ON current_database_status TO jeex_user;

-- Create additional health functions referenced elsewhere
CREATE OR REPLACE FUNCTION check_database_health()
RETURNS JSONB AS $$
BEGIN
    RETURN detailed_health_check();
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_database_metrics()
RETURNS JSONB AS $$
DECLARE
    metrics JSONB;
BEGIN
    SELECT jsonb_build_object(
        'connections', jsonb_build_object(
            'active', (SELECT count(*) FROM pg_stat_activity WHERE state = 'active'),
            'total', (SELECT count(*) FROM pg_stat_activity),
            'max_allowed', (SELECT setting::int FROM pg_settings WHERE name = 'max_connections')
        ),
        'performance', jsonb_build_object(
            'cache_hit_ratio', (
                SELECT round((blks_hit::NUMERIC / (blks_hit + blks_read)) * 100, 2)
                FROM pg_stat_database WHERE datname = current_database()
            )
        ),
        'database_size', pg_database_size(current_database()),
        'timestamp', CURRENT_TIMESTAMP
    ) INTO metrics;

    RETURN metrics;
END;
$$ LANGUAGE plpgsql;

-- Log successful setup
\echo 'JEEX Idea PostgreSQL health monitoring functions created successfully'
\echo 'Functions available:'
\echo '- detailed_health_check() -> Comprehensive health assessment'
\echo '- simple_health_check() -> Fast basic health check'
\echo '- check_database_health() -> Original health function'
\echo '- get_database_metrics() -> Performance metrics'
\echo '- current_database_status view -> Current status snapshot'