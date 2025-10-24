from __future__ import annotations

from typing import Any, Dict, List

from pydantic import Field

from .base import AgentInput, AgentOutput


class IdeaStageInput(AgentInput):
    previous_answers: List[Dict[str, Any]] = Field(default_factory=list)


class IdeaStageOutput(AgentOutput):
    questions: List[Dict[str, Any]] = Field(default_factory=list)
    section_text: str = ""


class SpecsStageInput(AgentInput):
    specs_context: Dict[str, Any] = Field(default_factory=dict)


class SpecsStageOutput(AgentOutput):
    spec_items: List[Dict[str, Any]] = Field(default_factory=list)


class ArchitectureStageInput(AgentInput):
    architecture_context: Dict[str, Any] = Field(default_factory=dict)


class ArchitectureStageOutput(AgentOutput):
    diagrams: List[Dict[str, Any]] = Field(default_factory=list)


class PlanningStageInput(AgentInput):
    plan_context: Dict[str, Any] = Field(default_factory=dict)


class PlanningStageOutput(AgentOutput):
    tasks: List[Dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "IdeaStageInput",
    "IdeaStageOutput",
    "SpecsStageInput",
    "SpecsStageOutput",
    "ArchitectureStageInput",
    "ArchitectureStageOutput",
    "PlanningStageInput",
    "PlanningStageOutput",
]
