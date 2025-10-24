# Story 7: Setup Multi-Agent Framework — Requirements

All requirements follow EARS (Easy Approach to Requirements Syntax) patterns for clarity and verifiability.

## 1. Functional Requirements

### REQ-AGT-001: CrewAI Orchestrator Integration

**While** the system is processing a multi-agent workflow,  
**the orchestrator** shall initialize CrewAI crews with project-specific execution context (project_id, correlation_id, language).

**Verification:**

- Unit test: Orchestrator creates crew with context
- Integration test: Crew receives correct project_id and language

---

### REQ-AGT-002: Pydantic AI Contract Validation

**Where** an agent input or output is processed,  
**the system** shall validate data against Pydantic AI contract schemas and raise ValidationError for invalid data.

**Verification:**

- Contract test: Invalid input rejected with ValidationError
- Contract test: Valid input passes validation

---

### REQ-AGT-003: Product Manager Agent Skeleton

**When** the agent framework is initialized,  
**the system** shall provide a basic Product Manager agent skeleton capable of receiving delegation requests.

**Note:** Full Product Manager implementation is Story 8.

**Verification:**

- Unit test: Product Manager agent instantiates successfully
- Integration test: Product Manager accepts delegation request

---

### REQ-AGT-004: Execution Context Propagation

**When** an agent is invoked,  
**the execution context** shall include project_id (UUID, required), correlation_id (UUID, required), and language (string, required).

**Verification:**

- Unit test: Context creation includes all required fields
- Integration test: Context propagates to nested agent calls

---

### REQ-AGT-005: Agent Execution Tracking

**When** an agent execution starts,  
**the system** shall create a record in the agent_executions table with status "pending" and timestamp.

**When** an agent execution completes,  
**the system** shall update the record with status ("completed" or "failed"), end timestamp, and duration.

**Verification:**

- Integration test: Execution record created on start
- Integration test: Execution record updated on completion
- Database query: Records exist with correct status and timestamps

---

### REQ-AGT-006: Project Isolation Enforcement

**While** an agent is executing,  
**all database queries and vector searches** shall be filtered by project_id from execution context.

**If** an agent attempts to access data from a different project,  
**then** the system shall reject the operation and log a security warning.

**Verification:**

- Security test: Cross-project access attempt fails
- Integration test: Agent only accesses own project data

---

### REQ-AGT-007: Language Isolation Enforcement

**While** an agent is executing within a project,  
**all prompts and generated content** shall use the language specified in the project metadata.

**Verification:**

- Integration test: Agent receives correct language in context
- Manual test: Generated content matches project language

---

### REQ-AGT-008: Redis Execution State Management

**When** an agent workflow starts,  
**the system** shall store execution state in Redis with key pattern `agent:execution:{correlation_id}` and TTL of 24 hours.

**While** the workflow progresses,  
**the system** shall update the state to reflect current agent and progress percentage.

**Verification:**

- Integration test: Execution state stored in Redis
- Integration test: State updates during workflow
- Integration test: TTL set correctly

---

### REQ-AGT-009: Agent Contract Schemas

**Where** agent input/output is defined,  
**the contract schema** shall include:

- Base fields: project_id (UUID, required), correlation_id (UUID, required), language (string, required)
- Agent-specific fields: defined per agent type
- Validation rules: all required fields enforced

**Verification:**

- Contract test: Schema includes required base fields
- Contract test: Missing required field raises ValidationError

---

### REQ-AGT-010: ADK Protocol Stubs

**Where** future remote agent support is anticipated,  
**the system** shall provide protocol stub classes (RemoteAgentWrapper) that raise NotImplementedError.

**Note:** Full ADK implementation is post-MVP.

**Verification:**

- Unit test: Protocol stubs exist and can be instantiated
- Unit test: Remote invocation raises NotImplementedError

---

## 2. Non-Functional Requirements

### REQ-AGT-NFR-001: Agent Execution Performance

**When** an agent executes,  
**the execution duration** shall not exceed:

- Agent initialization: < 100ms (P95)
- Context loading: < 200ms (P95)
- Single agent execution: < 5s (P95)

**Verification:**

- Performance test: Measure and verify timing thresholds
- OpenTelemetry metrics: Monitor production performance

---

### REQ-AGT-NFR-002: Error Handling Resilience

**When** an agent encounters an error,  
**the system** shall:

- Log full error context with correlation_id
- Emit OpenTelemetry error span
- Return sanitized error message to user (no internal details)
- Prevent API crash (graceful degradation)

**Verification:**

- Integration test: Agent error doesn't crash API
- Integration test: Error logged with correlation_id
- Security test: User-facing error contains no secrets

---

### REQ-AGT-NFR-003: Circuit Breaker Pattern

**If** an agent fails more than 5 times consecutively,  
**then** the circuit breaker shall open and reject subsequent requests for 60 seconds.

