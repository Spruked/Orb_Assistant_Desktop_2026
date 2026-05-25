"""Core presence and cognition-memory modules."""

from .desktop_presence import DesktopPresence, launch_desktop_presence
from .memory_learner import SystemBehaviorLearner

__all__ = ["DesktopPresence", "SystemBehaviorLearner", "launch_desktop_presence"]

