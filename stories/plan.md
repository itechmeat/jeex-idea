# Implementation Plan — JEEX Idea MVP (Document Idea Generation Phase)

## Setup Stories (Infrastructure First)

- [x] 1. **Setup Docker Development Environment** — Configure core services with health checks

  - **Scope:** Create docker-compose.yml with PostgreSQL, Redis, Qdrant, Nginx, API services, health checks, development tooling
  - **Dependencies:** None
  - **Estimated Complexity:** Medium (7 tasks)

- [x] 2. **Setup PostgreSQL Database with Migrations** — Initialize primary database and schema

  - **Scope:** PostgreSQL 18 container, connection pooling, initial migrations, health checks, UUID v7 support
  - **Dependencies:** Story 1
  - **Estimated Complexity:** Medium (22 tasks - expanded due to comprehensive implementation)
  - **Key Outcomes:** Monolithic Integrated PostgreSQL implemented with CoV Variant A (90% score), QA validated (91.3% score), production ready

- [x] 3. **Setup Vector Database (Qdrant)** — Configure semantic search and project memory

  - **Scope:** Qdrant 1.15.4+ container, collection setup with project+language filtering, health checks, performance optimization
  - **Dependencies:** Story 1
  - **Estimated Complexity:** Medium (16 tasks - expanded for comprehensive implementation)
  - **Key Outcomes:** Vector database with project/language isolation, comprehensive testing suite, performance benchmarks, production-ready

- [ ] 4. **Setup Cache and Queue Service (Redis)** — Configure caching and task coordination

  - **Scope:** Redis 6.4.0+ container, connection configuration, basic caching patterns, rate limiting setup, health checks
  - **Dependencies:** Story 1
  - **Estimated Complexity:** Low (4 tasks)

- [ ] 5. **Setup Observability Stack** — Configure monitoring and tracing

  - **Scope:** OpenTelemetry collector, basic logging, metrics collection, health checks, development dashboard
  - **Dependencies:** Story 1
  - **Estimated Complexity:** Low (3 tasks)

- [ ] 6. **Setup FastAPI Backend Foundation** — Initialize API service with core architecture

  - **Scope:** FastAPI 0.116.2+ project structure, middleware, security, basic API structure, health checks, development server
  - **Dependencies:** Stories 1-5
  - **Estimated Complexity:** Medium (8 tasks)

## Core Agent System Stories

- [ ] 7. **Setup Multi-Agent Framework** — Configure CrewAI orchestration with ADK compatibility

  - **Scope:** CrewAI 0.186.1+ integration, agent contracts via Pydantic AI 1.0.8+, ADK protocol preparation, basic agent infrastructure
  - **Dependencies:** Story 6
  - **Estimated Complexity:** High (10 tasks)

- [ ] 8. **Implement Product Manager Agent** — Create central coordinator agent

  - **Scope:** Product Manager agent with document lifecycle management, expert coordination, language context handling, document integration logic
  - **Dependencies:** Story 7
  - **Estimated Complexity:** High (11 tasks)

## Language Detection and Context Stories

- [ ] 9. **Implement LLM-based Language Detection** — Create language detection service with project-level locking

  - **Scope:** LLM-based language detection from first message, project language metadata storage, language context distribution to agents, immutability enforcement
  - **Dependencies:** Story 8
  - **Estimated Complexity:** High (9 tasks)

## Idea Generation Stage Stories

- [ ] 10. **Implement Idea Stage Agent Team** — Create specialized experts for idea refinement

  - **Scope:** Business Analyst, Venture Expert, TRIZ Expert, Design Thinker, System Analyst agents with I/O contracts, question generation, response parsing
  - **Dependencies:** Story 9
  - **Estimated Complexity:** High (12 tasks)

- [ ] 11. **Implement Response Parser Service** — Create flexible response parsing system

  - **Scope:** Free text parsing, structured format parsing (1.b, 2.c), mixed format handling, context extraction, validation
  - **Dependencies:** Story 10
  - **Estimated Complexity:** Medium (7 tasks)

- [ ] 12. **Implement Embedding Service** — Create vector embedding system for project memory

  - **Scope:** Text normalization, embedding computation, Qdrant integration with project+language filtering, deduplication, quality control
  - **Dependencies:** Stories 3, 10
  - **Estimated Complexity:** Medium (8 tasks)

## API and Integration Stories

