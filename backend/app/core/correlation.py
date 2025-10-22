"""
JEEX Idea Correlation ID Middleware

Implements correlation ID management for request tracking across services.
Provides automatic correlation ID generation and propagation with OpenTelemetry integration.

Features:
- Automatic UUID v4 correlation ID generation for new requests
- Respects existing correlation ID from request headers
- Adds correlation ID to response headers
- Integrates with OpenTelemetry context
- Thread-safe async implementation
"""

import uuid
import logging
from typing import Optional, Callable, Awaitable
from fastapi import Request, Response, HTTPException
from starlette.types import ASGIApp
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

from .telemetry import set_correlation_id, get_correlation_id

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware for managing correlation IDs in HTTP requests.

    Automatically generates or extracts correlation IDs, ensures they are
    propagated through OpenTelemetry context, and added to response headers.
    """

    def __init__(
        self,
        app: ASGIApp,
        header_name: str = "x-correlation-id",
        validate_format: bool = True,
        propagate_to_downstream: bool = True,
    ):
        """
        Initialize correlation ID middleware.

        Args:
            app: ASGI application
            header_name: Header name for correlation ID
            validate_format: Whether to validate correlation ID format
            propagate_to_downstream: Whether to propagate correlation ID to downstream services
        """
        super().__init__(app)
        self.header_name = header_name.lower()
        self.validate_format = validate_format
        self.propagate_to_downstream = propagate_to_downstream

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[StarletteResponse]],
    ) -> StarletteResponse:
        """
        Process request and manage correlation ID.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response with correlation ID headers
        """
        correlation_id = self._extract_or_generate_correlation_id(request)

        # Set correlation ID in OpenTelemetry context
        set_correlation_id(correlation_id)

        # Log request with correlation ID
        logger.info(
            "Request started",
            method=request.method,
            url=str(request.url),
            client_host=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            extra={"correlation_id": correlation_id},
        )

        try:
            # Process request
            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers[self.header_name] = correlation_id

            # Log successful response
            logger.info(
                "Request completed",
                status_code=response.status_code,
                extra={"correlation_id": correlation_id},
            )

            return response

        except HTTPException as e:
            # Handle HTTP exceptions
            logger.warning(
                "HTTP exception occurred",
                status_code=e.status_code,
                detail=str(e.detail),
                extra={"correlation_id": correlation_id},
            )
            raise

        except Exception as e:
            # Handle unexpected exceptions
            logger.error(
                f"Unexpected error during request processing: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise

    def _extract_or_generate_correlation_id(self, request: Request) -> str:
        """
        Extract correlation ID from request or generate new one.

        Args:
            request: HTTP request

        Returns:
            Correlation ID string
        """
        # Try to extract from headers
        correlation_id = self._extract_from_headers(request)

        if correlation_id:
            # Validate existing correlation ID format if required
            if self.validate_format and not self._is_valid_correlation_id(
                correlation_id
            ):
                logger.warning(
                    "Invalid correlation ID format in request header, generating new one",
                    received_correlation_id=correlation_id,
                )
                correlation_id = self._generate_correlation_id()
        else:
            # Generate new correlation ID
            correlation_id = self._generate_correlation_id()
            logger.debug(
                "Generated new correlation ID",
                correlation_id=correlation_id,
            )

        return correlation_id

    def _extract_from_headers(self, request: Request) -> Optional[str]:
        """
        Extract correlation ID from request headers.

        Args:
            request: HTTP request

        Returns:
            Correlation ID if found and valid, None otherwise
        """
        # Check multiple possible header names (case-insensitive)
        possible_headers = [
            "x-correlation-id",
            "correlation-id",
            "x-request-id",
            "request-id",
            "x-trace-id",
            "trace-id",
        ]

        for header_name in possible_headers:
            if header_name in request.headers:
                correlation_id = request.headers[header_name].strip()
                if correlation_id:
                    return correlation_id

        return None

    def _generate_correlation_id(self) -> str:
        """
        Generate a new correlation ID.

        Returns:
            New UUID v4 correlation ID
        """
        return str(uuid.uuid4())

    def _is_valid_correlation_id(self, correlation_id: str) -> bool:
        """
        Validate correlation ID format.

        Args:
            correlation_id: Correlation ID to validate

        Returns:
            True if valid, False otherwise
        """
        if not correlation_id or not isinstance(correlation_id, str):
            return False

        correlation_id = correlation_id.strip()

        # Check length (reasonable bounds)
        if len(correlation_id) < 1 or len(correlation_id) > 255:
            return False

        # Basic format validation for UUID-like strings
        # Allow UUID format or other reasonable formats
        import re

        # UUID v4 format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
        uuid_pattern = (
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
        if re.match(uuid_pattern, correlation_id, re.IGNORECASE):
            return True

        # Allow other reasonable formats (alphanumeric, hyphens, underscores)
        alnum_pattern = r"^[a-zA-Z0-9\-_\.]+$"
        if re.match(alnum_pattern, correlation_id) and len(correlation_id) >= 8:
            return True

        return False


class ProjectCorrelationMixin:
    """
    Mixin for adding project-scoped correlation functionality.

    Provides methods for working with correlation IDs in a project context.
    """

    @staticmethod
    def add_project_context(correlation_id: str, project_id: str) -> None:
        """
        Add project context to correlation.

        Args:
            correlation_id: Current correlation ID
            project_id: Project ID to associate with correlation
        """
        from .telemetry import add_span_attribute

        # Add project attributes to current span
        add_span_attribute("project_id", project_id)
        add_span_attribute("correlation.project_id", project_id)

        logger.debug(
            "Added project context to correlation",
            correlation_id=correlation_id,
            project_id=project_id,
        )

    @staticmethod
    def create_project_correlation_id(project_id: str) -> str:
        """
        Create a correlation ID with project context.

        Args:
            project_id: Project ID to include in correlation

        Returns:
            Project-scoped correlation ID
        """
        base_id = str(uuid.uuid4())
        return f"{project_id}-{base_id}"

    @staticmethod
    def extract_project_from_correlation(correlation_id: str) -> Optional[str]:
        """
        Extract project ID from correlation ID if present.

        Args:
            correlation_id: Correlation ID to parse

        Returns:
            Project ID if present, None otherwise
        """
        if not correlation_id:
            return None

        # Try to extract project ID from pattern: {project_id}-{uuid}
        if "-" in correlation_id:
            parts = correlation_id.split("-", 1)
            if len(parts) == 2:
                potential_project_id = parts[0]
                # Basic validation for project ID format (UUID-like)
                import re

                uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
                if re.match(uuid_pattern, parts[1], re.IGNORECASE):
                    return potential_project_id

        return None


def get_request_correlation_id(request: Request) -> Optional[str]:
    """
    Helper function to extract correlation ID from request.

    Args:
        request: HTTP request

    Returns:
        Correlation ID if present, None otherwise
    """
    # Try multiple header names
    header_names = [
        "x-correlation-id",
        "correlation-id",
        "x-request-id",
        "request-id",
        "x-trace-id",
        "trace-id",
    ]

    for header_name in header_names:
        if header_name in request.headers:
            correlation_id = request.headers[header_name].strip()
            if correlation_id:
                return correlation_id

    return None


def add_correlation_to_response(response: Response, correlation_id: str) -> None:
    """
    Helper function to add correlation ID to response.

    Args:
        response: HTTP response
        correlation_id: Correlation ID to add
    """
    response.headers["x-correlation-id"] = correlation_id


# Export key components
__all__ = [
    "CorrelationIdMiddleware",
    "ProjectCorrelationMixin",
    "get_request_correlation_id",
    "add_correlation_to_response",
]
