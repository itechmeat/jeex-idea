# Cache Domain Implementation

Domain-Driven Design (DDD) implementation for cache management with Redis backend. This module provides comprehensive caching, session management, rate limiting, and progress tracking capabilities with strict project isolation.

## Architecture Overview

The cache domain follows DDD principles with clear separation of concerns:

```
backend/app/domain/cache/
├── __init__.py                 # Module initialization
├── entities.py                 # Domain entities (ProjectCache, UserSession, etc.)
├── value_objects.py            # Value objects (CacheKey, TTL, etc.)
├── repository_interfaces.py    # Abstract repository contracts
├── domain_services.py          # Domain services (business logic)
└── README.md                   # This documentation

backend/app/infrastructure/repositories/
└── cache_repository.py         # Redis implementation of repositories

backend/app/services/cache/
└── cache_manager.py            # High-level cache management service
```

## Core Components

### Domain Entities

#### ProjectCache
Represents cached project data with versioning and access tracking:
- **Project isolation**: Each cache entry is scoped to a specific project
- **Version tracking**: Prevents stale data serving with version numbers
- **Access statistics**: Tracks cache hit patterns and usage
- **TTL management**: Automatic expiration with configurable time-to-live
- **Tag support**: Flexible cache invalidation by tags

#### UserSession
Manages user authentication sessions with project access rights:
- **Security**: Secure session ID generation and validation
- **Project access**: Manages which projects a user can access
- **Activity tracking**: Updates last activity timestamp
- **Automatic expiration**: Configurable session TTL with extension
- **Multi-session support**: Handles multiple active sessions per user

#### Progress
Tracks progress of long-running operations for SSE updates:
- **Step-by-step tracking**: Detailed progress with messages
- **Correlation ID**: Links progress to specific operations
- **Completion handling**: Marks operations as completed or failed
- **Automatic cleanup**: Expires progress data after operations finish

#### RateLimit
Enforces rate limiting with sliding window algorithm:
- **Multiple windows**: Minute, hour, and day rate limiting
- **Flexible identifiers**: User, project, and IP-based limiting
- **Automatic reset**: Window-based counter resets
- **Graceful degradation**: Fails open when rate limiting service unavailable

### Value Objects

#### CacheKey
Type-safe cache key generation with validation:
```python
# Project data key
key = CacheKey.project_data(project_id)

# User session key
key = CacheKey.user_session(session_id)

# Rate limit key
key = CacheKey.rate_limit("user", "user123", RateLimitWindow.HOUR)
```

#### TTL
Time-to-live configuration with presets:
```python
# Custom TTL
ttl = TTL.hours(2)

# Preset TTLs
ttl = TTL.project_data()  # 1 hour
ttl = TTL.user_session()  # 2 hours
ttl = TTL.rate_limit(RateLimitWindow.MINUTE)  # 1 minute
```

#### CacheTag
Cache invalidation by tags:
```python
# Project-specific tag
tag = CacheTag.project(project_id)

# Custom tag
tag = CacheTag("custom_group")
```

### Repository Interfaces

Abstract contracts for cache persistence:
- **ProjectCacheRepository**: Project cache operations
- **UserSessionRepository**: Session management
- **TaskQueueRepository**: Background task queues
- **ProgressRepository**: Progress tracking
- **RateLimitRepository**: Rate limiting state
- **CacheHealthRepository**: Health monitoring

### Domain Services

Business logic orchestration:
- **CacheInvalidationService**: Intelligent cache invalidation strategies
- **SessionManagementService**: Session lifecycle management
- **RateLimitingService**: Rate limiting business rules
- **CacheHealthService**: Health monitoring and metrics

## Usage Examples

### Basic Cache Operations

```python
from app.services.cache.cache_manager import cache_manager
from app.domain.cache.value_objects import TTL, CacheTag
from uuid import uuid4

# Initialize cache manager
await cache_manager.initialize()

# Cache project data
project_id = uuid4()
data = {"name": "My Project", "description": "Project description"}
success = await cache_manager.cache_project_data(project_id, data)

# Retrieve cached data
cached_data = await cache_manager.get_project_data(project_id)

# Invalidate project cache
invalidated_count = await cache_manager.invalidate_project_cache(project_id, "project_updated")
```

### Session Management

```python
# Create user session
user_id = uuid4()
user_data = {"name": "John Doe", "email": "john@example.com"}
project_access = [project_id, uuid4()]

session = await cache_manager.create_user_session(
    user_id=user_id,
    user_data=user_data,
    project_access=project_access
)

# Validate session
valid_session = await cache_manager.validate_user_session(session.session_id)

# Grant additional project access
await cache_manager.grant_project_access(session.session_id, new_project_id)

# Revoke session
await cache_manager.revoke_user_session(session.session_id, "logout")
```

