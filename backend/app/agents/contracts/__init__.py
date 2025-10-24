"""Pydantic AI contracts for agent inputs and outputs."""

from .base import AgentInput, AgentOutput, ExecutionStatus
from .stage_contracts import (
    IdeaStageInput,
    IdeaStageOutput,
    SpecsStageInput,
    SpecsStageOutput,
    ArchitectureStageInput,
    ArchitectureStageOutput,
    PlanningStageInput,
    PlanningStageOutput,
)

__all__ = [
    "AgentInput",
    "AgentOutput",
    "ExecutionStatus",
    "IdeaStageInput",
    "IdeaStageOutput",
    "SpecsStageInput",
    "SpecsStageOutput",
    "ArchitectureStageInput",
    "ArchitectureStageOutput",
    "PlanningStageInput",
    "PlanningStageOutput",
]
