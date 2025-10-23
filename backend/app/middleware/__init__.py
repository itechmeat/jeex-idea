"""
Middleware modules for request/response processing.

Includes:
- Security headers (SEC-001)
# TODO: Correlation ID tracking middleware is implemented in core.correlation
"""

from .security import SecurityHeadersMiddleware

__all__ = [
    "SecurityHeadersMiddleware",
]