**Verification:**

- Integration test: Circuit breaker opens after threshold
- Integration test: Circuit breaker closes after timeout

---

### REQ-AGT-NFR-004: OpenTelemetry Integration

**When** an agent operation occurs,  
**the system** shall emit traces with spans:

- `agent.execution.start`
- `agent.execution.complete`
- `agent.delegation`
- `agent.context.load`

**While** emitting traces,  
**the system** shall include attributes: project_id (one-way SHA-256 hashed), agent_type, stage, status, language.

**Where** project_id appears as a trace attribute,  
**the system** shall transform the raw UUID to its SHA-256 hex digest before attaching it to OpenTelemetry spans (the raw UUID must never be logged or transmitted in telemetry data).

**Verification:**

- Integration test: Traces emitted with correct span names
- Integration test: Attributes present and correct
- Manual test: Traces visible in observability dashboard

---

### REQ-AGT-NFR-005: Dependency Version Compliance

**Where** agent framework dependencies are installed,  
**the system** shall use:

- CrewAI >= 0.186.1
- Pydantic AI >= 1.0.8
- Tenacity >= 9.0.0

**Verification:**

- CI test: Dependency versions meet minimums
- Manual review: `requirements.txt` contains correct versions

---

## 3. Security Requirements

### REQ-AGT-SEC-001: Project ID Immutability

**While** an agent is executing,  
**the project_id in execution context** shall be immutable (cannot be modified after creation).

**Verification:**

- Unit test: Execution context fields are frozen
- Integration test: Attempt to modify project_id raises error

---

### REQ-AGT-SEC-002: Input Sanitization

**When** agent input data is logged or traced,  
**the system** shall sanitize sensitive fields (user_message content, personal data).

**Verification:**

- Integration test: Logs don't contain raw user_message
- Manual review: Trace data sanitized

---

### REQ-AGT-SEC-003: Agent Execution Authorization

**When** an agent workflow is initiated,  
**the system** shall verify that the requesting user has access to the project_id in context.

**Verification:**

- Integration test: Unauthorized user request rejected
- Integration test: Authorized user request succeeds

---

## 4. Data Requirements

### REQ-AGT-DAT-001: Agent Executions Persistence

**When** an agent execution occurs,  
**the following data** shall be persisted to agent_executions table:

- id (UUID, primary key)
- project_id (UUID, foreign key, required)
- agent_type (string, required)
- correlation_id (UUID, required)
- input_data (JSONB, sanitized)
- output_data (JSONB, sanitized)
- status (enum: pending, running, completed, failed)
- error_message (text, optional)
- started_at (timestamp, required)
- completed_at (timestamp, optional)
- duration_ms (integer, optional)

**Verification:**

- Database schema test: All fields exist with correct types
- Integration test: Data persisted correctly

---

### REQ-AGT-DAT-002: Redis State Expiration

**When** execution state is stored in Redis,  
**the TTL** shall be set to 24 hours to prevent memory bloat.

**Verification:**

- Integration test: Redis key has TTL set
- Integration test: Key expires after TTL

---

## 5. Integration Requirements

### REQ-AGT-INT-001: FastAPI Dependency Injection

**Where** agent orchestrator is used in API endpoints,  
**the orchestrator** shall be injectable via FastAPI dependency system.

**Verification:**

- Integration test: Endpoint receives orchestrator via DI
- Unit test: Dependency provider returns orchestrator instance

---

### REQ-AGT-INT-002: PostgreSQL Transaction Safety

**When** an agent updates multiple database records,  
**the operations** shall execute within a database transaction (ACID guarantees).

**If** any operation fails,  
**then** all changes shall be rolled back.

**Verification:**

- Integration test: Partial failure triggers rollback
- Integration test: Successful execution commits all changes

---

### REQ-AGT-INT-003: Qdrant Context Loading

**When** an agent loads project context from Qdrant,  
**the query** shall filter by both project_id AND language.

**Verification:**

- Integration test: Query includes both filters
- Integration test: Results match project and language

---

## 6. Testing Requirements

### REQ-AGT-TST-001: Unit Test Coverage

**Where** agent framework code is written,  
**the unit test coverage** shall be >= 90% for:

- Contract validation
- Execution context management
- Agent execution tracker
- Error handling logic

**Verification:**

- CI test: Coverage report meets threshold
- Manual review: Critical paths tested

---

### REQ-AGT-TST-002: Integration Test Coverage

**Where** agent orchestration is implemented,  
**integration tests** shall verify:

- End-to-end agent execution flow
- Database persistence
- Redis state management
- Project and language isolation

**Verification:**

- CI test: Integration tests pass
- Manual review: All scenarios covered

---

### REQ-AGT-TST-003: Contract Validation Tests

**Where** Pydantic AI contracts are defined,  
**contract tests** shall verify:

- Valid input passes validation
- Invalid input raises ValidationError
- All required fields enforced
- Output structure correctness

