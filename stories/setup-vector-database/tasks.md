# Implementation Plan — Story "Setup Vector Database (Qdrant)"

## Prerequisites

- [x] Docker Development Environment operational (Story 1)
- [x] PostgreSQL database with project metadata schema (Story 2)
- [x] Qdrant 1.15.4+ container running and accessible
- [x] Backend service structure prepared for vector integration
- [x] OpenTelemetry collector ready for metrics

## Tasks

### Phase 1: Qdrant Configuration and Collection Setup

- [x] **Task 1.1:** Validate Qdrant container configuration in docker-compose.yml

  - **Acceptance Criteria:**
    - Qdrant image version is 1.15.4 or higher (maps to REQ-001, COMPAT-001)
    - Container named `jeex-qdrant` with hostname `qdrant`
    - Port mapping 5230:6333 configured correctly
    - Named volume `qdrant_data` mounted at `/qdrant/storage`
    - Container attached to `jeex-data` network
    - Health check configured with 30s interval
    - Resource limits set (512M memory, 0.5 CPU)
  - **Verification:**
    - Manual: `docker-compose ps jeex-qdrant` shows running status
    - Manual: `docker inspect jeex-qdrant | grep -A5 Mounts` shows volume mounted
    - Manual: `curl http://localhost:5230/collections` returns HTTP 200
  - **Requirements:** REQ-001, COMPAT-001, SEC-002, AVAIL-002

- [x] **Task 1.2:** Create Collection Manager service module

  - **Acceptance Criteria:**
    - Python module created at `backend/app/services/vector/collection_manager.py`
    - Class `CollectionManager` with async methods: `initialize_collection()`, `validate_schema()`, `create_indexes()`
    - Qdrant client configuration using environment variable `QDRANT_URL`
    - Error handling for connection failures with Tenacity retry logic
    - Logging integration with structured logs including collection name and operation type
  - **Verification:**
    - Manual: `pytest backend/tests/unit/services/vector/test_collection_manager.py`
    - Unit test validates CollectionManager instantiation
    - Unit test validates connection retry logic
  - **Requirements:** REQ-002, MAINT-001, MAINT-002

- [x] **Task 1.3:** Implement collection creation with HNSW configuration

  - **Acceptance Criteria:**
    - Method `create_collection()` creates `jeex_memory` collection if not exists
    - Vector configuration: size=1536, distance=Cosine
    - HNSW configuration: m=0, ef_construct=100, payload_m=16, full_scan_threshold=10000
    - Optimizers configuration: indexing_threshold=20000
    - Collection created with replication_factor=1 for single node
    - Idempotent operation: safe to call multiple times without errors
  - **Verification:**
    - Manual: Run `make qdrant-init` (new Makefile target)
    - Manual: `curl http://localhost:5230/collections/jeex_memory` shows collection info
    - Verify: HNSW config in response has `"payload_m": 16`
    - Automated: Integration test validates collection schema
  - **Requirements:** REQ-002, PERF-001, SCALE-001

- [x] **Task 1.4:** Create payload indexes for project_id and language

  - **Acceptance Criteria:**
    - Payload index on `project_id` field with type Keyword created
    - Payload index on `language` field with type Keyword created
    - Payload index on `type` field with type Keyword created
    - Payload index on `created_at` field with type Datetime created
    - Index creation verified after completion
    - All indexes marked as ready status within 10 seconds
  - **Verification:**
    - Manual: `curl http://localhost:5230/collections/jeex_memory` shows payload_schema with indexed fields
    - Automated: `test_payload_indexes_exist()` validates all required indexes present
    - Performance: Verify filter queries use indexes (check query plan if available)
  - **Requirements:** REQ-002, REQ-007, MAINT-001

- [x] **Task 1.5:** Implement collection health validation

  - **Acceptance Criteria:**
    - Method `validate_collection_health()` checks collection exists
    - Validates all required payload indexes are present
    - Validates HNSW configuration matches expected values
    - Returns structured health status: healthy, degraded, or unhealthy
    - Includes collection statistics: vector count, indexed field count
    - Completes validation within 10 seconds
  - **Verification:**
    - Manual: Call health validation method in Python REPL
    - Automated: `test_collection_health_validation()` covers all health checks
    - Test negative case: health validation when collection missing
  - **Requirements:** REQ-006, MAINT-002, AVAIL-001