### Rate Limiting

```python
from app.domain.cache.value_objects import RateLimitConfig, RateLimitWindow

# Configure rate limit
config = RateLimitConfig(
    requests_per_window=100,
    window_seconds=3600,  # 1 hour
    burst_allowed=5
)

# Check rate limit
result = await cache_manager.check_rate_limit("user123", "user", config)

if result["allowed"]:
    # Process request
    pass
else:
    # Rate limit exceeded
    retry_after = result["reset_seconds"]
```

### Progress Tracking

```python
# Start progress tracking
correlation_id = uuid4()
await cache_manager.start_progress_tracking(correlation_id, 5)

# Update progress
await cache_manager.increment_progress(correlation_id, "Processing business analyst response")
await cache_manager.increment_progress(correlation_id, "Generating architecture document")

# Complete progress
await cache_manager.complete_progress(correlation_id, "All documents generated successfully")

# Get current progress
progress = await cache_manager.get_progress(correlation_id)
print(f"Progress: {progress['percentage']}% - {progress['message']}")
```

## Performance Requirements

The implementation is designed to meet strict performance requirements:

- **Cache reads**: 95% of operations under 5ms
- **Rate limit checks**: 99% of operations under 2ms
- **Progress updates**: 95% of operations under 3ms
- **Cache writes**: 95% of operations under 10ms

### Performance Testing

Run performance tests to validate requirements:

```bash
# Run cache performance tests
pytest tests/performance/test_cache_performance.py -v

# Run with specific test
pytest tests/performance/test_cache_performance.py::TestCachePerformance::test_cache_read_performance -v
```

## Project Isolation

The implementation enforces strict project isolation:

- **Key prefixing**: All cache keys include project ID prefix
- **Connection isolation**: Separate Redis connection pools per project
- **Repository filtering**: Automatic project ID filtering in repositories
- **Security**: Project access validation in sessions

Example of project isolation:
```python
# Each project gets isolated cache keys
project_1_key = "proj:project-1-uuid:data"
project_2_key = "proj:project-2-uuid:data"

# Redis connection factory enforces project isolation
async with redis_service.get_connection(str(project_id)) as redis_client:
    # All operations are automatically project-isolated
    await redis_client.set("key", "value")  # Becomes "proj:project-uuid:key"
```

## Configuration

### Environment Variables

```bash
# Redis configuration
REDIS_URL=redis://localhost:5240
REDIS_MAX_CONNECTIONS=20

# Cache TTLs (seconds)
CACHE_PROJECT_DATA_TTL=3600
CACHE_USER_SESSION_TTL=7200
CACHE_PROGRESS_TTL=1800

# Rate limiting
RATE_LIMIT_DEFAULT_REQUESTS=100
RATE_LIMIT_DEFAULT_WINDOW=3600

# Performance monitoring
CACHE_METRICS_BUFFER_SIZE=100
CACHE_HEALTH_CHECK_INTERVAL=30
```

### TTL Presets

Default TTL configurations:
- **Project data**: 1 hour (3600 seconds)
- **User sessions**: 2 hours (7200 seconds)
- **Rate limits**: Window-dependent (60s, 3600s, 86400s)
- **Progress tracking**: 30 minutes (1800 seconds)
- **Task status**: 24 hours (86400 seconds)

## Error Handling

The implementation includes comprehensive error handling:

### Graceful Degradation

```python
# Rate limiting fails open - allows requests if service unavailable
result = await cache_manager.check_rate_limit("user123", "user", config)
if "error" in result:
    # Service unavailable, request allowed
    logger.warning("Rate limiting service unavailable")
    # Continue processing request
```

### Circuit Breaker

Redis operations are protected by circuit breaker:
- **Automatic detection**: Detects Redis failures
- **Circuit opening**: Stops operations after consecutive failures
- **Automatic recovery**: Tests and recovers when Redis is available
- **Fallback**: Degrades gracefully when Redis is unavailable

### Retry Logic

Automatic retry with exponential backoff:
```python
# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # Base delay in seconds
BACKOFF_MULTIPLIER = 2.0
```

## Monitoring and Observability

### OpenTelemetry Integration

All operations are instrumented with OpenTelemetry:
```python
# Spans are automatically created for cache operations
with tracer.start_as_current_span("cache_manager.get_project_data") as span:
    span.set_attribute("project_id", str(project_id))
    span.set_attribute("cache_hit", True)
```

### Metrics

