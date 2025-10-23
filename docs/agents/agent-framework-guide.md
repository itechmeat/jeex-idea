# Agent Framework Developer Guide (MVP)

This guide explains how to define Pydantic AI contracts, integrate with the orchestrator, emit telemetry, and test agents.

## Contracts

- Base contracts live in `backend/app/agents/contracts/`.
- All inputs must include `project_id` (UUID, required) and `language`.

## Orchestrator

- Use FastAPI DI via `orchestrator_provider`.
- Start workflows at `POST /projects/{project_id}/agents/workflows/{stage}/start`.

## Telemetry

- Spans: `agent.execution.start`, `agent.execution.complete`, `agent.delegation`, `agent.context.load`.
- Attributes include: `project_id` (hashed in exporters), `agent_type`, `stage`, `status`, `language`, `duration_ms`.

## Testing

- Unit tests under `backend/tests/unit/test_agents/`.
- Integration tests under `backend/tests/integration/test_agent_orchestration.py`.

## ADK Stubs

- Protocols in `backend/app/agents/adk/`. Remote calls are NotImplemented in MVP.
