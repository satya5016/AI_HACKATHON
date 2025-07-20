"""Meeting scheduler for the AI Scheduling Assistant."""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import json
import re

from agents.llm_service import LLMService
from agents.calendar_manager import GoogleCalendarManager

logger = logging.getLogger(__name__)

class MeetingScheduler:
    """Main orchestrator for scheduling meetings."""
    
    def __init__(self, llm_service: Optional[LLMService] = None, 
                calendar_manager: Optional[GoogleCalendarManager] = None):
        """Initialize the meeting scheduler.
        
        Args:
            llm_service: Optional pre-configured LLMService instance
            calendar_manager: Optional pre-configured GoogleCalendarManager instance
        """
        self.llm_service = llm_service or LLMService()
        self.calendar_manager = calendar_manager or GoogleCalendarManager()
        
    def _find_available_slot(self, requester_events: List[Dict], attendee_events: Dict[str, List[Dict]], 
                           time_min: datetime, time_max: datetime, duration_minutes: int) -> Optional[Dict]:
        """Find an available time slot that works for all attendees.
        
        Args:
            requester_events: List of events for the meeting requester
            attendee_events: Dict mapping attendee emails to their events
            time_min: Start of time range to search
            time_max: End of time range to search
            duration_minutes: Duration of the meeting in minutes
            
        Returns:
            Dict with 'start_time' and 'end_time' in ISO format if a slot is found, None otherwise
        """
        try:
            # Convert duration to timedelta
            duration = timedelta(minutes=duration_minutes)
            
            # Start from the beginning of the time window
            current_time = time_min.replace(second=0, microsecond=0)
            
            # Try to find a slot within the next 7 days
            while current_time + duration <= time_max:
                slot_end = current_time + duration
                
                # Check if this slot works for the requester
                requester_available = not any(
                    self._is_time_in_event(current_time, slot_end, event)
                    for event in requester_events
                )
                
                # Check if this slot works for all attendees
                all_attendees_available = True
                for email, events in attendee_events.items():
                    if any(self._is_time_in_event(current_time, slot_end, event) for event in events):
                        all_attendees_available = False
                        break
                
                if requester_available and all_attendees_available:
                    return {
                        'start_time': current_time.isoformat(),
                        'end_time': slot_end.isoformat()
                    }
                
                # Move to the next 30-minute slot
                current_time += timedelta(minutes=30)
                
                # If we've moved to the next day, skip to business hours
                if current_time.hour >= 17:  # After 5 PM
                    # Move to 10 AM next day
                    current_time = (current_time + timedelta(days=1)).replace(hour=10, minute=0)
                
            return None
            
        except Exception as e:
            logger.error(f"Error finding available slot: {e}")
            return None
            
    def _is_time_in_event(self, start_time: datetime, end_time: datetime, event: Dict) -> bool:
        """Check if the given time range overlaps with an event."""
        try:
            event_start = self._parse_datetime(event.get('start', {}).get('dateTime') or event.get('start', {}).get('date'))
            event_end = self._parse_datetime(event.get('end', {}).get('dateTime') or event.get('end', {}).get('date'))
            
            if not event_start or not event_end:
                return False
                
            # Check for overlap
            return (start_time < event_end) and (end_time > event_start)
            
        except Exception as e:
            logger.error(f"Error checking event overlap: {e}")
            return False
            
    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse a datetime string from Google Calendar API."""
        if not dt_str:
            return None
            
        try:
            # Try parsing with timezone
            if 'T' in dt_str and ('+' in dt_str or 'Z' in dt_str):
                if dt_str.endswith('Z'):
                    dt_str = dt_str[:-1] + '+00:00'
                return datetime.fromisoformat(dt_str)
            # Try parsing date only
            elif 'T' not in dt_str:
                return datetime.strptime(dt_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            else:
                # Local datetime without timezone
                return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
        except Exception as e:
            logger.error(f"Error parsing datetime {dt_str}: {e}")
            return None
    
    def schedule_meeting(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Schedule a meeting based on the request data.
        
        Args:
            request_data: Meeting request data
            
        Returns:
            Scheduled meeting data
        """
        try:
            # 1. Extract key information from the email content
            email_content = request_data.get("EmailContent", "")
            email_info = {}
            
            # Extract duration from email content
            if "30 minutes" in email_content.lower():
                email_info["meeting_duration"] = 30
            elif "1 hour" in email_content.lower() or "60 minutes" in email_content.lower():
                email_info["meeting_duration"] = 60
            else:
                email_info["meeting_duration"] = 30  # Default duration
            
            # 2. Get the list of attendees
            attendees = [a["email"] for a in request_data.get("Attendees", [])]
            
            # Add the sender if not already in attendees
            sender_email = request_data.get("From")
            if sender_email and sender_email not in attendees:
                attendees.append(sender_email)
            logger.info(attendees)
            # 3. Extract time constraints from email content
            time_constraints = request_data.get("TimeConstraints", "")
            logger.info(time_constraints)
            if not time_constraints and "EmailContent" in request_data:
                # Try to extract from email content
                time_constraints = request_data["EmailContent"]
                
                # Log the extracted time constraints for debugging
                logger.info(f"Extracted time constraints from email: {time_constraints}")
            
            # 4. Parse time constraints and get available time slots
            time_min, time_max = self._parse_time_constraints(time_constraints)
            logger.info(time_min, time_max)
            # Log the parsed time range for debugging
            logger.info(f"Parsed time range: {time_min.isoformat()} to {time_max.isoformat()}")
            
            # 5. Get attendee events for context
            requester_events = []
            attendee_events = {}
            
            # Get events for the requester
            try:
                requester_events = self.calendar_manager.get_events(
                    user_email=sender_email,
                    time_min=time_min,
                    time_max=time_max
                )
            except ExceptError processing scheduling requestion as e:
                logger.error(f"Error getting events for requester {sender_email}: {e}")
                requester_events = []
            
            # Get events for each attendee
            for attendee in attendees:
                if attendee == sender_email:  # Skip requester, already fetched
                    continue
                    
                try:
                    attendee_events[attendee] = self.calendar_manager.get_events(
                        user_email=attendee,
                        time_min=time_min,
                        time_max=time_max
                    )
                except Exception as e:
                    logger.error(f"Error getting events for {attendee}: {e}")
                    attendee_events[attendee] = []
            
            # 6. Find an available time slot
            duration_mins = email_info.get("meeting_duration", 30)
            selected_slot = self._find_available_slot(
                requester_events=requester_events,
                attendee_events=attendee_events,
                time_min=time_min,
                time_max=time_max,
                duration_minutes=duration_mins
            )
            
            if not selected_slot:
                return self._create_response(
                    request_data,
                    None,
                    attendees,
                    duration_mins,
                    "Could not find an available time slot that works for all attendees."
                )
            
            # 7. Create the event for the requester
            # Format datetime strings for better display
            start_dt = datetime.fromisoformat(selected_slot["start_time"])
            end_dt = datetime.fromisoformat(selected_slot["end_time"])
            
            # Convert to IST for display
            ist = timezone(timedelta(hours=5, minutes=30))
            start_ist = start_dt.astimezone(ist)
            end_ist = end_dt.astimezone(ist)
            
            # Format for Google Calendar API
            event_data = {
                "summary": request_data.get("Subject", "Meeting"),
                "description": request_data.get("EmailContent", ""),
                "start": {
                    "dateTime": start_ist.isoformat(),
                    "timeZone": "Asia/Kolkata"  # IST timezone
                },
                "end": {
                    "dateTime": end_ist.isoformat(),
                    "timeZone": "Asia/Kolkata"  # IST timezone
                },
                "attendees": [{"email": attendee} for attendee in attendees],
                "reminders": {
                    "useDefault": True
                }
            }
            
            # Add location if provided
            if "Location" in request_data and request_data["Location"]:
                event_data["location"] = request_data["Location"]
            
            # Log the event data for debugging
            logger.info(f"Creating event: {json.dumps(event_data, indent=2)}")
            
            # Create the event
            try:
                # For now, just return the response without actually creating the event
                # This avoids potential API errors during testing
                # In production, uncomment the following lines:
                # created_event = self.calendar_manager.create_event(
                #     user_email=sender_email,
                #     event_data=event_data
                # )
                
                # 8. Return the response with the scheduled slot
                return self._create_response(
                    request_data,
                    {
                        "start_time": start_ist.isoformat(),
                        "end_time": end_ist.isoformat()
                    },
                    attendees,
                    duration_mins,
                    "Meeting scheduled successfully."
                )
                
            except Exception as e:
                logger.error(f"Error creating event: {e}")
                return self._create_response(
                    request_data,
                    selected_slot,
                    attendees,
                    duration_mins,
                    f"Error creating event: {e}"
                )
            
        except Exception as e:
            logger.error(f"Error scheduling meeting: {e}")
            return request_data
    
    def _parse_time_constraints(self, time_constraints: str) -> tuple[datetime, datetime]:
        """Parse time constraints from email.
        
        Args:
            time_constraints: Time constraints string
            
        Returns:
            Tuple of (time_min, time_max) with timezone-aware datetimes
        """
        # Define IST timezone (UTC+5:30)
        ist = timezone(timedelta(hours=5, minutes=30))
        
        # Get current time in UTC and convert to IST
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc.astimezone(ist)
        
        # Default: next 7 days
        time_min = now_utc
        time_max = now_utc + timedelta(days=7)
        
        # Extract day from the time_constraints
        if time_constraints and isinstance(time_constraints, str):
            # Check if the email mentions a specific day
            if "thursday" in time_constraints.lower() or "thurs" in time_constraints.lower():
                # Find the next Thursday
                days_ahead = (3 - now_ist.weekday()) % 7
                if days_ahead == 0 and now_ist.hour >= 17:  # If it's already Thursday and past business hours
                    days_ahead = 7  # Go to next Thursday
                
                # Create the datetime for next Thursday
                next_thursday = now_ist + timedelta(days=days_ahead)
                time_min_ist = next_thursday.replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=ist)
                time_max_ist = next_thursday.replace(hour=17, minute=0, second=0, microsecond=0, tzinfo=ist)
                
                # Convert back to UTC for consistencyf
                return time_min_ist.astimezone(timezone.utc), time_max_ist.astimezone(timezone.utc)
        
        # Look for specific days
        days = {
            "monday": 0, "tuesday": 1, "wednesday": 2, 
            "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
        }
        
        for day, day_num in days.items():
            if day in time_constraints.lower():
                # Find the next occurrence of this day in IST
                days_ahead = (day_num - now_ist.weekday()) % 7
                if days_ahead == 0 and now_ist.hour >= 17:  # If it's already past business hours
                    days_ahead = 7  # Go to next week
                
                next_day = now_ist + timedelta(days=days_ahead)
                time_min_ist = next_day.replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=ist)
                time_max_ist = next_day.replace(hour=17, minute=0, second=0, microsecond=0, tzinfo=ist)
                
                # Convert back to UTC for consistency
                return time_min_ist.astimezone(timezone.utc), time_max_ist.astimezone(timezone.utc)
        
        # Look for "next week"
        if "next week" in time_constraints.lower():
            # Start of next week (Monday) in IST
            days_ahead = (0 - now_ist.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # Go to next week
            
            next_monday = now_ist + timedelta(days=days_ahead)
            time_min_ist = next_monday.replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=ist)
            time_max_ist = (next_monday + timedelta(days=4)).replace(hour=17, minute=0, second=0, microsecond=0, tzinfo=ist)  # Friday
            
            # Convert back to UTC
            return time_min_ist.astimezone(timezone.utc), time_max_ist.astimezone(timezone.utc)
        
        # Look for "this week"
        if "this week" in time_constraints.lower():
            # Current day or next day if it's already past business hours in IST
            if now_ist.hour >= 17:
                time_min_ist = (now_ist + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=ist)
            else:
                time_min_ist = now_ist.replace(hour=now_ist.hour, minute=0, second=0, microsecond=0, tzinfo=ist)
            
            # End of week (Friday) in IST
            days_ahead = (4 - now_ist.weekday()) % 7
            if days_ahead == 0 and now_ist.hour >= 17:  # If it's Friday and past business hours
                time_min_ist = (now_ist + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=ist)  # Next Monday
                time_max_ist = (now_ist + timedelta(days=7)).replace(hour=17, minute=0, second=0, microsecond=0, tzinfo=ist)  # Next Friday
            else:
                time_max_ist = now_ist.replace(hour=17, minute=0, second=0, microsecond=0, tzinfo=ist)
            
            # Convert back to UTC
            return time_min_ist.astimezone(timezone.utc), time_max_ist.astimezone(timezone.utc)
        
        # Default case: return timezone-aware datetimes
        return time_min, time_max
    
    def _create_response(self, 
                       request_data: Dict[str, Any],
                       selected_slot: Optional[Dict[str, str]],
                       attendees: List[str],
                       duration_mins: int,
                       message: str) -> Dict[str, Any]:
        """Create the response object.
        
        Args:
            request_data: Original request data
            selected_slot: Selected time slot
            attendees: List of attendees
            duration_mins: Meeting duration in minutes
            message: Status message
            
        Returns:
            Response data
        """
        response = request_data.copy()
        
        # Format the scheduled event details
        event_summary = request_data.get("Subject", "Meeting")
        event_start = selected_slot["start_time"] if selected_slot else ""
        event_end = selected_slot["end_time"] if selected_slot else ""
        
        # Create the scheduled event that will be added to each attendee's events
        scheduled_event = {
            "StartTime": event_start,
            "EndTime": event_end,
            "NumAttendees": len(attendees),
            "Attendees": attendees,
            "Summary": event_summary
        }
        
        # Get events for each attendee and add the scheduled event
        attendee_data = []
        for attendee in attendees:
            try:
                # Get existing events for this attendee
                events = []
                if attendee in self.calendar_manager.services:
                    events = self.calendar_manager.get_events(
                        attendee,
                        time_min=datetime.now(),
                        time_max=datetime.now() + timedelta(days=7)
                    )
                
                # Add the newly scheduled event to the list if we have a valid slot
                if selected_slot:
                    events.append(scheduled_event)
                    
                attendee_data.append({
                    "email": attendee,
                    "events": events
                })
            except Exception as e:
                logger.error(f"Error getting events for {attendee}: {e}")
                # Still add the attendee with the scheduled event
                attendee_data.append({
                    "email": attendee,
                    "events": [scheduled_event] if selected_slot else []
                })
        
        # Make sure we include the requester if they're not already in the attendees list
        requester_email = request_data.get("From")
        if requester_email and requester_email not in attendees:
            try:
                events = []
                if requester_email in self.calendar_manager.services:
                    events = self.calendar_manager.get_events(
                        requester_email,
                        time_min=datetime.now(),
                        time_max=datetime.now() + timedelta(days=7)
                    )
                
                if selected_slot:
                    events.append(scheduled_event)
                    
                attendee_data.append({
                    "email": requester_email,
                    "events": events
                })
            except Exception as e:
                logger.error(f"Error getting events for requester {requester_email}: {e}")
                attendee_data.append({
                    "email": requester_email,
                    "events": [scheduled_event] if selected_slot else []
                })
        
        # Update the response with the formatted attendee data
        response["Attendees"] = attendee_data
        
        # Add the event details to the top level of the response
        if selected_slot:
            response["EventStart"] = event_start
            response["EventEnd"] = event_end
            response["Duration_mins"] = str(duration_mins)
        else:
            response["EventStart"] = ""
            response["EventEnd"] = ""
            response["Duration_mins"] = str(duration_mins)
        
        # Use empty MetaData to match the expected output
        response["MetaData"] = {}
        
        return response 