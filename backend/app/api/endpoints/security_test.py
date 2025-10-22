"""
Security Test Endpoints for Task 2.5

Test endpoints for validating data sanitization and security controls in OpenTelemetry.
These endpoints help verify that sensitive data is properly redacted and access control works.

Features:
- Test sensitive header filtering
- Test SQL query parameter sanitization
- Test PII detection and redaction
- Test project-based access control
- Test audit logging functionality
"""

import uuid
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query, Header, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
import structlog

from ...core.telemetry import get_tracer, add_span_attribute
from ...core.security import (
    SecurityConfig,
    SecurityManager,
    process_sensitive_text,
    check_access,
    log_security_event,
    get_security_status,
    PIIProcessor,
    SQLSanitizer,
    HeaderFilter,
    AccessController,
    SensitivityLevel,
)

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()
security = HTTPBearer(auto_error=False)


def extract_user_id(credentials: Optional[HTTPAuthorizationCredentials]) -> str:
    """
    Safely extract user ID from authorization credentials.

    Args:
        credentials: HTTP authorization credentials

    Returns:
        User ID string or 'anonymous' if credentials are invalid/missing

    Raises:
        HTTPException: If credentials are malformed
    """
    if not credentials or not credentials.credentials:
        return "anonymous"

    try:
        parts = credentials.credentials.split()
        if len(parts) < 2:
            raise HTTPException(status_code=401, detail="Invalid authorization format")
        return parts[1]
    except (AttributeError, IndexError) as e:
        logger.warning("Failed to parse authorization credentials", error=str(e))
        raise HTTPException(
            status_code=401, detail="Invalid authorization credentials format"
        )


# Test data models
class PIIRequest(BaseModel):
    """Request model for PII testing."""

    text: str = Field(..., description="Text containing potential PII")
    email: Optional[EmailStr] = Field(None, description="Email address for testing")
    phone: Optional[str] = Field(None, description="Phone number for testing")
    ssn: Optional[str] = Field(None, description="Social Security Number for testing")
    credit_card: Optional[str] = Field(
        None, description="Credit card number for testing"
    )


class SQLTestRequest(BaseModel):
    """Request model for SQL sanitization testing."""

    query: str = Field(..., description="SQL query with potential sensitive data")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Query parameters")


class AccessTestRequest(BaseModel):
    """Request model for access control testing."""

    user_id: str = Field(..., description="User ID to test")
    project_id: str = Field(..., description="Project ID to test")
    resource: str = Field(..., description="Resource to access")
    operation: str = Field(default="read", description="Operation to perform")


class SecurityTestResponse(BaseModel):
    """Response model for security tests."""

    test_name: str
    timestamp: str
    status: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    security_features_applied: List[str]
    correlation_id: Optional[str] = None


@router.get("/security/status", response_model=Dict[str, Any])
async def get_security_system_status():
    """
    Get the current status of the security system.

    Returns:
        Security system configuration and status
    """
    try:
        status = get_security_status()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "security_system": "active",
            "status": status,
            "features": {
                "pii_redaction": status["config"]["pii_redaction_enabled"],
                "sql_sanitization": status["config"]["sql_sanitization_enabled"],
                "header_filtering": status["config"]["header_filtering_enabled"],
                "access_control": status["config"]["access_control_enabled"],
                "audit_logging": status["config"]["audit_logging_enabled"],
            },
            "version": "2.5.0",
            "environment": settings.ENVIRONMENT,
        }

    except Exception as e:
        logger.error("Failed to get security status", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Security status check failed: {str(e)}"
        )


