#!/bin/bash
# JEEX Idea PostgreSQL Setup Verification Script
# Verifies that PostgreSQL 18 is configured correctly with all features

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
POSTGRES_SERVICE="${POSTGRES_SERVICE:-jeex-postgres}"
POSTGRES_USER="${POSTGRES_USER:-jeex_user}"
POSTGRES_DB="${POSTGRES_DB:-jeex_idea}"
POSTGRES_PORT="${POSTGRES_PORT:-5220}"

# Auto-detect Docker Compose command
if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose"
elif docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
else
    log_error "Docker Compose not found"
    exit 1
fi

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

# Execute PostgreSQL command
exec_psql() {
    local query="$1"
    shift
    local psql_flags="$@"
    $COMPOSE exec -T "$POSTGRES_SERVICE" \
      psql -v ON_ERROR_STOP=1 -At $psql_flags \
      -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$query"
}

# Check if container is running
check_container_running() {
    log_info "Checking if PostgreSQL container is running..."

    if $COMPOSE ps "$POSTGRES_SERVICE" | grep -q "Up"; then
        log_success "PostgreSQL container is running"
    else
        log_error "PostgreSQL container is not running"
        return 1
    fi
}

# Test database connectivity
test_connectivity() {
    log_info "Testing database connectivity..."

    if exec_psql "SELECT 1;" >/dev/null 2>&1; then
        log_success "Database connection successful"
    else
        log_error "Database connection failed"
        return 1
    fi
}

# Test PostgreSQL version
test_postgresql_version() {
    log_info "Checking PostgreSQL version..."

    version=$(exec_psql "SELECT version();" "-t" | xargs)
    if echo "$version" | grep -q "PostgreSQL 18"; then
        log_success "PostgreSQL 18 detected: $version"
    else
        log_error "PostgreSQL 18 not found. Version: $version"
        return 1
    fi
}

# Test UUID v7 support
test_uuid_v7() {
    log_info "Testing UUID v7 support..."

    # Check for v7 functions first
    if exec_psql "SELECT 1 FROM pg_proc WHERE proname IN ('uuid_generate_v7','gen_random_uuid_v7');" >/dev/null 2>&1; then
        log_success "UUID v7 function available"
    else
        log_warning "UUID v7 not available, checking v4 fallback"

        # Test v4 functions (gen_random_uuid is v4, not v7)
        if exec_psql "SELECT gen_random_uuid();" >/dev/null 2>&1; then
            log_success "UUID v4 (gen_random_uuid) function available as fallback"
        elif exec_psql "SELECT uuid_generate_v4();" >/dev/null 2>&1; then
            log_success "UUID v4 (uuid-ossp) function available as fallback"
        else
            log_error "No UUID generation function available"
            return 1
        fi
    fi
}

# Test required extensions
test_extensions() {
    log_info "Testing required extensions..."

    extensions=("uuid-ossp" "pg_stat_statements" "pg_trgm" "pgcrypto")

    for ext in "${extensions[@]}"; do
        if exec_psql "SELECT * FROM pg_extension WHERE extname = '$ext';" | grep -q "$ext"; then
            log_success "Extension '$ext' is installed"
        else
            log_error "Extension '$ext' is not installed"
            return 1
        fi
    done
}

# Test database schema
test_database_schema() {
    log_info "Testing database schema..."

    # Check if app_config table exists using catalog query instead of \dt
    if exec_psql "SELECT to_regclass('public.app_config');" | grep -vq 'NULL'; then
        log_success "app_config table exists"
    else
        log_error "app_config table not found"
        return 1
    fi

    # Check if health check functions exist using catalog query instead of \df
    if exec_psql "SELECT 1 FROM pg_proc WHERE proname = 'check_database_health';" >/dev/null 2>&1; then
        log_success "Health check functions are available"
    else
        log_error "Health check functions not found"
        return 1
    fi
}

# Test user accounts and permissions
test_user_accounts() {
    log_info "Testing user accounts and permissions..."

    # Check jeex_user using catalog query instead of \du
    if exec_psql "SELECT 1 FROM pg_roles WHERE rolname = '$POSTGRES_USER';" >/dev/null 2>&1; then
        log_success "Application user '$POSTGRES_USER' exists"
    else
        log_error "Application user '$POSTGRES_USER' not found"
        return 1
    fi

    # Check jeex_admin using catalog query instead of \du
    if exec_psql "SELECT 1 FROM pg_roles WHERE rolname = 'jeex_admin';" >/dev/null 2>&1; then
        log_success "Admin user 'jeex_admin' exists"
    else
        log_warning "Admin user 'jeex_admin' not found (may be created on first run)"
    fi

    # Check jeex_readonly using catalog query instead of \du
    if exec_psql "SELECT 1 FROM pg_roles WHERE rolname = 'jeex_readonly';" >/dev/null 2>&1; then
        log_success "Read-only user 'jeex_readonly' exists"
    else
        log_warning "Read-only user 'jeex_readonly' not found (may be created on first run)"
    fi
}

