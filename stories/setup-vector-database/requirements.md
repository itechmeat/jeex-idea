# Requirements Document — Story "Setup Vector Database (Qdrant)"

## Introduction

This document specifies the functional and non-functional requirements for the Qdrant vector database setup in JEEX Idea. The vector database serves as the semantic memory layer for the multi-agent system, enabling context retrieval and knowledge management with strict project and language isolation.

All requirements follow the EARS (Easy Approach to Requirements Syntax) standard to ensure verifiability, testability, and unambiguous specification.

## System Context

**System Name:** Qdrant Vector Database Service

**Scope:** The Qdrant Vector Database Service encompasses the Qdrant 1.15.4+ container, collection management, payload filtering, server-side filter enforcement, health monitoring, and integration with the JEEX Idea backend services. The system boundary includes all components responsible for vector storage, semantic search, and multi-tenant data isolation.

**Dependencies:**

- Docker Development Environment (Story 1)
- PostgreSQL Database (Story 2) for project metadata including language
- Future Embedding Service (Story 12) for vector computation

## Functional Requirements

### REQ-001: Qdrant Service Initialization

**User Story Context:** As a backend developer, I want the Qdrant service to initialize automatically with the Docker stack, so that vector database capabilities are available immediately after system startup.

**EARS Requirements:**

1. When the Docker stack starts, the Qdrant service shall start within 40 seconds
2. When the Qdrant service starts, the system shall expose HTTP API on port 6333 (internal)
3. When the Qdrant service starts, the system shall map external port 5230 to internal port 6333
4. When the Qdrant service container starts, the system shall mount the persistent volume `qdrant_data` at `/qdrant/storage`
5. When the Qdrant service initializes, the system shall validate the Qdrant version is 1.15.4 or higher

**Rationale:** Automatic initialization ensures the vector database is ready for agent operations without manual intervention. Version validation guarantees access to multi-tenancy optimizations and payload filtering improvements.

**Traceability:** Links to design.md section "Proposed Architecture → Vector Database Architecture Overview"

### REQ-002: Collection Creation and Schema

**User Story Context:** As a backend developer, I want a unified collection with proper schema and indexing, so that all projects can share infrastructure while maintaining strict isolation.

**EARS Requirements:**

1. When the backend application starts, the Collection Manager shall create the `jeex_memory` collection if it does not exist
2. When creating the `jeex_memory` collection, the system shall configure vector parameters with size 1536 and distance metric Cosine
3. When creating the `jeex_memory` collection, the system shall configure HNSW with parameter `m` set to 16 and parameter `payload_m` set to 16
4. When creating the `jeex_memory` collection, the system shall configure HNSW with parameter `ef_construct` set to 100
5. When creating the `jeex_memory` collection, the system shall create payload index on field `project_id` with type Keyword
6. When creating the `jeex_memory` collection, the system shall create payload index on field `language` with type Keyword
7. When the collection creation completes, the system shall validate all required indexes exist

**Rationale:** Single collection with payload filtering balances operational simplicity with isolation requirements. HNSW configuration with `payload_m=16` optimizes for filtered search performance. Composite indexing on project_id and language enables fast multi-tenant queries.

**Traceability:** Links to design.md section "Collection Design" and "Multi-Tenancy Strategy"

### REQ-003: Server-Side Filter Enforcement

**User Story Context:** As a security engineer, I want all vector queries to be filtered by project_id AND language at the server side, so that cross-project and cross-language data leakage is impossible.

**EARS Requirements:**

1. When a vector search request is received, the Vector Search Service shall extract project_id from the request context
2. When a vector search request is received, the Vector Search Service shall extract language from the request context
3. If project_id is missing from the request context, then the Vector Search Service shall reject the request with error "Missing project_id"
4. If language is missing from the request context, then the Vector Search Service shall reject the request with error "Missing language"
5. When project_id and language are present, the Vector Search Service shall construct a Filter with mandatory conditions for both fields
6. When querying Qdrant, the Vector Search Service shall apply the mandatory Filter before executing vector search
7. When search results are returned, the Vector Search Service shall validate all results match the requested project_id and language

**Rationale:** Server-side filter enforcement prevents clients from bypassing isolation constraints. Fail-fast validation ensures no query executes without proper filtering. Result validation provides defense-in-depth against filter bugs.

**Traceability:** Links to design.md section "Multi-Tenancy Strategy" and "Security Considerations → Data Isolation"

### REQ-004: Vector Point Storage

**User Story Context:** As an agent developer, I want to store document embeddings with rich metadata, so that semantic search can retrieve relevant context with proper filtering.

**EARS Requirements:**

