"""
JEEX Idea OpenTelemetry Instrumentation Setup

OpenTelemetry auto-instrumentation and configuration for FastAPI application.
Implements distributed tracing with proper resource detection and sampling.

This module provides:
- Auto-instrumentation for FastAPI, SQLAlchemy, Redis, HTTP clients
- Resource detection with service name and environment attributes
- Tracer provider with configurable sampling strategy
- OTLP exporter for sending telemetry data to collector
- Error handling and graceful degradation
"""

import os
import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from opentelemetry import trace, metrics, baggage, propagate
from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import Decision, SamplingResult
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as OTLPGrpcSpanExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter as OTLPGrpcMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as OTLPHttpSpanExporter,
)

# Removed: from opentelemetry.instrumentation.auto_instrumentation import load_instrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

# HTTP client instrumentation - conditional imports
try:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
except ImportError:
    HTTPXClientInstrumentor = None

try:
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
except ImportError:
    RequestsInstrumentor = None
# Note: Only available instrumentation packages are used
from opentelemetry.propagate import set_global_textmap

# from opentelemetry.propagators.b3 import B3MultiFormat  # Not available, using default
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.semconv.trace import SpanAttributes

from .config import get_settings
from .resilient_exporter import ResilientSpanExporter

logger = logging.getLogger(__name__)

# Log warnings for missing instrumentation packages
if HTTPXClientInstrumentor is None:
    logger.warning(
        "HTTPX instrumentation not available - install opentelemetry-instrumentation-httpx"
    )

if RequestsInstrumentor is None:
    logger.warning(
        "Requests instrumentation not available - install opentelemetry-instrumentation-requests"
    )


class ProjectAwareSampler:
    """
    Custom sampler that enforces project-based sampling and respects privacy.

    Implements sampling strategy with project isolation and performance considerations.
    """

    def __init__(self, sample_rate: float = 1.0, max_spans_per_second: int = 1000):
        """
        Initialize project-aware sampler.

        Args:
            sample_rate: Sampling rate (0.0 to 1.0). Default is 1.0 for development
            max_spans_per_second: Maximum spans to sample per second
        """
        self.sample_rate = max(0.0, min(1.0, sample_rate))
        self.max_spans_per_second = max_spans_per_second
        self._span_count = 0
        self._last_reset = 0

    def should_sample(
        self,
        parent_context: Optional[Any],
        trace_id: int,
        name: str,
        kind: Optional[Any] = None,
        attributes: Optional[Dict[str, Any]] = None,
        span_kind: Optional[Any] = None,
    ) -> SamplingResult:
        """
        Determine if a span should be sampled.

        Args:
            parent_context: Parent span context
            trace_id: Trace ID
            name: Span name
            kind: Span kind
            attributes: Span attributes
            span_kind: Span kind

        Returns:
            SamplingResult with decision and attributes

        TODO: MEDIUM PRIORITY - Add input validation for all parameters to prevent invalid states
        """
        # Always sample if parent is already sampled
        if parent_context and trace.get_current_span(parent_context).is_recording():
            return SamplingResult(Decision.RECORD_AND_SAMPLE, attributes)

        # Respect privacy and security - filter sensitive spans
        if self._is_sensitive_span(name, attributes):
            return SamplingResult(Decision.DROP, attributes)

        # Rate limiting to prevent excessive spans
        if self._should_rate_limit():
            return SamplingResult(Decision.DROP, attributes)

        # Apply sampling rate
        import random

        if random.random() <= self.sample_rate:
            # Add sampling attribute
            if attributes is None:
                attributes = {}
            attributes["sampling.rate.applied"] = self.sample_rate
            return SamplingResult(Decision.RECORD_AND_SAMPLE, attributes)

        return SamplingResult(Decision.DROP, attributes)

    def _is_sensitive_span(
        self, name: str, attributes: Optional[Dict[str, Any]]
    ) -> bool:
        """Check if span contains sensitive information that should not be sampled."""
        sensitive_keywords = [
            "password",
            "token",
            "secret",
            "key",
            "auth",
            "credential",
            "login",
            "logout",
            "session",
            "cookie",
        ]

        name_lower = name.lower()
        if any(keyword in name_lower for keyword in sensitive_keywords):
            return True

        if attributes:
            for key, value in attributes.items():
                if any(keyword in key.lower() for keyword in sensitive_keywords):
                    return True

        return False

    def _should_rate_limit(self) -> bool:
        """Implement simple rate limiting to prevent span explosion."""
        import time

        current_time = time.time()

        # Reset counter every second
        if current_time - self._last_reset >= 1.0:
            self._span_count = 0
            self._last_reset = current_time

        self._span_count += 1
        return self._span_count > self.max_spans_per_second


