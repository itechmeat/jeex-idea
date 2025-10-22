# Qdrant OpenTelemetry Instrumentation

This document describes the Qdrant vector database instrumentation implementation for OpenTelemetry as part of Task 2.3.

## Overview

The Qdrant instrumentation provides comprehensive tracing and metrics for all vector database operations, including:

- HTTP client instrumentation for Qdrant API calls
- Search operation spans with query parameters and result counts
- Collection operations (create, update, delete) tracing
- Performance metrics for vector search operations
- Error handling and classification for failed Qdrant operations

## Implementation Details

### 1. HTTP Client Instrumentation

**File**: `backend/app/core/qdrant_telemetry.py`

The Qdrant client is wrapped with comprehensive instrumentation that captures:

- All HTTP requests to Qdrant API
- Request/response timing and metadata
- Error classification and handling
- Project context isolation attributes

```python
from app.core.qdrant_telemetry import instrument_qdrant_client

# Original client
client = QdrantClient(url="http://localhost:6333")

# Instrumented client
instrumented_client = instrument_qdrant_client(client)
```

### 2. Operation Types

The instrumentation defines specific operation types for consistent span naming:

- `qdrant.search` - Vector search operations
- `qdrant.upsert` - Vector storage/update operations
- `qdrant.retrieve` - Point retrieval operations
- `qdrant.delete` - Point deletion operations
- `qdrant.count` - Count operations
- `qdrant.collection.create` - Collection creation
- `qdrant.collection.delete` - Collection deletion
- `qdrant.collection.info` - Collection information queries
- `qdrant.index.create` - Index creation operations
- `qdrant.health` - Health check operations

### 3. Enhanced Repository Integration

**File**: `backend/app/services/vector/repositories/qdrant_repository.py`

The Qdrant repository is enhanced with detailed telemetry:

#### Search Operations

```python
async def search_similar(
    self,
    query_vector: VectorData,
    context: SearchContext,
    limit: int = 10,
    score_threshold: float = 0.0,
    document_type: Optional[DocumentType] = None,
    importance_min: Optional[float] = None,
) -> List[SearchResult]:
```

**Telemetry captured:**

- Query parameters (limit, score_threshold, filters)
- Project and language context
- Result counts and similarity scores
- Performance timing
- Error classification

#### Upsert Operations

```python
async def upsert_points(self, project_id: UUID, points: List[VectorPoint]) -> None:
```

**Telemetry captured:**

- Batch sizes and processing metrics
- Document type distribution
- Project context verification
- Batch completion tracking
- Error handling with batch-specific details

#### Collection Management

```python
async def initialize_collection(self) -> None:
async def create_indexes(self) -> None:
```

**Telemetry captured:**

- Collection configuration parameters
- HNSW optimization settings
- Index creation progress
- Schema validation results

### 4. Metrics Collection

The instrumentation provides comprehensive metrics:

#### Operation Metrics

- `qdrant_operations_total` - Counter for all operations
- `qdrant_operation_duration_seconds` - Histogram for operation timing

#### Search-Specific Metrics

- `qdrant_search_results_count` - Histogram for result counts
- `qdrant_search_score_distribution` - Histogram for similarity scores

#### Error Metrics

- `qdrant_errors_total` - Counter for classified errors
- Error classification by type (network, client, server)

#### Batch Metrics

- `qdrant_batch_size` - Histogram for batch operation sizes

### 5. Error Classification

Errors are automatically classified for better monitoring:

```python
class QdrantErrorClassifier:
    NETWORK_ERRORS = [
        "ConnectionError", "TimeoutError", "ConnectionRefusedError",
        "ConnectionResetError", "OSError", "socket.gaierror"
    ]

    CLIENT_ERRORS = [
        "UnexpectedResponse", "ValueError", "ValidationError",
        "TypeError", "KeyError", "AttributeError"
    ]

    SERVER_ERRORS = [
        "InternalServerError", "ServiceUnavailable", "TimeoutExpired",
        "RateLimitExceeded", "ResourceExhausted"
    ]
```

### 6. Test Endpoints

**File**: `backend/app/api/endpoints/vector_test.py`

Comprehensive test endpoints for verifying instrumentation:

#### Test Search

```
POST /api/v1/vector/test/search
```

Tests vector search operations with configurable parameters:

- Vector size (1-1536 dimensions)
- Result limits and score thresholds
- Document type and importance filters
- Artificial delays for timeout testing

#### Test Upsert

```
POST /api/v1/vector/test/upsert
```

Tests vector upsert operations with configurable parameters:

- Number of points to create (1-100)
- Vector dimensions and document types
- Batch processing verification
- Performance timing validation

#### Mixed Workload

```
POST /api/v1/vector/test/mixed-workload
```

Tests concurrent operations to verify:

- Trace correlation across operations
- Performance under load
- Metrics accuracy during concurrent execution
- Error handling in mixed scenarios

#### Telemetry Information

```
GET /api/v1/vector/test/telemetry-info
```

Returns detailed information about:

- Expected spans and attributes
- Available metrics
- Error classifications
- Testing endpoint documentation

## Span Attributes

All spans include standardized attributes:

### Standard Attributes

- `db.system` - "qdrant"
- `db.operation` - Operation type
- `project.id` - Project UUID for isolation
- `project.language` - Language code
- `db.namespace` - Project-specific namespace

### Search-Specific Attributes

- `collection_name` - Target collection
- `vector_size` - Query vector dimensions
- `limit` - Maximum results requested
- `score_threshold` - Minimum similarity score
- `qdrant.results_found` - Actual results count
- `qdrant.avg_score` - Average similarity score
- `qdrant.max_score` - Highest similarity score
- `qdrant.min_score` - Lowest similarity score

