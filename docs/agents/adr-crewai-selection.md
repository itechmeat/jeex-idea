# ADR: CrewAI Orchestrator Selection for Multi-Agent Framework

## Context

We evaluated multiple approaches for implementing the multi-agent orchestration layer. The MVP requires strict project and language isolation, Pydantic AI contracts, and OpenTelemetry observability, while preparing for ADK-compatible remote agents post-MVP.

## Decision

Selected Variant A: RESTful orchestration with CrewAI crews, repository pattern for persistence, Redis-backed state, and OpenTelemetry tracing. Contracts via Pydantic AI. ADK-compatible protocol stubs added for future.

## Alternatives Considered

### Variant A: CrewAI + REST + Redis State (Selected)

- Pros: Simple, aligns with current stack, fast to implement, good observability
- Cons: Requires later expansion for complex workflows

### Variant B: GraphQL + Resolver-based Agents

- Pros: Flexible querying and batching
- Cons: Higher complexity, new infra; not aligned with existing REST APIs

### Variant C: Event-driven CQRS with message bus

- Pros: High scalability, loose coupling
- Cons: Overkill for MVP, larger footprint and operational overhead

## Consequences

- Positive: Rapid MVP delivery, strong isolation, clear contracts, OTEL-ready
- Negative: Limited workflow sophistication until extended in later stories
- Technical Debt: Minimal; remote agents postponed with explicit NotImplementedError

## Verification Results

- Requirements Compliance: ✅
- Architectural Alignment: ✅
- Quality Attributes: ✅
- Implementation Risk: Low

## Date

2025-10-23