Comprehensive metrics collection:
- **Operation counts**: Hit/miss ratios for cache operations
- **Execution times**: Performance metrics for monitoring
- **Memory usage**: Redis memory monitoring
- **Error rates**: Failure tracking and alerting

### Health Checks

Built-in health monitoring:
```python
# Comprehensive health check
health_status = await cache_manager.health_check()

# Check individual components
memory_usage = await cache_manager.health_service.get_memory_usage()
performance_metrics = await cache_manager.get_performance_metrics()
```

## Testing

### Unit Tests

```bash
# Run all unit tests
pytest tests/unit/domain/test_cache_domain.py -v

# Run specific entity tests
pytest tests/unit/domain/test_cache_domain.py::TestProjectCache -v

# Run service tests
pytest tests/unit/services/test_cache_manager.py -v
```

### Integration Tests

```bash
# Run integration tests (requires Redis)
pytest tests/integration/test_cache_integration.py -v
```

### Performance Tests

```bash
# Run performance tests
pytest tests/performance/test_cache_performance.py -v -s

# Run specific performance test
pytest tests/performance/test_cache_performance.py::TestCachePerformance::test_cache_read_performance -v -s
```

## Best Practices

### Cache Key Design

- **Consistent patterns**: Use established key patterns
- **Human readable**: Keys should be understandable
- **Hierarchical**: Use colons for hierarchy (project:id:data)
- **Limited length**: Keep keys under 250 characters

### TTL Management

- **Appropriate values**: Set TTL based on data volatility
- **Expiration strategy**: Consider access patterns
- **Memory management**: Monitor memory usage with TTL
- **Refresh strategy**: Implement cache warming for frequently accessed data

### Error Handling

- **Fail open**: Allow operations when cache fails
- **Logging**: Comprehensive error logging
- **Monitoring**: Alert on high error rates
- **Fallback**: Always have database fallback

### Performance

- **Batch operations**: Use Redis pipelines where possible
- **Connection pooling**: Reuse connections efficiently
- **Memory monitoring**: Watch Redis memory usage
- **Slow queries**: Monitor and optimize slow operations

## Security Considerations

### Data Protection

- **Sensitive data**: Avoid caching sensitive information
- **Encryption**: Use Redis encryption for sensitive data
- **Access control**: Implement proper Redis authentication
- **Network security**: Use TLS for Redis connections

### Project Isolation

- **Key isolation**: Enforce project-based key separation
- **Connection isolation**: Separate connection pools per project
- **Access validation**: Validate project access in all operations
- **Audit logging**: Log all cache access patterns

## Migration Guide

### From Direct Redis Usage

```python
# Old approach
import redis
redis_client = redis.Redis()
await redis_client.set(f"project:{project_id}:data", json.dumps(data))

# New approach
from app.services.cache.cache_manager import cache_manager
await cache_manager.cache_project_data(project_id, data)
```

### Benefits of Migration

1. **Type safety**: Pydantic models prevent runtime errors
2. **Project isolation**: Automatic multi-tenancy support
3. **Performance**: Optimized operations with monitoring
4. **Reliability**: Circuit breaker and retry logic
5. **Observability**: Built-in metrics and tracing
6. **Maintainability**: Clear domain model and interfaces

## Troubleshooting

### Common Issues

#### Cache Misses
```python
# Check if cache exists
project_data = await cache_manager.get_project_data(project_id)
if project_data is None:
    # Cache miss - fetch from database and cache
    data = await database.get_project(project_id)
    await cache_manager.cache_project_data(project_id, data)
```

#### Performance Issues
```python
# Check performance metrics
metrics = await cache_manager.get_performance_metrics()
if metrics["slow_operations"]["count"] > 0:
    # Investigate slow operations
    logger.warning(f"Slow cache operations detected: {metrics}")
```

#### Memory Issues
```python
# Check memory usage
health = await cache_manager.health_check()
memory_pct = health["memory"]["usage_percentage"]
if memory_pct > 80:
    # Implement cache cleanup
    await cache_manager.cleanup_expired_entries()
```

### Debug Mode

Enable debug logging:
```python
import logging
logging.getLogger("app.domain.cache").setLevel(logging.DEBUG)
logging.getLogger("app.services.cache").setLevel(logging.DEBUG)
```

## Contributing

When contributing to the cache domain:

1. **Follow DDD principles**: Maintain clear domain boundaries
2. **Add tests**: Include unit and integration tests
3. **Performance testing**: Validate performance requirements
4. **Documentation**: Update documentation for new features
5. **Error handling**: Include comprehensive error handling
6. **Monitoring**: Add appropriate metrics and tracing

## License

This cache domain implementation is part of the JEEX Idea project and follows the same licensing terms.