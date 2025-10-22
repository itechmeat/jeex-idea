"""
Security Controls Tests for Task 2.5

Test suite for validating data sanitization and security controls in OpenTelemetry.
Comprehensive tests for PII redaction, SQL sanitization, header filtering, and access control.

Test Coverage:
- PII detection and redaction
- SQL query parameter sanitization
- HTTP header filtering
- Project-based access control
- Audit logging functionality
- Security span processor integration
"""

import pytest
import uuid
import json
import re
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any

from app.core.security import (
    SecurityConfig,
    SecurityManager,
    PIIProcessor,
    SQLSanitizer,
    HeaderFilter,
    AuditLogger,
    AccessController,
    SecuritySpanProcessor,
    SensitivityLevel,
    security_manager,
    process_sensitive_text,
    check_access,
    log_security_event,
    get_security_status,
)
from app.core.telemetry import get_tracer


class TestSecurityConfig:
    """Test security configuration."""

    def test_default_config(self):
        """Test default security configuration."""
        config = SecurityConfig()

        assert len(config.sensitive_headers) > 0
        assert "authorization" in config.sensitive_headers
        assert "cookie" in config.sensitive_headers
        assert "x-api-key" in config.sensitive_headers

        assert len(config.pii_patterns) > 0
        assert config.sql_sanitization_enabled is True
        assert config.sql_parameter_redaction is True
        assert config.dashboard_access_control_enabled is True
        assert config.project_isolation_enforced is True
        assert config.audit_logging_enabled is True

    def test_custom_config(self):
        """Test custom security configuration."""
        custom_headers = {"custom-header", "another-header"}
        config = SecurityConfig(
            sensitive_headers=custom_headers,
            sql_sanitization_enabled=False,
            audit_logging_enabled=False,
        )

        assert config.sensitive_headers == custom_headers
        assert config.sql_sanitization_enabled is False
        assert config.audit_logging_enabled is False


class TestPIIProcessor:
    """Test PII detection and redaction."""

    def test_email_detection(self):
        """Test email address detection and redaction."""
        config = SecurityConfig()
        processor = PIIProcessor(config)

        text = "Contact john.doe@example.com for details"
        pii_instances = processor.detect_pii(text)

        assert len(pii_instances) == 1
        assert pii_instances[0]["type"] == "email"
        assert pii_instances[0]["value"] == "john.doe@example.com"
        assert pii_instances[0]["redacted_value"] == "j***@example.com"

    def test_phone_detection(self):
        """Test phone number detection and redaction."""
        config = SecurityConfig()
        processor = PIIProcessor(config)

        text = "Call me at (555) 123-4567 or 555-123-4567"
        pii_instances = processor.detect_pii(text)

        assert len(pii_instances) >= 1
        phone_instances = [pii for pii in pii_instances if pii["type"] == "phone"]
        assert len(phone_instances) >= 1

    def test_ssn_detection(self):
        """Test Social Security Number detection and redaction."""
        config = SecurityConfig()
        processor = PIIProcessor(config)

        text = "My SSN is 123-45-6789"
        pii_instances = processor.detect_pii(text)

        assert len(pii_instances) == 1
        assert pii_instances[0]["type"] == "ssn"
        assert pii_instances[0]["value"] == "123-45-6789"
        assert pii_instances[0]["redacted_value"] == "***-**-6789"

    def test_credit_card_detection(self):
        """Test credit card number detection and redaction."""
        config = SecurityConfig()
        processor = PIIProcessor(config)

        text = "Card number: 4111-1111-1111-1111"
        pii_instances = processor.detect_pii(text)

        assert len(pii_instances) == 1
        assert pii_instances[0]["type"] == "credit_card"
        assert "4111" in pii_instances[0]["value"]

    def test_multiple_pii_redaction(self):
        """Test redaction of multiple PII types in one text."""
        config = SecurityConfig()
        processor = PIIProcessor(config)

        text = "John Doe (john.doe@example.com) can be reached at (555) 123-4567. SSN: 123-45-6789"
        redacted_text = processor.redact_pii(text)

        # Should redact all PII instances
        assert "john.doe@example.com" not in redacted_text
        assert "(555) 123-4567" not in redacted_text
        assert "123-45-6789" not in redacted_text
        assert "***" in redacted_text

    def test_no_pii_text(self):
        """Test handling of text without PII."""
        config = SecurityConfig()
        processor = PIIProcessor(config)

        text = "This is a regular text without personal information"
        pii_instances = processor.detect_pii(text)
        redacted_text = processor.redact_pii(text)

        assert len(pii_instances) == 0
        assert redacted_text == text

    def test_empty_text(self):
        """Test handling of empty text."""
        config = SecurityConfig()
        processor = PIIProcessor(config)

        assert processor.detect_pii("") == []
        assert processor.redact_pii("") == ""
        assert processor.redact_pii(None) is None