1. When storing a vector point, the system shall require payload field `project_id` as UUID string
2. When storing a vector point, the system shall require payload field `language` as ISO 639-1 code
3. When storing a vector point, the system shall validate the vector dimension is exactly 1536
4. If the vector dimension is not 1536, then the system shall reject the upsert operation with error "Invalid vector dimension"
5. When storing a vector point, the system shall compute content_hash from the text content for deduplication
6. When a vector point with duplicate content_hash exists, the system shall update the existing point instead of creating a duplicate
7. When upserting vector points, the system shall perform batch operations with batches of maximum 100 points

**Rationale:** Mandatory payload fields ensure all vectors are filterable by project and language. Dimension validation prevents embedding model mismatches. Content hashing enables deduplication. Batch operations optimize performance.

**Traceability:** Links to design.md section "Data Models → Vector Point Structure"

### REQ-005: Payload Schema Validation

**User Story Context:** As a backend developer, I want payload validation to prevent schema inconsistencies, so that indexed fields maintain their types and filtering works reliably.

**EARS Requirements:**

1. When upserting a vector point, the system shall validate payload field `project_id` is a valid UUID string
2. When upserting a vector point, the system shall validate payload field `language` is a valid ISO 639-1 code
3. When upserting a vector point, the system shall validate payload field `type` is one of: "knowledge", "memory", "agent_context"
4. If payload validation fails, then the system shall reject the upsert with a detailed validation error message
5. When payload contains field `created_at`, the system shall validate it is a valid ISO 8601 timestamp
6. When payload contains field `metadata.importance`, the system shall validate it is a number between 0.0 and 1.0

**Rationale:** Schema validation at service layer prevents malformed data from entering the vector database. Type validation ensures payload indexes function correctly. Clear error messages aid debugging.

**Traceability:** Links to design.md section "Data Models → Vector Point Structure"

### REQ-006: Health Monitoring and Validation

**User Story Context:** As a DevOps engineer, I want comprehensive health checks for the Qdrant service, so that monitoring systems can detect and alert on database issues.

**EARS Requirements:**

1. When the health check endpoint is called, the system shall verify Qdrant HTTP API is reachable on port 6333
2. When the health check endpoint is called, the system shall verify the `jeex_memory` collection exists
3. When the health check endpoint is called, the system shall verify all required payload indexes exist
4. If any health check fails, then the system shall return HTTP 503 with detailed failure information
5. When all health checks pass, the system shall return HTTP 200 with collection statistics
6. When health check completes, the system shall export metrics to OpenTelemetry collector

**Rationale:** Multi-level health checks (service, collection, indexes) provide granular failure detection. Detailed failure information aids troubleshooting. Metrics export enables monitoring dashboards.

**Traceability:** Links to design.md section "Components and Interfaces → Health Monitor"

### REQ-007: Query Performance Optimization

**User Story Context:** As a product manager, I want fast vector search responses, so that agent interactions feel responsive and real-time to users.

**EARS Requirements:**

1. When executing a vector search query, the system shall complete the search within 100ms at P95 percentile
2. When the collection contains more than 10,000 vectors for a single project, the system shall utilize payload indexes for filtering
3. When search results are returned, the system shall limit results to maximum 50 points per query
4. When multiple search requests arrive concurrently, the system shall handle at least 10 concurrent queries without degradation
5. If a search query exceeds 5 seconds, then the system shall cancel the query and return timeout error

**Rationale:** P95 latency under 100ms ensures responsive agent interactions. Payload index utilization maintains performance at scale. Result limiting prevents oversized responses. Timeout prevents hung queries.

**Traceability:** Links to design.md section "Performance Considerations → Query Optimization"

### REQ-008: Multi-Tenant Data Isolation

**User Story Context:** As a security engineer, I want absolute data isolation between projects, so that no agent can access another project's semantic memory.

**EARS Requirements:**

1. When querying vectors, the system shall filter results to only include points matching the provided project_id
2. When querying vectors, the system shall filter results to only include points matching the provided language
3. When a query includes project_id "A" and language "en", the system shall never return points with project_id "B"
4. When a query includes language "en", the system shall never return points with language "ru"
5. When inserting vectors, the system shall assign project_id from authenticated request context only
6. When inserting vectors, the system shall assign language from project metadata in PostgreSQL only
7. If a search result violates isolation constraints, then the system shall log a security alert and filter the result

**Rationale:** Dual filtering by project_id AND language provides defense-in-depth isolation. Immutable assignment from trusted sources prevents spoofing. Security alerts enable detection of filter bugs.

**Traceability:** Links to design.md section "Security Considerations → Data Isolation"

## Non-Functional Requirements

### PERF-001: Search Performance

While the `jeex_memory` collection contains up to 100,000 vector points, the Vector Search Service shall complete search queries with P95 latency below 100 milliseconds.

