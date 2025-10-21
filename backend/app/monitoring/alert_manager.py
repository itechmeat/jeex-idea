"""
Redis Alert Manager

Advanced alert management system for Redis monitoring.
Handles threshold-based alerting, alert aggregation, and notification routing.
Implements Domain-Driven patterns with project isolation.
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID, uuid4
from collections import defaultdict
import json

from redis.asyncio import Redis
from redis.exceptions import RedisError
import structlog

from ..core.config import settings
from ..infrastructure.redis.connection_factory import redis_connection_factory
from .redis_metrics import redis_metrics_collector
from .health_checker import redis_health_checker, HealthStatus

logger = structlog.get_logger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status levels."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class AlertCategory(Enum):
    """Alert categories for grouping."""

    MEMORY = "memory"
    PERFORMANCE = "performance"
    CONNECTIVITY = "connectivity"
    CONNECTION_POOL = "connection_pool"
    ERROR_RATE = "error_rate"
    AVAILABILITY = "availability"


@dataclass
class AlertRule:
    """Alert rule configuration."""

    id: str
    name: str
    category: AlertCategory
    severity: AlertSeverity
    threshold: float
    operator: str  # ">", "<", ">=", "<=", "=="
    metric_path: str  # Path to metric in data
    description: str
    enabled: bool = True
    cooldown_minutes: int = 5
    suppression_hours: int = 1
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class Alert:
    """Alert instance.

    CRITICAL: project_id is REQUIRED for proper project isolation.
    """

    project_id: UUID  # REQUIRED - never Optional, never None
    id: UUID = field(default_factory=uuid4)
    rule_id: str = ""
    category: AlertCategory = AlertCategory.MEMORY
    severity: AlertSeverity = AlertSeverity.WARNING
    status: AlertStatus = AlertStatus.ACTIVE
    title: str = ""
    message: str = ""
    current_value: float = 0.0
    threshold: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class AlertNotification:
    """Alert notification configuration."""

    id: str
    name: str
    type: str  # "log", "webhook", "email", "slack"
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    filters: Dict[str, Any] = field(default_factory=dict)  # Severity, category filters


class RedisAlertManager:
    """
    Advanced Redis alert management system.

    Features:
    - Threshold-based alerting with configurable rules
    - Alert aggregation and deduplication
    - Alert cooldown and suppression mechanisms
    - Multiple notification channels
    - Alert lifecycle management (acknowledge, resolve, suppress)
    - Project-scoped alerting
    - Alert history and analytics
    """

    def __init__(self):
        self.settings = settings

        # Alert storage
        self._alerts: Dict[UUID, Alert] = {}
        self._alert_rules: Dict[str, AlertRule] = {}
        self._notifications: Dict[str, AlertNotification] = {}
        self._alert_history: List[Alert] = []
        self._max_history_size = 10000

        # Alert state tracking
        self._last_evaluation: Dict[str, datetime] = {}
        self._suppressed_rules: Dict[str, datetime] = {}
        self._alert_counts: Dict[str, int] = defaultdict(int)

        # Background evaluation task
        self._evaluation_task: Optional[asyncio.Task] = None

        # Initialize default alert rules
        self._initialize_default_rules()

        logger.info(
            "Redis alert manager initialized",
            rules_count=len(self._alert_rules),
            notifications_count=len(self._notifications),
        )

    def _initialize_default_rules(self) -> None:
        """Initialize default alert rules for Redis monitoring."""
        default_rules = [
            # Memory alerts
            AlertRule(
                id="redis_memory_usage_warning",
                name="Redis Memory Usage Warning",
                category=AlertCategory.MEMORY,
                severity=AlertSeverity.WARNING,
                threshold=80.0,
                operator=">=",
                metric_path="memory.percentage",
                description="Redis memory usage is above 80%",
                cooldown_minutes=5,
                tags={"component": "redis", "metric": "memory"},
            ),
            AlertRule(
                id="redis_memory_usage_critical",
                name="Redis Memory Usage Critical",
                category=AlertCategory.MEMORY,
                severity=AlertSeverity.CRITICAL,
                threshold=90.0,
                operator=">=",
                metric_path="memory.percentage",
                description="Redis memory usage is above 90%",
                cooldown_minutes=2,
                tags={"component": "redis", "metric": "memory"},
            ),
            AlertRule(
                id="redis_hit_rate_low",
                name="Redis Cache Hit Rate Low",
                category=AlertCategory.PERFORMANCE,
                severity=AlertSeverity.WARNING,
                threshold=0.8,
                operator="<",
                metric_path="memory.hit_rate",
                description="Redis cache hit rate is below 80%",
                cooldown_minutes=10,
                tags={"component": "redis", "metric": "hit_rate"},
            ),
            AlertRule(
                id="redis_response_time_high",
                name="Redis Response Time High",
                category=AlertCategory.PERFORMANCE,
                severity=AlertSeverity.ERROR,
                threshold=100.0,
                operator=">",
                metric_path="commands.p95_duration_ms",
                description="Redis P95 response time is above 100ms",
                cooldown_minutes=5,
                tags={"component": "redis", "metric": "response_time"},
            ),
            AlertRule(
                id="redis_connection_pool_high",
                name="Redis Connection Pool Usage High",
                category=AlertCategory.CONNECTION_POOL,
                severity=AlertSeverity.WARNING,
                threshold=0.8,
                operator=">",
                metric_path="connections.connection_utilization",
                description="Redis connection pool usage is above 80%",
                cooldown_minutes=5,
                tags={"component": "redis", "metric": "connections"},
            ),
            AlertRule(
                id="redis_connection_pool_critical",
                name="Redis Connection Pool Usage Critical",
                category=AlertCategory.CONNECTION_POOL,
                severity=AlertSeverity.CRITICAL,
                threshold=0.95,
                operator=">",
                metric_path="connections.connection_utilization",
                description="Redis connection pool usage is above 95%",
                cooldown_minutes=2,
                tags={"component": "redis", "metric": "connections"},
            ),
            AlertRule(
                id="redis_error_rate_high",
                name="Redis Error Rate High",
                category=AlertCategory.ERROR_RATE,
                severity=AlertSeverity.ERROR,
                threshold=0.05,
                operator=">",
                metric_path="performance.error_rate_5m",
                description="Redis error rate is above 5%",
                cooldown_minutes=5,
                tags={"component": "redis", "metric": "error_rate"},
            ),
            AlertRule(
                id="redis_unhealthy",
                name="Redis Service Unhealthy",
                category=AlertCategory.AVAILABILITY,
                severity=AlertSeverity.CRITICAL,
                threshold=1.0,
                operator="==",
                metric_path="health.unhealthy_checks",
                description="Redis health check is unhealthy",
                cooldown_minutes=1,
                tags={"component": "redis", "metric": "health"},
            ),
        ]

        for rule in default_rules:
            self._alert_rules[rule.id] = rule

        # Initialize default notification
        default_notification = AlertNotification(
            id="log_notification",
            name="Log Notification",
            type="log",
            enabled=True,
            config={},
            filters={"severity": ["warning", "error", "critical"]},
        )
        self._notifications[default_notification.id] = default_notification

    async def start_alerting(self) -> None:
        """Start background alert evaluation."""
        if self._evaluation_task is None:
            self._evaluation_task = asyncio.create_task(self._evaluation_loop())
            logger.info("Redis alert management started")

    async def stop_alerting(self) -> None:
        """Stop background alert evaluation."""
        if self._evaluation_task:
            self._evaluation_task.cancel()
            try:
                await self._evaluation_task
            except asyncio.CancelledError:
                pass
            self._evaluation_task = None
            logger.info("Redis alert management stopped")

    async def _evaluation_loop(self) -> None:
        """Background alert evaluation loop."""
        while True:
            try:
                await self._evaluate_alert_rules()
                await self._cleanup_old_alerts()
                await self._cleanup_suppressions()
                await asyncio.sleep(60)  # Evaluate every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(
                    "Redis alert evaluation error", error=str(e), exc_info=True
                )
                await asyncio.sleep(5)
                # Note: Not re-raising here as this is a background loop that should continue
                # But we log with full exception context

    async def _evaluate_alert_rules(self) -> None:
        """Evaluate all enabled alert rules."""
        # TODO: REDO - Alert manager needs to be project-scoped
        # Current implementation doesn't provide project_id context
        # This requires architectural changes to make alert manager per-project
        raise NotImplementedError(
            "Alert manager needs project context for proper isolation"
        )

        # Get current metrics
        metrics_summary = await redis_metrics_collector.get_metrics_summary()
        health_status = await redis_health_checker.get_latest_health_status()

        # Combine metrics for evaluation
        evaluation_data = {
            "memory": metrics_summary.get("memory", {}),
            "connections": metrics_summary.get("connections", {}),
            "commands": metrics_summary.get("commands", {}),
            "performance": metrics_summary.get("performance", {}),
            "health": {
                "status": health_status.status.value if health_status else "unknown",
                "unhealthy_checks": len(
                    [
                        c
                        for c in health_status.checks
                        if c.status == HealthStatus.UNHEALTHY
                    ]
                )
                if health_status
                else 0,
            },
        }

        # Evaluate each rule
        for rule in self._alert_rules.values():
            if not rule.enabled:
                continue

            # Check cooldown
            if not self._should_evaluate_rule(rule):
                continue

            try:
                # TODO: Pass project_id here - requires project context
                await self._evaluate_rule(
                    rule, evaluation_data, UUID(int=0)
                )  # Placeholder
            except Exception as e:
                logger.error(
                    "Failed to evaluate alert rule",
                    rule_id=rule.id,
                    error=str(e),
                    exc_info=True,
                )
                # Re-raise to preserve error context
                raise

    def _should_evaluate_rule(self, rule: AlertRule) -> bool:
        """Check if rule should be evaluated based on cooldown."""
        now = datetime.utcnow()

        # Check if rule is suppressed
        if rule.id in self._suppressed_rules:
            suppression_end = self._suppressed_rules[rule.id]
            if now < suppression_end:
                return False
            else:
                # Suppression expired, remove it
                del self._suppressed_rules[rule.id]

        # Check cooldown
        last_eval = self._last_evaluation.get(rule.id)
        if last_eval:
            time_since_last = (now - last_eval).total_seconds()
            if time_since_last < rule.cooldown_minutes * 60:
                return False

        return True

    async def _evaluate_rule(
        self, rule: AlertRule, data: Dict[str, Any], project_id: UUID
    ) -> None:
        """Evaluate a single alert rule."""
        try:
            # Extract metric value using the metric path
            current_value = self._extract_metric_value(rule.metric_path, data)

            if current_value is None:
                logger.debug(
                    "Metric value not found for rule",
                    rule_id=rule.id,
                    metric_path=rule.metric_path,
                    project_id=project_id,
                )
                return

            # Evaluate threshold condition
            triggered = self._evaluate_threshold(
                current_value, rule.threshold, rule.operator
            )

            # Update last evaluation time
            self._last_evaluation[rule.id] = datetime.utcnow()

            if triggered:
                await self._trigger_alert(rule, current_value, data, project_id)
            else:
                await self._check_alert_resolution(rule, current_value, project_id)

        except Exception as e:
            logger.error(
                "Failed to evaluate alert rule",
                rule_id=rule.id,
                project_id=project_id,
                error=str(e),
                exc_info=True,
            )
            # Re-raise to preserve error context
            raise

    def _extract_metric_value(
        self, metric_path: str, data: Dict[str, Any]
    ) -> Optional[float]:
        """Extract metric value from data using dot notation."""
        try:
            parts = metric_path.split(".")
            current = data

            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None

            # Convert to float if possible
            if isinstance(current, (int, float)):
                return float(current)
            elif isinstance(current, str):
                # Handle percentage values
                if current.endswith("%"):
                    return float(current.rstrip("%"))
                else:
                    return float(current)
            else:
                return None

        except Exception:
            return None

    def _evaluate_threshold(
        self, current_value: float, threshold: float, operator: str
    ) -> bool:
        """Evaluate threshold condition."""
        if operator == ">":
            return current_value > threshold
        elif operator == ">=":
            return current_value >= threshold
        elif operator == "<":
            return current_value < threshold
        elif operator == "<=":
            return current_value <= threshold
        elif operator == "==":
            return current_value == threshold
        elif operator == "!=":
            return current_value != threshold
        else:
            logger.warning("Unknown threshold operator", operator=operator)
            return False

    async def _trigger_alert(
        self,
        rule: AlertRule,
        current_value: float,
        data: Dict[str, Any],
        project_id: UUID,
    ) -> None:
        """Trigger an alert for a rule."""
        # Check if there's already an active alert for this rule
        existing_alert = self._find_active_alert(rule.id, project_id)
        if existing_alert:
            # Update existing alert
            existing_alert.current_value = current_value
            existing_alert.updated_at = datetime.utcnow()
            existing_alert.metadata.update(data)
            logger.debug(
                "Updated existing alert",
                alert_id=existing_alert.id,
                rule_id=rule.id,
                project_id=project_id,
                current_value=current_value,
            )
            return

        # Create new alert
        alert = Alert(
            project_id=project_id,
            rule_id=rule.id,
            category=rule.category,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            title=f"{rule.name}: {current_value:.2f}",
            message=self._generate_alert_message(rule, current_value, data),
            current_value=current_value,
            threshold=rule.threshold,
            metadata=data.copy(),
            tags=rule.tags.copy(),
        )

        # Store alert
        self._alerts[alert.id] = alert
        self._alert_history.append(alert)
        if len(self._alert_history) > self._max_history_size:
            self._alert_history.pop(0)

        # Update alert count
        self._alert_counts[rule.id] += 1

        # Send notifications
        await self._send_notifications(alert)

        # Log alert
        log_method = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.ERROR: logger.error,
            AlertSeverity.CRITICAL: logger.critical,
        }.get(alert.severity, logger.warning)

        log_method(
            "Redis alert triggered",
            alert_id=alert.id,
            rule_id=rule.id,
            title=alert.title,
            severity=alert.severity.value,
            current_value=current_value,
            threshold=rule.threshold,
        )

    def _find_active_alert(self, rule_id: str, project_id: UUID) -> Optional[Alert]:
        """Find existing active alert for a rule."""
        for alert in self._alerts.values():
            if (
                alert.rule_id == rule_id
                and alert.project_id == project_id
                and alert.status == AlertStatus.ACTIVE
            ):
                return alert
        return None

    def _generate_alert_message(
        self, rule: AlertRule, current_value: float, data: Dict[str, Any]
    ) -> str:
        """Generate alert message."""
        message = rule.description

        # Add context based on category
        if rule.category == AlertCategory.MEMORY:
            memory_data = data.get("memory", {})
            used_memory_mb = memory_data.get("used_memory_mb", 0)
            max_memory_mb = memory_data.get("max_memory_mb", 0)
            if used_memory_mb > 0 and max_memory_mb > 0:
                message += f" (Used: {used_memory_mb:.1f}MB / {max_memory_mb:.1f}MB)"

        elif rule.category == AlertCategory.PERFORMANCE:
            if "hit_rate" in rule.metric_path:
                hit_rate = current_value * 100  # Convert to percentage
                message += f" (Current: {hit_rate:.1f}%)"
            elif "duration" in rule.metric_path:
                message += f" (Current: {current_value:.2f}ms)"

        elif rule.category == AlertCategory.CONNECTION_POOL:
            connection_data = data.get("connections", {})
            active_connections = connection_data.get("active_connections", 0)
            max_connections = connection_data.get("max_connections", 0)
            if active_connections > 0 and max_connections > 0:
                message += f" (Active: {active_connections}/{max_connections})"

        return message

    async def _check_alert_resolution(
        self, rule: AlertRule, current_value: float, project_id: UUID
    ) -> None:
        """Check if active alerts should be resolved."""
        existing_alert = self._find_active_alert(rule.id, project_id)
        if not existing_alert:
            return

        # Check if the condition is no longer met
        triggered = self._evaluate_threshold(
            current_value, rule.threshold, rule.operator
        )

        if not triggered:
            # Resolve the alert
            existing_alert.status = AlertStatus.RESOLVED
            existing_alert.resolved_at = datetime.utcnow()
            existing_alert.updated_at = datetime.utcnow()

            logger.info(
                "Redis alert resolved",
                alert_id=existing_alert.id,
                rule_id=rule.id,
                current_value=current_value,
                threshold=rule.threshold,
            )

    async def _send_notifications(self, alert: Alert) -> None:
        """Send notifications for an alert."""
        for notification in self._notifications.values():
            if not notification.enabled:
                continue

            # Check if alert matches notification filters
            if not self._alert_matches_filters(alert, notification.filters):
                continue

            try:
                await self._send_notification(alert, notification)
            except Exception as e:
                logger.error(
                    "Failed to send notification",
                    alert_id=alert.id,
                    notification_id=notification.id,
                    error=str(e),
                    exc_info=True,
                )
                # Note: Not re-raising here as notification failures shouldn't block alert creation
                # But we log with full exception context

    def _alert_matches_filters(self, alert: Alert, filters: Dict[str, Any]) -> bool:
        """Check if alert matches notification filters."""
        # Filter by severity
        if "severity" in filters:
            allowed_severities = filters["severity"]
            if isinstance(allowed_severities, list):
                if alert.severity.value not in allowed_severities:
                    return False
            elif alert.severity.value != allowed_severities:
                return False

        # Filter by category
        if "category" in filters:
            allowed_categories = filters["category"]
            if isinstance(allowed_categories, list):
                if alert.category.value not in allowed_categories:
                    return False
            elif alert.category.value != allowed_categories:
                return False

        return True

    async def _send_notification(
        self, alert: Alert, notification: AlertNotification
    ) -> None:
        """Send notification through specific channel."""
        if notification.type == "log":
            await self._send_log_notification(alert, notification)
        elif notification.type == "webhook":
            await self._send_webhook_notification(alert, notification)
        else:
            logger.warning("Unknown notification type", type=notification.type)

    async def _send_log_notification(
        self, alert: Alert, notification: AlertNotification
    ) -> None:
        """Send log notification."""
        log_method = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.ERROR: logger.error,
            AlertSeverity.CRITICAL: logger.critical,
        }.get(alert.severity, logger.warning)

        log_method(
            "ALERT NOTIFICATION",
            alert_id=str(alert.id),
            title=alert.title,
            message=alert.message,
            severity=alert.severity.value,
            category=alert.category.value,
            current_value=alert.current_value,
            threshold=alert.threshold,
            project_id=str(alert.project_id) if alert.project_id else None,
            metadata=alert.metadata,
        )

    async def _send_webhook_notification(
        self, alert: Alert, notification: AlertNotification
    ) -> None:
        """Send webhook notification."""
        import httpx

        webhook_url = notification.config.get("url")
        if not webhook_url:
            logger.warning(
                "Webhook URL not configured", notification_id=notification.id
            )
            return

        payload = {
            "alert_id": str(alert.id),
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity.value,
            "category": alert.category.value,
            "current_value": alert.current_value,
            "threshold": alert.threshold,
            "project_id": str(alert.project_id) if alert.project_id else None,
            "metadata": alert.metadata,
            "created_at": alert.created_at.isoformat(),
            "tags": alert.tags,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers=notification.config.get("headers", {}),
                )
                response.raise_for_status()

                logger.info(
                    "Webhook notification sent",
                    alert_id=str(alert.id),
                    webhook_url=webhook_url,
                    status_code=response.status_code,
                )

        except Exception as e:
            logger.error(
                "Failed to send webhook notification",
                alert_id=str(alert.id),
                webhook_url=webhook_url,
                error=str(e),
                exc_info=True,
            )
            # Re-raise to preserve error context
            raise

    async def _cleanup_old_alerts(self) -> None:
        """Clean up old resolved alerts."""
        cutoff_time = datetime.utcnow() - timedelta(hours=24)

        # Remove old resolved alerts from active alerts
        alerts_to_remove = []
        for alert_id, alert in self._alerts.items():
            if alert.status == AlertStatus.RESOLVED and alert.resolved_at:
                if alert.resolved_at < cutoff_time:
                    alerts_to_remove.append(alert_id)

        for alert_id in alerts_to_remove:
            del self._alerts[alert_id]

        # Clean up alert history
        if len(self._alert_history) > self._max_history_size:
            self._alert_history = self._alert_history[-self._max_history_size :]

    async def _cleanup_suppressions(self) -> None:
        """Clean up expired suppressions."""
        now = datetime.utcnow()
        expired_suppressions = []

        for rule_id, suppression_end in self._suppressed_rules.items():
            if now >= suppression_end:
                expired_suppressions.append(rule_id)

        for rule_id in expired_suppressions:
            del self._suppressed_rules[rule_id]
            logger.debug("Alert suppression expired", rule_id=rule_id)

    # API methods for alert management
    async def acknowledge_alert(self, alert_id: UUID, acknowledged_by: str) -> bool:
        """Acknowledge an alert."""
        alert = self._alerts.get(alert_id)
        if not alert or alert.status != AlertStatus.ACTIVE:
            return False

        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = acknowledged_by
        alert.updated_at = datetime.utcnow()

        logger.info(
            "Alert acknowledged",
            alert_id=str(alert_id),
            acknowledged_by=acknowledged_by,
        )

        return True

    async def resolve_alert(self, alert_id: UUID) -> bool:
        """Manually resolve an alert."""
        alert = self._alerts.get(alert_id)
        if not alert or alert.status == AlertStatus.RESOLVED:
            return False

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.utcnow()
        alert.updated_at = datetime.utcnow()

        logger.info("Alert resolved", alert_id=str(alert_id))

        return True

    async def suppress_rule(self, rule_id: str, hours: int, reason: str = "") -> bool:
        """Suppress an alert rule for a specified duration."""
        rule = self._alert_rules.get(rule_id)
        if not rule:
            return False

        suppression_end = datetime.utcnow() + timedelta(hours=hours)
        self._suppressed_rules[rule_id] = suppression_end

        # Resolve any active alerts for this rule
        for alert in self._alerts.values():
            if alert.rule_id == rule_id and alert.status == AlertStatus.ACTIVE:
                alert.status = AlertStatus.SUPPRESSED
                alert.updated_at = datetime.utcnow()

        logger.info(
            "Alert rule suppressed",
            rule_id=rule_id,
            hours=hours,
            reason=reason,
            suppression_end=suppression_end.isoformat(),
        )

        return True

    async def get_alerts(
        self,
        status: Optional[AlertStatus] = None,
        severity: Optional[AlertSeverity] = None,
        category: Optional[AlertCategory] = None,
        project_id: Optional[UUID] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """Get alerts with optional filtering."""
        alerts = list(self._alerts.values())

        # Apply filters
        if status:
            alerts = [a for a in alerts if a.status == status]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if category:
            alerts = [a for a in alerts if a.category == category]

        if project_id:
            alerts = [a for a in alerts if a.project_id == project_id]

        # Sort by creation time (newest first)
        alerts.sort(key=lambda a: a.created_at, reverse=True)

        # Apply limit
        return alerts[:limit]

    async def get_alert_summary(self) -> Dict[str, Any]:
        """Get alert summary statistics."""
        active_alerts = [
            a for a in self._alerts.values() if a.status == AlertStatus.ACTIVE
        ]
        acknowledged_alerts = [
            a for a in self._alerts.values() if a.status == AlertStatus.ACKNOWLEDGED
        ]
        resolved_alerts = [
            a for a in self._alerts.values() if a.status == AlertStatus.RESOLVED
        ]

        # Count by severity
        severity_counts = defaultdict(int)
        for alert in active_alerts:
            severity_counts[alert.severity.value] += 1

        # Count by category
        category_counts = defaultdict(int)
        for alert in active_alerts:
            category_counts[alert.category.value] += 1

        return {
            "total_alerts": len(self._alerts),
            "active_alerts": len(active_alerts),
            "acknowledged_alerts": len(acknowledged_alerts),
            "resolved_alerts": len(resolved_alerts),
            "suppressed_rules": len(self._suppressed_rules),
            "severity_breakdown": dict(severity_counts),
            "category_breakdown": dict(category_counts),
            "rules_enabled": len([r for r in self._alert_rules.values() if r.enabled]),
            "rules_disabled": len(
                [r for r in self._alert_rules.values() if not r.enabled]
            ),
        }


# Global Redis alert manager instance
redis_alert_manager = RedisAlertManager()