class TestSQLSanitizer:
    """Test SQL query and parameter sanitization."""

    def test_basic_sql_sanitization(self):
        """Test basic SQL query sanitization."""
        config = SecurityConfig()
        sanitizer = SQLSanitizer(config)

        query = "SELECT * FROM users WHERE email = 'test@example.com'"
        result = sanitizer.sanitize_sql_query(query)

        assert result["sanitized"] is True
        assert result["original_length"] > 0
        assert result["query"] != query  # Should be modified

    def test_sensitive_parameter_sanitization(self):
        """Test sanitization of sensitive SQL parameters."""
        config = SecurityConfig()
        sanitizer = SQLSanitizer(config)

        parameters = {
            "email": "user@example.com",
            "password": "secret123",
            "token": "abc123xyz",
        }

        result = sanitizer.sanitize_sql_query("SELECT 1", parameters)
        sanitized_params = result["parameters"]

        assert sanitized_params["email"] == "user@example.com"  # Not sensitive
        assert sanitized_params["password"] == "***"  # Should be redacted
        assert sanitized_params["token"] == "***"  # Should be redacted

    def test_comment_removal(self):
        """Test removal of SQL comments."""
        config = SecurityConfig()
        sanitizer = SQLSanitizer(config)

        query = """
        SELECT * FROM users -- This is a comment
        WHERE active = 1 /* Another comment */
        """
        result = sanitizer.sanitize_sql_query(query)

        sanitized_query = result["query"]
        assert "-- This is a comment" not in sanitized_query
        assert "/* Another comment */" not in sanitized_query

    def test_disabled_sanitization(self):
        """Test behavior when sanitization is disabled."""
        config = SecurityConfig(sql_sanitization_enabled=False)
        sanitizer = SQLSanitizer(config)

        query = "SELECT * FROM users WHERE password = 'secret'"
        result = sanitizer.sanitize_sql_query(query)

        assert result["sanitized"] is False
        assert result["query"] == query

    def test_long_string_truncation(self):
        """Test truncation of long string parameters."""
        config = SecurityConfig()
        sanitizer = SQLSanitizer(config)

        long_value = "x" * 150
        parameters = {"long_field": long_value}

        result = sanitizer.sanitize_sql_query("SELECT 1", parameters)
        sanitized_params = result["parameters"]

        assert len(sanitized_params["long_field"]) <= 103  # 100 + "..."
        assert sanitized_params["long_field"].endswith("...")


class TestHeaderFilter:
    """Test HTTP header filtering."""

    def test_sensitive_header_filtering(self):
        """Test filtering of sensitive headers."""
        config = SecurityConfig()
        header_filter = HeaderFilter(config)

        headers = {
            "authorization": "Bearer abc123xyz",
            "cookie": "session=abc123; theme=dark",
            "x-api-key": "secret-api-key",
            "content-type": "application/json",
            "accept": "application/json",
        }

        filtered = header_filter.filter_headers(headers)

        # Sensitive headers should be redacted
        assert filtered["authorization"] == "Bearer ***"
        assert (
            "[1 cookie(s)]" in filtered["cookie"] or "cookie(s)]" in filtered["cookie"]
        )
        assert filtered["x-api-key"].endswith("***")

        # Non-sensitive headers should be preserved
        assert filtered["content-type"] == "application/json"
        assert filtered["accept"] == "application/json"

    def test_case_insensitive_matching(self):
        """Test case-insensitive header matching."""
        config = SecurityConfig()
        header_filter = HeaderFilter(config)

        headers = {
            "Authorization": "Bearer token123",
            "AUTHORIZATION": "Bearer token456",
            "Cookie": "session=abc",
            "X-API-KEY": "secret123",
        }

        filtered = header_filter.filter_headers(headers)

        assert filtered["Authorization"].startswith("Bearer")
        assert filtered["Authorization"].endswith("***")
        assert filtered["AUTHORIZATION"].endswith("***")
        assert "cookie(s)" in filtered["Cookie"].lower()
        assert filtered["X-API-KEY"].endswith("***")

    def test_pattern_matching(self):
        """Test pattern-based header detection."""
        config = SecurityConfig()
        header_filter = HeaderFilter(config)

        headers = {
            "x-auth-token": "secret123",
            "user-secret": "value",
            "my-token-header": "abc123",
        }

        filtered = header_filter.filter_headers(headers)

        # Headers matching sensitive patterns should be redacted
        assert filtered["x-auth-token"].endswith("***")
        assert filtered["user-secret"] == "***"
        assert filtered["my-token-header"].endswith("***")


