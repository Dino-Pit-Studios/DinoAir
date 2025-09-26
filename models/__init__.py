"""
Lightweight repo-local models for database layer decoupling.
Provides minimal DTOs used by database/* without GUI dependencies.
"""

from .artifact import Artifact, ArtifactCollection, ArtifactVersion
from .calendar_event import CalendarEvent
from .note import Note
from .project import Project, ProjectStatistics, ProjectStatus, ProjectSummary
from .watchdog_metrics import WatchdogMetric, WatchdogMetricsManager

__all__ = [
    "Note",
    "CalendarEvent",
    "Project",
    "ProjectStatus",
    "ProjectSummary",
    "ProjectStatistics",
    "Artifact",
    "ArtifactCollection",
    "ArtifactVersion",
    "WatchdogMetric",
    "WatchdogMetricsManager",
]
