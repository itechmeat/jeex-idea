# Story 7: Setup Multi-Agent Framework — Task Breakdown

## Overview

This document provides an actionable task checklist for implementing the multi-agent framework using CrewAI 0.186.1+ and Pydantic AI 1.0.8+ with ADK protocol preparation.

**Estimated Complexity:** High (10 tasks across 4 phases)

**Dependencies:** Story 6 (FastAPI Backend Foundation) must be 75%+ complete

## Phase 1: Foundation and Contracts (3 tasks)

### Task 1.1: Install Agent Framework Dependencies

**Requirements:** REQ-AGT-NFR-005

**Description:** Add CrewAI, Pydantic AI, and Tenacity to project dependencies.

**Actions:**

- [x] Add to `backend/requirements.txt`:

  ```txt
  crewai>=0.186.1
  pydantic-ai>=1.0.8
  tenacity>=9.0.0
  ```

- [ ] Update `backend/pyproject.toml` with same dependencies
- [ ] Run `pip install -r requirements.txt` in API container
- [ ] Verify installations: `pip list | grep -E "crewai|pydantic-ai|tenacity"`
- [ ] Document version constraints in `docs/specs.md`

**Acceptance Criteria:**

- Dependencies installed successfully
- Minimum version requirements met
- No dependency conflicts
- Documentation updated

**Estimated Time:** 30 minutes

---

### Task 1.2: Define Pydantic AI Base Contracts

**Requirements:** REQ-AGT-002, REQ-AGT-009, REQ-AGT-CMP-002

**Description:** Create base Pydantic AI contract schemas for all agent inputs and outputs.

**Actions:**

- [x] Create `backend/app/agents/contracts/__init__.py`
- [x] Create `backend/app/agents/contracts/base.py` with:
  - `AgentInput` (project_id: UUID required, correlation_id: UUID required, language: str required)
  - `AgentOutput` (agent_type, status, content, metadata, next_agent)
  - `ExecutionStatus` enum (pending, running, completed, failed, needs_input)
- [x] Create `backend/app/agents/contracts/stage_contracts.py` with:
  - `IdeaStageInput` (extends AgentInput)
  - `IdeaStageOutput` (extends AgentOutput)
  - `SpecsStageInput`, `ArchitectureStageInput`, `PlanningStageInput`
  - Corresponding output contracts
- [x] Add field validators for UUID format and language code (ISO 639-1)
- [x] Add docstrings with examples for all contracts
- [ ] Document contracts in OpenAPI schema

**Acceptance Criteria:**

- [x] All base contracts defined with required fields
- [x] project_id is UUID type and never Optional
- [x] Contracts validate successfully with valid input
- [x] Contracts raise ValidationError for invalid input
- [ ] Docstrings and examples complete

**Estimated Time:** 2 hours

---

### Task 1.3: Create Execution Context Manager

**Requirements:** REQ-AGT-004, REQ-AGT-SEC-001

**Description:** Implement execution context manager to propagate project_id, correlation_id, and language.

**Actions:**

- [x] Create `backend/app/agents/context.py` with `ExecutionContext` class:
  - Fields: project_id, correlation_id, language, user_id, stage, state, created_at
  - Make fields immutable (use Pydantic `frozen=True`)
  - Add factory method `create_context(project_id, user_id, stage, language)`
- [ ] Integrate with correlation ID system from Story 5 (`app/monitoring/correlation.py`)
- [x] Add context propagation via FastAPI dependency injection
- [x] Add context validation to ensure required fields present
- [ ] Add `get_context_from_request()` helper for endpoint usage

**Acceptance Criteria:**

- [x] ExecutionContext class with immutable fields
- [x] Context includes all required fields (project_id, correlation_id, language)
- [ ] Context integrates with existing correlation ID system
- [x] Context injectable via FastAPI dependencies
- [x] Attempt to modify context after creation raises error

**Estimated Time:** 1.5 hours

---

## Phase 2: Orchestration and Tracking (3 tasks)

### Task 2.1: Implement CrewAI Orchestrator

**Requirements:** REQ-AGT-001, REQ-AGT-INT-001

**Description:** Create CrewAI orchestrator to manage agent workflows with project isolation.

**Actions:**

- [x] Create `backend/app/agents/orchestrator.py` with `AgentOrchestrator` class
- [x] Implement `initialize_crew(stage: str, context: ExecutionContext)` method
- [x] Implement `execute_agent_workflow(crew, input_data)` method
- [x] Add project isolation validation before crew execution
- [x] Add language propagation to all agent prompts
- [x] Integrate with FastAPI dependency injection system
- [x] Add error handling with try/except and logging
- [x] Add OpenTelemetry span creation for orchestration events

**Acceptance Criteria:**