class TestAuditLogger:
    """Test audit logging functionality."""

    def test_successful_access_log(self):
        """Test logging of successful access attempts."""
        config = SecurityConfig(audit_logging_enabled=True)
        audit_logger = AuditLogger(config)

        audit_logger.log_access_attempt(
            operation="test_operation",
            user_id="user123",
            project_id="proj456",
            resource="test_resource",
            success=True,
        )

        audit_log = audit_logger.get_audit_log()
        assert len(audit_log) > 0

        latest_entry = audit_log[0]
        assert latest_entry["operation"] == "test_operation"
        assert latest_entry["user_id"] == "user123"
        assert latest_entry["project_id"] == "proj456"
        assert latest_entry["success"] is True

    def test_failed_access_log(self):
        """Test logging of failed access attempts."""
        config = SecurityConfig(audit_logging_enabled=True)
        audit_logger = AuditLogger(config)

        audit_logger.log_access_attempt(
            operation="test_operation",
            user_id="user123",
            project_id="proj456",
            resource="test_resource",
            success=False,
            reason="Access denied",
        )

        audit_log = audit_logger.get_audit_log()
        latest_entry = audit_log[0]

        assert latest_entry["success"] is False
        assert latest_entry["reason"] == "Access denied"

    def test_audit_log_filtering(self):
        """Test filtering of audit log entries."""
        config = SecurityConfig(audit_logging_enabled=True)
        audit_logger = AuditLogger(config)

        # Add multiple log entries
        audit_logger.log_access_attempt("op1", "user1", "proj1", success=True)
        audit_logger.log_access_attempt("op2", "user2", "proj2", success=True)
        audit_logger.log_access_attempt("op1", "user1", "proj3", success=False)

        # Test filtering by user
        user1_logs = audit_logger.get_audit_log(user_id="user1")
        assert len(user1_logs) == 2
        assert all(entry["user_id"] == "user1" for entry in user1_logs)

        # Test filtering by operation
        op1_logs = audit_logger.get_audit_log(operation="op1")
        assert len(op1_logs) == 2
        assert all(entry["operation"] == "op1" for entry in op1_logs)

    def test_disabled_audit_logging(self):
        """Test behavior when audit logging is disabled."""
        config = SecurityConfig(audit_logging_enabled=False)
        audit_logger = AuditLogger(config)

        audit_logger.log_access_attempt(
            operation="test_operation", user_id="user123", success=True
        )

        # Should not create any log entries
        audit_log = audit_logger.get_audit_log()
        assert len(audit_log) == 0

    def test_log_trimming(self):
        """Test automatic log trimming when exceeding max entries."""
        config = SecurityConfig(audit_logging_enabled=True)
        audit_logger = AuditLogger(config)

        # Set a small max for testing
        audit_logger._max_entries = 5

        # Add more entries than the max
        for i in range(10):
            audit_logger.log_access_attempt(f"operation_{i}", f"user_{i}", success=True)

        audit_log = audit_logger.get_audit_log()
        # Should be trimmed to max_entries
        assert len(audit_log) <= 5


