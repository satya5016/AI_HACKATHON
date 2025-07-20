"""Data models and schemas for the AI Scheduling Assistant."""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, validator

class Attendee(BaseModel):
    """Represents a meeting attendee."""
    email: str
    response_status: Optional[str] = None
    self: Optional[bool] = None

class TimeSlot(BaseModel):
    """Represents a time slot for a meeting."""
    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"

    @validator('end_time')
    def end_time_must_be_after_start_time(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('end_time must be after start_time')
        return v

class Event(BaseModel):
    """Represents a calendar event."""
    summary: str
    description: Optional[str] = None
    start: Dict[str, str]
    end: Dict[str, str]
    attendees: List[Dict[str, str]] = []
    location: Optional[str] = None
    status: Optional[str] = "confirmed"

class SchedulingRequest(BaseModel):
    """Input schema for scheduling requests."""
    request_id: str = Field(..., description="Unique identifier for the request")
    datetime: str = Field(..., description="ISO 8601 timestamp of the request")
    location: Optional[str] = Field(None, description="Meeting location")
    from_email: str = Field(..., description="Email of the requester")
    attendees: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of attendees with their emails"
    )
    subject: str = Field(..., description="Meeting subject")
    email_content: str = Field(..., description="Content of the scheduling email")
    duration_minutes: int = Field(30, description="Duration of the meeting in minutes")
    timezone: str = Field("UTC", description="Timezone for the meeting")

class SchedulingResponse(BaseModel):
    """Output schema for scheduling responses."""
    request_id: str
    status: str
    message: Optional[str] = None
    scheduled_events: Optional[List[Dict]] = None
    suggested_times: Optional[List[Dict]] = None
    errors: Optional[List[str]] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "6118b54f-907b-4451-8d48-dd13d76033a5",
                "status": "scheduled",
                "message": "Meeting successfully scheduled",
                "scheduled_events": [
                    {
                        "start_time": "2025-07-24T10:30:00+05:30",
                        "end_time": "2025-07-24T11:00:00+05:30",
                        "attendees": ["user1@example.com", "user2@example.com"],
                        "summary": "Project Status Update"
                    }
                ]
            }
        }
    }
