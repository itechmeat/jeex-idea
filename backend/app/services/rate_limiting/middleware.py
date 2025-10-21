"""
Rate Limiting Middleware

FastAPI middleware for automatic rate limiting.
Provides HTTP 429 responses with retry-after headers.
"""

import logging
import time
from typing import Optional, Dict, Any, Callable
from uuid import UUID

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from opentelemetry import trace

from .rate_limiter import rate_limiter, RateLimitConfig, RateLimitResult

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automatic rate limiting.

    Applies rate limiting based on user authentication, IP address,
    and API endpoint patterns with automatic HTTP 429 responses.
    """

    def __init__(
        self,
        app,
        user_id_extractor: Optional[Callable[[Request], Optional[str]]] = None,
        exclude_paths: Optional[list[str]] = None,
        enabled: bool = True,
    ):
        """
        Initialize rate limiting middleware.

        Args:
            app: FastAPI application
            user_id_extractor: Function to extract user ID from request
            exclude_paths: List of paths to exclude from rate limiting
            enabled: Whether rate limiting is enabled
        """
        super().__init__(app)
        self.user_id_extractor = user_id_extractor or self._default_user_id_extractor
        self.exclude_paths = set(
            exclude_paths or ["/health", "/metrics", "/docs", "/openapi.json"]
        )
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request through rate limiting middleware.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response with rate limiting headers
        """
        if not self.enabled:
            return await call_next(request)

        # Skip rate limiting for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        with tracer.start_as_current_span("rate_limiting_middleware.dispatch") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.path", request.url.path)

            try:
                # Extract identifiers for rate limiting
                user_id = await self._extract_user_id(request)
                client_ip = self._get_client_ip(request)
                endpoint = self._normalize_endpoint(request.url.path)

                # Determine request cost based on method and endpoint
                cost = self._calculate_request_cost(request)

                # Apply rate limiting checks
                rate_limit_result = await self._apply_rate_limits(
                    request, user_id, client_ip, endpoint, cost, span
                )

                if not rate_limit_result.allowed:
                    # Return HTTP 429 Too Many Requests
                    return self._create_rate_limit_response(rate_limit_result, span)

                # Add rate limiting headers to successful response
                response = await call_next(request)
                self._add_rate_limit_headers(response, rate_limit_result)

                return response

            except Exception as e:
                logger.error(f"Rate limiting middleware error: {e}")
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

                # Fail open - allow request on middleware errors
                return await call_next(request)

    async def _default_user_id_extractor(self, request: Request) -> Optional[str]:
        """Default user ID extraction from request headers."""
        # Try to get user ID from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # In a real implementation, this would decode JWT token
            # For now, we'll return None to skip user-based rate limiting
            pass

        # Try to get user ID from custom header
        user_id = request.headers.get("X-User-ID")
        if user_id:
            return user_id

        return None

    async def _extract_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request using configured extractor."""
        try:
            return await self.user_id_extractor(request)
        except Exception as e:
            logger.warning(f"Failed to extract user ID from request: {e}")
            return None

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        # Check for forwarded IP first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to client IP
        return request.client.host if request.client else "unknown"

    def _normalize_endpoint(self, path: str) -> str:
        """Normalize endpoint path for rate limiting."""
        # Remove query parameters
        if "?" in path:
            path = path.split("?")[0]

        # Handle dynamic path segments (e.g., /api/v1/projects/{id})
        path_parts = path.split("/")
        normalized_parts = []

        for part in path_parts:
            if part and not part.startswith("{") and not part.isdigit():
                normalized_parts.append(part)
            elif part and (part.startswith("{") or part.isdigit()):
                # Replace dynamic segments with placeholder
                if normalized_parts:
                    normalized_parts.append("id")

        return "/" + "/".join(normalized_parts) if normalized_parts else "/"

    def _calculate_request_cost(self, request: Request) -> int:
        """Calculate request cost based on method and endpoint."""
        # Higher cost for write operations
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            # Even higher cost for expensive operations
            if "documents" in request.url.path and request.method == "POST":
                return 3  # Document creation is expensive
            if "agents" in request.url.path and request.method == "POST":
                return 5  # Agent operations are very expensive
            return 2
        return 1  # Read operations have normal cost

    async def _apply_rate_limits(
        self,
        request: Request,
        user_id: Optional[str],
        client_ip: str,
        endpoint: str,
        cost: int,
        span,
    ) -> RateLimitResult:
        """Apply multiple rate limiting checks."""

        # 1. IP-based rate limiting (always applied)
        ip_result = await rate_limiter.check_ip_rate_limit(client_ip, cost=cost)
        span.set_attribute("rate_limit.ip.allowed", ip_result.allowed)
        span.set_attribute("rate_limit.ip.remaining", ip_result.remaining_requests)

        if not ip_result.allowed:
            span.set_attribute("rate_limit.blocked_by", "ip")
            return ip_result

        # 2. User-based rate limiting (if user is authenticated)
        if user_id:
            try:
                user_result = await rate_limiter.check_user_rate_limit(
                    user_id, cost=cost
                )
                span.set_attribute("rate_limit.user.allowed", user_result.allowed)
                span.set_attribute(
                    "rate_limit.user.remaining", user_result.remaining_requests
                )

                if not user_result.allowed:
                    span.set_attribute("rate_limit.blocked_by", "user")
                    return user_result

            except Exception as e:
                logger.warning(f"User rate limiting failed for {user_id}: {e}")

        # 3. Endpoint-based rate limiting
        try:
            endpoint_result = await rate_limiter.check_endpoint_rate_limit(
                endpoint, user_id, cost=cost
            )
            span.set_attribute("rate_limit.endpoint.allowed", endpoint_result.allowed)
            span.set_attribute(
                "rate_limit.endpoint.remaining", endpoint_result.remaining_requests
            )

            if not endpoint_result.allowed:
                span.set_attribute("rate_limit.blocked_by", "endpoint")
                return endpoint_result

        except Exception as e:
            logger.warning(f"Endpoint rate limiting failed for {endpoint}: {e}")

        # Return the most restrictive result (lowest remaining requests)
        results = [ip_result]
        if user_id:
            try:
                results.append(user_result)
            except:
                pass
        try:
            results.append(endpoint_result)
        except:
            pass

        # Find the most restrictive limit
        most_restrictive = min(results, key=lambda r: r.remaining_requests)
        span.set_attribute("rate_limit.remaining", most_restrictive.remaining_requests)

        return most_restrictive

    def _create_rate_limit_response(
        self, result: RateLimitResult, span
    ) -> JSONResponse:
        """Create HTTP 429 Too Many Requests response."""

        span.set_attribute("http.status_code", status.HTTP_429_TOO_MANY_REQUESTS)
        span.set_attribute("rate_limit.limit", result.limit)
        span.set_attribute("rate_limit.window", result.window)
        span.set_attribute("rate_limit.reset_seconds", result.reset_seconds)

        response_content = {
            "error": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests",
            "details": {
                "limit": result.limit,
                "window": result.window,
                "reset_seconds": result.reset_seconds,
                "limit_type": result.limit_type,
                "identifier": result.identifier,
            },
        }

        response = JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, content=response_content
        )

        # Add rate limiting headers
        self._add_rate_limit_headers(response, result)

        return response

    def _add_rate_limit_headers(
        self, response: Response, result: RateLimitResult
    ) -> None:
        """Add rate limiting headers to response."""

        headers = {
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining_requests),
            "X-RateLimit-Reset": str(int(time.time()) + result.reset_seconds),
            "X-RateLimit-Window": str(result.window),
            "X-RateLimit-Type": result.limit_type,
        }

        if result.retry_after:
            headers["Retry-After"] = str(result.retry_after)

        # Add headers to response
        for key, value in headers.items():
            response.headers[key] = value

    def configure_endpoint_limits(
        self, endpoint_limits: Dict[str, RateLimitConfig]
    ) -> None:
        """
        Configure custom rate limits for specific endpoints.

        Args:
            endpoint_limits: Dictionary of endpoint -> rate limit config
        """
        rate_limiter.API_ENDPOINT_LIMITS.update(endpoint_limits)
        logger.info(f"Updated rate limits for {len(endpoint_limits)} endpoints")

    def add_excluded_path(self, path: str) -> None:
        """Add path to rate limiting exclusion list."""
        self.exclude_paths.add(path)
        logger.debug(f"Added path to rate limiting exclusions: {path}")

    def remove_excluded_path(self, path: str) -> None:
        """Remove path from rate limiting exclusion list."""
        self.exclude_paths.discard(path)
        logger.debug(f"Removed path from rate limiting exclusions: {path}")

    def enable(self) -> None:
        """Enable rate limiting middleware."""
        self.enabled = True
        logger.info("Rate limiting middleware enabled")

    def disable(self) -> None:
        """Disable rate limiting middleware."""
        self.enabled = False
        logger.info("Rate limiting middleware disabled")
