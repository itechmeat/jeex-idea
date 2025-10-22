# Redis Infrastructure - Domain-Driven Connection Management

This module provides Redis connection management following the Domain-Driven approach with comprehensive features for production use.

## Architecture Overview

The implementation follows **Variant C - Domain-Driven Abstraction Layer** as specified in the requirements:

```
┌─────────────────────────────────────────────────────────────┐
│                    RedisService                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ Health Check    │  │ Retry Logic     │  │ Metrics      │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│              RedisConnectionFactory                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ Connection Pool │  │ Project Isolation│  │ Health Check│ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│              Circuit Breaker                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ Failure Tracking│  │ Recovery Logic  │  │ Metrics      │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. RedisService (`redis_service.py`)

**Main service class** with connection pooling, health monitoring, and retry logic.

**Features:**
- Connection pooling with configurable minimum 10 connections
- Comprehensive health checks with performance metrics
- Automatic retry with exponential backoff
- Background health monitoring
- Memory usage analysis and alerts
- OpenTelemetry instrumentation

**Usage:**
```python
from app.infrastructure.redis import redis_service

async with redis_service.get_connection(project_id="my-project") as redis_client:
    await redis_client.set("key", "value", ex=3600)
    value = await redis_client.get("key")
```

### 2. RedisConnectionFactory (`connection_factory.py`)

**Connection management** with project isolation enforcement.

**Features:**
- Connection pooling with configurable pool sizes
- Project-specific connection pools
- Automatic connection testing and validation
- Graceful connection failure handling
- Connection factory metrics

**Project Isolation:**
```python
# Keys are automatically prefixed with project ID
# Original key: "user_data"
# Stored as: "proj:my-project:user_data"
```

### 3. ProjectIsolatedRedisClient (`connection_factory.py`)

**Redis client wrapper** that enforces project isolation by prefixing keys.

**Key Pattern:**
- Project keys: `proj:{project_id}:{key}`
- Ensures no cross-project data access
- Transparent to application code

### 4. Circuit Breaker (`circuit_breaker.py`)

**Resilience pattern** for Redis unavailability.

**States:**
- **CLOSED**: Normal operation
- **OPEN**: Rejecting calls (service degraded)
- **HALF_OPEN**: Testing recovery

**Configuration:**
- Failure threshold: 5 failures
- Recovery timeout: 60 seconds
- Success threshold: 3 successes
- Operation timeout: 10 seconds

### 5. Exceptions (`exceptions.py`)

**Domain-specific exceptions** with proper error context.

**Exception Hierarchy:**
```
RedisException
├── RedisConnectionException
├── RedisAuthenticationException
├── RedisOperationTimeoutException
├── RedisMemoryException
├── RedisCircuitBreakerOpenException
├── RedisKeyNotFoundException
├── RedisProjectIsolationException
├── RedisConfigurationException
└── RedisPoolExhaustedException
```

## Configuration

### Environment Variables

```bash
# Redis connection
REDIS_URL=redis://localhost:5240
REDIS_MAX_CONNECTIONS=10

# Timeouts and retries
REDIS_CONNECTION_TIMEOUT=10.0
REDIS_OPERATION_TIMEOUT=10.0
REDIS_MAX_RETRIES=3
REDIS_RETRY_DELAY=1.0

# Health monitoring
REDIS_HEALTH_CHECK_INTERVAL=30.0

# Circuit breaker
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60.0
```

### RedisServiceConfig

```python
from app.infrastructure.redis import RedisService, RedisServiceConfig

config = RedisServiceConfig(
    max_connections=10,           # Minimum per REQ-001
    connection_timeout=10.0,      # seconds
    operation_timeout=10.0,       # seconds
    health_check_interval=30.0,   # seconds
    max_retries=3,                # retry attempts
    memory_warning_threshold=0.8,  # 80%
    memory_critical_threshold=0.9  # 90%
)

service = RedisService(config)
```

## Acceptance Criteria - Task 1.2 ✅

### ✅ RedisService class created with connection pooling
- `RedisService` class implemented with `RedisServiceConfig`
- Connection pooling with minimum 10 connections
- Global `redis_service` instance available

### ✅ Connection pool configured with minimum 10 connections
- `REDIS_MAX_CONNECTIONS` defaults to 10
- Configurable per service instance
- Pool size monitoring in metrics

### ✅ Health check method implemented
- `RedisService.health_check()` returns comprehensive status
- Tests connection, memory usage, and response times
- Background health monitoring task

### ✅ Automatic reconnection logic for failed connections
- Retry logic with exponential backoff
- Connection factory validates connections on creation
- Graceful handling of connection failures

### ✅ Circuit breaker pattern for Redis unavailability
- `RedisCircuitBreaker` implementation
- States: CLOSED, OPEN, HALF_OPEN
- Automatic recovery testing
- Circuit breaker metrics

### ✅ Project isolation enforcement
- `ProjectIsolatedRedisClient` wrapper
- Automatic key prefixing: `proj:{project_id}:{key}`
- Validation in production environment

### ✅ OpenTelemetry instrumentation
- Redis operations automatically instrumented
- Span attributes for operations and project IDs
- Integration with existing OpenTelemetry setup

## Monitoring and Observability

### Health Check Response

```json
{
  "status": "healthy",
  "timestamp": 1697523456.789,
  "service": "redis",
  "factory": {
    "status": "healthy",
    "pools": {
      "default": {
        "created_connections": 5,
        "available_connections": 3,
        "max_connections": 10
      }
    },
    "circuit_breaker": {
      "state": "closed",
      "metrics": {
        "total_calls": 100,
        "success_rate": 0.98,
        "circuit_opens": 0
      }
    }
  },
  "test_operations": {
    "status": "passed",
    "response_times_ms": {
      "ping": 0.17,
      "set_get_delete": 0.42
    }
  },
  "memory": {
    "status": "healthy",
    "usage_percentage": 0.23,
    "usage_bytes": 117760,
    "max_memory_bytes": 512000
  }
}
```

### Metrics Collection

```python
from app.infrastructure.redis import redis_service