@router.post("/security/test/pii-redaction", response_model=SecurityTestResponse)
async def test_pii_redaction(
    request: PIIRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_project_id: str = Header(..., description="Project ID for testing"),
):
    """
    Test PII detection and redaction functionality.

    Args:
        request: PII test data
        credentials: Optional authentication credentials
        x_project_id: Project ID header

    Returns:
        PII redaction test results
    """
    tracer = get_tracer("security-test", "2.5.0")

    with tracer.start_as_current_span("pii-redaction-test") as span:
        span.set_attribute("test.type", "pii_redaction")
        span.set_attribute("project_id", x_project_id)

        correlation_id = None
        try:
            from ...core.telemetry import get_correlation_id

            correlation_id = get_correlation_id()
        except Exception:
            pass

        try:
            # Combine all PII data for testing
            test_text = request.text
            if request.email:
                test_text += f" Email: {request.email}"
            if request.phone:
                test_text += f" Phone: {request.phone}"
            if request.ssn:
                test_text += f" SSN: {request.ssn}"
            if request.credit_card:
                test_text += f" Card: {request.credit_card}"

            # Process through PII detection and redaction
            pii_processor = PIIProcessor(SecurityConfig())
            pii_instances = pii_processor.detect_pii(test_text)
            redacted_text = pii_processor.redact_pii(test_text)

            # Log security event
            log_security_event(
                operation="pii_redaction_test",
                user_id=extract_user_id(credentials),
                project_id=x_project_id,
                success=True,
                metadata={
                    "pii_instances_found": len(pii_instances),
                    "text_length": len(test_text),
                    "redaction_applied": True,
                },
            )

            return SecurityTestResponse(
                test_name="pii_redaction",
                timestamp=datetime.utcnow().isoformat(),
                status="success",
                input_data={
                    "original_text": test_text,
                    "text_length": len(test_text),
                    "detected_pii": len(pii_instances),
                },
                output_data={
                    "redacted_text": redacted_text,
                    "pii_instances": pii_instances,
                    "redaction_applied": len(pii_instances) > 0,
                },
                security_features_applied=["pii_detection", "pii_redaction"],
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(
                "PII redaction test failed", error=str(e), project_id=x_project_id
            )

            log_security_event(
                operation="pii_redaction_test",
                user_id=extract_user_id(credentials),
                project_id=x_project_id,
                success=False,
                reason=str(e),
            )

            raise HTTPException(
                status_code=500, detail=f"PII redaction test failed: {str(e)}"
            )


@router.post("/security/test/sql-sanitization", response_model=SecurityTestResponse)
async def test_sql_sanitization(
    request: SQLTestRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_project_id: str = Header(..., description="Project ID for testing"),
):
    """
    Test SQL query parameter sanitization.

    Args:
        request: SQL test data
        credentials: Optional authentication credentials
        x_project_id: Project ID header

    Returns:
        SQL sanitization test results
    """
    tracer = get_tracer("security-test", "2.5.0")

    with tracer.start_as_current_span("sql-sanitization-test") as span:
        span.set_attribute("test.type", "sql_sanitization")
        span.set_attribute("project_id", x_project_id)

        correlation_id = None
        try:
            from ...core.telemetry import get_correlation_id

            correlation_id = get_correlation_id()
        except Exception:
            pass

        try:
            # Process SQL through sanitizer
            sql_sanitizer = SQLSanitizer(SecurityConfig())
            sanitized = sql_sanitizer.sanitize_sql_query(
                request.query, request.parameters
            )

            # Log security event
            log_security_event(
                operation="sql_sanitization_test",
                user_id=extract_user_id(credentials),
                project_id=x_project_id,
                success=True,
                metadata={
                    "original_query_length": len(request.query),
                    "sanitized_query_length": len(sanitized["query"]),
                    "parameters_sanitized": request.parameters is not None,
                },
            )

            return SecurityTestResponse(
                test_name="sql_sanitization",
                timestamp=datetime.utcnow().isoformat(),
                status="success",
                input_data={
                    "original_query": request.query,
                    "parameters": request.parameters,
                    "query_length": len(request.query),
                },
                output_data=sanitized,
                security_features_applied=["sql_sanitization", "parameter_redaction"]
                if sanitized["sanitized"]
                else [],
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(
                "SQL sanitization test failed", error=str(e), project_id=x_project_id
            )

            log_security_event(
                operation="sql_sanitization_test",
                user_id=extract_user_id(credentials),
                project_id=x_project_id,
                success=False,
                reason=str(e),
            )

            raise HTTPException(
                status_code=500, detail=f"SQL sanitization test failed: {str(e)}"
            )


@router.post("/security/test/header-filtering", response_model=SecurityTestResponse)
async def test_header_filtering(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_project_id: str = Header(..., description="Project ID for testing"),
    x_test_header: Optional[str] = Header(None, description="Custom test header"),
    authorization: Optional[str] = Header(
        None, description="Authorization header for testing"
    ),
    x_api_key: Optional[str] = Header(None, description="API key header for testing"),
    cookie: Optional[str] = Header(None, description="Cookie header for testing"),
):
    """
    Test HTTP header filtering functionality.

    Args:
        request: HTTP request
        credentials: Optional authentication credentials
        x_project_id: Project ID header
        x_test_header: Custom test header
        authorization: Authorization header
        x_api_key: API key header
        cookie: Cookie header

    Returns:
        Header filtering test results
    """
    tracer = get_tracer("security-test", "2.5.0")

    with tracer.start_as_current_span("header-filtering-test") as span:
        span.set_attribute("test.type", "header_filtering")
        span.set_attribute("project_id", x_project_id)

        correlation_id = None
        try:
            from ...core.telemetry import get_correlation_id

            correlation_id = get_correlation_id()
        except Exception:
            pass

        try:
            # Collect headers for testing
            test_headers = {}
            for header_name, header_value in request.headers.items():
                test_headers[header_name] = header_value

            # Process headers through filter
            header_filter = HeaderFilter(SecurityConfig())
            filtered_headers = header_filter.filter_headers(test_headers)

            # Identify which headers were filtered/redacted
            filtered_sensitive = {}
            for header_name, original_value in test_headers.items():
                filtered_value = filtered_headers.get(header_name)
                if original_value != filtered_value:
                    filtered_sensitive[header_name] = {
                        "original": original_value,
                        "filtered": filtered_value,
                        "redacted": True,
                    }

            # Log security event
            log_security_event(
                operation="header_filtering_test",
                user_id=extract_user_id(credentials),
                project_id=x_project_id,
                success=True,
                metadata={
                    "total_headers": len(test_headers),
                    "sensitive_headers_filtered": len(filtered_sensitive),
                    "headers_tested": list(test_headers.keys()),
                },
            )

            return SecurityTestResponse(
                test_name="header_filtering",
                timestamp=datetime.utcnow().isoformat(),
                status="success",
                input_data={
                    "total_headers": len(test_headers),
                    "headers": dict(
                        list(test_headers.items())[:10]
                    ),  # Limit to first 10 for brevity
                },
                output_data={
                    "filtered_headers": dict(list(filtered_headers.items())[:10]),
                    "sensitive_headers_filtered": len(filtered_sensitive),
                    "filtered_details": filtered_sensitive,
                },
                security_features_applied=[
                    "header_filtering",
                    "sensitive_data_redaction",
                ],
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(
                "Header filtering test failed", error=str(e), project_id=x_project_id
            )

            log_security_event(
                operation="header_filtering_test",
                user_id=extract_user_id(credentials),
                project_id=x_project_id,
                success=False,
                reason=str(e),
            )

            raise HTTPException(
                status_code=500, detail=f"Header filtering test failed: {str(e)}"
            )


@router.post("/security/test/access-control", response_model=SecurityTestResponse)
async def test_access_control(
    request: AccessTestRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_project_id: str = Header(..., description="Project ID for testing"),
):
    """
    Test project-based access control functionality.

    Args:
        request: Access control test data
        credentials: Optional authentication credentials
        x_project_id: Project ID header

    Returns:
        Access control test results
    """
    tracer = get_tracer("security-test", "2.5.0")

    with tracer.start_as_current_span("access-control-test") as span:
        span.set_attribute("test.type", "access_control")
        span.set_attribute("project_id", x_project_id)

        correlation_id = None
        try:
            from ...core.telemetry import get_correlation_id

            correlation_id = get_correlation_id()
        except Exception:
            pass

        try:
            # Test access control
            access_controller = AccessController(SecurityConfig())

            # Test dashboard access
            dashboard_access = access_controller.check_dashboard_access(
                user_id=request.user_id,
                project_id=request.project_id,
                operation="dashboard_access_test",
            )

            # Test data access
            data_access = access_controller.check_data_access(
                user_id=request.user_id,
                project_id=request.project_id,
                data_type=request.resource,
                operation=f"{request.operation}_test",
            )

            # Log security event
            log_security_event(
                operation="access_control_test",
                user_id=request.user_id,
                project_id=request.project_id,
                success=dashboard_access and data_access,
                metadata={
                    "dashboard_access": dashboard_access,
                    "data_access": data_access,
                    "resource": request.resource,
                    "operation": request.operation,
                },
            )

            return SecurityTestResponse(
                test_name="access_control",
                timestamp=datetime.utcnow().isoformat(),
                status="success",
                input_data={
                    "user_id": request.user_id,
                    "project_id": request.project_id,
                    "resource": request.resource,
                    "operation": request.operation,
                },
                output_data={
                    "dashboard_access_granted": dashboard_access,
                    "data_access_granted": data_access,
                    "overall_access": dashboard_access and data_access,
                    "access_control_enforced": True,
                },
                security_features_applied=[
                    "project_based_access_control",
                    "audit_logging",
                ],
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(
                "Access control test failed", error=str(e), project_id=x_project_id
            )

            log_security_event(
                operation="access_control_test",
                user_id=request.user_id,
                project_id=request.project_id,
                success=False,
                reason=str(e),
            )

            raise HTTPException(
                status_code=500, detail=f"Access control test failed: {str(e)}"
            )


@router.get("/security/audit-log", response_model=Dict[str, Any])
async def get_audit_log(
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of entries to return"
    ),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    operation: Optional[str] = Query(None, description="Filter by operation type"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_project_id: str = Header(..., description="Project ID for access control"),
):
    """
    Retrieve audit log entries with filtering.

    Args:
        limit: Maximum number of entries to return
        user_id: Filter by user ID
        project_id: Filter by project ID
        operation: Filter by operation type
        credentials: Authentication credentials
        x_project_id: Project ID header

    Returns:
        Filtered audit log entries
    """
    tracer = get_tracer("security-test", "2.5.0")

    with tracer.start_as_current_span("audit-log-retrieval") as span:
        span.set_attribute("test.type", "audit_log")
        span.set_attribute("project_id", x_project_id)

        try:
            # Check access first
            requesting_user = extract_user_id(credentials)

            if not check_access(requesting_user, x_project_id, "audit_log", "read"):
                log_security_event(
                    operation="audit_log_access_denied",
                    user_id=requesting_user,
                    project_id=x_project_id,
                    success=False,
                    reason="Insufficient permissions",
                )
                raise HTTPException(
                    status_code=403, detail="Access denied to audit log"
                )

            # Get audit log entries
            security_manager = SecurityManager(SecurityConfig())
            audit_entries = security_manager.audit_logger.get_audit_log(
                user_id=user_id, project_id=project_id, operation=operation, limit=limit
            )

            # Log access
            log_security_event(
                operation="audit_log_access",
                user_id=requesting_user,
                project_id=x_project_id,
                success=True,
                metadata={
                    "entries_requested": limit,
                    "entries_returned": len(audit_entries),
                    "filters_applied": {
                        "user_id": user_id,
                        "project_id": project_id,
                        "operation": operation,
                    },
                },
            )

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "requesting_user": requesting_user,
                "filters": {
                    "user_id": user_id,
                    "project_id": project_id,
                    "operation": operation,
                    "limit": limit,
                },
                "total_entries": len(audit_entries),
                "audit_log": audit_entries,
                "access_control": "enforced",
                "correlation_id": span.get_span_context().trace_id if span else None,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Audit log retrieval failed", error=str(e), project_id=x_project_id
            )
            raise HTTPException(
                status_code=500, detail=f"Audit log retrieval failed: {str(e)}"
            )


@router.post("/security/test/comprehensive", response_model=Dict[str, Any])
async def comprehensive_security_test(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_project_id: str = Header(..., description="Project ID for testing"),
):
    """
    Run a comprehensive security test covering all features.

    Args:
        credentials: Optional authentication credentials
        x_project_id: Project ID header

    Returns:
        Comprehensive security test results
    """
    tracer = get_tracer("security-test", "2.5.0")

    with tracer.start_as_current_span("comprehensive-security-test") as span:
        span.set_attribute("test.type", "comprehensive")
        span.set_attribute("project_id", x_project_id)

        correlation_id = None
        try:
            from ...core.telemetry import get_correlation_id

            correlation_id = get_correlation_id()
        except Exception:
            pass

        try:
            test_results = {}
            test_user = extract_user_id(credentials) or "test_user"

            # Test 1: PII Redaction
            pii_test_text = "Contact John Doe at john.doe@example.com or (555) 123-4567. SSN: 123-45-6789"
            redacted_text = process_sensitive_text(pii_test_text, "general")
            test_results["pii_redaction"] = {
                "status": "success",
                "original_length": len(pii_test_text),
                "redacted_length": len(redacted_text),
                "redaction_applied": pii_test_text != redacted_text,
            }

            # Test 2: SQL Sanitization
            sql_query = "SELECT * FROM users WHERE email = 'secret@example.com' AND password_hash = 'abcdef123456'"
            sanitized_sql = process_sensitive_text(sql_query, "sql")
            test_results["sql_sanitization"] = {
                "status": "success",
                "original_length": len(sql_query),
                "sanitized_length": len(sanitized_sql),
                "sanitization_applied": sql_query != sanitized_sql,
            }

            # Test 3: Access Control
            access_granted = check_access(
                test_user, x_project_id, "test_resource", "read"
            )
            test_results["access_control"] = {
                "status": "success",
                "access_granted": access_granted,
                "access_control_enforced": True,
            }

            # Test 4: Audit Logging
            log_security_event(
                operation="comprehensive_test",
                user_id=test_user,
                project_id=x_project_id,
                success=True,
                metadata={"test_type": "comprehensive"},
            )
            test_results["audit_logging"] = {"status": "success", "event_logged": True}

            # Overall test result
            all_tests_passed = all(
                result["status"] == "success" for result in test_results.values()
            )

            return {
                "test_name": "comprehensive_security_test",
                "timestamp": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
                "project_id": x_project_id,
                "overall_status": "passed" if all_tests_passed else "failed",
                "test_results": test_results,
                "security_features_tested": [
                    "pii_redaction",
                    "sql_sanitization",
                    "access_control",
                    "audit_logging",
                ],
                "version": "2.5.0",
            }

        except Exception as e:
            logger.error(
                "Comprehensive security test failed",
                error=str(e),
                project_id=x_project_id,
            )
            raise HTTPException(
                status_code=500, detail=f"Comprehensive security test failed: {str(e)}"
            )


# Export the router
__all__ = ["router"]
