# JEEX Idea PostgreSQL 18 Setup Guide

This document describes the PostgreSQL 18 database setup for JEEX Idea, including configuration, security, monitoring, and maintenance procedures.

## Overview

The JEEX Idea application uses PostgreSQL 18 as its primary database with the following features:

- **UUID v7 Support**: Modern UUID generation for primary keys
- **Performance Optimization**: Optimized settings for containerized environments
- **Security Hardening**: TLS encryption, SCRAM-SHA-256 authentication, role-based access
- **Health Monitoring**: Built-in health checks and OpenTelemetry integration
- **WAL Archiving**: Point-in-time recovery capabilities
- **Connection Pooling**: Efficient connection management

## Architecture

### Database Components

1. **PostgreSQL 18 Server**: Main database engine
2. **Extensions**: uuid-ossp, pg_stat_statements, pg_trgm, pgcrypto
3. **Security**: TLS encryption, role-based access control
4. **Monitoring**: Health checks, performance metrics
5. **Backup**: WAL archiving for point-in-time recovery

### User Roles

- **jeex_user**: Application user with limited privileges
- **jeex_admin**: Database administrator for maintenance
- **jeex_readonly**: Read-only user for reporting (future use)

## Configuration Files

### PostgreSQL Configuration (`docker/postgres/postgresql.conf`)

Optimized configuration for containerized PostgreSQL 18 with:

- Memory settings tuned for 1GB container limit
- Performance optimizations for SSD storage
- WAL archiving configuration
- Logging and monitoring settings
- JIT compilation settings

### Authentication Configuration (`docker/postgres/pg_hba.conf`)

Enhanced security configuration with:

- SCRAM-SHA-256 authentication
- TLS encryption enforcement
- Network access controls
- Role-based restrictions

### Database Initialization (`docker/postgres/init-db.sql`)

Comprehensive initialization script that:

- Creates required extensions
- Sets up user accounts with proper privileges
- Creates monitoring functions
- Implements audit logging
- Configures security settings

## Database Schema

### Core Tables

#### Users

- Primary authentication and user management
- UUID primary keys
- Email uniqueness constraints
- Soft delete support

#### Projects

- Project isolation with mandatory `project_id`
- Language tracking (immutable)
- Status and progress tracking
- JSON metadata support

#### Document Versions

- Document content versioning
- Project-scoped access
- Performance scores (readability, grammar)
- Full-text search capabilities

#### Agent Executions

- Agent workflow tracking
- Correlation ID support
- Input/output data storage
- Performance metrics

#### Exports

- Document export management
- File tracking with manifest
- Expiration handling
- Download statistics

### Indexes and Performance

- Composite indexes for project isolation
- JSONB GIN indexes for metadata queries
- Foreign key indexes for joins
- Partial indexes for active data

## Security Features

### Authentication

- **SCRAM-SHA-256**: Modern password hashing
- **TLS Encryption**: Encrypted data in transit
- **Role-Based Access**: Principle of least privilege
- **Connection Limits**: Resource protection

### Data Protection

- **Row-Level Security**: Optional for defense-in-depth
- **Audit Logging**: All data access operations
- **Network Isolation**: Docker network restrictions
- **Secret Management**: Environment-based configuration

## Monitoring and Health Checks

### Health Check Functions

#### `simple_health_check()`

Fast health check for load balancers:

- Connection count
- Cache hit ratio
- Basic status

#### `detailed_health_check()`

Comprehensive health assessment:

- Connection metrics
- Performance indicators
- WAL status
- Autovacuum status
- Error and warning collection

#### `get_database_metrics()`

Performance metrics collection:

- Query performance statistics
- Slow query tracking
- Statement execution counts

### OpenTelemetry Integration

Database metrics exported to OpenTelemetry:

- Connection utilization
- Cache hit ratios
- Query performance
- Database size
- WAL metrics

## Maintenance Procedures

### Backups

#### Automated Backups

