"""Main scheduler agent implementation using LangGraph."""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging
from langgraph.graph import StateGraph

from ..models.schemas import SchedulingRequest, SchedulingResponse, TimeSlot, Attendee
from agents.calendar_manager import GoogleCalendarManager

logger = logging.getLogger(__name__)

class SchedulerAgent:
    """Main agent for handling scheduling requests."""
    
    def __init__(self, calendar_manager: Optional[GoogleCalendarManager] = None):
        """Initialize the scheduler agent.
        
        Args:
            calendar_manager: Optional pre-configured GoogleCalendarManager instance
        """
        self.calendar_manager = calendar_manager or GoogleCalendarManager()
        self.workflow = self._create_workflow()
    
    def _create_workflow(self) -> StateGraph:
        """Create the LangGraph workflow for scheduling."""
        workflow = StateGraph(SchedulingRequest)
        
        # Define nodes
        workflow.add_node("parse_request", self._parse_request)
        workflow.add_node("check_availability", self._check_availability)
        workflow.add_node("schedule_event", self._schedule_event)
        workflow.add_node("handle_conflict", self._handle_conflict)
        workflow.add_node("generate_response", self._generate_response)
        
        # Define edges
        workflow.add_edge("parse_request", "check_availability")
        workflow.add_conditional_edges(
            "check_availability",
            self._check_availability_decision,
            {
                "available": "schedule_event",
                "conflict": "handle_conflict"
            }
        )
        workflow.add_edge("schedule_event", "generate_response")
        workflow.add_edge("handle_conflict", "generate_response")
        
        # Set entry point
        workflow.set_entry_point("parse_request")
        
        return workflow.compile()
    
    def schedule(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a scheduling request.
        
        Args:
            request: Scheduling request data
            
        Returns:
            Scheduling response
        """
        try:
            # Validate and parse request
            scheduling_request = SchedulingRequest(**request)
            
            # Execute workflow
            result = self.workflow.invoke(scheduling_request)
            
            return result.dict()
            
        except Exception as e:
            logger.error(f"Error processing scheduling request: {e}")
            return SchedulingResponse(
                request_id=request.get("request_id", "unknown"),
                status="error",
                message=str(e),
                errors=[str(e)]
            ).dict()
    
    def _parse_request(self, state: SchedulingRequest) -> SchedulingRequest:
        """Parse and validate the scheduling request."""
        # Add the requester to attendees if not already present
        requester_email = state.from_email
        attendee_emails = {a["email"] for a in state.attendees}
        
        if requester_email not in attendee_emails:
            state.attendees.append({"email": requester_email})
            
        return state
    
    def _check_availability(self, state: SchedulingRequest) -> Dict[str, Any]:
        """Check attendee availability."""
        attendee_emails = [a["email"] for a in state.attendees]
        
        # Find available time slots
        available_slots = self.calendar_manager.find_available_slots(
            attendees=attendee_emails,
            duration_minutes=state.duration_minutes,
            time_min=datetime.utcnow(),
            time_max=datetime.utcnow() + timedelta(days=7)
        )
        
        return {
            "state": state,
            "available_slots": available_slots,
            "has_availability": bool(available_slots)
        }
    
    def _check_availability_decision(self, data: Dict[str, Any]) -> str:
        """Determine next step based on availability."""
        return "available" if data["has_availability"] else "conflict"
    
    def _schedule_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Schedule the event using the first available slot."""
        state = data["state"]
        slot = data["available_slots"][0]  # Use first available slot
        
        event_data = {
            "summary": state.subject,
            "description": state.email_content,
            "start": {
                "dateTime": slot.start_time.isoformat(),
                "timeZone": state.timezone
            },
            "end": {
                "dateTime": slot.end_time.isoformat(),
                "timeZone": state.timezone
            },
            "attendees": [{"email": a["email"]} for a in state.attendees],
            "location": state.location or ""
        }
        
        # Create the event
        event = self.calendar_manager.create_event(
            user_email=state.from_email,
            event_data=event_data
        )
        
        return {
            "state": state,
            "scheduled_event": event,
            "scheduled_slot": slot
        }
    
    def _handle_conflict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle scheduling conflicts by suggesting alternative times."""
        state = data["state"]
        
        # Find next available slots (wider search)
        attendee_emails = [a["email"] for a in state.attendees]
        
        # Look further ahead for available slots
        suggested_slots = self.calendar_manager.find_available_slots(
            attendees=attendee_emails,
            duration_minutes=state.duration_minutes,
            time_min=datetime.utcnow() + timedelta(days=1),
            time_max=datetime.utcnow() + timedelta(days=14)
        )
        
        return {
            "state": state,
            "suggested_slots": suggested_slots[:3]  # Return top 3 suggestions
        }
    
    def _generate_response(self, data: Dict[str, Any]) -> SchedulingResponse:
        """Generate the final response."""
        state = data["state"]
        
        if "scheduled_event" in data:
            # Success case
            return SchedulingResponse(
                request_id=state.request_id,
                status="scheduled",
                message="Meeting successfully scheduled",
                scheduled_events=[{
                    "start_time": data["scheduled_slot"].start_time.isoformat(),
                    "end_time": data["scheduled_slot"].end_time.isoformat(),
                    "attendees": [a["email"] for a in state.attendees],
                    "summary": state.subject
                }]
            )
        else:
            # Conflict case with suggestions
            suggested_times = [
                {
                    "start_time": slot.start_time.isoformat(),
                    "end_time": slot.end_time.isoformat()
                }
                for slot in data.get("suggested_slots", [])
            ]
            
            return SchedulingResponse(
                request_id=state.request_id,
                status="conflict",
                message="No available slots found. Here are some suggested times:",
                suggested_times=suggested_times
            )
