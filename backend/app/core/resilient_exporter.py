"""
JEEX Idea Resilient OpenTelemetry Exporter

Implements error handling and resilience patterns for OpenTelemetry telemetry export.
Provides graceful degradation, local buffering, exponential backoff, and circuit breaker.

Features:
- Graceful degradation when collector unavailable
- Local buffering of telemetry data (up to 5 minutes)
- Exponential backoff retry logic for failed exports
- Fallback to file-based storage when primary exporter fails
- Circuit breaker pattern for external observability services
"""

import asyncio
import json
import logging
import os
import time
import tempfile
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
import threading
import queue

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, ReadableSpan
from opentelemetry.sdk.metrics.export import (
    MetricExporter,
    MetricExportResult,
    MetricsData,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceResponse,
)

from .config import get_settings

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovery occurred


@dataclass
class ExportMetrics:
    """Metrics for export operations."""

    total_exports: int = 0
    successful_exports: int = 0
    failed_exports: int = 0
    circuit_breaker_trips: int = 0
    buffer_size: int = 0
    fallback_usage: int = 0
    last_export_success: Optional[datetime] = None
    last_export_failure: Optional[datetime] = None


class CircuitBreaker:
    """
    Circuit breaker implementation for external service calls.

    Prevents cascading failures by temporarily stopping calls to failing services.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying again
            expected_exception: Exception type that counts as failure
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED

        self._lock = threading.Lock()

    def __call__(self, func: Callable) -> Callable:
        """Decorator to apply circuit breaker to function."""

        def wrapper(*args, **kwargs):
            if not self.allow_request():
                raise Exception("Circuit breaker is OPEN - request rejected")

            try:
                result = func(*args, **kwargs)
                self.on_success()
                return result
            except self.expected_exception as e:
                self.on_failure()
                raise e

        return wrapper

    def allow_request(self) -> bool:
        """
        Check if request should be allowed based on circuit state.

        Returns:
            True if request allowed, False otherwise
        """
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if (
                    self.last_failure_time
                    and time.time() - self.last_failure_time >= self.recovery_timeout
                ):
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                    return True
                return False

            # HALF_OPEN state - allow some requests to test recovery
            return True

    def on_success(self) -> None:
        """Handle successful call."""
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info("Circuit breaker transitioning to CLOSED")

    def on_failure(self) -> None:
        """Handle failed call."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker transitioning to OPEN (failure in HALF_OPEN)"
                )
            elif (
                self.state == CircuitState.CLOSED
                and self.failure_count >= self.failure_threshold
            ):
                self.state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker transitioning to OPEN - failures: %d, threshold: %d",
                    self.failure_count,
                    self.failure_threshold,
                )