# Get service metrics
metrics = redis_service.get_metrics()
print(f"Service initialized: {metrics['initialized']}")
print(f"Active pools: {metrics['connection_factory']['pools_count']}")
print(f"Circuit breaker state: {metrics['connection_factory']['circuit_breaker']['state']}")
```

## Error Handling

### No Silent Fallbacks

Following project standards, this implementation **NEVER** uses silent fallbacks:

```python
# ❌ WRONG - Silent fallback
value = redis.get(key) or default_value

# ✅ CORRECT - Explicit error handling
try:
    value = await redis.get(key)
    if value is None:
        raise RedisKeyNotFoundException(key, project_id)
except RedisException:
    logger.error("Redis operation failed", exc_info=True)
    raise  # Preserve original context
```

### Graceful Degradation

When Redis is unavailable:
1. Circuit breaker opens after failure threshold
2. Operations fail fast with `RedisCircuitBreakerOpenException`
3. Application can implement fallback logic at business layer
4. No silent fallback to default values

## Testing

### Integration Tests

```bash
# Run Redis integration tests
docker-compose exec api pytest tests/test_infrastructure/test_redis_integration.py -v -m integration
```

### Manual Testing

```python
# Quick manual test
from app.infrastructure.redis import redis_service

async def test():
    await redis_service.initialize()

    async with redis_service.get_connection(project_id="test") as redis_client:
        await redis_client.ping()
        print("✅ Redis connection successful")

    health = await redis_service.health_check()
    print(f"✅ Health check: {health['status']}")

    await redis_service.close()
```

## Production Usage

### Startup Sequence

```python
# In main application startup
from app.infrastructure.redis import redis_service

async def startup():
    await redis_service.initialize()
    logger.info("Redis service initialized")

async def shutdown():
    await redis_service.close()
    logger.info("Redis service closed")
```

### API Integration

```python
# In API endpoints
from app.infrastructure.redis import redis_service
from app.infrastructure.redis.exceptions import RedisProjectIsolationException

@router.get("/projects/{project_id}/cache")
async def get_project_cache(project_id: UUID):
    try:
        async with redis_service.get_connection(str(project_id)) as redis_client:
            cached_data = await redis_client.get(f"project:{project_id}:data")
            return {"cached_data": cached_data}
    except RedisProjectIsolationException:
        raise HTTPException(400, "Project ID required")
    except RedisException as e:
        logger.error(f"Redis error: {e}")
        raise HTTPException(503, "Cache service unavailable")
```

## Security Considerations

### Project Isolation

- **Mandatory** `project_id` parameter in production environment
- Automatic key prefixing prevents cross-project data access
- Validation ensures project isolation cannot be bypassed

### Connection Security

- Redis AUTH password authentication required
- Network-level access restrictions via Docker networks
- Connection timeouts prevent hanging operations

### Memory Protection

- Memory usage monitoring with alerts at 80% and 90%
- Automatic LRU eviction configured in Redis
- Memory pressure detection and logging

## Performance Characteristics

### Connection Pooling

- Minimum 10 connections per pool (configurable)
- Connection reuse reduces overhead
- Health checks ensure connection validity

### Response Times

- Redis ping: < 1ms typical
- Set/Get operations: < 2ms typical
- Health check: < 100ms comprehensive

### Memory Usage

- Connection pools: ~1MB per 10 connections
- Circuit breaker metrics: negligible
- Health monitoring: negligible overhead

## Troubleshooting

### Common Issues

1. **Redis connection failed**
   - Check Redis service is running: `make redis-health`
   - Verify Redis URL and port configuration
   - Check Redis AUTH password

2. **Circuit breaker open**
   - Check Redis service health
   - Monitor error rates in logs
   - Circuit will auto-recover after timeout

3. **Project isolation errors**
   - Ensure `project_id` is provided in production
   - Check project ID format (UUID string)

### Debug Logging

```python
import logging
logging.getLogger("app.infrastructure.redis").setLevel(logging.DEBUG)
```

### Metrics Monitoring

Monitor these metrics:
- Circuit breaker state changes
- Connection pool utilization
- Operation response times
- Memory usage percentage
- Error rates and types

## Files

- `__init__.py` - Module exports
- `redis_service.py` - Main RedisService class
- `connection_factory.py` - Connection management and project isolation
- `circuit_breaker.py` - Circuit breaker implementation
- `exceptions.py` - Redis-specific exceptions
- `README.md` - This documentation

## Dependencies

- `redis==6.4.0+` - Async Redis client
- `opentelemetry-instrumentation-redis` - OpenTelemetry instrumentation
- `pydantic` - Configuration validation
- `tenacity` - Retry logic (for future use)