class OpenTelemetryManager:
    """
    Manages OpenTelemetry instrumentation lifecycle.

    Handles initialization, configuration, and cleanup of all OpenTelemetry components
    with proper error handling and graceful degradation.
    """

    def __init__(self):
        self._initialized = False
        self._tracer_provider: Optional[TracerProvider] = None
        self._meter_provider: Optional[MeterProvider] = None
        self._settings = get_settings()

    async def initialize(self) -> bool:
        """
        Initialize OpenTelemetry instrumentation.

        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            logger.warning("OpenTelemetry already initialized")
            return True

        try:
            logger.info("Initializing OpenTelemetry instrumentation")

            # Create resource with service information
            resource = self._create_resource()

            # Initialize tracer provider with custom sampler
            await self._initialize_tracing(resource)

            # Initialize metrics
            await self._initialize_metrics(resource)

            # Set up auto-instrumentation
            await self._setup_auto_instrumentation()

            # Configure global propagation
            self._configure_propagation()

            self._initialized = True
            logger.info(
                "OpenTelemetry instrumentation initialized successfully",
                service_name=self._settings.OTEL_SERVICE_NAME,
                service_version=self._settings.OTEL_SERVICE_VERSION,
                endpoint=self._settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to initialize OpenTelemetry instrumentation: {str(e)}",
                exc_info=True,
            )
            return False

    async def shutdown(self) -> None:
        """Gracefully shutdown OpenTelemetry components."""
        if not self._initialized:
            return

        try:
            logger.info("Shutting down OpenTelemetry instrumentation")

            # Shutdown tracer provider
            if self._tracer_provider:
                self._tracer_provider.shutdown()

            # Shutdown meter provider
            if self._meter_provider:
                self._meter_provider.shutdown()

            self._initialized = False
            logger.info("OpenTelemetry instrumentation shutdown completed")

        except Exception as e:
            logger.error(
                f"Error during OpenTelemetry shutdown: {str(e)}", exc_info=True
            )

    def _create_resource(self) -> Resource:
        """
        Create OpenTelemetry resource with service attributes.

        Returns:
            Configured Resource instance
        """
        # Parse resource attributes from environment
        resource_attributes = {}
        if self._settings.OTEL_RESOURCE_ATTRIBUTES:
            for attr in self._settings.OTEL_RESOURCE_ATTRIBUTES.split(","):
                if "=" in attr:
                    key, value = attr.split("=", 1)
                    resource_attributes[key.strip()] = value.strip()

        # Ensure required attributes are present
        resource_attributes.update(
            {
                ResourceAttributes.SERVICE_NAME: self._settings.OTEL_SERVICE_NAME,
                ResourceAttributes.SERVICE_VERSION: self._settings.OTEL_SERVICE_VERSION,
                ResourceAttributes.DEPLOYMENT_ENVIRONMENT: self._settings.ENVIRONMENT,
                "project.id": self._settings.PROJECT_ID,
            }
        )

        # Add system attributes
        import socket

        resource_attributes.update(
            {
                ResourceAttributes.HOST_NAME: socket.gethostname(),
                ResourceAttributes.PROCESS_PID: os.getpid(),
            }
        )

        return Resource.create(resource_attributes)

    async def _initialize_tracing(self, resource: Resource) -> None:
        """
        Initialize distributed tracing.

        Args:
            resource: OpenTelemetry resource
        """
        # Create custom sampler based on environment
        sample_rate = 1.0 if self._settings.ENVIRONMENT == "development" else 0.1
        sampler = ProjectAwareSampler(sample_rate=sample_rate)

        # Create tracer provider
        self._tracer_provider = TracerProvider(resource=resource, sampler=sampler)

        # Configure span exporter with fallback
        span_exporter = self._create_span_exporter()

        # Add batch processor for efficient exporting
        batch_processor = BatchSpanProcessor(
            span_exporter,
            max_queue_size=2048,
            max_export_batch_size=512,
            export_timeout_millis=30000,
            schedule_delay_millis=5000,
        )

        self._tracer_provider.add_span_processor(batch_processor)

        # Add security span processor for data sanitization and redaction
        try:
            from .security import SecuritySpanProcessor

            security_processor = SecuritySpanProcessor()
            self._tracer_provider.add_span_processor(security_processor)
            logger.info(
                "Security span processor added for data sanitization and redaction"
            )
        except Exception as e:
            logger.warning("Failed to add security span processor", error=str(e))

        # Set global tracer provider
        trace.set_tracer_provider(self._tracer_provider)

        logger.info(
            "Distributed tracing initialized",
            sample_rate=sample_rate,
            endpoint=self._settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        )

    async def _initialize_metrics(self, resource: Resource) -> None:
        """
        Initialize metrics collection (disabled for MVP).

        Args:
            resource: OpenTelemetry resource
        """
        # Metrics disabled for MVP to focus on tracing
        logger.info(
            "Metrics collection disabled for MVP - focusing on distributed tracing"
        )

    async def _setup_auto_instrumentation(self) -> None:
        """Set up auto-instrumentation for supported libraries."""
        instrumentations = []

        try:
            # FastAPI instrumentation
            FastAPIInstrumentor.instrument()
            instrumentations.append("FastAPI")

        except Exception as e:
            logger.warning("Failed to instrument FastAPI", error=str(e))

        try:
            # SQLAlchemy instrumentation
            SQLAlchemyInstrumentor.instrument()
            instrumentations.append("SQLAlchemy")

        except Exception as e:
            logger.warning("Failed to instrument SQLAlchemy", error=str(e))

        try:
            # Redis instrumentation
            RedisInstrumentor.instrument()
            instrumentations.append("Redis")

        except Exception as e:
            logger.warning("Failed to instrument Redis", error=str(e))

        # HTTPX instrumentation (for Qdrant HTTP client)
        if HTTPXClientInstrumentor is not None:
            try:
                HTTPXClientInstrumentor.instrument()
                instrumentations.append("HTTPX")
            except Exception as e:
                logger.warning("Failed to instrument HTTPX", error=str(e))
        else:
            logger.info("HTTPX instrumentation skipped - package not available")

        # Requests instrumentation (fallback HTTP client)
        if RequestsInstrumentor is not None:
            try:
                RequestsInstrumentor.instrument()
                instrumentations.append("Requests")
            except Exception as e:
                logger.warning("Failed to instrument Requests", error=str(e))
        else:
            logger.info("Requests instrumentation skipped - package not available")

        # HTTP client instrumentation is now available for Qdrant operations

        logger.info("Auto-instrumentation completed", libraries=instrumentations)

    def _configure_propagation(self) -> None:
        """Configure global context propagation."""
        try:
            # Use default propagation format (W3C Trace Context)
            from opentelemetry.propagate import set_global_textmap
            from opentelemetry.propagators.textmap import TextMapPropagator

            set_global_textmap(TextMapPropagator())
            logger.info("Context propagation configured with default format")

        except Exception as e:
            logger.warning(f"Failed to configure propagation: {str(e)}")

    def _create_span_exporter(self) -> SpanExporter:
        """
        Create resilient span exporter with fallback and retry capabilities.

        Returns:
            Configured resilient span exporter
        """
        endpoint = self._settings.OTEL_EXPORTER_OTLP_ENDPOINT

        # Create primary exporter
        primary_exporter = None
        try:
            # Try gRPC exporter first (preferred) - use clean endpoint without protocol
            if endpoint.startswith("http://"):
                # Extract host:port from HTTP endpoint
                clean_endpoint = endpoint.replace("http://", "")
                logger.info("Creating primary gRPC exporter", endpoint=clean_endpoint)
                primary_exporter = OTLPGrpcSpanExporter(
                    endpoint=clean_endpoint, insecure=True, timeout=30
                )
            else:
                # Use endpoint as-is (should be host:port format)
                logger.info("Creating primary gRPC exporter", endpoint=endpoint)
                primary_exporter = OTLPGrpcSpanExporter(
                    endpoint=endpoint, insecure=True, timeout=30
                )

        except Exception as e:
            logger.warning(
                "Failed to create gRPC span exporter, falling back to HTTP",
                error=str(e),
            )
            # Fallback to HTTP exporter - use HTTP endpoint with port 4318
            if endpoint.endswith(":4317"):
                http_endpoint = endpoint.replace(":4317", ":4318")
            else:
                http_endpoint = endpoint

            logger.info(
                "Creating primary HTTP fallback exporter", endpoint=http_endpoint
            )
            try:
                primary_exporter = OTLPHttpSpanExporter(
                    endpoint=http_endpoint, timeout=30
                )
            except Exception as e:
                logger.error(
                    "Failed to create HTTP span exporter, using resilient exporter with no-op fallback",
                    error=str(e),
                )
                # Create no-op exporter as primary
                from opentelemetry.sdk.trace.export import (
                    SpanExporter,
                    SpanExportResult,
                )

                class NoOpSpanExporter(SpanExporter):
                    def export(self, spans, timeout_millis=30000):
                        logger.debug(
                            "Spans discarded (collector unavailable)", count=len(spans)
                        )
                        return SpanExportResult.SUCCESS

                    def shutdown(self):
                        pass

                    def force_flush(self, timeout_millis=30000):
                        return SpanExportResult.SUCCESS

                primary_exporter = NoOpSpanExporter()

        # Wrap primary exporter with resilient features
        logger.info(
            "Creating resilient span exporter with buffering and circuit breaker"
        )
        return ResilientSpanExporter(
            primary_exporter=primary_exporter,
            fallback_enabled=True,
            buffer_size=10000,
            buffer_max_age_minutes=5,
            circuit_breaker_threshold=self._settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            circuit_breaker_timeout=self._settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
        )

    def _create_metric_exporter(self):
        """Create metric exporter."""
        try:
            # Try gRPC exporter first
            if self._settings.OTEL_EXPORTER_OTLP_ENDPOINT.startswith("http://"):
                endpoint = self._settings.OTEL_EXPORTER_OTLP_ENDPOINT.replace(
                    "http://", ""
                ).replace(":4317", ":4317")
                return OTLPGrpcMetricExporter(
                    endpoint=endpoint, insecure=True, timeout=30
                )
            else:
                return OTLPGrpcMetricExporter(
                    endpoint=self._settings.OTEL_EXPORTER_OTLP_ENDPOINT,
                    insecure=True,
                    timeout=30,
                )

        except Exception as e:
            logger.warning("Failed to create metric exporter", error=str(e))
            # Return a mock exporter that does nothing
            from opentelemetry.sdk.metrics.export import MetricExporter
            from opentelemetry.sdk.metrics.export import MetricExportResult

            class NoOpMetricExporter(MetricExporter):
                def export(self, data, timeout_millis=30000):
                    return MetricExportResult.SUCCESS

                def shutdown(self):
                    pass

                def force_flush(self, timeout_millis=30000):
                    return MetricExportResult.SUCCESS

            return NoOpMetricExporter()

    def get_tracer(self, name: str, version: Optional[str] = None):
        """
        Get tracer instance.

        Args:
            name: Instrumentation name
            version: Instrumentation version

        Returns:
            Tracer instance
        """
        if not self._initialized:
            logger.warning("OpenTelemetry not initialized, returning no-op tracer")
            return trace.NoOpTracer()

        return trace.get_tracer(name, version)

    def get_meter(self, name: str, version: Optional[str] = None):
        """
        Get meter instance.

        Args:
            name: Instrumentation name
            version: Instrumentation version

        Returns:
            Meter instance
        """
        if not self._initialized or not self._meter_provider:
            logger.warning(
                "OpenTelemetry metrics not initialized, returning no-op meter"
            )
            return metrics.NoOpMeter()

        return metrics.get_meter(name, version)

    def get_resilience_metrics(self) -> Optional[Dict[str, Any]]:
        """
        Get resilience metrics from the span exporter.

        Returns:
            Resilience metrics dictionary or None if not available
        """
        if not self._initialized or not self._tracer_provider:
            return None

        # Get resilience metrics from the span processor
        try:
            # Access the batch processor to get the exporter
            if hasattr(self._tracer_provider, "_span_processor"):
                span_processor = self._tracer_provider._span_processor
                if hasattr(span_processor, "span_exporter"):
                    exporter = span_processor.span_exporter
                    if hasattr(exporter, "get_metrics"):
                        metrics = exporter.get_metrics()
                        return {
                            "total_exports": metrics.total_exports,
                            "successful_exports": metrics.successful_exports,
                            "failed_exports": metrics.failed_exports,
                            "success_rate": metrics.successful_exports
                            / max(1, metrics.total_exports),
                            "buffer_size": metrics.buffer_size,
                            "fallback_usage": metrics.fallback_usage,
                            "circuit_breaker_trips": metrics.circuit_breaker_trips,
                            "last_export_success": metrics.last_export_success.isoformat()
                            if metrics.last_export_success
                            else None,
                            "last_export_failure": metrics.last_export_failure.isoformat()
                            if metrics.last_export_failure
                            else None,
                        }
        except Exception as e:
            logger.warning("Failed to get resilience metrics", error=str(e))

        return None

    def get_telemetry_health(self) -> Dict[str, Any]:
        """
        Get telemetry system health status.

        Returns:
            Health status dictionary
        """
        resilience_metrics = self.get_resilience_metrics()

        # Determine health status
        is_healthy = True
        status = "healthy"
        issues = []

        if resilience_metrics:
            if resilience_metrics.get("failed_exports", 0) > resilience_metrics.get(
                "successful_exports", 1
            ):
                is_healthy = False
                status = "degraded"
                issues.append("High failure rate")

            if resilience_metrics.get("buffer_size", 0) > 5000:
                is_healthy = False
                status = "degraded"
                issues.append("Buffer overflow risk")

            if resilience_metrics.get("circuit_breaker_trips", 0) > 0:
                status = "degraded"
                issues.append("Circuit breaker active")

        return {
            "status": status,
            "healthy": is_healthy,
            "initialized": self._initialized,
            "issues": issues,
            "resilience_metrics": resilience_metrics,
            "collector_endpoint": self._settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            "service_name": self._settings.OTEL_SERVICE_NAME,
        }


# Global OpenTelemetry manager instance
otel_manager = OpenTelemetryManager()


@asynccontextmanager
async def instrumented_lifespan(app):
    """
    Context manager for instrumented application lifespan.

    This should be used in FastAPI lifespan function to ensure proper
    OpenTelemetry initialization and cleanup.

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    # Initialize OpenTelemetry
    success = await otel_manager.initialize()
    if not success:
        logger.warning(
            "OpenTelemetry initialization failed, continuing without telemetry"
        )

    try:
        yield
    finally:
        # Cleanup OpenTelemetry
        await otel_manager.shutdown()