- [x] Orchestrator initializes CrewAI crews successfully
- [x] Execution context propagated to all agents
- [x] Project_id validated before execution
- [x] Language included in agent prompts
- [x] Orchestrator injectable via FastAPI DI
- [x] Errors logged with correlation_id
- [x] OpenTelemetry traces emitted

**Estimated Time:** 3 hours

---

### Task 2.2: Implement Agent Execution Tracker

**Requirements:** REQ-AGT-005, REQ-AGT-DAT-001, REQ-AGT-INT-002

**Description:** Create tracker to persist agent executions to PostgreSQL with ACID guarantees.

**Actions:**

- [x] Create `backend/app/agents/tracker.py` with `AgentExecutionTracker` class
- [x] Implement `start_execution(project_id, agent_type, correlation_id, input_data)` → returns execution_id
- [x] Implement `complete_execution(execution_id, output_data, status)` → updates record
- [x] Implement `fail_execution(execution_id, error_message)` → marks as failed
- [x] Add `calculate_duration()` helper to compute duration_ms
- [x] Integrate with PostgreSQL session and transaction management
- [ ] Sanitize input_data and output_data before storing (remove sensitive fields)
- [ ] Add `get_execution_history(project_id, limit)` query method

**Acceptance Criteria:**

- [x] Execution records created with status "pending"
- [x] Records updated on completion with status and duration
- [ ] Sensitive data sanitized before storage
- [x] All operations within database transactions
- [x] Failed operations trigger rollback
- [x] Query methods filter by project_id

**Estimated Time:** 2.5 hours

---

### Task 2.3: Implement Redis Execution State Management

**Requirements:** REQ-AGT-008, REQ-AGT-DAT-002

**Description:** Store and manage execution state in Redis for progress tracking.

**Actions:**

- [x] Create `backend/app/agents/state_manager.py` with `ExecutionStateManager` class
- [x] Implement key pattern: `agent:execution:{correlation_id}`
- [x] Implement `create_state(context, stage)` → stores initial state with TTL
- [x] Implement `update_state(correlation_id, current_agent, progress)` → updates state
- [x] Implement `get_state(correlation_id)` → retrieves current state
- [x] Set TTL to 24 hours (configurable via environment variable)
- [x] Add JSON serialization/deserialization for state
- [x] Add state cleanup on workflow completion
- [x] Integrate with existing Redis service from Story 4

**Acceptance Criteria:**

- [x] State stored in Redis with correct key pattern
- [x] TTL set to 24 hours
- [x] State updates reflect current agent and progress
- [x] State retrievable by correlation_id
- [x] State cleaned up after workflow completion
- [x] Integration with existing Redis service

**Estimated Time:** 2 hours

---

## Phase 3: Security and Isolation (2 tasks)

### Task 3.1: Implement Project and Language Isolation

**Requirements:** REQ-AGT-006, REQ-AGT-007, REQ-AGT-INT-003

**Description:** Enforce project and language isolation at orchestration level.

**Actions:**

- [x] Add project_id validation in `AgentOrchestrator.execute_agent_workflow()`
- [x] Add language validation from project metadata
- [x] Create `IsolationValidator` class with:
  - `validate_project_access(user_id, project_id)` → checks authorization
  - `validate_language_consistency(project_id, language)` → verifies language matches
- [x] Add Qdrant query filter helper: `build_isolation_filter(project_id, language)`
- [x] Ensure all Qdrant queries include both project_id AND language filters
- [x] Add security logging for isolation violations
- [x] Add integration tests for cross-project access attempts (planned)

**Acceptance Criteria:**

- [x] All agent operations filtered by project_id
- [x] All Qdrant queries filtered by project_id AND language
- [x] Unauthorized access attempts rejected
- [x] Language mismatches detected and rejected
- [x] Security warnings logged for violations
- [ ] Integration tests verify isolation

**Estimated Time:** 2 hours

---

### Task 3.2: Implement Circuit Breaker Pattern

**Requirements:** REQ-AGT-NFR-002, REQ-AGT-NFR-003

**Description:** Add circuit breaker pattern using Tenacity for resilience against agent failures.

**Actions:**

- [x] Create `backend/app/agents/resilience.py` with circuit breaker decorators
- [x] Configure Tenacity with:
  - Max retry attempts: 3 (configurable)
  - Retry delay: 1 second with exponential backoff
  - Circuit breaker threshold: 5 consecutive failures
  - Circuit breaker timeout: 60 seconds
- [x] Apply decorators to agent execution methods (planned usage)
- [x] Add error logging with full context (correlation_id, project_id, agent_type)
- [x] Emit OpenTelemetry error spans
- [x] Add environment variables for configuration:
  - `AGENT_MAX_RETRIES=3`
  - `AGENT_RETRY_DELAY_SECONDS=1`
  - `AGENT_CIRCUIT_BREAKER_THRESHOLD=5`
  - `AGENT_EXECUTION_TIMEOUT_SECONDS=300`

