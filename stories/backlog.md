# Backlog — JEEX Idea MVP (Document Idea Generation Phase)

## Completed Stories

### 2025-Q1

1. [x] **[Setup Docker Development Environment](docker-development-environment/design.md)** — Configure core services with health checks

   - Completed: 2025-01-18
   - Key Outcomes: Docker development environment established with PostgreSQL, Redis, Qdrant, Nginx, API services, health checks, and development tooling. All core services containerized and ready for development.

2. [x] **[Setup PostgreSQL Database with Migrations](setup-postgresql-database/design.md)** — Initialize primary database and schema

   - Completed: 2025-01-19
   - Key Outcomes: Monolithic Integrated PostgreSQL implemented with Variant A (CoV score: 90%), comprehensive schema with all tables, performance optimization (P95 <100ms), security controls, backup/recovery procedures, QA validated (91.3% score). Production-ready database foundation.

3. [x] **[Setup Vector Database (Qdrant)](setup-vector-database/design.md)** — Configure semantic search and project memory

   - Completed: 2025-01-24
   - Key Outcomes: Vector database with project/language isolation, comprehensive testing suite, performance benchmarks, all 16 tasks completed (100%), critical issues resolved (logging, metrics, integration tests, performance testing), production-ready with security validation and monitoring integration.

4. [x] **[Setup Cache and Queue Service (Redis)](setup-redis-cache-queue/design.md)** — Configure caching and task coordination

   - Completed: 2025-01-25
   - Key Outcomes: Full Redis integration with project isolation, performance optimization, connection pooling, rate limiting, task queuing, progress tracking, health monitoring, and comprehensive test coverage. All 16 tasks completed with production-ready configuration.

5. [x] **[Setup Observability Stack](setup-observability-stack/design.md)** — Configure monitoring and tracing

   - Completed: 2025-01-22
   - Key Outcomes: Full OpenTelemetry infrastructure with auto-instrumentation, correlation ID system, comprehensive instrumentation for PostgreSQL, Redis, and Qdrant, security controls, data sanitization, error handling and resilience mechanisms. CoV Analysis: Variant A selected with 4/4 critical criteria and 7/9 high-priority wins. Production-ready observability stack.

## Current Sprint (or Working On)

6. [~] **[Setup FastAPI Backend Foundation](setup-fastapi-backend/)** — Initialize API service with core architecture (75% Complete)

   - Status: ⚠️ In Progress (Blocked by OTEL metrics exporter issue)
   - Started: 2025-10-22
   - Key Outcomes:
     - ✅ Chain-of-Verification applied: 3 variants analyzed, Variant C selected (88% score)
     - ✅ BaseRepository pattern with project isolation (SEC-002 CRITICAL)
     - ✅ Security Headers middleware with 7 headers (SEC-001)
     - ✅ SSE streaming service with Redis pub/sub (REQ-006)
     - ✅ ADR and Completion Report documenting architectural decisions
   - Blocker: API service cannot accept HTTP connections due to OTEL metrics exporter crash
   - Next Action: Disable OTEL metrics for MVP (15-30 min) OR proceed to Story 7
   - Technical Debt: 7 SP deferred with clear repayment plan (see Technical Debt section)


---

## Technical Debt (Deferred with Repayment Plan)

Items deferred from completed stories with clear repayment strategies and triggers.

### From Story 6: Setup FastAPI Backend Foundation (7 SP)

**Total Debt: 7 SP** — Minimal debt with low risk

#### 1. Service Layer Implementation (3 SP)

- **Deferred Because:** No complex business logic exists yet (MVP principle)
- **Add When:** Story 7+ requires transaction coordination across multiple repositories
- **Effort:** 3 SP
- **Risk:** LOW - Repository pattern provides clean integration point
- **Location:** Add `backend/app/services/` layer between routes and repositories
- **Trigger:** When business logic requires multi-step transactions or orchestration

#### 2. Auth Middleware Activation (2 SP)

- **Deferred Because:** OAuth2/Twitter integration scheduled for Story 18
- **Add When:** Story 18 implementation
- **Effort:** 2 SP (infrastructure already prepared in `app/core/security.py`)
- **Risk:** LOW - Code scaffolded with TODO markers
- **Location:** Activate `OAuth2PasswordBearer` dependency in routes
- **Trigger:** Story 18 starts (Authentication System)

#### 3. Advanced SSE Features (2 SP)

- **Deferred Because:** MVP does not need backpressure until proven by load testing
- **Add When:** Memory monitoring shows >10MB per connection OR client disconnect issues emerge
- **Effort:** 2 SP (enhance existing `SSEService`)
- **Risk:** LOW - Basic implementation functional for MVP
- **Location:** Enhance `backend/app/services/sse.py`
- **Trigger:** Load testing or production monitoring reveals issues

---

## Post-MVP Infrastructure Improvements

Tasks that can be completed after MVP launch but before production scale.

### Fix OpenTelemetry Full Integration (2-3 hours)

- **Scope:** Debug OTEL collector unhealthy status, fix metrics exporter crash, restore full tracing and metrics
- **Priority:** MEDIUM (observability nice-to-have for MVP, critical for production)
- **Dependencies:** Post-MVP OR Story 19 (Security and Isolation)
- **Deferred From:** Story 6 (Setup FastAPI Backend Foundation)
- **Current Status:** API service blocked from accepting HTTP connections due to metrics exporter crash in background thread
- **Recommended Action:** Disable OTEL metrics for MVP, re-enable after launch with proper error handling
- **Resolution Options:**
  1. Disable OTEL metrics entirely (keep traces only) — 15-30 min
  2. Fix OTEL collector connectivity — 2-3 hours
  3. Wrap metrics exporter in additional error handling — 1 hour

---

## Debt Repayment Schedule

| Item | Story | Priority | Effort | When |
|------|-------|----------|--------|------|
| Service Layer | Story 7+ | LOW | 3 SP | When orchestration needed |
| Auth Middleware | Story 18 | HIGH | 2 SP | Story 18 starts |
| Advanced SSE | Post-MVP | MEDIUM | 2 SP | Load testing shows need |
| OTEL Fix | Post-MVP/Story 19 | MEDIUM | 2-3 hrs | Before production scale |

**Total Known Debt:** 7 SP + 2-3 hours
**Risk Level:** LOW (all items have clear triggers and integration points)

