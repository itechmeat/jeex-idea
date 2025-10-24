# ADR: Selection of CrewAI for Multi-Agent Orchestration

**Status:** Accepted

**Date:** 2025-01-26

**Context:** Story 7 — Setup Multi-Agent Framework

---

## Context and Problem Statement

JEEX Idea requires a multi-agent orchestration framework to coordinate teams of specialized AI agents across four project stages (Idea, Specs, Architecture, Planning). The framework must support:

- **Product Manager agent** as central coordinator
- **13 specialist agents** organized in stage-specific teams
- **Strict I/O contracts** via Pydantic AI for type safety
- **Project and language isolation** enforcement
- **Future scalability** to remote agent services (ADK compatibility)
- **Observability** via OpenTelemetry
- **Resilience** patterns (retry, circuit breaker)

The question is: **Which multi-agent orchestration framework best meets these requirements?**

---

## Decision Drivers

### Critical Requirements

1. **Multi-agent coordination:** Support for agent teams with hierarchical delegation
2. **Type safety:** Integration with Pydantic for strict contracts
3. **Python ecosystem:** Compatible with FastAPI backend
4. **Production readiness:** Stable API, active maintenance, battle-tested
5. **Extensibility:** Support for custom agent implementations
6. **Observability:** Hooks for tracing and metrics

### Nice-to-Have Features

- Built-in memory management
- LLM provider flexibility (OpenAI, Anthropic, local models)
- Documentation and community support
- ADK protocol compatibility (or adaptability)

---

## Options Considered

### Option 1: CrewAI 0.186.1+

**Description:** Specialized framework for orchestrating AI agent crews with role-based coordination.

**Pros:**

- ✅ **Native crew/team model** — Built-in support for agent teams with roles
- ✅ **Task delegation** — Product Manager pattern naturally fits
- ✅ **Pydantic integration** — Uses Pydantic for all data models
- ✅ **LLM flexibility** — Supports multiple LLM providers
- ✅ **Active development** — Regular updates, growing community
- ✅ **Memory management** — Built-in short/long-term memory
- ✅ **Python-first** — Seamless FastAPI integration
- ✅ **Process abstraction** — Sequential, hierarchical, and consensus processes

**Cons:**

- ⚠️ **Younger framework** — Less mature than LangChain (but stable since 0.186+)
- ⚠️ **No native ADK support** — Will need custom wrapper (acceptable for MVP)
- ⚠️ **Learning curve** — Team needs to learn CrewAI concepts

**Fit Score:** 9/10

---

### Option 2: LangChain + LangGraph

**Description:** General-purpose LLM framework with LangGraph for agent orchestration.

**Pros:**

- ✅ **Mature ecosystem** — Battle-tested, extensive documentation
- ✅ **Large community** — Many examples and integrations
- ✅ **Flexible** — Can build any agent pattern
- ✅ **Tool ecosystem** — Rich set of pre-built tools

**Cons:**

- ❌ **Overly generic** — Not optimized for multi-agent crews
- ❌ **Verbose setup** — More boilerplate for agent teams
- ❌ **Graph complexity** — LangGraph adds cognitive overhead for simple delegation
- ❌ **Memory management** — Requires custom implementation for project isolation

**Fit Score:** 6/10

---

### Option 3: Custom Framework (Build from Scratch)

**Description:** Build custom orchestration layer with Pydantic AI contracts.

**Pros:**

- ✅ **Full control** — Tailor exactly to requirements
- ✅ **No external dependencies** — Reduce third-party risk
- ✅ **ADK-first design** — Build with ADK compatibility from day 1

**Cons:**

- ❌ **High development cost** — Weeks of engineering effort
- ❌ **Maintenance burden** — Ongoing support and bug fixes
- ❌ **Reinventing wheel** — Loses benefits of community solutions
- ❌ **Delayed MVP** — Pushes timeline significantly

**Fit Score:** 4/10

---

### Option 4: AutoGen

**Description:** Microsoft's framework for multi-agent conversations.

**Pros:**