class LocalBuffer:
    """
    Local buffer for telemetry data when exporter is unavailable.

    Stores data in memory with optional file-based persistence for durability.
    """

    def __init__(self, max_size: int = 10000, max_age_minutes: int = 5):
        """
        Initialize local buffer.

        Args:
            max_size: Maximum number of items to buffer
            max_age_minutes: Maximum age of buffered items in minutes
        """
        self.max_size = max_size
        self.max_age = timedelta(minutes=max_age_minutes)

        self._buffer = queue.Queue(maxsize=max_size)
        self._timestamps: queue.Queue = queue.Queue(maxsize=max_size)
        self._lock = threading.Lock()

        # File backup for persistence across restarts
        self.backup_dir = Path(tempfile.gettempdir()) / "jeex-telemetry-backup"
        self.backup_dir.mkdir(exist_ok=True)

        self._load_from_backup()

    def put(self, data: Any) -> bool:
        """
        Add item to buffer.

        Args:
            data: Data to buffer

        Returns:
            True if added successfully, False if buffer full
        """
        try:
            with self._lock:
                if self._buffer.full():
                    # Remove oldest item to make space
                    try:
                        self._buffer.get_nowait()
                        self._timestamps.get_nowait()
                    except queue.Empty:
                        pass

                self._buffer.put(data)
                self._timestamps.put(datetime.utcnow())

                # Periodically save to backup
                if self._buffer.qsize() % 100 == 0:
                    self._save_to_backup()

                return True
        except Exception as e:
            logger.error("Failed to add item to buffer: %s", str(e))
            return False

    def get_all(self, max_age: Optional[timedelta] = None) -> List[Any]:
        """
        Get all items from buffer, optionally filtered by age.

        Args:
            max_age: Maximum age of items to retrieve

        Returns:
            List of buffered items
        """
        items = []
        timestamps = []

        try:
            with self._lock:
                # Get all items
                while not self._buffer.empty():
                    try:
                        items.append(self._buffer.get_nowait())
                        timestamps.append(self._timestamps.get_nowait())
                    except queue.Empty:
                        break

            # Filter by age if specified
            if max_age:
                cutoff = datetime.utcnow() - max_age
                filtered_items = []
                for item, timestamp in zip(items, timestamps):
                    if timestamp > cutoff:
                        filtered_items.append(item)
                return filtered_items

            return items
        except Exception as e:
            logger.error("Failed to retrieve items from buffer: %s", str(e))
            return []

    def size(self) -> int:
        """Get current buffer size."""
        return self._buffer.qsize()

    def clear(self) -> None:
        """Clear all buffered items."""
        with self._lock:
            while not self._buffer.empty():
                try:
                    self._buffer.get_nowait()
                    self._timestamps.get_nowait()
                except queue.Empty:
                    break

    def cleanup_expired(self) -> int:
        """
        Remove expired items from buffer.

        Returns:
            Number of items removed
        """
        cutoff = datetime.utcnow() - self.max_age
        removed = 0

        try:
            with self._lock:
                temp_items = []
                temp_timestamps = []

                # Move all items to temporary storage
                while not self._buffer.empty():
                    try:
                        temp_items.append(self._buffer.get_nowait())
                        temp_timestamps.append(self._timestamps.get_nowait())
                    except queue.Empty:
                        break

                # Put back non-expired items
                for item, timestamp in zip(temp_items, temp_timestamps):
                    if timestamp > cutoff:
                        self._buffer.put(item)
                        self._timestamps.put(timestamp)
                    else:
                        removed += 1
        except Exception as e:
            logger.error("Failed to cleanup expired items: %s", str(e))

        return removed

    def _save_to_backup(self) -> None:
        """Save buffer content to backup file."""
        try:
            backup_file = self.backup_dir / f"telemetry_backup_{int(time.time())}.json"
            backup_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "items": [],
                "timestamps": [],
            }

            # Create temporary copies of queues for iteration
            temp_items = []
            temp_timestamps = []

            with self._lock:
                while not self._buffer.empty():
                    try:
                        item = self._buffer.get_nowait()
                        timestamp = self._timestamps.get_nowait()

                        temp_items.append(item)
                        temp_timestamps.append(timestamp)

                        # Convert to serializable format
                        if hasattr(item, "to_json"):
                            backup_data["items"].append(item.to_json())
                        elif hasattr(item, "__dict__"):
                            backup_data["items"].append(item.__dict__)
                        else:
                            backup_data["items"].append(str(item))

                        backup_data["timestamps"].append(timestamp.isoformat())

                        # Put back to buffer
                        self._buffer.put(item)
                        self._timestamps.put(timestamp)
                    except queue.Empty:
                        break

            with open(backup_file, "w") as f:
                json.dump(backup_data, f, indent=2)

            # Cleanup old backup files (keep only last 10)
            self._cleanup_backup_files()

        except Exception as e:
            logger.error("Failed to save buffer to backup: %s", str(e))

    def _load_from_backup(self) -> None:
        """Load buffer content from backup files."""
        try:
            backup_files = sorted(
                self.backup_dir.glob("telemetry_backup_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )

            if not backup_files:
                return

            # Load only the most recent backup
            latest_backup = backup_files[0]
            with open(latest_backup, "r") as f:
                backup_data = json.load(f)

            # Check if backup is not too old (older than max_age)
            backup_time = datetime.fromisoformat(backup_data["timestamp"])
            if datetime.utcnow() - backup_time > self.max_age:
                logger.info("Backup file too old, skipping restore")
                latest_backup.unlink()  # Remove old backup
                return

            # Restore items (simplified restoration for spans)
            restored_count = 0
            for item_data in backup_data["items"]:
                if self._buffer.full():
                    break

                # For now, just store as dict (real implementation would reconstruct objects)
                self._buffer.put(item_data)
                self._timestamps.append(backup_time)
                restored_count += 1

            if restored_count > 0:
                logger.info(f"Restored {restored_count} items from backup")

            # Remove backup file after successful restore
            latest_backup.unlink()

        except Exception as e:
            logger.error("Failed to load buffer from backup: %s", str(e))

    def _cleanup_backup_files(self) -> None:
        """Cleanup old backup files, keeping only the most recent ones."""
        try:
            backup_files = sorted(
                self.backup_dir.glob("telemetry_backup_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )

            # Keep only last 10 files
            for backup_file in backup_files[10:]:
                backup_file.unlink()

        except Exception as e:
            logger.error("Failed to cleanup backup files: %s", str(e))


class ExponentialBackoffRetry:
    """
    Exponential backoff retry logic with jitter.
    """

    def __init__(
        self,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
    ):
        """
        Initialize exponential backoff retry.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            jitter: Whether to add random jitter to delays
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with exponential backoff retry.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Last exception if all retries exhausted
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if attempt == self.max_retries:
                    logger.error(
                        "All retry attempts exhausted",
                        attempts=attempt + 1,
                        final_error=str(e),
                    )
                    raise e

                delay = self._calculate_delay(attempt)
                logger.warning(
                    "Operation failed, retrying",
                    attempt=attempt + 1,
                    max_retries=self.max_retries + 1,
                    delay=delay,
                    error=str(e),
                )

                await asyncio.sleep(delay)

        raise last_exception

    def _calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for given attempt.

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Delay in seconds
        """
        delay = self.base_delay * (2**attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            import random

            # Add ±25% jitter
            jitter_factor = 0.75 + (random.random() * 0.5)
            delay *= jitter_factor

        return delay


class ResilientSpanExporter(SpanExporter):
    """
    Resilient span exporter with buffering, circuit breaker, and fallback.
    """

    def __init__(
        self,
        primary_exporter: SpanExporter,
        fallback_enabled: bool = True,
        buffer_size: int = 10000,
        buffer_max_age_minutes: int = 5,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: int = 60,
    ):
        """
        Initialize resilient span exporter.

        Args:
            primary_exporter: Primary OTLP exporter
            fallback_enabled: Whether to enable fallback mechanisms
            buffer_size: Maximum buffer size for telemetry data
            buffer_max_age_minutes: Maximum age of buffered data
            circuit_breaker_threshold: Circuit breaker failure threshold
            circuit_breaker_timeout: Circuit breaker recovery timeout
        """
        self.primary_exporter = primary_exporter
        self.fallback_enabled = fallback_enabled

        # Initialize resilience components
        self.buffer = LocalBuffer(
            max_size=buffer_size, max_age_minutes=buffer_max_age_minutes
        )
        self.retry = ExponentialBackoffRetry()
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_threshold,
            recovery_timeout=circuit_breaker_timeout,
        )

        # Metrics
        self.metrics = ExportMetrics()

        # Fallback file exporter
        self.fallback_exporter = FileSpanExporter() if fallback_enabled else None

        # Background tasks
        self._retry_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False

        # Start background tasks
        self._start_background_tasks()

    def export(
        self, spans: List[ReadableSpan], timeout_millis: int = 30000
    ) -> SpanExportResult:
        """
        Export spans with resilience patterns.

        Args:
            spans: List of spans to export
            timeout_millis: Export timeout in milliseconds

        Returns:
            SpanExportResult
        """
        if not spans:
            return SpanExportResult.SUCCESS

        self.metrics.total_exports += 1

        # Try primary exporter with circuit breaker
        if self.circuit_breaker.allow_request():
            try:
                result = self._export_with_retry(spans, timeout_millis)
                if result == SpanExportResult.SUCCESS:
                    self.metrics.successful_exports += 1
                    self.metrics.last_export_success = datetime.utcnow()
                    return result
            except Exception as e:
                logger.warning("Primary exporter failed", error=str(e))
                self.metrics.failed_exports += 1
                self.metrics.last_export_failure = datetime.utcnow()
                self.circuit_breaker.on_failure()

        # Buffer spans for later retry
        if self.fallback_enabled:
            buffered_count = 0
            for span in spans:
                if self.buffer.put(span):
                    buffered_count += 1
                else:
                    logger.warning("Buffer full, dropping span", span_name=span.name)

            self.metrics.buffer_size = self.buffer.size()
            logger.info(f"Buffered {buffered_count} spans for retry")

        # Try fallback exporter if available
        if self.fallback_exporter:
            try:
                result = self.fallback_exporter.export(spans, timeout_millis)
                if result == SpanExportResult.SUCCESS:
                    self.metrics.fallback_usage += 1
                    logger.info("Used fallback exporter successfully")
                    return result
            except Exception as e:
                logger.error("Fallback exporter also failed: %s", str(e))

        # All export methods failed
        return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        """Shutdown exporter and cleanup resources."""
        logger.info("Shutting down resilient span exporter")

        self._shutdown = True

        # Cancel background tasks
        if self._retry_task and not self._retry_task.done():
            self._retry_task.cancel()

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

        # Try to export remaining buffered spans
        remaining_spans = self.buffer.get_all()
        if remaining_spans and self.fallback_exporter:
            try:
                self.fallback_exporter.export(remaining_spans)
                logger.info(
                    f"Exported {len(remaining_spans)} remaining spans to fallback"
                )
            except Exception as e:
                logger.error("Failed to export remaining spans: %s", str(e))

        # Shutdown primary exporter
        try:
            self.primary_exporter.shutdown()
        except Exception as e:
            logger.error("Failed to shutdown primary exporter: %s", str(e))

        # Shutdown fallback exporter
        if self.fallback_exporter:
            try:
                self.fallback_exporter.shutdown()
            except Exception as e:
                logger.error("Failed to shutdown fallback exporter: %s", str(e))

    def force_flush(self, timeout_millis: int = 30000) -> SpanExportResult:
        """Force flush buffered spans."""
        # Try to export buffered spans
        remaining_spans = self.buffer.get_all()
        if not remaining_spans:
            return SpanExportResult.SUCCESS

        try:
            result = self._export_with_retry(remaining_spans, timeout_millis)
            if result == SpanExportResult.SUCCESS:
                logger.info(f"Force flushed {len(remaining_spans)} buffered spans")
            return result
        except Exception as e:
            logger.error("Force flush failed: %s", str(e))
            return SpanExportResult.FAILURE

    def _export_with_retry(
        self, spans: List[ReadableSpan], timeout_millis: int
    ) -> SpanExportResult:
        """Export spans with retry logic."""
        try:
            # Use synchronous retry for export operation
            for attempt in range(self.retry.max_retries + 1):
                try:
                    return self.primary_exporter.export(spans, timeout_millis)
                except Exception as e:
                    if attempt == self.retry.max_retries:
                        raise e

                    delay = self.retry._calculate_delay(attempt)
                    logger.warning(
                        "Export attempt failed, retrying - attempt: %d/%d, delay: %.2fs, error: %s",
                        attempt + 1,
                        self.retry.max_retries + 1,
                        delay,
                        str(e),
                    )
                    time.sleep(delay)

        except Exception as e:
            logger.error("Export with retry failed: %s", str(e))
            raise

    def _start_background_tasks(self) -> None:
        """Start background tasks for retry and cleanup."""
        try:
            self._retry_task = asyncio.create_task(self._retry_buffered_spans())
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        except Exception as e:
            logger.error("Failed to start background tasks: %s", str(e))

    async def _retry_buffered_spans(self) -> None:
        """Background task to retry exporting buffered spans."""
        while not self._shutdown:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                if self.circuit_breaker.allow_request() and self.buffer.size() > 0:
                    spans = self.buffer.get_all(max_age=timedelta(minutes=1))
                    if spans:
                        try:
                            await self.retry.execute_with_retry(
                                self._export_spans_sync, spans
                            )
                            logger.info(
                                f"Successfully exported {len(spans)} buffered spans"
                            )
                            self.metrics.buffer_size = self.buffer.size()
                        except Exception as e:
                            logger.warning(
                                "Failed to export buffered spans: %s", str(e)
                            )
                            # Put spans back in buffer
                            for span in spans:
                                self.buffer.put(span)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in retry background task: %s", str(e))

    def _export_spans_sync(self, spans: List[ReadableSpan]) -> None:
        """Synchronous export for background task."""
        result = self.primary_exporter.export(spans)
        if result != SpanExportResult.SUCCESS:
            raise Exception(f"Export failed with result: {result}")

    async def _periodic_cleanup(self) -> None:
        """Background task for periodic cleanup of expired data."""
        while not self._shutdown:
            try:
                await asyncio.sleep(300)  # Every 5 minutes

                # Cleanup expired buffer items
                removed = self.buffer.cleanup_expired()
                if removed > 0:
                    logger.info(f"Cleaned up {removed} expired buffer items")
                    self.metrics.buffer_size = self.buffer.size()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in cleanup background task: %s", str(e))

    def get_metrics(self) -> ExportMetrics:
        """Get current export metrics."""
        self.metrics.buffer_size = self.buffer.size()
        return self.metrics


class FileSpanExporter(SpanExporter):
    """
    Fallback file-based span exporter.

    Stores spans in JSON files when primary exporter is unavailable.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize file span exporter.

        Args:
            output_dir: Directory to store span files
        """
        if output_dir is None:
            output_dir = Path(tempfile.gettempdir()) / "jeex-telemetry-fallback"

        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)

        self._file_counter = 0
        self._current_file: Optional[Path] = None
        self._current_spans = []
        self._lock = threading.Lock()

        logger.info(f"File span exporter initialized", output_dir=str(self.output_dir))

    def export(
        self, spans: List[ReadableSpan], timeout_millis: int = 30000
    ) -> SpanExportResult:
        """
        Export spans to file.

        Args:
            spans: List of spans to export
            timeout_millis: Export timeout (ignored for file exporter)

        Returns:
            SpanExportResult.SUCCESS if successful
        """
        if not spans:
            return SpanExportResult.SUCCESS

        try:
            with self._lock:
                self._current_spans.extend(spans)

                # Flush to file if we have enough spans or timeout exceeded
                if len(self._current_spans) >= 100:
                    self._flush_to_file()

            return SpanExportResult.SUCCESS

        except Exception as e:
            logger.error("Failed to export spans to file: %s", str(e))
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        """Shutdown exporter and flush remaining spans."""
        try:
            with self._lock:
                if self._current_spans:
                    self._flush_to_file()
        except Exception as e:
            logger.error("Failed to shutdown file exporter: %s", str(e))

    def force_flush(self, timeout_millis: int = 30000) -> SpanExportResult:
        """Force flush remaining spans to file."""
        try:
            with self._lock:
                if self._current_spans:
                    self._flush_to_file()
            return SpanExportResult.SUCCESS
        except Exception as e:
            logger.error("Failed to force flush file exporter: %s", str(e))
            return SpanExportResult.FAILURE

    def _flush_to_file(self) -> None:
        """Flush current spans to file."""
        if not self._current_spans:
            return

        # Create new file for this batch
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"spans_{timestamp}_{self._file_counter}.json"
        self._current_file = self.output_dir / filename

        # Convert spans to serializable format
        serializable_spans = []
        for span in self._current_spans:
            span_data = {
                "name": span.name,
                "trace_id": f"{span.trace_id:032x}",
                "span_id": f"{span.span_id:016x}",
                "parent_span_id": f"{span.parent_span_id:016x}"
                if span.parent_span_id
                else None,
                "start_time": span.start_time,
                "end_time": span.end_time,
                "status": {
                    "status_code": span.status.status_code.name,
                    "description": span.status.description,
                }
                if span.status
                else None,
                "attributes": dict(span.attributes) if span.attributes else {},
                "events": [
                    {
                        "timestamp": event.timestamp,
                        "attributes": dict(event.attributes)
                        if event.attributes
                        else {},
                    }
                    for event in (span.events or [])
                ],
                "resource": {
                    "attributes": dict(span.resource.attributes)
                    if span.resource and span.resource.attributes
                    else {}
                }
                if span.resource
                else None,
            }
            serializable_spans.append(span_data)

        # Write to file
        export_data = {
            "export_timestamp": datetime.utcnow().isoformat(),
            "span_count": len(serializable_spans),
            "spans": serializable_spans,
        }

        with open(self._current_file, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info(
            f"Exported {len(serializable_spans)} spans to file",
            filename=str(self._current_file),
        )

        # Reset for next batch
        self._current_spans.clear()
        self._file_counter += 1