**Rationale:** Ensures responsive agent interactions even as semantic memory grows. P95 metric accounts for outliers while maintaining acceptable typical performance.

**Traceability:** Links to design.md section "Performance Considerations → Query Optimization"

### PERF-002: Indexing Performance

When upserting vector points in batches, the Vector Search Service shall process batches of 100 points within 500 milliseconds per batch.

**Rationale:** Efficient batch processing enables real-time embedding storage during agent document generation. 500ms per batch supports throughput of 200 vectors/second.

**Traceability:** Links to design.md section "Performance Considerations → Storage Optimization"

### SCALE-001: Storage Capacity

Where the system stores vector data, the Qdrant service shall support at least 1,000,000 vector points in the `jeex_memory` collection without performance degradation.

**Rationale:** Provides headroom for MVP growth (100 projects × 10,000 vectors each). Single-node Qdrant handles 1M vectors with proper configuration.

**Traceability:** Links to design.md section "Performance Considerations → Scalability Planning"

### SCALE-002: Concurrent Query Capacity

When multiple agents execute searches concurrently, the Qdrant service shall handle at least 100 concurrent queries per second with P95 latency below 100ms.

**Rationale:** Supports multi-agent architecture where multiple agents may search simultaneously. 100 QPS accommodates 10 concurrent projects with 10 agents each.

**Traceability:** Links to design.md section "Performance Considerations → Query Optimization"

### AVAIL-001: Service Availability

When the Docker stack is running, the Qdrant service shall maintain availability of 99.9% or higher during development.

**Rationale:** High availability ensures agents can access semantic memory without interruption. 99.9% allows ~8.6 hours downtime per year for maintenance.

**Traceability:** Links to design.md section "Error Handling Strategy → Connection Errors"

### AVAIL-002: Data Persistence

When the Qdrant container restarts, the system shall restore all vector points from persistent storage without data loss.

**Rationale:** Named volume persistence ensures semantic memory survives container restarts. Critical for development environment stability.

**Traceability:** Links to design.md section "Proposed Architecture → Vector Database Architecture Overview"

### SEC-001: Filter Enforcement

When any vector search query is executed, the Vector Search Service shall enforce mandatory project_id AND language filters without exception.

**Rationale:** Absolute requirement for multi-tenancy security. No query should bypass isolation constraints regardless of client behavior.

**Traceability:** Links to design.md section "Security Considerations → Data Isolation"

### SEC-002: Network Isolation

While the Qdrant service is running, the system shall restrict direct external access to Qdrant API and allow connections only from backend services on the `jeex-data` Docker network.

**Rationale:** Network isolation prevents unauthorized direct access to vector database. Backend service acts as security boundary.

**Traceability:** Links to design.md section "Security Considerations → Network Security"

### SEC-003: Audit Logging

When a search query is executed, the Vector Search Service shall log the query parameters including project_id, language, and query vector to audit trail.

**Rationale:** Audit logging enables security monitoring, debugging, and compliance verification. Logs support detection of filter bypass attempts.

**Traceability:** Links to design.md section "Security Considerations → Data Isolation"

### MAINT-001: Index Maintenance

When payload indexes are created or updated, the Collection Manager shall validate index status within 10 seconds.

**Rationale:** Fast index validation enables rapid feedback during development and deployment. 10-second timeout balances thoroughness with responsiveness.

**Traceability:** Links to design.md section "Components and Interfaces → Collection Manager Service"

### MAINT-002: Collection Health Validation

When the backend application starts, the Collection Manager shall validate collection schema compatibility and report any inconsistencies within 30 seconds.

**Rationale:** Startup validation prevents application launch with incompatible vector database schema. Early detection prevents runtime errors.

**Traceability:** Links to design.md section "Components and Interfaces → Collection Manager Service"

### COMPAT-001: Version Compatibility

Where Qdrant service is deployed, the system shall use Qdrant version 1.15.4 or higher to ensure multi-tenancy optimizations are available.

**Rationale:** Version 1.15.4 includes critical multi-tenancy optimizations and payload filtering improvements. Earlier versions lack required features.

**Traceability:** Links to design.md section "Overview" and specs.md minimum version requirements

### COMPAT-002: Embedding Model Compatibility

When storing vector points, the system shall accept vectors of exactly 1536 dimensions to maintain compatibility with OpenAI text-embedding-3-small model.

**Rationale:** Single embedding model for MVP simplifies infrastructure. 1536 dimensions is the output size of OpenAI text-embedding-3-small.

**Traceability:** Links to design.md section "Collection Design → Vector Configuration"

### MONITOR-001: Metrics Collection

When the Qdrant service is running, the Health Monitor shall export query latency, query count, and error rate metrics to OpenTelemetry collector every 30 seconds.

