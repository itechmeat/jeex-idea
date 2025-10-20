"""
JEEX Idea Global Constants

Centralized location for all system-wide constants used across the application.
"""

from uuid import UUID
from datetime import datetime, timezone

# System Constants
SYSTEM_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000000")

# Timestamp Constants
CURRENT_TIMESTAMP = datetime.now(timezone.utc)

# Application Constants
APP_NAME = "JEEX Idea"
APP_VERSION = "1.0.0"