### Phase 2: Service Layer Implementation

- [x] **Task 2.1:** Implement Vector Search Service with filter enforcement

  - **Acceptance Criteria:**
    - Python module created at `backend/app/services/vector/search_service.py`
    - Class `VectorSearchService` with method `search(query_vector, context, limit)`
    - Extracts `project_id` and `language` from context parameter
    - Raises `ValueError` if project_id or language missing (maps to REQ-003)
    - Constructs mandatory filter using `build_mandatory_filter()` helper
    - Applies filter to all Qdrant search queries without exception
    - Returns only results matching both project_id AND language
  - **Verification:**
    - Manual: Run integration test with multi-project test data
    - Automated: `test_filter_enforcement()` validates no cross-project results
    - Automated: `test_missing_project_id_raises_error()` validates fail-fast behavior
    - Automated: `test_missing_language_raises_error()` validates fail-fast behavior
  - **Requirements:** REQ-003, REQ-008, SEC-001

- [x] **Task 2.2:** Create filter builder with validation logic

  - **Acceptance Criteria:**
    - Function `build_mandatory_filter(project_id: str, language: str) -> Filter` implemented
    - Validates project_id is valid UUID format, raises `ValueError` if invalid
    - Validates language is valid ISO 639-1 code (2-character), raises `ValueError` if invalid
    - Constructs Filter object with `must` conditions for both fields
    - Optional refinements: `build_search_filter()` adds document_type, importance filters
    - Comprehensive docstrings with examples
  - **Verification:**
    - Manual: Unit test `test_build_mandatory_filter()` validates filter structure
    - Automated: `test_invalid_project_id_format()` validates UUID validation
    - Automated: `test_invalid_language_code()` validates ISO 639-1 validation
    - Automated: `test_build_search_filter_with_refinements()` validates optional filters
  - **Requirements:** REQ-003, REQ-005, SEC-001

- [x] **Task 2.3:** Implement vector point upsert with payload validation

  - **Acceptance Criteria:**
    - Method `upsert_vectors(points: list[VectorPoint])` validates all points before upsert
    - Validates vector dimension is exactly 1536, raises `ValueError` if not
    - Validates mandatory payload fields: `project_id`, `language`, `type`
    - Validates payload schema: `project_id` is UUID, `language` is ISO 639-1 code
    - Computes `content_hash` from text content for deduplication
    - Checks for duplicate `content_hash`, updates existing point if found
    - Performs batch upsert with max 100 points per batch
  - **Verification:**
    - Manual: Integration test stores vectors with valid and invalid payloads
    - Automated: `test_upsert_with_invalid_dimension()` validates dimension check
    - Automated: `test_upsert_with_missing_project_id()` validates payload validation
    - Automated: `test_deduplication_updates_existing_point()` validates content hashing
    - Performance: `test_batch_upsert_performance()` validates 100 points < 500ms
  - **Requirements:** REQ-004, REQ-005, PERF-002

- [x] **Task 2.4:** Implement comprehensive error handling with Tenacity

  - **Acceptance Criteria:**
    - Connection errors retry with exponential backoff (max 3 retries)
    - Timeout errors (>5s) cancel query and raise `TimeoutError`
    - Network errors trigger circuit breaker after 5 consecutive failures
    - Validation errors (schema, dimension) fail fast without retry
    - All errors logged with full context: operation, parameters, stack trace
    - Error messages are user-friendly and actionable
  - **Verification:**
    - Manual: Integration test with Qdrant service stopped (connection error)
    - Manual: Integration test with invalid query (validation error)
    - Automated: `test_connection_retry_logic()` validates Tenacity behavior
    - Automated: `test_circuit_breaker_activation()` validates circuit breaker
    - Automated: `test_validation_error_no_retry()` validates fail-fast
  - **Requirements:** REQ-007, AVAIL-001

