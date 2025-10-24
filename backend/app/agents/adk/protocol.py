from __future__ import annotations

from typing import Protocol
from uuid import UUID

from ..contracts import AgentInput, AgentOutput


class ADKAgentProtocol(Protocol):
    async def execute(
        self, input: AgentInput
    ) -> AgentOutput:  # pragma: no cover - interface
        """Standard execution interface for all agents."""
        ...


class RemoteAgentWrapper:
    """
    Wrapper for future remote agent calls via ADK.
    MVP: All agents are local.
    Post-MVP: Can invoke remote agents without changing contracts.
    """

    async def invoke_remote(
        self, project_id: UUID, agent_url: str, input: AgentInput
    ) -> AgentOutput:
        if not isinstance(project_id, UUID):
            raise ValueError("project_id must be a UUID")
        if not isinstance(agent_url, str) or not agent_url.strip():
            raise ValueError("agent_url must be a non-empty string")
        # TODO: Implement ADK remote invocation post-MVP (service discovery, auth, A2A protocol)
        raise NotImplementedError("Remote agents not supported in MVP")