def get_tracer(name: str, version: Optional[str] = None):
    """
    Get tracer instance for manual instrumentation.

    Args:
        name: Instrumentation name (e.g., service name)
        version: Instrumentation version

    Returns:
        Tracer instance
    """
    return otel_manager.get_tracer(name, version)


def get_meter(name: str, version: Optional[str] = None):
    """
    Get meter instance for metrics collection.

    Args:
        name: Instrumentation name (e.g., service name)
        version: Instrumentation version

    Returns:
        Meter instance
    """
    return otel_manager.get_meter(name, version)


def add_span_attribute(key: str, value: Any) -> None:
    """
    Add attribute to current span.

    Args:
        key: Attribute key
        value: Attribute value
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(key, value)


def set_correlation_id(correlation_id: str) -> None:
    """
    Set correlation ID in current context and span.

    Args:
        correlation_id: Correlation ID to set
    """
    # Add to current span
    add_span_attribute("correlation_id", correlation_id)

    # Add to baggage for propagation
    baggage.set_baggage("correlation_id", correlation_id)


def get_correlation_id() -> Optional[str]:
    """
    Get correlation ID from current context.

    Returns:
        Correlation ID if present, None otherwise
    """
    # Try baggage first
    correlation_id = baggage.get_baggage("correlation_id")
    if correlation_id:
        logger.debug("Correlation ID found in baggage", correlation_id=correlation_id)
        return correlation_id

    # Try current span attributes
    span = trace.get_current_span()
    if span and span.is_recording():
        attributes = span.attributes or {}
        correlation_id = attributes.get("correlation_id")
        if correlation_id:
            logger.debug(
                "Correlation ID found in span attributes", correlation_id=correlation_id
            )
            return correlation_id
    else:
        logger.debug(
            "No active span or span not recording for correlation ID retrieval"
        )

    logger.debug("No correlation ID found in current context")
    return None


def get_telemetry_health() -> Dict[str, Any]:
    """
    Get telemetry system health status.

    Returns:
        Health status dictionary
    """
    return otel_manager.get_telemetry_health()


def get_resilience_metrics() -> Optional[Dict[str, Any]]:
    """
    Get resilience metrics from the telemetry system.

    Returns:
        Resilience metrics dictionary or None if not available
    """
    return otel_manager.get_resilience_metrics()


# Export key functions for easy access
__all__ = [
    "OpenTelemetryManager",
    "otel_manager",
    "instrumented_lifespan",
    "get_tracer",
    "get_meter",
    "add_span_attribute",
    "set_correlation_id",
    "get_correlation_id",
    "get_telemetry_health",
    "get_resilience_metrics",
]