**Verification:**

- CI test: Contract tests pass
- Manual review: All contracts tested

---

## 7. Documentation Requirements

### REQ-AGT-DOC-001: API Contract Documentation

**Where** agent contracts are defined,  
**the documentation** shall include:

- Contract schema (OpenAPI/JSON Schema)
- Field descriptions
- Validation rules
- Example input/output

**Verification:**

- Manual review: OpenAPI docs generated
- Manual review: Examples provided

---

### REQ-AGT-DOC-002: Developer Guide

**Where** developers create new agents,  
**the developer guide** shall document:

- How to define Pydantic AI contracts
- How to integrate with orchestrator
- How to test agent implementations
- How to emit telemetry

**Verification:**

- Manual review: Guide exists and is complete
- Manual review: Examples are functional

---

## 8. Deployment Requirements

### REQ-AGT-DEP-001: Database Migration

**When** the agent framework is deployed,  
**the database migration** shall:

- Verify agent_executions table exists
- Add duration_ms column if missing
- Create required indexes

**Verification:**

- Migration test: Migration runs successfully
- Database test: Schema matches expectations

---

### REQ-AGT-DEP-002: Configuration Management

**Where** agent framework is configured,  
**the configuration** shall support:

- Max retry attempts (default: 3)
- Retry delay (default: 1 second)
- Circuit breaker threshold (default: 5 failures)
- Execution timeout (default: 300 seconds)

**Verification:**

- Integration test: Configuration values respected
- Manual review: Environment variables documented

---

## 9. Compliance Requirements

### REQ-AGT-CMP-001: No Production Fallbacks

**Where** agent framework code is written for production paths,  
**the code** shall NOT contain:

- Mock implementations
- Stub implementations with fallback logic
- Hardcoded default values for project_id or language

**If** a feature is not implemented,  
**then** raise NotImplementedError with TODO comment.

**Verification:**

- Code review: No mocks/stubs outside test directories
- Static analysis: No fallback patterns detected

---

### REQ-AGT-CMP-002: Project ID Mandatory

**Where** agent input contracts are defined,  
**the project_id field** shall be:

- Type: UUID
- Required: True (never Optional)
- Validated: Must be valid UUID format

**Verification:**

- Contract test: Missing project_id raises ValidationError
- Contract test: Invalid UUID format raises ValidationError

---

## 10. Traceability Matrix

| Requirement ID  | Design Section          | Test Location                     |
| --------------- | ----------------------- | --------------------------------- |
| REQ-AGT-001     | 4.1 CrewAI Orchestrator | `test_orchestrator.py`            |
| REQ-AGT-002     | 4.2 Pydantic Contracts  | `test_agent_contracts.py`         |
| REQ-AGT-003     | 4.1 Orchestrator        | `test_product_manager.py`         |
| REQ-AGT-004     | 4.3 Context Manager     | `test_execution_context.py`       |
| REQ-AGT-005     | 4.4 Execution Tracker   | `test_agent_tracking.py`          |
| REQ-AGT-006     | 6.1 Project Isolation   | `test_project_isolation.py`       |
| REQ-AGT-007     | 6.2 Language Isolation  | `test_language_isolation.py`      |
| REQ-AGT-008     | 4.3 Context Manager     | `test_redis_state.py`             |
| REQ-AGT-009     | 4.2 Pydantic Contracts  | `test_contract_schemas.py`        |
| REQ-AGT-010     | 4.5 ADK Protocol        | `test_adk_stubs.py`               |
| REQ-AGT-NFR-001 | 7.2 Performance         | `test_performance.py`             |
| REQ-AGT-NFR-002 | 6.3 Error Handling      | `test_error_handling.py`          |
| REQ-AGT-NFR-003 | 6.3 Error Handling      | `test_circuit_breaker.py`         |
| REQ-AGT-NFR-004 | 7.1 Observability       | `test_telemetry.py`               |
| REQ-AGT-NFR-005 | 9.2 Dependencies        | `test_dependencies.py`            |
| REQ-AGT-SEC-001 | 6.1 Security            | `test_context_immutability.py`    |
| REQ-AGT-SEC-002 | 6.3 Error Handling      | `test_input_sanitization.py`      |
| REQ-AGT-SEC-003 | 6.1 Security            | `test_authorization.py`           |
| REQ-AGT-DAT-001 | 5.1 Data Models         | `test_agent_executions_schema.py` |
| REQ-AGT-DAT-002 | 5.2 Redis State         | `test_redis_ttl.py`               |
| REQ-AGT-INT-001 | 4.1 Orchestrator        | `test_fastapi_integration.py`     |
| REQ-AGT-INT-002 | 4.4 Tracker             | `test_transaction_safety.py`      |
| REQ-AGT-INT-003 | 4.3 Context             | `test_qdrant_filtering.py`        |
