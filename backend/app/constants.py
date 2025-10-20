"""
JEEX Idea Global Constants

Centralized location for all system-wide constants used across the application.
"""

from uuid import UUID
from datetime import datetime, timezone

# System Constants
SYSTEM_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000000")


# Timestamp Functions
def get_current_timestamp() -> datetime:
    """Get current timestamp with UTC timezone.

    Returns:
        datetime: Current UTC timestamp

    Note: Use this function instead of a constant to get real-time timestamps.
    """
    return datetime.now(timezone.utc)


# Application Constants
APP_NAME = "JEEX Idea"
APP_VERSION = "1.0.0"