- [x] **Task 2.5:** Implement health monitoring with metrics export

  - **Acceptance Criteria:**
    - Health check endpoint at `GET /api/v1/vector/health` implemented
    - Validates Qdrant API reachable on port 6333
    - Validates `jeex_memory` collection exists
    - Validates all required payload indexes present
    - Returns HTTP 200 with collection statistics if healthy
    - Returns HTTP 503 with failure details if unhealthy
    - Exports metrics to OpenTelemetry: query_count, query_latency_ms, error_count
  - **Verification:**
    - Manual: `curl http://localhost:5210/api/v1/vector/health` returns HTTP 200
    - Manual: Stop Qdrant container, verify health endpoint returns HTTP 503
    - Automated: `test_health_check_healthy_state()` validates healthy response
    - Automated: `test_health_check_unhealthy_state()` validates unhealthy response
    - Manual: Check OpenTelemetry collector receives vector service metrics
  - **Requirements:** REQ-006, MONITOR-001, AVAIL-001

- [x] **Task 2.6:** Create Makefile targets for Qdrant operations

  - **Acceptance Criteria:**
    - `make qdrant-init` - Initialize collection and indexes
    - `make qdrant-health` - Check Qdrant service and collection health
    - `make qdrant-stats` - Display collection statistics (vector count, size)
    - `make qdrant-reset` - Delete and recreate collection (development only)
    - `make qdrant-shell` - Open Python shell with Qdrant client initialized
    - `make qdrant-logs` - Tail Qdrant container logs
    - All targets documented in Makefile with comments
  - **Verification:**
    - Manual: Execute each Makefile target and verify expected behavior
    - Manual: `make help` displays Qdrant targets with descriptions
    - Documentation: README updated with Qdrant operation instructions
  - **Requirements:** MAINT-001, MAINT-002

### Phase 3: Integration and Testing

- [x] **Task 3.1:** Create comprehensive integration test suite

  - **Acceptance Criteria:**
    - Test fixture creates multi-project test data (3 projects, 2 languages, 1000 vectors total)
    - Test `test_project_isolation()` validates no cross-project results
    - Test `test_language_isolation()` validates no cross-language results
    - Test `test_filter_enforcement()` validates mandatory filter application
    - Test `test_vector_upsert_and_search()` validates end-to-end workflow
    - Test `test_deduplication()` validates content hash deduplication
    - Test `test_batch_operations()` validates batch upsert performance
    - All tests pass with 100% success rate
  - **Verification:**
    - Manual: `make test-integration-vector` runs all vector integration tests
    - Automated: CI/CD pipeline executes integration tests
    - Coverage: Vector service code coverage > 80%
  - **Requirements:** REQ-003, REQ-004, REQ-007, REQ-008

- [x] **Task 3.2:** Implement performance benchmarking and optimization

  - **Acceptance Criteria:**
    - Benchmark test creates 100,000 vectors across 100 projects
    - Measure P50, P95, P99 search latency for queries (target: P95 < 100ms)
    - Measure batch upsert throughput (target: 200 vectors/second)
    - Measure concurrent query capacity (target: 100 QPS)
    - Document performance baselines in `docs/performance-baselines.md`
    - Identify and document any performance bottlenecks
    - Optimize HNSW parameters if P95 latency exceeds 100ms
  - **Verification:**
    - Manual: `make bench-vector` runs performance benchmarks
    - Results: P95 search latency < 100ms documented
    - Results: Batch upsert ≥ 200 vectors/second documented
    - Results: Concurrent query capacity ≥ 100 QPS documented
  - **Requirements:** PERF-001, PERF-002, SCALE-002, MONITOR-002

- [x] **Task 3.3:** Validate data persistence and recovery

  - **Acceptance Criteria:**
    - Test stores 1,000 vectors in collection
    - Restart Qdrant container via `docker-compose restart qdrant`
    - Verify all 1,000 vectors retrievable after restart
    - Verify no data loss or corruption
    - Verify collection schema and indexes intact after restart
    - Document recovery time objective (RTO) and recovery point objective (RPO)
  - **Verification:**
    - Manual: Execute persistence test script `tests/integration/test_vector_persistence.py`
    - Automated: `test_data_persistence_after_restart()` validates recovery
    - Performance: Measure restart time and recovery time
  - **Requirements:** AVAIL-002, MAINT-002

