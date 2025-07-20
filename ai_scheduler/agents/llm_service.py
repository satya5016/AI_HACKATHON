"""LLM service for the AI Scheduling Assistant."""

import json
import logging
from typing import Dict, Any, List, Optional
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class LLMService:
    """Service for interacting with the LLM."""
    
    def __init__(self, base_url: str = "http://localhost:3000/v1", model_path: str = "/home/user/Models/deepseek-ai/deepseek-llm-7b-chat", api_key: str = "abc-123"):
        """Initialize the LLM service.
        
        Args:
            base_url: Base URL for the vLLM server
            model_path: Path to the model to use
            api_key: API key for authentication with the vLLM server
        """
        self.base_url = base_url
        self.model_path = model_path
        self.api_key = api_key
        
    def parse_email(self, email_text: str) -> Dict[str, Any]:
        """Parse email content to extract scheduling information.
        
        Args:
            email_text: Email content to parse
            
        Returns:
            Dict with extracted information
        """
        prompt = f"""
        You are an Agent that helps in scheduling meetings.
        Your job is to extract Email IDs and Meeting Duration.
        You should return:
        1. List of email ids of participants (comma-separated).
        2. Meeting duration in minutes.
        3. Time constraints (e.g., 'next week', 'Thursday').
        If the List of email ids of participants are just names, then append @amd.com at the end and return.
        Return as json with 'participants', 'time_constraints' & 'meeting_duration'.
        Strictly follow the instructions. Strictly return dict with participants email ids, time constraints & meeting duration in minutes only.
        Do not add any other instructions or information.
        
        Email: {email_text}
        """
        
        try:
            response = self._call_llm(prompt)
            # Parse the response as JSON
            return json.loads(response)
        except Exception as e:
            logger.error(f"Error parsing email with LLM: {e}")
            # Return a default response if parsing fails
            return {
                "participants": [],
                "time_constraints": "",
                "meeting_duration": 30
            }
    
    def suggest_meeting_time(self, 
                           request_data: Dict[str, Any], 
                           available_slots: List[Dict[str, Any]],
                           attendee_events: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Suggest the best meeting time based on available slots and attendee events.
        
        Args:
            request_data: Original request data
            available_slots: List of available time slots
            attendee_events: Dictionary of attendee events
            
        Returns:
            Dict with suggested meeting time
        """
        # Limit the number of slots to reduce token usage
        limited_slots = available_slots[:5]  # Only use the first 5 slots
        
        # Convert available slots to a more readable format
        formatted_slots = []
        for i, slot in enumerate(limited_slots):
            start = datetime.fromisoformat(slot["start_time"])
            end = datetime.fromisoformat(slot["end_time"])
            formatted_slots.append({
                "index": i,
                "day": start.strftime("%A"),
                "date": start.strftime("%Y-%m-%d"),
                "start_time": start.strftime("%H:%M"),
                "end_time": end.strftime("%H:%M")
            })
        
        # Format attendee events - limit to only relevant events
        formatted_events = {}
        for attendee, events in attendee_events.items():
            formatted_events[attendee] = []
            # Only include events on the same days as the available slots
            slot_dates = {datetime.fromisoformat(slot["start_time"]).strftime("%Y-%m-%d") for slot in limited_slots}
            
            for event in events:
                event_date = datetime.fromisoformat(event["StartTime"]).strftime("%Y-%m-%d")
                if event_date in slot_dates:
                    start = datetime.fromisoformat(event["StartTime"])
                    end = datetime.fromisoformat(event["EndTime"])
                    formatted_events[attendee].append({
                        "day": start.strftime("%A"),
                        "date": start.strftime("%Y-%m-%d"),
                        "start_time": start.strftime("%H:%M"),
                        "end_time": end.strftime("%H:%M"),
                        "summary": event["Summary"]
                    })
        
        prompt = f"""
        You are an AI Scheduling Assistant that helps find the optimal meeting time.
        
        Meeting Request:
        Subject: {request_data.get('Subject', 'Meeting')}
        Email Content: {request_data.get('EmailContent', '')}
        
        Available Slots:
        {json.dumps(formatted_slots, indent=2)}
        
        Based on the meeting request and available slots, suggest the best meeting time.
        Consider:
        1. Time constraints mentioned in the email
        2. Working hours (9 AM - 5 PM)
        3. Preferring morning slots for important meetings
        
        Return a JSON with:
        1. selected_slot: The index of the selected slot from the available slots list
        2. reasoning: A brief explanation of why this slot was chosen
        
        Return only valid JSON.
        """
        
        try:
            response = self._call_llm(prompt)
            # Parse the response as JSON
            result = json.loads(response)
            selected_index = result.get("selected_slot", 0)
            
            # Ensure the index is valid
            if selected_index >= len(available_slots):
                selected_index = 0
                
            return {
                "selected_slot": available_slots[selected_index],
                "reasoning": result.get("reasoning", "This time works for all attendees.")
            }
        except Exception as e:
            logger.error(f"Error suggesting meeting time with LLM: {e}")
            # Return the first available slot if parsing fails
            return {
                "selected_slot": available_slots[0] if available_slots else None,
                "reasoning": "Default selection due to processing error."
            }
    
    def _call_llm(self, prompt: str) -> str:
        """Call the LLM with a prompt.
        
        Args:
            prompt: Prompt to send to the LLM
            
        Returns:
            LLM response text
        """
        try:
            payload = {
                "model": self.model_path,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 500  # Reduced from 1000 to 500
            }
            
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            response = requests.post(
                f"{self.base_url}/chat/completions", 
                headers=headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                logger.error(f"Error calling LLM API: {response.status_code} - {response.text}")
                return "{}"
        except Exception as e:
            logger.error(f"Exception when calling LLM API: {e}")
            return "{}" 