```bash
# Create backup
make db-backup

# Manual backup with pg_dump
docker-compose exec postgres pg_dump -U jeex_user jeex_idea > backup.sql
```

#### Point-in-Time Recovery

- WAL archiving enabled
- Archive retention policies
- Recovery procedures documented

### Performance Maintenance

#### Autovacuum Configuration

- Automatic vacuum and analyze
- Tuned for container environment
- Monitoring and alerts

#### Index Maintenance

- Bloat monitoring
- Reindexing procedures
- Performance analysis

#### Connection Pooling

- SQLAlchemy async engine
- Connection recycling
- Pool size optimization

## Development Workflow

### Database Migrations

#### Creating Migrations

```bash
# Create new migration
make db-migrate-create MSG="add_new_table"

# Run migrations
make db-migrate

# Check migration status
make db-migrate-current
```

#### Migration Best Practices

- Use Alembic autogenerate
- Test migrations in development
- Keep migrations reversible
- Document migration purpose

### Database Access

#### Direct SQL Access

```bash
# Open PostgreSQL shell
make db-shell

# Execute SQL from file
docker-compose exec postgres psql -U jeex_user -d jeex_idea -f script.sql
```

#### Application Access

```python
# Using async database session
async with get_database_session() as db:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
```

## Troubleshooting

### Common Issues

#### Connection Problems

```bash
# Check container status
docker-compose ps postgres

# Check logs
docker-compose logs postgres

# Test connectivity
make verify-postgresql
```

#### Performance Issues

```bash
# Check slow queries
SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;

# Check cache hit ratio
SELECT datname, blks_hit, blks_read,
       round((blks_hit::numeric / (blks_hit + blks_read)) * 100, 2) AS hit_ratio
FROM pg_stat_database;
```

#### Disk Space Issues

```bash
# Check database size
SELECT pg_database_size('jeex_idea') / 1024 / 1024 AS size_mb;

# Check table sizes
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables WHERE schemaname = 'public';
```

### Monitoring

#### Health Endpoints

```bash
# Basic health check
curl http://localhost:5210/health

# Database health
curl http://localhost:5210/health/database

# Database metrics
curl http://localhost:5210/health/database/metrics
```

#### Logs

```bash
# PostgreSQL logs
docker-compose logs postgres

# Application logs
docker-compose logs api
```

## Environment Variables

### Required Variables

```bash
# Database configuration
DATABASE_URL=postgresql+asyncpg://jeex_user:password@postgres:5432/jeex_idea
POSTGRES_PASSWORD=your_secure_password

# Connection pooling
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
```

### Optional Variables

```bash
# Debug mode
DEBUG=true
LOG_LEVEL=DEBUG

# Security
CORS_ORIGINS=http://localhost:3000
```

## Production Deployment

### Security Checklist

- [ ] Change default passwords
- [ ] Enable TLS encryption
- [ ] Configure network access controls
- [ ] Set up monitoring and alerts
- [ ] Configure backup procedures
- [ ] Review user permissions
- [ ] Enable audit logging

### Performance Tuning

- [ ] Adjust memory settings based on available resources
- [ ] Optimize connection pool sizes
- [ ] Configure autovacuum settings
- [ ] Set up performance monitoring
- [ ] Implement backup verification

### Monitoring Setup

- [ ] Configure OpenTelemetry collector
- [ ] Set up health check endpoints
- [ ] Configure alert thresholds
- [ ] Create performance dashboards
- [ ] Test notification systems

## References

- [PostgreSQL 18 Documentation](https://www.postgresql.org/docs/18/)
- [Alembic Migration Guide](https://alembic.sqlalchemy.org/en/latest/)
- [SQLAlchemy Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Docker PostgreSQL Best Practices](https://github.com/docker-library/docs/tree/master/postgres)

## Support

For issues with the PostgreSQL setup:

1. Check the verification script: `make verify-postgresql`
2. Review container logs: `docker-compose logs postgres`
3. Consult the troubleshooting section above
4. Check application health endpoints: `curl http://localhost:5210/health/database`