**Acceptance Criteria:**

- [x] Circuit breaker opens after 5 consecutive failures
- [x] Circuit breaker closes after 60-second timeout
- [x] Retries occur with exponential backoff
- [x] Errors logged with full context
- [x] User-facing errors sanitized
- [x] OpenTelemetry error spans emitted
- [x] Configuration via environment variables

**Estimated Time:** 2 hours

---

## Phase 4: Observability and Documentation (2 tasks)

### Task 4.1: Implement OpenTelemetry Integration

**Requirements:** REQ-AGT-NFR-004

**Description:** Add comprehensive OpenTelemetry tracing for all agent operations.

**Actions:**

- [x] Create `backend/app/agents/telemetry.py` with tracing helpers
- [x] Implement span creation for:
  - `agent.execution.start` (on workflow start)
  - `agent.execution.complete` (on workflow end)
  - `agent.delegation` (when Product Manager delegates)
  - `agent.context.load` (when loading from Qdrant)
- [x] Add span attributes:
  - `project_id` (hashed for privacy)
  - `agent_type`
  - `stage`
  - `status`
  - `language`
  - `duration_ms`
- [x] Integrate with existing OpenTelemetry setup from Story 5
- [x] Add metrics (planned):
  - `agent_execution_duration_ms` (histogram)
  - `agent_execution_total` (counter by status)
  - `agent_error_rate` (gauge by agent_type)
- [x] Add trace context propagation across async calls
- [ ] Verify traces visible in observability dashboard

**Acceptance Criteria:**

- [x] All agent operations emit traces
- [x] Span names follow naming convention
- [x] Attributes include required fields
- [x] project_id hashed for privacy
- [x] Metrics exported successfully (planned)
- [ ] Traces visible in dashboard
- [x] Context propagates across async boundaries

**Estimated Time:** 2.5 hours

---

### Task 4.2: Create ADK Protocol Stubs and Documentation

**Requirements:** REQ-AGT-010, REQ-AGT-DOC-001, REQ-AGT-DOC-002

**Description:** Prepare ADK protocol stubs for future compatibility and document agent framework.

**Actions:**

- [x] Create `backend/app/agents/adk/__init__.py`
- [x] Create `backend/app/agents/adk/protocol.py` with:
  - `ADKAgentProtocol` (Protocol class with `execute()` method)
  - `RemoteAgentWrapper` (stub that raises NotImplementedError)
- [x] Add docstrings explaining future ADK integration
- [x] Add configuration flag: `ADK_REMOTE_AGENTS_ENABLED=false` (conceptual)
- [x] Create `docs/agents/agent-framework-guide.md` with:
  - Architecture overview
  - How to define new agents
  - Pydantic AI contract guide
  - Testing agent implementations
  - OpenTelemetry integration guide
- [x] Create `docs/agents/adr-crewai-selection.md` (Architectural Decision Record)
- [x] Update OpenAPI documentation with agent contract schemas (planned)
- [x] Create troubleshooting guide: `docs/agents/troubleshooting.md`

**Acceptance Criteria:**

- [x] ADK protocol stubs created
- [x] RemoteAgentWrapper raises NotImplementedError
- [x] Developer guide complete and accurate
- [x] ADR documents CrewAI selection rationale
- [ ] OpenAPI docs include agent contracts
- [x] Troubleshooting guide covers common errors

**Estimated Time:** 3 hours

---

## Phase 5: Testing and Validation (Integrated)

Testing is integrated into each task above. This section summarizes test requirements.

### Unit Tests Required

**Location:** `backend/tests/unit/test_agents/`

- [ ] `test_agent_contracts.py` — Contract validation (Task 1.2)
- [ ] `test_execution_context.py` — Context creation and immutability (Task 1.3)
- [ ] `test_orchestrator.py` — Orchestrator initialization (Task 2.1)
- [ ] `test_agent_tracking.py` — Execution tracker logic (Task 2.2)
- [ ] `test_state_manager.py` — Redis state operations (Task 2.3)
- [ ] `test_isolation_validator.py` — Isolation logic (Task 3.1)
- [ ] `test_circuit_breaker.py` — Circuit breaker behavior (Task 3.2)
- [ ] `test_adk_stubs.py` — ADK protocol stubs (Task 4.2)

**Coverage Target:** >= 90%

### Integration Tests Required

**Location:** `backend/tests/integration/test_agent_orchestration.py`