class TestAccessController:
    """Test project-based access control."""

    def test_dashboard_access_granted(self):
        """Test successful dashboard access."""
        config = SecurityConfig(dashboard_access_control_enabled=True)
        access_controller = AccessController(config)

        # Mock the project membership check to return True
        with patch.object(
            access_controller, "_check_project_membership", return_value=True
        ):
            has_access = access_controller.check_dashboard_access(
                user_id="user123", project_id="proj456"
            )

        assert has_access is True

        # Check that audit log was created
        audit_log = access_controller.audit_logger.get_audit_log(limit=1)
        assert len(audit_log) > 0
        assert audit_log[0]["operation"] == "dashboard_access"
        assert audit_log[0]["success"] is True

    def test_dashboard_access_denied(self):
        """Test denied dashboard access."""
        config = SecurityConfig(dashboard_access_control_enabled=True)
        access_controller = AccessController(config)

        # Mock the project membership check to return False
        with patch.object(
            access_controller, "_check_project_membership", return_value=False
        ):
            has_access = access_controller.check_dashboard_access(
                user_id="user123", project_id="proj456"
            )

        assert has_access is False

        # Check that audit log was created with failure
        audit_log = access_controller.audit_logger.get_audit_log(limit=1)
        assert len(audit_log) > 0
        assert audit_log[0]["success"] is False
        assert audit_log[0]["reason"] == "Not a project member"

    def test_data_access_control(self):
        """Test data-specific access control."""
        config = SecurityConfig(project_isolation_enforced=True)
        access_controller = AccessController(config)

        # Mock both checks to return True
        with (
            patch.object(
                access_controller, "_check_project_membership", return_value=True
            ),
            patch.object(
                access_controller, "_check_data_type_permissions", return_value=True
            ),
        ):
            has_access = access_controller.check_data_access(
                user_id="user123", project_id="proj456", data_type="sensitive_data"
            )

        assert has_access is True

    def test_disabled_access_control(self):
        """Test behavior when access control is disabled."""
        config = SecurityConfig(dashboard_access_control_enabled=False)
        access_controller = AccessController(config)

        # Should grant access without checks
        has_access = access_controller.check_dashboard_access(
            user_id="user123", project_id="proj456"
        )

        assert has_access is True

    def test_project_isolation_disabled(self):
        """Test behavior when project isolation is disabled."""
        config = SecurityConfig(project_isolation_enforced=False)
        access_controller = AccessController(config)

        # Should grant data access without isolation checks
        has_access = access_controller.check_data_access(
            user_id="user123", project_id="proj456", data_type="any_data"
        )

        assert has_access is True


class TestSecuritySpanProcessor:
    """Test OpenTelemetry security span processor."""

    def test_span_processor_initialization(self):
        """Test security span processor initialization."""
        config = SecurityConfig()
        processor = SecuritySpanProcessor(config)

        assert processor.config is config
        assert processor.pii_processor is not None
        assert processor.sql_sanitizer is not None
        assert processor.header_filter is not None

    def test_http_span_processing(self):
        """Test processing of HTTP spans."""
        config = SecurityConfig()
        processor = SecuritySpanProcessor(config)

        # Create a mock HTTP span
        mock_span = Mock()
        mock_span.is_recording.return_value = True
        mock_span.kind = "SERVER"
        mock_span.attributes = {
            "http.request.header.authorization": "Bearer secret-token",
            "http.request.header.cookie": "session=abc123",
            "http.request.header.content-type": "application/json",
        }

        # Process the span
        processor.on_end(mock_span)

        # Check that set_attribute was called for sensitive headers
        assert mock_span.set_attribute.called

    def test_database_span_processing(self):
        """Test processing of database spans."""
        config = SecurityConfig()
        processor = SecuritySpanProcessor(config)

        # Create a mock database span
        mock_span = Mock()
        mock_span.is_recording.return_value = True
        mock_span.name = "sql.query"
        mock_span.attributes = {
            "db.statement": "SELECT * FROM users WHERE password = 'secret'"
        }

        # Process the span
        processor.on_end(mock_span)

        # Check that the SQL statement was sanitized
        mock_span.set_attribute.assert_any_call("db.statement", Mock())
        mock_span.set_attribute.assert_any_call("security.sql_sanitized", True)

    def test_pii_redaction_in_attributes(self):
        """Test PII redaction in span attributes."""
        config = SecurityConfig()
        processor = SecuritySpanProcessor(config)

        # Create a mock span with PII in attributes
        mock_span = Mock()
        mock_span.is_recording.return_value = True
        mock_span.attributes = {
            "user.email": "john.doe@example.com",
            "user.phone": "(555) 123-4567",
            "regular.field": "normal_value",
        }

        # Process the span
        processor.on_end(mock_span)

        # Check that PII attributes were redacted
        calls = mock_span.set_attribute.call_args_list
        pii_calls = [call for call in calls if "security.pii_redacted." in call[0][0]]
        assert len(pii_calls) >= 1  # At least one PII field should be marked

    def test_non_recording_span_handling(self):
        """Test handling of non-recording spans."""
        config = SecurityConfig()
        processor = SecuritySpanProcessor(config)

        # Create a non-recording mock span
        mock_span = Mock()
        mock_span.is_recording.return_value = False

        # Should not process non-recording spans
        processor.on_end(mock_span)
        assert not mock_span.set_attribute.called