- ✅ **Multi-agent focus** — Designed for agent collaboration
- ✅ **Conversation patterns** — Good for iterative refinement
- ✅ **Microsoft backing** — Strong institutional support

**Cons:**

- ❌ **Different paradigm** — Focuses on conversations, not hierarchical teams
- ❌ **Less flexible roles** — Harder to implement Product Manager pattern
- ❌ **Less Pydantic integration** — More manual contract management

**Fit Score:** 5/10

---

## Decision

**Selected Option:** **CrewAI 0.186.1+**

### Rationale

CrewAI provides the best balance of:

1. **Natural fit for hierarchical teams** — Product Manager + specialist agents map directly to CrewAI's crew/role model
2. **Pydantic-native** — Strict I/O contracts enforced automatically
3. **Production readiness** — Version 0.186+ is stable with active maintenance
4. **Fast implementation** — Reduces Story 7 timeline from weeks to days
5. **Extensibility** — Can add ADK wrapper layer without framework changes

### Trade-offs Accepted

- **Framework maturity:** CrewAI is younger than LangChain, but stability since 0.186+ mitigates risk
- **ADK compatibility:** Will need custom wrapper, but contracts remain portable
- **Learning curve:** Team invests time learning CrewAI concepts, but documentation is good

---

## Implementation Strategy

### Phase 1: MVP (Story 7)

- Use CrewAI for all local agent orchestration
- Implement Pydantic AI contracts as CrewAI tool interfaces
- Prepare ADK protocol stubs (not implemented)
- Focus on project/language isolation and observability

### Phase 2: Post-MVP

- Evaluate ADK integration necessity based on scale
- If remote agents needed:
  - Build `RemoteAgentWrapper` with ADK protocol
  - Keep Pydantic contracts unchanged
  - Add service discovery layer
- If scaling with CrewAI sufficient:
  - Optimize crew configurations
  - Add advanced memory strategies

---

## Consequences

### Positive

- **Faster MVP delivery** — Story 7 complexity reduced from "Very High" to "High"
- **Type safety** — Pydantic contracts prevent runtime errors
- **Maintainability** — Standard framework reduces custom code
- **Community support** — Active CrewAI community for troubleshooting

### Negative

- **Vendor lock-in (mild)** — Some CrewAI-specific code, but contracts remain portable
- **ADK integration effort** — Will need custom wrapper layer post-MVP
- **Framework risk** — If CrewAI abandoned, migration effort required (mitigated by contract abstraction)

### Neutral

- **Learning investment** — Team learns CrewAI patterns (useful long-term skill)
- **Documentation burden** — Need internal docs for CrewAI best practices

---

## Validation Criteria

This decision will be considered successful if:

1. ✅ Story 7 completed within estimated 21 hours
2. ✅ Agent teams operational by Story 10 completion
3. ✅ Project/language isolation enforced without framework limitations
4. ✅ OpenTelemetry integration functional
5. ✅ Pydantic contracts portable (can migrate to ADK if needed)
6. ✅ No critical CrewAI bugs blocking MVP

**Review Date:** End of Story 10 (Idea Stage Agent Team Implementation)

If validation criteria not met, reconsider custom framework or LangChain migration.

---

## References

- [CrewAI Documentation](https://docs.crewai.com/)
- [CrewAI GitHub Repository](https://github.com/joaomdmoura/crewAI)
- [Pydantic AI Documentation](https://ai.pydantic.dev/)
- [Google ADK Documentation](https://google.github.io/adk-docs/)
- [LangChain vs CrewAI Comparison](https://python.langchain.com/docs/langgraph)

---

## Related Decisions

- **Pydantic AI for contracts** — Selected for type safety (implicitly accepted with CrewAI)
- **ADK protocol preparation** — Deferred to post-MVP, stubs created in Story 7
- **OpenTelemetry integration** — Required from Story 5, compatible with CrewAI

---

**Decision Owner:** Tech Lead (Backend)

**Approved By:** Architecture Review (Implicit via Story 7 acceptance)

**Last Updated:** 2025-01-26