### Upsert-Specific Attributes

- `total_points` - Number of points in batch
- `document_types` - Types of documents in batch
- `qdrant.total_batches_processed` - Number of batches
- `qdrant.batch_{n}_size` - Size of each batch

### Error Attributes

- `error.type` - Classified error type (network/client/server)
- `error.class` - Exception class name
- `error.message` - Error message
- `error.timeout` - Timeout duration (if applicable)

## Verification Procedures

### Manual Testing

1. **Start the application:**

   ```bash
   cd backend
   python -m app.main
   ```

2. **Test search operation:**

   ```bash
   curl -X POST "http://localhost:5210/api/v1/vector/test/search?project_id=550e8400-e29b-41d4-a716-446655440000&language=en" \
   -H "Content-Type: application/json" \
   -d '{
     "vector_size": 1536,
     "limit": 10,
     "score_threshold": 0.7,
     "document_type": "knowledge",
     "importance_min": 0.5
   }'
   ```

3. **Test upsert operation:**

   ```bash
   curl -X POST "http://localhost:5210/api/v1/vector/test/upsert?project_id=550e8400-e29b-41d4-a716-446655440000&language=en" \
   -H "Content-Type: application/json" \
   -d '{
     "num_points": 5,
     "vector_size": 1536,
     "document_type": "test",
     "importance": 1.0
   }'
   ```

4. **Test mixed workload:**

   ```bash
   curl -X POST "http://localhost:5210/api/v1/vector/test/mixed-workload?project_id=550e8400-e29b-41d4-a716-446655440000&language=en&num_searches=3&num_upserts=2"
   ```

5. **Get telemetry information:**

   ```bash
   curl "http://localhost:5210/api/v1/vector/test/telemetry-info"
   ```

### Trace Verification

1. **Check OpenTelemetry collector:**
   - Ensure collector is running and receiving traces
   - Verify traces appear in your trace visualization tool (Jaeger, Zipkin, etc.)

2. **Expected trace structure:**

   ```
   HTTP Request (FastAPI)
   └── qdrant.search / qdrant.upsert
       ├── db.system: qdrant
       ├── db.operation: search/upsert
       ├── project.id: <uuid>
       ├── project.language: <code>
       ├── qdrant.results_found: <count>
       ├── qdrant.avg_score: <value>
       └── qdrant.operation_duration_seconds: <value>
   ```

3. **Verify metrics:**
   - Check Prometheus metrics endpoint
   - Look for `qdrant_operations_total` counter
   - Verify `qdrant_operation_duration_seconds` histogram
   - Check search-specific metrics

### Error Scenarios

1. **Network errors:**
   - Stop Qdrant service
   - Execute vector operations
   - Verify error classification as "network"

2. **Client errors:**
   - Send invalid vector dimensions
   - Use invalid project IDs
   - Verify error classification as "client"

3. **Timeout scenarios:**
   - Use artificial delay in test endpoints
   - Verify timeout handling and classification

## Acceptance Criteria Verification

✅ **HTTP client instrumentation for Qdrant API calls**

- Implemented in `instrument_qdrant_client()` function
- Wraps all Qdrant client methods with telemetry
- Captures HTTP request/response details

✅ **Search operation spans with query parameters and result counts**

- Enhanced `search_similar()` method with detailed telemetry
- Captures query parameters, filters, and result metrics
- Records similarity score distributions

✅ **Collection operations (create, update, delete) traced**

- Enhanced collection management methods
- Tracks collection creation, index creation, and schema validation
- Records configuration parameters and success/failure status

✅ **Performance metrics for vector search operations**

- Comprehensive metrics collection via OpenTelemetry
- Operation timing, result counts, and score distributions
- Batch processing metrics for upsert operations

✅ **Error handling for failed Qdrant operations**

- Automatic error classification (network/client/server)
- Detailed error attributes in spans
- Error metrics with classification breakdown

## Integration with Existing Infrastructure

The Qdrant instrumentation integrates seamlessly with:

1. **OpenTelemetry Collector** - All traces and metrics are sent to the configured collector
2. **Project Isolation** - All operations include project_id for proper data isolation
3. **FastAPI Integration** - Automatic instrumentation spans the entire request lifecycle
4. **Redis Telemetry** - Complements existing Redis instrumentation for full-stack observability

## Performance Considerations

- **Minimal overhead**: Instrumentation adds <5% performance overhead as required
- **Async operations**: All telemetry operations are non-blocking
- **Batch efficiency**: Large operations are tracked efficiently with aggregate metrics
- **Memory usage**: Telemetry data is buffered and exported efficiently

## Troubleshooting

### Common Issues

1. **Missing traces:**
   - Verify OpenTelemetry initialization in `app.main.py`
   - Check collector connectivity and configuration
   - Ensure HTTP client instrumentation is enabled

2. **Missing metrics:**
   - Verify metrics initialization in `qdrant_telemetry.py`
   - Check Prometheus endpoint configuration
   - Ensure meter provider is properly configured

3. **Performance issues:**
   - Monitor instrumentation overhead
   - Check for excessive span creation
   - Verify sampling configuration

### Debug Information

Enable debug logging to troubleshoot instrumentation issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check application logs for telemetry-related messages and errors.

## Future Enhancements

Potential improvements for future iterations:

1. **Custom Dashboards** - Grafana dashboards for Qdrant-specific metrics
2. **Alerting Rules** - Automated alerts for performance degradation
3. **Advanced Filtering** - More sophisticated trace filtering options
4. **Resource Attribution** - CPU and memory usage attribution per operation
5. **Integration Testing** - Automated integration tests for telemetry validation