class TestSecurityManager:
    """Test the main security manager."""

    def test_security_manager_initialization(self):
        """Test security manager initialization."""
        manager = SecurityManager()

        assert manager.config is not None
        assert manager.pii_processor is not None
        assert manager.sql_sanitizer is not None
        assert manager.header_filter is not None
        assert manager.access_controller is not None
        assert manager.audit_logger is not None
        assert manager.span_processor is not None

    def test_process_text_general(self):
        """Test general text processing."""
        text = "Contact john.doe@example.com for details"
        processed = security_manager.process_text(text, "general")

        assert text != processed  # Should be modified
        assert "john.doe@example.com" not in processed  # PII should be redacted

    def test_process_text_sql(self):
        """Test SQL text processing."""
        sql = "SELECT * FROM users WHERE password = 'secret123'"
        processed = security_manager.process_text(sql, "sql")

        assert sql != processed  # Should be modified
        assert "secret123" not in processed  # Should be redacted/sanitized

    def test_get_security_status(self):
        """Test security status retrieval."""
        status = security_manager.get_security_status()

        assert "config" in status
        assert "processors" in status
        assert "statistics" in status

        # Check configuration
        config = status["config"]
        assert "pii_redaction_enabled" in config
        assert "sql_sanitization_enabled" in config
        assert "header_filtering_enabled" in config

        # Check processors
        processors = status["processors"]
        assert "pii_processor" in processors
        assert "sql_sanitizer" in processors
        assert "header_filter" in processors

    def test_custom_security_manager_config(self):
        """Test security manager with custom configuration."""
        custom_config = SecurityConfig(
            sql_sanitization_enabled=False, audit_logging_enabled=False
        )
        manager = SecurityManager(custom_config)

        assert manager.config.sql_sanitization_enabled is False
        assert manager.config.audit_logging_enabled is False


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_process_sensitive_text_function(self):
        """Test the process_sensitive_text convenience function."""
        text = "Email: john.doe@example.com"
        processed = process_sensitive_text(text)

        assert text != processed
        assert "john.doe@example.com" not in processed

    def test_check_access_function(self):
        """Test the check_access convenience function."""
        # Mock the access controller to return True
        with patch.object(
            security_manager.access_controller, "check_data_access", return_value=True
        ):
            result = check_access("user123", "proj456", "resource", "read")

        assert result is True

    def test_log_security_event_function(self):
        """Test the log_security_event convenience function."""
        log_security_event(
            operation="test_operation",
            user_id="user123",
            project_id="proj456",
            success=True,
        )

        # Check that the event was logged
        audit_log = security_manager.audit_logger.get_audit_log(limit=1)
        assert len(audit_log) > 0
        assert audit_log[0]["operation"] == "test_operation"

    def test_get_security_status_function(self):
        """Test the get_security_status convenience function."""
        status = get_security_status()

        assert isinstance(status, dict)
        assert "config" in status
        assert "processors" in status

    def test_get_security_span_processor_function(self):
        """Test the get_security_span_processor convenience function."""
        processor = get_security_span_processor()

        assert isinstance(processor, SecuritySpanProcessor)
        assert processor.config is not None