- [ ] 13. **Implement Idea Generation API Endpoints** — Create RESTful API for idea stage

  - **Scope:** POST /projects, POST /projects/{id}/step1, GET /projects/{id}/progress, SSE streaming, authentication middleware, project isolation
  - **Dependencies:** Stories 8, 11
  - **Estimated Complexity:** Medium (9 tasks)

- [ ] 14. **Implement Document Management System** — Create document versioning and storage

  - **Scope:** Document storage in PostgreSQL, version management, metadata handling, document lifecycle, integration with Product Manager
  - **Dependencies:** Stories 2, 8, 13
  - **Estimated Complexity:** Medium (8 tasks)

## Frontend Stories

- [ ] 15. **Setup React Frontend Foundation** — Initialize frontend application structure

  - **Scope:** React.js + Vite, TypeScript, CSS Modules, RadixUI components, development server on port 5200, pnpm package management
  - **Dependencies:** None (parallel development)
  - **Estimated Complexity:** Medium (6 tasks)

- [ ] 16. **Implement Unified Chat Interface** — Create single chat UI for all agent interactions

  - **Scope:** Chat component, message history, agent interaction display, structured questions UI, free text input, real-time updates via SSE
  - **Dependencies:** Stories 13, 15
  - **Estimated Complexity:** High (11 tasks)

- [ ] 17. **Implement Project and Progress Management UI** — Create project management interface

  - **Scope:** Project creation wizard, progress tracking, document preview, version history, language detection feedback, project isolation by URL
  - **Dependencies:** Stories 14, 16
  - **Estimated Complexity:** Medium (8 tasks)

## Quality and Testing Stories

- [ ] 18. **Implement Authentication System** — Add Twitter OAuth2 authentication

  - **Scope:** Twitter OAuth2 integration, JWT tokens, user management, project ownership, role-based access control (owner/editor/viewer)
  - **Dependencies:** Stories 6, 13
  - **Estimated Complexity:** Medium (7 tasks)

- [ ] 19. **Implement Security and Isolation** — Add comprehensive security measures

  - **Scope:** Rate limiting, project data isolation, CORS, input validation, security headers, RBAC enforcement
  - **Dependencies:** Stories 14, 18
  - **Estimated Complexity:** Medium (6 tasks)

- [ ] 20. **Implement Testing Infrastructure** — Create comprehensive test suites

  - **Scope:** Pytest backend tests, frontend component tests, API integration tests, basic E2E tests, agent contract validation
  - **Dependencies:** Stories 17, 19
  - **Estimated Complexity:** Medium (8 tasks)

## Integration and Polish Stories

- [ ] 21. **Implement Export Service** — Create document export functionality

  - **Scope:** Document archive generation, Markdown formatting, folder structure, manifest generation, download links, temporary file storage
  - **Dependencies:** Stories 14, 17
  - **Estimated Complexity:** Low (4 tasks)

- [ ] 22. **Implement Error Handling and Resilience** — Add comprehensive error management

  - **Scope:** Circuit breakers, retry logic (Tenacity), graceful degradation, error reporting, user-friendly error messages, agent error recovery
  - **Dependencies:** Stories 20, 21
  - **Estimated Complexity:** Medium (6 tasks)

- [ ] 23. **Implement Performance Optimization** — Optimize system performance

  - **Scope:** Caching strategies, query optimization, async processing, streaming improvements, resource usage monitoring
  - **Dependencies:** Stories 22
  - **Estimated Complexity:** Medium (5 tasks)

## Notes

- **Focus Scope:** This plan focuses exclusively on the "Document Idea Generation" phase (Stage 1 of 4)
- **Future Compatibility:** Architecture accounts for future stages (Specs → Architecture → Planning) without requiring rework
- **Language Detection:** Critical requirement - language detection MUST be LLM-based, script/library detection is prohibited
- **Project Isolation:** All data access MUST be filtered by project_id AND language with server-side enforcement
- **Agent Architecture:** All agents designed with ADK compatibility for future remote service deployment
- **Development Pattern:** Frontend runs locally (port 5200), backend and infrastructure containerized
- **Authentication:** Twitter OAuth2 only for MVP (single provider)
- **Document Storage:** PostgreSQL as source of truth, Qdrant for semantic search and agent context
- **Real-time Updates:** SSE streaming for all agent interactions and progress updates
- **Quality Focus:** Each story includes verification steps and acceptance criteria
- **Testing Strategy:** Comprehensive testing at unit, integration, and E2E levels

**Total Estimated Tasks:** 154 tasks across 23 stories
**Estimated Development Time:** 8-12 weeks for MVP (Idea Generation Stage)
