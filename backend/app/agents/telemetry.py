from __future__ import annotations

from typing import Optional

from opentelemetry import trace
from opentelemetry.trace import Span


tracer = trace.get_tracer(__name__)


def start_span(name: str) -> Span:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("span name must be a non-empty string")
    return tracer.start_span(name)


def add_common_span_attributes(
    span: Optional[Span],
    *,
    project_id: str | None = None,
    agent_type: str | None = None,
    stage: str | None = None,
    status: str | None = None,
    language: str | None = None,
    duration_ms: int | None = None,
) -> None:
    if not span:
        return
    if project_id is not None:
        span.set_attribute("project_id", project_id)
    if agent_type is not None:
        span.set_attribute("agent_type", agent_type)
    if stage is not None:
        span.set_attribute("stage", stage)
    if status is not None:
        span.set_attribute("status", status)
    if language is not None:
        span.set_attribute("language", language)
    if duration_ms is not None:
        span.set_attribute("duration_ms", duration_ms)