class TestIntegration:
    """Integration tests for the complete security system."""

    def test_end_to_end_pii_processing(self):
        """Test end-to-end PII processing."""
        # Test text with multiple PII types
        text = """
        User: John Doe
        Email: john.doe@example.com
        Phone: (555) 123-4567
        SSN: 123-45-6789
        Credit Card: 4111-1111-1111-1111
        """

        # Process through the security system
        processed = process_sensitive_text(text, "general")

        # Verify all PII is redacted
        assert "john.doe@example.com" not in processed
        assert "(555) 123-4567" not in processed
        assert "123-45-6789" not in processed
        assert "4111-1111-1111-1111" not in processed
        assert "***" in processed

    def test_security_span_processor_integration(self):
        """Test integration with OpenTelemetry span processor."""
        processor = get_security_span_processor()

        # Create a realistic mock span
        mock_span = Mock()
        mock_span.is_recording.return_value = True
        mock_span.kind = "SERVER"
        mock_span.attributes = {
            "http.request.header.authorization": "Bearer secret123",
            "user.email": "test@example.com",
            "db.statement": "SELECT * FROM users WHERE password = 'secret456'",
            "project_id": "test-project-123",
        }

        # Process the span
        processor.on_end(mock_span)

        # Verify that security processing was applied
        assert mock_span.set_attribute.called

        # Check for security-related attribute updates
        calls = mock_span.set_attribute.call_args_list
        call_keys = [call[0][0] for call in calls]

        # Should have processed headers
        header_calls = [
            key for key in call_keys if "http.request.header.authorization" in key
        ]
        assert len(header_calls) > 0

        # Should have processed PII
        pii_calls = [key for key in call_keys if "security.pii_redacted." in key]
        assert len(pii_calls) > 0

        # Should have processed SQL
        sql_calls = [key for key in call_keys if "security.sql_sanitized" in key]
        assert len(sql_calls) > 0

    def test_audit_trail_completeness(self):
        """Test that all security operations create audit trails."""
        # Perform various security operations
        process_sensitive_text("test@example.com", "general")
        check_access("user123", "proj456", "resource", "read")
        log_security_event("manual_test", user_id="user123", success=True)

        # Get audit log
        audit_log = security_manager.audit_logger.get_audit_log(limit=10)

        # Should have entries for all operations
        operations = [entry["operation"] for entry in audit_log]
        assert "manual_test" in operations

        # All entries should have required fields
        for entry in audit_log:
            assert "timestamp" in entry
            assert "operation" in entry
            assert "success" in entry
            assert "correlation_id" in entry

    @pytest.mark.asyncio
    async def test_concurrent_security_processing(self):
        """Test security processing under concurrent load."""
        import asyncio

        async def process_text_batch():
            texts = ["Email: user{}@example.com".format(i) for i in range(10)]

            results = []
            for text in texts:
                processed = process_sensitive_text(text, "general")
                results.append(processed)

            return results

        # Run multiple concurrent batches
        tasks = [process_text_batch() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All batches should complete successfully
        assert len(results) == 5

        for batch_results in results:
            assert len(batch_results) == 10
            # All results should be processed (redacted)
            for result in batch_results:
                assert "@example.com" not in result or "***" in result

    def test_security_feature_flags(self):
        """Test that security feature flags work correctly."""
        # Test with all features disabled
        disabled_config = SecurityConfig(
            sql_sanitization_enabled=False,
            audit_logging_enabled=False,
            dashboard_access_control_enabled=False,
        )
        disabled_manager = SecurityManager(disabled_config)

        # SQL should not be sanitized
        sql = "SELECT password FROM users"
        processed = disabled_manager.process_text(sql, "sql")
        assert processed == sql  # Should be unchanged

        # Audit logging should not create entries
        disabled_manager.audit_logger.log_access_attempt(
            operation="test", user_id="user", success=True
        )
        audit_log = disabled_manager.audit_logger.get_audit_log()
        assert len(audit_log) == 0

        # Access control should always grant
        has_access = disabled_manager.access_controller.check_dashboard_access(
            user_id="user", project_id="proj"
        )
        assert has_access is True


if __name__ == "__main__":
    pytest.main([__file__])
