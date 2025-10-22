"""
Redis Instrumentation Integration Module

Integration layer for Redis OpenTelemetry instrumentation with the existing system.
This module provides proper initialization, configuration, and lifecycle management
for enhanced Redis instrumentation.

Implements Task 2.2 integration requirements:
- Redis client instrumentation initialization
- Cache hit/miss ratio monitoring setup
- Operation latency metrics configuration
- Memory usage monitoring integration
- Connection pool metrics setup
"""

import asyncio
import logging
from typing import Optional, Dict, Any

from .redis_instrumentation import redis_instrumentation
from .telemetry import get_tracer, add_span_attribute
from .config import settings
from ..infrastructure.redis.connection_factory import redis_connection_factory

logger = logging.getLogger(__name__)


class RedisInstrumentationIntegration:
    """
    Integration manager for Redis OpenTelemetry instrumentation.

    Handles initialization, configuration, and lifecycle management of
    enhanced Redis instrumentation with proper error handling and fallbacks.
    """

    def __init__(self):
        self.tracer = get_tracer(__name__)
        self._initialized = False
        self._background_collection_running = False
        self._redis_client_for_collection = None

    async def initialize(self) -> bool:
        """
        Initialize enhanced Redis instrumentation.

        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            logger.warning("Redis instrumentation integration already initialized")
            return True

        try:
            with self.tracer.start_as_current_span(
                "redis.instrumentation.initialize"
            ) as span:
                logger.info("Initializing enhanced Redis instrumentation integration")

                # Ensure connection factory is initialized
                await redis_connection_factory.initialize()

                # Get admin connection for background collection
                # Store reference outside context manager to prevent premature closure
                self._redis_client_for_collection = (
                    await redis_connection_factory.get_admin_connection().__aenter__()
                )

                # Start background metrics collection
                await redis_instrumentation.start_background_collection(
                    self._redis_client_for_collection
                )
                self._background_collection_running = True

                self._initialized = True

                # Set span attributes
                add_span_attribute("redis.instrumentation.initialized", True)
                add_span_attribute("redis.instrumentation.background_collection", True)

                logger.info(
                    "Enhanced Redis instrumentation integration initialized successfully",
                    background_collection=self._background_collection_running,
                )
                return True

        except Exception as e:
            logger.error(
                "Failed to initialize enhanced Redis instrumentation integration",
                error=str(e),
                exc_info=True,
            )
            add_span_attribute("redis.instrumentation.initialized", False)
            add_span_attribute("redis.instrumentation.error", str(e))
            raise

    async def shutdown(self) -> None:
        """Gracefully shutdown Redis instrumentation integration."""
        if not self._initialized:
            return

        try:
            with self.tracer.start_as_current_span(
                "redis.instrumentation.shutdown"
            ) as span:
                logger.info("Shutting down enhanced Redis instrumentation integration")

                # Stop background collection
                if self._background_collection_running:
                    await redis_instrumentation.stop_background_collection()
                    self._background_collection_running = False

                # Properly close Redis client connection if it exists
                if self._redis_client_for_collection:
                    try:
                        await self._redis_client_for_collection.aclose()
                    except Exception as close_error:
                        logger.warning(
                            "Error closing Redis client connection during shutdown",
                            error=str(close_error),
                        )
                    finally:
                        self._redis_client_for_collection = None

                self._initialized = False

                add_span_attribute("redis.instrumentation.shutdown", True)

                logger.info(
                    "Enhanced Redis instrumentation integration shutdown completed"
                )

        except Exception as e:
            logger.error(
                "Error during Redis instrumentation shutdown",
                error=str(e),
                exc_info=True,
            )
            # Continue with shutdown even if individual components fail
            # Don't re-raise to allow graceful shutdown

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on Redis instrumentation integration.

        Returns:
            Health status with detailed component information
        """
        health_status = {
            "status": "healthy",
            "timestamp": 0,
            "components": {},
            "errors": [],
        }

        try:
            import time

            health_status["timestamp"] = time.time()

            # Check initialization status
            health_status["components"]["initialization"] = {
                "status": "healthy" if self._initialized else "unhealthy",
                "initialized": self._initialized,
            }

            # Check background collection
            health_status["components"]["background_collection"] = {
                "status": "healthy"
                if self._background_collection_running
                else "stopped",
                "running": self._background_collection_running,
            }

            # Check connection factory
            try:
                connection_factory_health = (
                    await redis_connection_factory.health_check()
                )
                health_status["components"]["connection_factory"] = {
                    "status": connection_factory_health.get("status", "unknown"),
                    "details": connection_factory_health,
                }
            except Exception as e:
                health_status["components"]["connection_factory"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }
                health_status["errors"].append(
                    f"Connection factory health check failed: {e}"
                )

            # Check enhanced instrumentation metrics
            try:
                cache_performance = (
                    redis_instrumentation.get_cache_performance_summary()
                )
                error_stats = redis_instrumentation.get_error_rate_stats()

                health_status["components"]["instrumentation_metrics"] = {
                    "status": "healthy",
                    "cache_performance": cache_performance,
                    "error_rates": error_stats,
                }

                # Check for high error rates
                if error_stats.get("error_rate", 0) > 0.1:  # 10% error rate threshold
                    health_status["components"]["instrumentation_metrics"]["status"] = (
                        "degraded"
                    )
                    health_status["errors"].append(
                        f"High error rate detected: {error_stats['error_rate']:.2%}"
                    )

            except Exception as e:
                health_status["components"]["instrumentation_metrics"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }
                health_status["errors"].append(
                    f"Instrumentation metrics check failed: {e}"
                )

            # Determine overall status
            component_statuses = [
                comp.get("status", "unknown")
                for comp in health_status["components"].values()
            ]

            if "unhealthy" in component_statuses:
                health_status["status"] = "unhealthy"
            elif "degraded" in component_statuses or "stopped" in component_statuses:
                health_status["status"] = "degraded"

        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["errors"].append(f"Health check failed: {e}")
            logger.error(
                "Redis instrumentation health check failed", error=str(e), exc_info=True
            )
            raise

    async def get_comprehensive_metrics(
        self, project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive Redis metrics from all sources.

        Args:
            project_id: Optional project ID for scoped metrics

        Returns:
            Comprehensive metrics dictionary
        """
        try:
            metrics = {
                "timestamp": 0,
                "project_id": project_id,
                "connection_factory": {},
                "enhanced_instrumentation": {},
                "cache_performance": {},
                "error_analysis": {},
                "command_latencies": {},
                "memory_usage": {},
            }

            import time

            metrics["timestamp"] = time.time()

            # Get connection factory metrics
            try:
                if hasattr(redis_connection_factory, "get_enhanced_metrics"):
                    metrics[
                        "connection_factory"
                    ] = await redis_connection_factory.get_enhanced_metrics()
                else:
                    metrics["connection_factory"] = (
                        redis_connection_factory.get_metrics()
                    )
            except Exception as e:
                logger.warning(f"Failed to get connection factory metrics: {e}")
                metrics["connection_factory"] = {"error": str(e)}

            # Get enhanced instrumentation metrics
            try:
                metrics["cache_performance"] = (
                    redis_instrumentation.get_cache_performance_summary()
                )
                metrics["error_analysis"] = redis_instrumentation.get_error_rate_stats()
                metrics[
                    "command_latencies"
                ] = await redis_instrumentation.get_command_latency_stats()
            except Exception as e:
                logger.warning(f"Failed to get enhanced instrumentation metrics: {e}")
                metrics["enhanced_instrumentation"] = {"error": str(e)}

            # Get memory usage statistics
            try:
                if self._redis_client_for_collection:
                    memory_stats = await redis_instrumentation.collect_redis_info(
                        self._redis_client_for_collection
                    )
                    metrics["memory_usage"] = {
                        "used_memory_mb": memory_stats.used_memory / 1024 / 1024,
                        "used_memory_rss_mb": memory_stats.used_memory_rss
                        / 1024
                        / 1024,
                        "max_memory_mb": memory_stats.max_memory / 1024 / 1024,
                        "fragmentation_ratio": memory_stats.memory_fragmentation_ratio,
                        "maxmemory_policy": memory_stats.maxmemory_policy,
                        "allocator_allocated_mb": memory_stats.allocator_allocated
                        / 1024
                        / 1024,
                        "allocator_active_mb": memory_stats.allocator_active
                        / 1024
                        / 1024,
                    }
            except Exception as e:
                logger.warning(f"Failed to collect memory usage statistics: {e}")
                metrics["memory_usage"] = {"error": str(e)}

            return metrics

        except Exception as e:
            logger.error(
                f"Failed to get comprehensive Redis metrics: {e}", exc_info=True
            )
            raise

    async def get_instrumentation_status(self) -> Dict[str, Any]:
        """
        Get detailed instrumentation status.

        Returns:
            Instrumentation status with component details
        """
        return {
            "initialized": self._initialized,
            "background_collection_running": self._background_collection_running,
            "redis_client_available": self._redis_client_for_collection is not None,
            "enhanced_instrumentation_available": redis_instrumentation is not None,
            "connection_factory_initialized": redis_connection_factory._initialized,
        }

    def get_tracer(self, name: str):
        """
        Get tracer instance for manual instrumentation.

        Args:
            name: Tracer name

        Returns:
            Tracer instance
        """
        return self.tracer

    def add_span_attribute(self, key: str, value: Any) -> None:
        """
        Add attribute to current span.

        Args:
            key: Attribute key
            value: Attribute value
        """
        add_span_attribute(key, value)


# Global Redis instrumentation integration instance
redis_instrumentation_integration = RedisInstrumentationIntegration()
