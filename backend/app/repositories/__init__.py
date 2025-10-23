"""
Repository Pattern Implementation

Provides base repository with project isolation enforcement (SEC-002).
All data access must go through repositories to ensure security boundaries.
"""

from .base import BaseRepository
from .project import ProjectRepository

__all__ = [
    "BaseRepository",
    "ProjectRepository",
]
