from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from opentelemetry.trace import Span

from .context import ExecutionContext
from .contracts import AgentInput
from .isolation import IsolationValidator
from .state_manager import ExecutionStateManager
from .telemetry import add_common_span_attributes, start_span
from .tracker import AgentExecutionTracker


class AgentOrchestrator:
    """CrewAI-based orchestrator for agent workflows with isolation and telemetry."""

    def __init__(
        self,
        tracker: AgentExecutionTracker,
        state_manager: ExecutionStateManager,
        isolation: IsolationValidator,
    ) -> None:
        self.tracker = tracker
        self.state_manager = state_manager
        self.isolation = isolation

    async def initialize_crew(self, stage: str, context: ExecutionContext) -> Any:
        """Initialize CrewAI crew for a given stage.

        Fails fast if CrewAI is not installed.
        """
        # Import lazily to fail fast without silent fallbacks
        try:
            from crewai import Crew  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "CrewAI is required (crewai>=0.186.1). Please install per docs/specs.md."
            ) from e

        # For MVP, initialize an empty crew; agents/tasks are provided by future stories
        crew = Crew(agents=[], tasks=[], verbose=False)
        return crew

    async def execute_agent_workflow(
        self,
        stage: str,
        context: ExecutionContext,
        input_data: AgentInput,
    ) -> dict:
        """Execute an agent workflow lifecycle with tracking and telemetry.

        Returns minimal execution metadata (execution_id, status).
        """
        # Isolation checks (fail fast)
        await self.isolation.validate_project_access(
            user_id=context.user_id, project_id=context.project_id
        )
        await self.isolation.validate_language_consistency(
            project_id=context.project_id, language=context.language
        )

        # Validate input matches context
        if input_data.project_id != context.project_id:
            raise ValueError("Input project_id does not match execution context")
        if input_data.language != context.language:
            raise ValueError("Input language does not match project language")

        span: Span | None = None
        try:
            span = start_span("agent.execution.start")
            add_common_span_attributes(
                span,
                project_id=str(context.project_id),
                agent_type="product_manager",
                stage=stage,
                status="running",
                language=context.language,
            )

            # Create DB tracking record within transaction scope
            async with self.tracker.session.begin():
                execution_id = await self.tracker.start_execution(
                    project_id=context.project_id,
                    agent_type="product_manager",
                    correlation_id=context.correlation_id,
                    input_data=input_data.model_dump(exclude_none=True),
                )

            # Initialize Redis execution state
            await self.state_manager.create_state(context=context, stage=stage)

            # Initialize crew (MVP)
            crew = await self.initialize_crew(stage=stage, context=context)

            async def _run():
                # TODO: Implement CrewAI task delegation (Story 8)
                # Agent execution not implemented yet per compliance requirements
                _ = crew
                raise NotImplementedError(
                    "Agent task delegation not implemented yet; see Story 8 for planned implementation."
                )

            timeout = int(os.getenv("AGENT_EXECUTION_TIMEOUT_SECONDS", "300"))
            await asyncio.wait_for(_run(), timeout=timeout)

            add_common_span_attributes(span, status="completed")
            return {"execution_id": str(execution_id), "status": "completed"}

        except TimeoutError:
            logging.exception("Agent workflow timed out")
            if span:
                add_common_span_attributes(span, status="failed")
            await self.tracker.fail_execution(
                correlation_id=context.correlation_id,
                error_message=f"TimeoutError: Agent workflow timed out at stage {stage} after {os.getenv('AGENT_EXECUTION_TIMEOUT_SECONDS', '300')}s",
            )
            raise
        except Exception as e:
            logging.exception("Agent workflow failed")
            # Ensure failure is recorded with full context; re-raise for upstream handling
            if span:
                add_common_span_attributes(span, status="failed")
            await self.tracker.fail_execution(
                correlation_id=context.correlation_id,
                error_message=f"{type(e).__name__}: Agent workflow failed at stage {stage}",
            )
            raise


async def get_orchestrator(
    tracker: AgentExecutionTracker,
    state_manager: ExecutionStateManager,
    isolation: IsolationValidator,
) -> AgentOrchestrator:
    """FastAPI DI provider for AgentOrchestrator."""
    return AgentOrchestrator(
        tracker=tracker, state_manager=state_manager, isolation=isolation
    )
