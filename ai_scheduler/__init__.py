"""
AI Scheduling Assistant - An agentic system for autonomous meeting scheduling.

This is the main package initialization file that re-exports the public API
from the main module.
"""

# Import directly from agents
from .agents.meeting_scheduler import MeetingScheduler
from .agents.llm_service import LLMService
from .agents.calendar_manager import GoogleCalendarManager

# Keep original imports if needed
from .main import *

__all__ = [
    'MeetingScheduler',
    'LLMService',
    'SchedulerAgent',
    'SchedulingRequest',
    'SchedulingResponse',
    'create_scheduler_agent',
    '__version__'
]