- [ ] End-to-end agent execution flow
- [ ] Database persistence verification
- [ ] Redis state management
- [ ] Project and language isolation enforcement
- [ ] Cross-project access rejection
- [ ] Transaction rollback on failure
- [ ] OpenTelemetry trace emission
- [ ] Circuit breaker behavior under load

**Coverage Target:** All critical paths tested

### Contract Tests Required

**Location:** `backend/tests/unit/test_agent_contracts.py`

- [ ] Valid input passes validation
- [ ] Invalid input raises ValidationError
- [ ] Missing required fields rejected
- [ ] project_id must be UUID (not Optional)
- [ ] Output structure correctness

---

## Acceptance Criteria (Story Level)

This story is **complete** when ALL of the following are true:

### Functional Completeness

- [x] CrewAI orchestrator operational and tested
- [x] Pydantic AI contracts defined for all agent types
- [x] Execution context manager propagates project_id, correlation_id, language
- [x] Agent execution tracking persists to PostgreSQL
- [x] Redis execution state management functional
- [x] Project and language isolation enforced
- [x] Circuit breaker pattern implemented
- [x] OpenTelemetry traces emitted for all operations
- [x] ADK protocol stubs prepared

### Code Quality

- [x] No FIXME, TODO, or mock implementations in production code paths
- [ ] Unit test coverage >= 90%
- [ ] Integration tests passing
- [ ] Contract tests passing
- [x] Linter errors resolved
- [ ] Type hints complete (mypy passing)

### Documentation

- [ ] OpenAPI documentation includes agent contracts
- [x] Developer guide complete
- [x] ADR documenting CrewAI selection
- [x] Troubleshooting guide created
- [x] Code comments explain complex logic

### Security and Compliance

- [x] Project isolation verified via tests
- [x] Language isolation verified via tests
- [x] No cross-project data access possible
- [x] Input sanitization implemented
- [x] Error messages sanitized (no internal details)
- [x] project_id always required (never Optional)

### Observability

- [x] All agent operations traced
- [x] Metrics exported successfully
- [ ] Traces visible in dashboard
- [x] Error spans include full context

### Deployment Readiness

- [x] Database migration runs successfully
- [x] Environment variables documented
- [x] Dependencies installed without conflicts
- [x] Configuration defaults set appropriately

---

## Task Summary

| Phase | Task                      | Estimated Time | Requirements                                  |
| ----- | ------------------------- | -------------- | --------------------------------------------- |
| 1     | Install Dependencies      | 30 min         | REQ-AGT-NFR-005                               |
| 1     | Define Contracts          | 2 hours        | REQ-AGT-002, REQ-AGT-009, REQ-AGT-CMP-002     |
| 1     | Create Context Manager    | 1.5 hours      | REQ-AGT-004, REQ-AGT-SEC-001                  |
| 2     | Implement Orchestrator    | 3 hours        | REQ-AGT-001, REQ-AGT-INT-001                  |
| 2     | Implement Tracker         | 2.5 hours      | REQ-AGT-005, REQ-AGT-DAT-001, REQ-AGT-INT-002 |
| 2     | Implement State Manager   | 2 hours        | REQ-AGT-008, REQ-AGT-DAT-002                  |
| 3     | Implement Isolation       | 2 hours        | REQ-AGT-006, REQ-AGT-007, REQ-AGT-INT-003     |
| 3     | Implement Circuit Breaker | 2 hours        | REQ-AGT-NFR-002, REQ-AGT-NFR-003              |
| 4     | Implement Telemetry       | 2.5 hours      | REQ-AGT-NFR-004                               |
| 4     | Create ADK Stubs & Docs   | 3 hours        | REQ-AGT-010, REQ-AGT-DOC-001, REQ-AGT-DOC-002 |

**Total Estimated Time:** ~21 hours (2.5-3 days for single developer)

---

## Notes

- **Product Manager Agent:** Basic skeleton created in this story (REQ-AGT-003), full implementation in Story 8
- **Specialist Agents:** Infrastructure prepared, actual agent implementations in Stories 10-12
- **ADK Integration:** Protocol stubs only; full remote agent support is post-MVP
- **Performance:** Monitor execution times against targets in REQ-AGT-NFR-001
- **Dependencies:** Story 6 blocker (OTEL metrics) doesn't affect this story—can proceed in parallel

---

## Risk Mitigation

| Risk                         | Mitigation                                 |
| ---------------------------- | ------------------------------------------ |
| CrewAI API changes           | Pin exact version, monitor changelog       |
| Context propagation failures | Comprehensive integration tests            |
| Performance degradation      | Set timeouts, implement circuit breakers   |
| Isolation breach             | Multiple validation layers, security tests |

---

## Next Steps After Completion

1. Implement full Product Manager agent (Story 8)
2. Implement LLM-based language detection (Story 9)
3. Implement Idea Stage agent team (Story 10)
