"""
Security Headers Middleware (SEC-001)

Implements security headers as required by SEC-001 to protect against common
web vulnerabilities:
- HSTS (Strict-Transport-Security)
- X-Content-Type-Options
- X-Frame-Options
- Content-Security-Policy
- X-XSS-Protection (legacy browsers)

CRITICAL: These headers are applied to ALL responses automatically.
"""

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable

logger = structlog.get_logger()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses (SEC-001).

    Headers implemented:
    1. Strict-Transport-Security (HSTS): Force HTTPS for 1 year
    2. X-Content-Type-Options: Prevent MIME sniffing
    3. X-Frame-Options: Prevent clickjacking
    4. Content-Security-Policy: Control resource loading
    5. X-XSS-Protection: Legacy XSS protection

    NOTE: This middleware should be added early in the middleware stack
    to ensure headers are applied to all responses, including error responses.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and add security headers to response.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or endpoint handler

        Returns:
            Response with security headers added
        """
        try:
            # Process request through the chain
            response = await call_next(request)

            # HSTS: Force HTTPS for 1 year (31536000 seconds)
            # includeSubDomains: Apply to all subdomains
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

            # Prevent MIME type sniffing
            # Ensures browsers respect Content-Type header
            response.headers["X-Content-Type-Options"] = "nosniff"

            # Prevent clickjacking attacks
            # DENY: Page cannot be displayed in frame/iframe
            response.headers["X-Frame-Options"] = "DENY"

            # Content Security Policy
            # default-src 'self': Only load resources from same origin
            # script-src 'self': Only execute scripts from same origin
            # style-src 'self' 'unsafe-inline': Allow same-origin styles + inline styles
            #   (unsafe-inline needed for some frontend frameworks)
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'"
            )

            # XSS protection for legacy browsers (deprecated in modern browsers)
            # mode=block: Block rendering if XSS detected
            response.headers["X-XSS-Protection"] = "1; mode=block"

            # Referrer Policy: Control referrer information
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

            # Permissions Policy: Disable unnecessary browser features
            response.headers["Permissions-Policy"] = (
                "geolocation=(), "
                "microphone=(), "
                "camera=(), "
                "payment=(), "
                "usb=(), "
                "magnetometer=(), "
                "gyroscope=(), "
                "accelerometer=()"
            )

            logger.debug(
                "Security headers added", path=request.url.path, method=request.method
            )

            return response

        except Exception as e:
            logger.error(
                "Failed to add security headers",
                path=request.url.path,
                method=request.method,
                error=str(e),
                exc_info=True,
            )
            # Re-raise to let error handlers deal with it
            # Better to fail than to skip security headers
            raise
