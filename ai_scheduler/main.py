"""
AI Scheduling Assistant - Main module.

This module provides the main entry point for the AI Scheduling Assistant package.
"""

__version__ = "0.1.0"

from .agents.scheduler_agent import SchedulerAgent
from .models.schemas import SchedulingRequest, SchedulingResponse

def create_scheduler_agent() -> SchedulerAgent:
    """Create and initialize a new SchedulerAgent instance."""
    return SchedulerAgent()
