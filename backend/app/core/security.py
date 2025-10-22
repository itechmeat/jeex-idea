"""
JEEX Idea Security and Data Sanitization Module

Comprehensive security controls for OpenTelemetry observability stack.
Implements data sanitization, PII redaction, and access control mechanisms.

Features:
- Sensitive header filtering for HTTP spans
- SQL query parameter sanitization in database spans
- PII detection and redaction in custom attributes
- Project-based access control for dashboard access
- Audit logging for security-sensitive operations
- Security-focused testing utilities
"""

import re
import hashlib
import logging
import json
import time
from typing import Dict, List, Any, Optional, Set, Union, Pattern
from datetime import datetime, UTC
from uuid import UUID
from dataclasses import dataclass, field
from enum import Enum
from contextvars import ContextVar

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.semconv.trace import SpanAttributes

# Project imports
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Context variable for current user context
current_user_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "current_user_context", default=None
)


class SensitivityLevel(Enum):
    """Data sensitivity levels for classification."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


@dataclass
class SecurityConfig:
    """Configuration for security and sanitization controls."""

    # Header filtering
    sensitive_headers: Set[str] = field(
        default_factory=lambda: {
            "authorization",
            "cookie",
            "set-cookie",
            "x-api-key",
            "x-auth-token",
            "x-forwarded-for",
            "x-real-ip",
            "user-agent",
            "referer",
        }
    )

    # PII patterns
    pii_patterns: List[Pattern] = field(
        default_factory=lambda: [
            # Email addresses
            re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            # Phone numbers (various formats)
            re.compile(
                r"\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b"
            ),
            # Social Security Numbers
            re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
            # Credit card numbers
            re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
            # IPv4 addresses
            re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
            # API keys (common patterns)
            re.compile(r"\b[A-Za-z0-9]{20,}\b"),
        ]
    )

    # SQL sanitization
    sql_sanitization_enabled: bool = True
    sql_parameter_redaction: bool = True
    sql_sensitive_keywords: Set[str] = field(
        default_factory=lambda: {
            "password",
            "token",
            "secret",
            "key",
            "hash",
            "salt",
            "credential",
        }
    )

    # Access control
    dashboard_access_control_enabled: bool = True
    project_isolation_enforced: bool = True

    # Audit logging
    audit_logging_enabled: bool = True
    audit_retention_days: int = 90


class PIIProcessor:
    """Process and redact Personally Identifiable Information from telemetry data."""

    def __init__(self, config: SecurityConfig):
        self.config = config
        self._redaction_cache: Dict[str, str] = {}

    def detect_pii(self, text: str) -> List[Dict[str, Any]]:
        """
        Detect PII patterns in text.

        Args:
            text: Text to scan for PII

        Returns:
            List of detected PII instances with metadata
        """
        pii_instances = []

        for pattern in self.config.pii_patterns:
            matches = pattern.finditer(text)
            for match in matches:
                pii_type = self._classify_pii_pattern(pattern.pattern)
                pii_instances.append(
                    {
                        "type": pii_type,
                        "value": match.group(),
                        "start": match.start(),
                        "end": match.end(),
                        "redacted_value": self._redact_value(match.group(), pii_type),
                    }
                )

        return pii_instances

    def redact_pii(self, text: str) -> str:
        """
        Redact PII from text while preserving structure.

        Args:
            text: Text containing PII

        Returns:
            Text with PII redacted
        """
        if not text:
            return text

        # Check cache first
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        if text_hash in self._redaction_cache:
            return self._redaction_cache[text_hash]

        redacted_text = text
        pii_instances = self.detect_pii(text)

        # Replace PII instances from end to start to preserve indices
        for pii in sorted(pii_instances, key=lambda x: x["start"], reverse=True):
            redacted_text = (
                redacted_text[: pii["start"]]
                + pii["redacted_value"]
                + redacted_text[pii["end"] :]
            )

        # Cache result
        self._redaction_cache[text_hash] = redacted_text

        return redacted_text

    def _classify_pii_pattern(self, pattern: str) -> str:
        """Classify PII type based on regex pattern."""
        if "@" in pattern:
            return "email"
        elif r"\d{3}-\d{2}-\d{4}" in pattern:
            return "ssn"
        elif "credit" in pattern.lower() or r"\d{4}" in pattern:
            return "credit_card"
        elif r"[0-9]{1,3}\.[0-9]{1,3}" in pattern:
            return "ip_address"
        elif "phone" in pattern.lower():
            return "phone"
        else:
            return "unknown"

    def _redact_value(self, value: str, pii_type: str) -> str:
        """Redact a specific PII value."""
        if pii_type == "email":
            # Show first character and domain
            if "@" in value:
                local, domain = value.split("@", 1)
                return f"{local[0]}***@{domain}"
            return "***@***.***"

        elif pii_type == "phone":
            # Show area code only
            return f"({value[:3]}) ***-****" if len(value) >= 10 else "***-****"

        elif pii_type in ["ssn", "credit_card"]:
            # Show last 4 digits
            return f"***-**-{value[-4:]}" if len(value) >= 4 else "****"

        elif pii_type == "ip_address":
            # Show first two octets
            parts = value.split(".")
            if len(parts) >= 4:
                return f"{parts[0]}.{parts[1]}.***.***"
            return "***.***.***.***"

        else:
            # Generic redaction
            if len(value) <= 4:
                return "*" * len(value)
            return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


class SQLSanitizer:
    """Sanitize SQL queries and parameters for telemetry."""

    def __init__(self, config: SecurityConfig):
        self.config = config

    def sanitize_sql_query(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Sanitize SQL query and parameters for safe telemetry recording.

        Args:
            query: SQL query string
            parameters: Query parameters

        Returns:
            Sanitized query and parameters
        """
        if not self.config.sql_sanitization_enabled:
            return {"query": query, "parameters": parameters, "sanitized": False}

        sanitized_query = self._sanitize_query_text(query)
        sanitized_parameters = (
            self._sanitize_parameters(parameters) if parameters else None
        )

        return {
            "query": sanitized_query,
            "parameters": sanitized_parameters,
            "sanitized": True,
            "original_length": len(query),
            "sanitized_length": len(sanitized_query),
        }

    def _sanitize_query_text(self, query: str) -> str:
        """Remove or redact sensitive information from SQL query text."""
        # Remove comments that might contain sensitive info
        query = re.sub(r"--.*$", "", query, flags=re.MULTILINE)
        query = re.sub(r"/\*.*?\*/", "", query, flags=re.DOTALL)

        # Redact literal values that might be sensitive
        # Look for string literals that might contain sensitive data
        sensitive_patterns = [
            (r"'([^']*(?:password|token|secret|key|hash)[^']*)'", r"'***'"),
            (r'"([^"]*(?:password|token|secret|key|hash)[^"]*)"', r'"***"'),
            (r"'([^']{20,})'", r"'***'"),  # Long strings
        ]

        for pattern, replacement in sensitive_patterns:
            query = re.sub(pattern, replacement, query, flags=re.IGNORECASE)

        return query.strip()

    def _sanitize_parameters(
        self, parameters: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Redact sensitive parameter values."""
        if not self.config.sql_parameter_redaction or not parameters:
            return parameters

        sanitized = {}
        for key, value in parameters.items():
            if self._is_sensitive_parameter(key):
                sanitized[key] = "***"
            elif isinstance(value, str) and len(value) > 100:
                # Truncate long string values
                sanitized[key] = value[:100] + "..."
            else:
                sanitized[key] = value

        return sanitized

    def _is_sensitive_parameter(self, key: str) -> bool:
        """Check if parameter key indicates sensitive data."""
        key_lower = key.lower()
        return any(
            keyword in key_lower for keyword in self.config.sql_sensitive_keywords
        )


class HeaderFilter:
    """Filter sensitive HTTP headers from telemetry spans."""

    def __init__(self, config: SecurityConfig):
        self.config = config
        self._sensitive_header_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in [
                r"^authorization$",
                r"^cookie$",
                r"^set-cookie$",
                r"^x-api-key$",
                r"^x-auth-token$",
                r"^x-forwarded-for$",
                r"^x-real-ip$",
                r"^user-agent$",
                r"^referer$",
                r".*token.*",
                r".*secret.*",
                r".*key.*",
            ]
        ]

    def filter_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Filter sensitive headers from telemetry data.

        Args:
            headers: HTTP headers dictionary

        Returns:
            Filtered headers with sensitive values redacted
        """
        filtered_headers = {}

        for header_name, header_value in headers.items():
            if self._is_sensitive_header(header_name):
                filtered_headers[header_name] = self._redact_header_value(
                    header_name, header_value
                )
            else:
                filtered_headers[header_name] = header_value

        return filtered_headers

    def _is_sensitive_header(self, header_name: str) -> bool:
        """Check if header is considered sensitive."""
        header_lower = header_name.lower()

        # Check against known sensitive headers
        if header_lower in self.config.sensitive_headers:
            return True

        # Check against patterns
        return any(
            pattern.match(header_lower) for pattern in self._sensitive_header_patterns
        )

    def _redact_header_value(self, header_name: str, header_value: str) -> str:
        """Redact header value while preserving some structure for debugging."""
        header_lower = header_name.lower()

        if header_lower == "authorization":
            # Show auth type but redact credentials
            if " " in header_value:
                auth_type = header_value.split(" ")[0]
                return f"{auth_type} ***"
            return "***"

        elif header_lower in ["cookie", "set-cookie"]:
            # Show cookie count but redact values
            cookie_count = len(header_value.split(";"))
            return f"[{cookie_count} cookie(s)]"

        elif "key" in header_lower or "token" in header_lower:
            # Show first few characters only
            if len(header_value) <= 8:
                return "***"
            return f"{header_value[:4]}***"

        else:
            # Generic redaction
            return "***"


class AuditLogger:
    """Audit logging for security-sensitive operations."""

    def __init__(self, config: SecurityConfig):
        self.config = config
        self._audit_log = []
        self._max_entries = 10000  # In-memory limit

    def log_access_attempt(
        self,
        operation: str,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        resource: Optional[str] = None,
        success: bool = True,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an access attempt for audit purposes.

        Args:
            operation: Operation being attempted
            user_id: User identifier
            project_id: Project identifier
            resource: Resource being accessed
            success: Whether access was successful
            reason: Reason for failure (if applicable)
            metadata: Additional metadata
        """
        if not self.config.audit_logging_enabled:
            return

        # Get correlation ID if available (avoid circular import)
        correlation_id = None
        try:
            from .telemetry import get_correlation_id

            correlation_id = get_correlation_id()
        except ImportError:
            pass

        audit_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "operation": operation,
            "user_id": user_id,
            "project_id": project_id,
            "resource": resource,
            "success": success,
            "reason": reason,
            "correlation_id": correlation_id,
            "metadata": metadata or {},
            "ip_address": self._get_client_ip(),
        }

        # Add to in-memory log
        self._audit_log.append(audit_entry)

        # Trim log if necessary
        if len(self._audit_log) > self._max_entries:
            self._audit_log = self._audit_log[-self._max_entries :]

        # Log to application logger
        level = logging.INFO if success else logging.WARNING
        logger.log(
            level,
            f"Security audit: {operation}",
            extra={
                "audit": True,
                "audit_entry": audit_entry,
                "correlation_id": correlation_id,
            },
        )

    def get_audit_log(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        operation: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit log entries with filtering.

        Args:
            user_id: Filter by user ID
            project_id: Filter by project ID
            operation: Filter by operation type
            limit: Maximum number of entries to return

        Returns:
            Filtered audit log entries
        """
        filtered_log = self._audit_log

        if user_id:
            filtered_log = [
                entry for entry in filtered_log if entry.get("user_id") == user_id
            ]

        if project_id:
            filtered_log = [
                entry for entry in filtered_log if entry.get("project_id") == project_id
            ]

        if operation:
            filtered_log = [
                entry for entry in filtered_log if entry.get("operation") == operation
            ]

        # Return most recent entries first
        return list(reversed(filtered_log))[:limit]

    def _get_client_ip(self) -> Optional[str]:
        """Get client IP address from current context."""
        # This would typically come from request context
        # For now, return None as it's context-dependent
        return None


class AccessController:
    """Project-based access control for dashboard and sensitive operations."""

    def __init__(self, config: SecurityConfig):
        self.config = config
        self.audit_logger = AuditLogger(config)

    def check_dashboard_access(
        self, user_id: str, project_id: str, operation: str = "dashboard_access"
    ) -> bool:
        """
        Check if user has access to project dashboard.

        Args:
            user_id: User identifier
            project_id: Project identifier
            operation: Operation being performed

        Returns:
            True if access granted, False otherwise
        """
        if not self.config.dashboard_access_control_enabled:
            return True

        # Check project membership (this would integrate with user management)
        has_access = self._check_project_membership(user_id, project_id)

        if has_access:
            self.audit_logger.log_access_attempt(
                operation=operation,
                user_id=user_id,
                project_id=project_id,
                success=True,
                metadata={"access_level": "project_member"},
            )
        else:
            self.audit_logger.log_access_attempt(
                operation=operation,
                user_id=user_id,
                project_id=project_id,
                success=False,
                reason="Not a project member",
                metadata={"access_level": "denied"},
            )

        return has_access

    def check_data_access(
        self,
        user_id: str,
        project_id: str,
        data_type: str,
        operation: str = "data_access",
    ) -> bool:
        """
        Check if user has access to specific project data.

        Args:
            user_id: User identifier
            project_id: Project identifier
            data_type: Type of data being accessed
            operation: Operation being performed

        Returns:
            True if access granted, False otherwise
        """
        if not self.config.project_isolation_enforced:
            return True

        # First check project membership
        if not self._check_project_membership(user_id, project_id):
            self.audit_logger.log_access_attempt(
                operation=operation,
                user_id=user_id,
                project_id=project_id,
                resource=data_type,
                success=False,
                reason="Not a project member",
            )
            return False

        # Check data type permissions
        has_data_access = self._check_data_type_permissions(
            user_id, project_id, data_type
        )

        if has_data_access:
            self.audit_logger.log_access_attempt(
                operation=operation,
                user_id=user_id,
                project_id=project_id,
                resource=data_type,
                success=True,
                metadata={"data_type": data_type},
            )
        else:
            self.audit_logger.log_access_attempt(
                operation=operation,
                user_id=user_id,
                project_id=project_id,
                resource=data_type,
                success=False,
                reason="Insufficient permissions for data type",
            )

        return has_data_access

    def _check_project_membership(self, user_id: str, project_id: str) -> bool:
        """
        Check if user is a member of the project.

        This is a placeholder implementation. In a real system, this would
        query the user management system or database to verify membership.

        Args:
            user_id: User identifier
            project_id: Project identifier

        Returns:
            True if user is a project member, False otherwise
        """
        # TODO: Implement actual project membership checking
        # For now, return True to allow development
        logger.debug(
            "Project membership check (placeholder)",
            user_id=user_id,
            project_id=project_id,
            placeholder_implementation=True,
        )
        return True

    def _check_data_type_permissions(
        self, user_id: str, project_id: str, data_type: str
    ) -> bool:
        """
        Check if user has permissions for specific data type.

        This is a placeholder implementation. In a real system, this would
        check role-based permissions for different data types.

        Args:
            user_id: User identifier
            project_id: Project identifier
            data_type: Type of data being accessed

        Returns:
            True if user has permissions, False otherwise
        """
        # TODO: Implement actual data type permission checking
        # For now, return True to allow development
        logger.debug(
            "Data type permission check (placeholder)",
            user_id=user_id,
            project_id=project_id,
            data_type=data_type,
            placeholder_implementation=True,
        )
        return True


class SecuritySpanProcessor(SpanProcessor):
    """OpenTelemetry span processor that applies security controls."""

    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or SecurityConfig()
        self.pii_processor = PIIProcessor(self.config)
        self.sql_sanitizer = SQLSanitizer(self.config)
        self.header_filter = HeaderFilter(self.config)

        logger.info(
            "Security span processor initialized",
            pii_redaction=True,
            sql_sanitization=self.config.sql_sanitization_enabled,
            header_filtering=True,
            access_control=self.config.dashboard_access_control_enabled,
        )

    def on_start(self, span, parent_context):
        """Called when a span is started."""
        pass

    def on_end(self, span):
        """Called when a span is ended. Apply security controls."""
        if not span.is_recording():
            return

        try:
            # Process different span types
            span_kind = span.kind if hasattr(span, "kind") else None

            if span_kind == SpanKind.SERVER or span_kind == SpanKind.CLIENT:
                self._process_http_span(span)
            elif span.name and (
                "sql" in span.name.lower() or "db" in span.name.lower()
            ):
                self._process_database_span(span)

            # Apply PII redaction to all span attributes
            self._redact_pii_in_attributes(span)

        except Exception as e:
            logger.error(
                "Error in security span processor",
                error=str(e),
                span_name=span.name,
                exc_info=True,
            )

    def _process_http_span(self, span):
        """Apply security controls to HTTP spans."""
        attributes = span.attributes or {}

        # Filter HTTP headers
        http_headers = {}
        for key, value in attributes.items():
            if key.startswith("http.request.header.") or key.startswith(
                "http.response.header."
            ):
                header_name = key.split(".")[-1]
                http_headers[header_name] = value

        if http_headers:
            filtered_headers = self.header_filter.filter_headers(http_headers)

            # Update span attributes with filtered headers
            for key, value in http_headers.items():
                header_key = f"http.request.header.{key}"
                if header_key in attributes:
                    span.set_attribute(header_key, filtered_headers.get(key, "***"))

    def _process_database_span(self, span):
        """Apply security controls to database spans."""
        attributes = span.attributes or {}

        # Sanitize SQL query
        db_statement = attributes.get("db.statement")
        if db_statement and self.config.sql_sanitization_enabled:
            sanitized = self.sql_sanitizer.sanitize_sql_query(db_statement)
            span.set_attribute("db.statement", sanitized["query"])

            if sanitized["parameters"]:
                span.set_attribute("db.parameters", str(sanitized["parameters"]))

            # Add sanitization metadata
            span.set_attribute("security.sql_sanitized", True)
            span.set_attribute("security.original_length", sanitized["original_length"])
            span.set_attribute(
                "security.sanitized_length", sanitized["sanitized_length"]
            )

    def _redact_pii_in_attributes(self, span):
        """Redact PII from all span attributes."""
        attributes = span.attributes or {}

        for key, value in attributes.items():
            if isinstance(value, str):
                # Check for PII and redact if found
                pii_instances = self.pii_processor.detect_pii(value)
                if pii_instances:
                    redacted_value = self.pii_processor.redact_pii(value)
                    span.set_attribute(key, redacted_value)
                    span.set_attribute(f"security.pii_redacted.{key}", True)

    def shutdown(self):
        """Called when the span processor is shutdown."""
        logger.info("Security span processor shutdown")


class SecurityManager:
    """Main security manager that coordinates all security components."""

    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or SecurityConfig()
        self.pii_processor = PIIProcessor(self.config)
        self.sql_sanitizer = SQLSanitizer(self.config)
        self.header_filter = HeaderFilter(self.config)
        self.access_controller = AccessController(self.config)
        self.audit_logger = AuditLogger(self.config)
        self.span_processor = SecuritySpanProcessor(self.config)

        logger.info(
            "Security manager initialized",
            features=[
                "PII redaction"
                if self.config.pii_patterns
                else "PII redaction: disabled",
                "SQL sanitization"
                if self.config.sql_sanitization_enabled
                else "SQL sanitization: disabled",
                "Header filtering"
                if self.config.sensitive_headers
                else "Header filtering: disabled",
                "Access control"
                if self.config.dashboard_access_control_enabled
                else "Access control: disabled",
                "Audit logging"
                if self.config.audit_logging_enabled
                else "Audit logging: disabled",
            ],
        )

    def process_text(self, text: str, text_type: str = "general") -> str:
        """
        Process text through all applicable security controls.

        Args:
            text: Text to process
            text_type: Type of text (general, sql, headers, etc.)

        Returns:
            Processed text with sensitive data redacted
        """
        if not text:
            return text

        processed_text = text

        # Apply PII redaction
        processed_text = self.pii_processor.redact_pii(processed_text)

        # Apply text-type specific processing
        if text_type == "sql":
            sanitized = self.sql_sanitizer.sanitize_sql_query(processed_text)
            processed_text = sanitized["query"]
        elif text_type == "headers":
            # This would need header dict, not just text
            pass

        return processed_text

    def get_security_status(self) -> Dict[str, Any]:
        """Get current security system status."""
        return {
            "config": {
                "pii_redaction_enabled": bool(self.config.pii_patterns),
                "sql_sanitization_enabled": self.config.sql_sanitization_enabled,
                "header_filtering_enabled": bool(self.config.sensitive_headers),
                "access_control_enabled": self.config.dashboard_access_control_enabled,
                "audit_logging_enabled": self.config.audit_logging_enabled,
            },
            "processors": {
                "pii_processor": "active",
                "sql_sanitizer": "active"
                if self.config.sql_sanitization_enabled
                else "disabled",
                "header_filter": "active",
                "access_controller": "active"
                if self.config.dashboard_access_control_enabled
                else "disabled",
                "audit_logger": "active"
                if self.config.audit_logging_enabled
                else "disabled",
                "span_processor": "active",
            },
            "statistics": {
                "audit_log_entries": len(self.audit_logger._audit_log),
                "pii_cache_size": len(self.pii_processor._redaction_cache),
            },
        }


# Global security manager instance
security_manager = SecurityManager()


# Convenience functions for easy access
def process_sensitive_text(text: str, text_type: str = "general") -> str:
    """Process text through security controls."""
    return security_manager.process_text(text, text_type)


def check_access(
    user_id: str, project_id: str, resource: str, operation: str = "access"
) -> bool:
    """Check user access to resource."""
    return security_manager.access_controller.check_data_access(
        user_id=user_id, project_id=project_id, data_type=resource, operation=operation
    )


def log_security_event(
    operation: str,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    success: bool = True,
    reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Log a security event."""
    security_manager.audit_logger.log_access_attempt(
        operation=operation,
        user_id=user_id,
        project_id=project_id,
        success=success,
        reason=reason,
        metadata=metadata,
    )


def get_security_span_processor() -> SecuritySpanProcessor:
    """Get the security span processor for OpenTelemetry."""
    return security_manager.span_processor


def get_security_status() -> Dict[str, Any]:
    """Get security system status."""
    return security_manager.get_security_status()


# Export key components
__all__ = [
    "SecurityConfig",
    "SecurityManager",
    "SecuritySpanProcessor",
    "PIIProcessor",
    "SQLSanitizer",
    "HeaderFilter",
    "AuditLogger",
    "AccessController",
    "SensitivityLevel",
    "security_manager",
    "process_sensitive_text",
    "check_access",
    "log_security_event",
    "get_security_span_processor",
    "get_security_status",
]