**Rationale:** Regular metrics export enables performance monitoring, capacity planning, and alerting on degradation.

**Traceability:** Links to design.md section "Components and Interfaces → Health Monitor"

### MONITOR-002: Performance Baselines

When query performance metrics are collected, the system shall establish baseline performance for P50, P95, and P99 latency percentiles.

**Rationale:** Performance baselines enable detection of regression and support capacity planning decisions.

**Traceability:** Links to design.md section "Performance Considerations → Query Optimization"

## Acceptance Test Scenarios

### Test Scenario for REQ-001: Qdrant Service Initialization

**Given:** Docker stack is stopped
**When:** Execute `make dev-up` command
**Then:** Qdrant container starts within 40 seconds AND health check passes AND HTTP API responds on port 5230

### Test Scenario for REQ-002: Collection Creation and Schema

**Given:** Qdrant service is running AND `jeex_memory` collection does not exist
**When:** Backend application starts and Collection Manager initializes
**Then:** Collection `jeex_memory` is created AND vector size is 1536 AND distance metric is Cosine AND HNSW config has `payload_m=16` AND payload indexes exist for `project_id` and `language`

### Test Scenario for REQ-003: Server-Side Filter Enforcement

**Given:** Collection contains vectors for project_id "A" with language "en" AND project_id "B" with language "ru"
**When:** Vector Search Service searches with project_id "A" and language "en"
**Then:** Results contain ONLY vectors with project_id "A" AND language "en" AND no vectors from project "B" are returned AND no vectors with language "ru" are returned

### Test Scenario for REQ-003 (Negative): Missing Filter Fields

**Given:** Vector Search Service receives a search request
**When:** Request context is missing project_id
**Then:** Vector Search Service rejects request with error "Missing project_id" AND no query is executed

### Test Scenario for REQ-004: Vector Point Storage

**Given:** Embedding service generates a 1536-dimension vector for a document chunk
**When:** Backend stores the vector with project_id "550e8400-e29b-41d4-a716-446655440000" and language "en"
**Then:** Vector is stored in Qdrant AND payload contains project_id "550e8400-e29b-41d4-a716-446655440000" AND payload contains language "en" AND content_hash is computed AND vector is retrievable via search

### Test Scenario for REQ-004 (Negative): Invalid Vector Dimension

**Given:** Attempt to store a vector with 512 dimensions
**When:** Vector Search Service validates the vector
**Then:** System rejects the upsert with error "Invalid vector dimension" AND no vector is stored

### Test Scenario for REQ-005: Payload Schema Validation

**Given:** Attempt to store a vector with invalid project_id format
**When:** Payload validation executes
**Then:** System rejects the upsert with error "Invalid project_id format" AND provides detailed validation message

### Test Scenario for REQ-006: Health Monitoring

**Given:** Qdrant service is running AND collection is properly configured
**When:** Health check endpoint `/health` is called
**Then:** Health check returns HTTP 200 AND response includes collection name AND response includes index status AND metrics are exported to OpenTelemetry

### Test Scenario for REQ-006 (Negative): Missing Collection

**Given:** Qdrant service is running AND `jeex_memory` collection does not exist
**When:** Health check endpoint is called
**Then:** Health check returns HTTP 503 AND response includes failure reason "Collection not found"

### Test Scenario for REQ-007: Query Performance

**Given:** Collection contains 50,000 vectors across 5 projects
**When:** Execute 100 search queries for a single project
**Then:** P95 latency is below 100ms AND all queries complete successfully AND no timeouts occur

### Test Scenario for REQ-008: Multi-Tenant Data Isolation

**Given:** Collection contains vectors for three projects:

- Project A (language: en, 1000 vectors)
- Project B (language: ru, 500 vectors)
- Project C (language: en, 750 vectors)

**When:** Search with project_id "A" and language "en"
**Then:** Results contain ONLY vectors from Project A AND results count is ≤ 1000 AND no vectors from Project B or C are returned

### Test Scenario for PERF-001: Search Performance at Scale

**Given:** Collection contains 100,000 vector points across 100 projects
**When:** Execute vector search for a project with 10,000 vectors
**Then:** P95 query latency is below 100ms AND result accuracy is maintained

### Test Scenario for SEC-001: Filter Enforcement

**Given:** Vector Search Service is configured
**When:** Any search query is executed
**Then:** Query includes mandatory filter for project_id AND query includes mandatory filter for language AND filter is constructed server-side AND client cannot modify filter

### Test Scenario for AVAIL-002: Data Persistence

**Given:** Collection contains 1,000 vector points
**When:** Qdrant container is restarted via `docker-compose restart qdrant`
**Then:** Container restarts successfully AND all 1,000 vector points are retrievable AND no data loss occurs