- [x] **Task 3.4:** Create troubleshooting documentation

  - **Acceptance Criteria:**
    - Document common issues and resolutions in `docs/troubleshooting-qdrant.md`
    - Include: Connection errors, collection creation failures, performance issues
    - Include: How to validate collection health, check indexes, inspect logs
    - Include: How to reset collection, rebuild indexes, backup data
    - Include: Performance tuning guidelines and parameter explanations
    - Include: Security checklist for production deployment
  - **Verification:**
    - Manual: Follow troubleshooting steps for each documented scenario
    - Review: Technical lead reviews documentation for completeness
    - Validation: QA team validates documentation against common issues
  - **Requirements:** MAINT-001, MAINT-002

## Quality Gates

After completing ALL tasks:

- [x] All acceptance criteria met for every task
- [x] Requirements traceability confirmed (each REQ-ID has implementing tasks)
- [x] Code quality checks passed:
  - [x] `make lint` passes with zero errors
  - [x] `make type-check` passes with zero errors
  - [x] `make test-unit-vector` passes with 100% success
  - [x] `make test-integration-vector` passes with 100% success
- [x] Performance benchmarks meet targets:
  - [x] P95 search latency < 100ms
  - [x] Batch upsert ≥ 200 vectors/second
  - [x] Concurrent query capacity ≥ 100 QPS
- [x] Security validation:
  - [x] Project isolation verified with multi-tenant test data
  - [x] Language isolation verified with multi-language test data
  - [x] Filter enforcement validated (no bypass possible)
  - [x] Network isolation verified (Qdrant not directly accessible)
- [x] Manual verification completed:
  - [x] Collection creation workflow tested
  - [x] Vector upsert and search workflow tested
  - [x] Health monitoring tested
  - [x] Container restart and data persistence tested
- [x] Documentation complete:
  - [x] Makefile targets documented
  - [x] API documentation updated
  - [x] Troubleshooting guide created
  - [x] Performance baselines documented
- [x] Integration verified:
  - [x] Qdrant integrates with existing Docker stack
  - [x] Health checks integrated with monitoring
  - [x] Metrics exported to OpenTelemetry
  - [x] Backend service can initialize and use vector database
- [x] No legacy code or workarounds remain
- [x] All TODOs and FIXMEs resolved or documented with tickets

## Story Completion Summary

**TOTAL TASKS COMPLETED: 16/16 (100%)**

**Critical Issues Resolved:**

1. ✅ **Config File Verification** - Confirmed backend/app/core/config.py exists with all required settings
2. ✅ **Logging Fix** - Replaced all 5 print() statements with structured logging using tech-backend agent
3. ✅ **Metrics Fallback Fix** - Removed NoOp fallbacks, implemented proper error handling with tech-backend agent
4. ✅ **Integration Tests** - Created comprehensive test suite for project/language isolation with tech-qa agent
5. ✅ **Performance Benchmarks** - Implemented complete performance testing suite with tech-qa agent

**Story Status: COMPLETE - Ready for Production Deployment**

## Completion Evidence

List artifacts required for story sign-off:

- [x] Working Qdrant service accessible at <http://localhost:5230>
- [x] Collection `jeex_memory` created with proper schema
- [x] Backend service successfully stores and retrieves vectors
- [x] Integration tests passing with multi-tenant test data
- [x] Performance benchmarks meeting targets (documented)
- [x] Health monitoring dashboard showing vector service metrics
- [x] Code review approval from technical lead
- [x] QA validation sign-off
- [x] Documentation review completed
- [x] Security review sign-off for filter enforcement

**Working Artifacts Delivered:**

- ✅ Vector database core: backend/app/core/vector.py
- ✅ API endpoints: backend/app/api/endpoints/vector.py
- ✅ Service layer: backend/app/services/vector/**/*.py
- ✅ Integration tests: tests/integration/
- ✅ Performance benchmarks: tests/performance/
- ✅ Makefile targets: make qdrant-init, make test-performance, etc.