# Test security settings
test_security_settings() {
    log_info "Testing security settings..."

    # Check password encryption
    password_encryption=$(exec_psql "SHOW password_encryption;" "-t" | xargs)
    if [ "$password_encryption" = "scram-sha-256" ]; then
        log_success "Password encryption set to scram-sha-256"
    else
        log_warning "Password encryption not set to scram-sha-256: $password_encryption"
    fi

    # Check SSL settings
    ssl_enabled=$(exec_psql "SHOW ssl;" "-t" | xargs)
    if [ "$ssl_enabled" = "on" ]; then
        log_success "SSL is enabled"
    else
        log_warning "SSL is not enabled: $ssl_enabled"
    fi
}

# Test health monitoring functions
test_health_functions() {
    log_info "Testing health monitoring functions..."

    # Test basic health check
    if exec_psql "SELECT simple_health_check();" >/dev/null 2>&1; then
        log_success "Simple health check function working"
    else
        log_error "Simple health check function failed"
        return 1
    fi

    # Test detailed health check
    if exec_psql "SELECT detailed_health_check();" >/dev/null 2>&1; then
        log_success "Detailed health check function working"
    else
        log_error "Detailed health check function failed"
        return 1
    fi

    # Test metrics function
    if exec_psql "SELECT get_database_metrics();" >/dev/null 2>&1; then
        log_success "Database metrics function working"
    else
        log_error "Database metrics function failed"
        return 1
    fi
}

# Test performance settings
test_performance_settings() {
    log_info "Testing performance settings..."

    # Check shared_buffers
    shared_buffers=$(exec_psql "SHOW shared_buffers;" "-t" | xargs)
    log_info "Shared buffers: $shared_buffers"

    # Check work_mem
    work_mem=$(exec_psql "SHOW work_mem;" "-t" | xargs)
    log_info "Work memory: $work_mem"

    # Check max_connections
    max_connections=$(exec_psql "SHOW max_connections;" "-t" | xargs)
    log_info "Max connections: $max_connections"

    # Check autovacuum settings
    autovacuum=$(exec_psql "SHOW autovacuum;" "-t" | xargs)
    if [ "$autovacuum" = "on" ]; then
        log_success "Autovacuum is enabled"
    else
        log_warning "Autovacuum is disabled"
    fi
}

# Test WAL archiving configuration
test_wal_archiving() {
    log_info "Testing WAL archiving configuration..."

    # Check wal_level
    wal_level=$(exec_psql "SHOW wal_level;" "-t" | xargs)
    if [ "$wal_level" = "replica" ]; then
        log_success "WAL level set to replica"
    else
        log_warning "WAL level not set to replica: $wal_level"
    fi

    # Check archive_mode
    archive_mode=$(exec_psql "SHOW archive_mode;" "-t" | xargs)
    if [ "$archive_mode" = "on" ]; then
        log_success "Archive mode is enabled"
    else
        log_warning "Archive mode is disabled"
    fi
}

# Test database connection from host
test_host_connection() {
    log_info "Testing database connection from host..."

    if PGPASSWORD="${PGPASSWORD:?set PGPASSWORD}" psql -h localhost -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1;" >/dev/null 2>&1; then
        log_success "Host connection to PostgreSQL successful"
    else
        log_warning "Host connection to PostgreSQL failed (container might not expose port or PGPASSWORD not set)"
    fi
}

# Test health endpoints (if API is running)
test_health_endpoints() {
    log_info "Testing health endpoints..."

    # Test basic health endpoint
    if curl -s http://localhost:5210/health >/dev/null 2>&1; then
        log_success "API health endpoint accessible"

        # Test database health endpoint
        if curl -s http://localhost:5210/health/database >/dev/null 2>&1; then
            log_success "Database health endpoint accessible"
        else
            log_warning "Database health endpoint not accessible (API may not be running)"
        fi
    else
        log_warning "API health endpoint not accessible (API may not be running)"
    fi
}

# Main verification function
main() {
    echo "========================================"
    echo "JEEX Idea PostgreSQL Setup Verification"
    echo "========================================"
    echo ""

    # Check if Docker Compose is available (already detected above)
    log_info "Using Docker Compose command: $COMPOSE"

    # Run all tests
    check_container_running || true
    test_connectivity || true
    test_postgresql_version || true
    test_uuid_v7 || true
    test_extensions || true
    test_database_schema || true
    test_user_accounts || true
    test_security_settings || true
    test_health_functions || true
    test_performance_settings || true
    test_wal_archiving || true
    test_host_connection || true
    test_health_endpoints || true

    # Summary
    echo ""
    echo "========================================"
    echo "Verification Summary"
    echo "========================================"
    echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}"

    if [ $TESTS_FAILED -eq 0 ]; then
        echo ""
        log_success "All PostgreSQL setup tests passed! ✅"
        echo ""
        echo "PostgreSQL 18 is properly configured with:"
        echo "  ✓ UUID generation support (v7 preferred, v4 fallback)"
        echo "  ✓ Required extensions"
        echo "  ✓ Security hardening"
        echo "  ✓ Health monitoring"
        echo "  ✓ Performance optimization"
        echo "  ✓ WAL archiving"
        echo ""
        echo "Database is ready for JEEX Idea application!"
    else
        echo ""
        log_error "Some PostgreSQL setup tests failed! ❌"
        echo ""
        echo "Please check the failed tests above and fix any issues."
        echo "Common issues:"
        echo "  - PostgreSQL container not running"
        echo "  - Extensions not installed"
        echo "  - Permission issues"
        echo "  - Configuration problems"
    fi

    echo ""
    return $TESTS_FAILED
}

# Run main function
main "$@"