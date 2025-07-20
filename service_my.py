from flask import Flask, request, jsonify
from threading import Thread
import json
import os
import sys
import logging
from datetime import datetime, timedelta
import uuid
from openai import OpenAI  # Use OpenAI client to connect to vLLM
import time 

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Define the base URL for the vLLM server
BASE_URL = "http://localhost:3000/v1"

# Define the model path
MODEL_PATH = "/home/user/Models/deepseek-ai/deepseek-llm-7b-chat"

# Set up the OpenAI client with the vLLM server
client = OpenAI(
    api_key="abc-123",  # API key set when starting vLLM server
    base_url=BASE_URL
)

# Add the current directory to path to ensure imports work
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Check token files
if os.path.exists('Keys'):
    files = os.listdir('Keys')
    logger.info(f"Files in Keys directory: {files}")
else:
    logger.error("Keys directory not found!")

# Import the ai_scheduler modules
from ai_scheduler.agents.scheduler_agent import SchedulerAgent
from ai_scheduler.agents.llm_service import LLMService
from ai_scheduler.agents.calendar_manager import GoogleCalendarManager

app = Flask(__name__)
received_data = []

# Initialize services with the model path
llm_service = LLMService(
    base_url=BASE_URL, 
    model_path=MODEL_PATH
)

calendar_manager = GoogleCalendarManager(token_dir='Keys')
scheduler_agent = SchedulerAgent(calendar_manager=calendar_manager)

def your_meeting_assistant(data): 
    """
    Process the meeting request and schedule a meeting using the SchedulerAgent.
    
    Args:
        data: Meeting request data
        
    Returns:
        Scheduled meeting data in the expected format
    """
    try:
        logger.info(f"Processing meeting request: {data.get('Request_id')}")
        
        # Format the request for SchedulerAgent
        request_data = {
            "request_id": data.get("Request_id", str(uuid.uuid4())),
            "datetime": datetime.utcnow().isoformat(),
            "from_email": data.get("From", ""),
            "attendees": [{"email": email.strip()} for email in data.get("To", "").split(",") if email.strip()],
            "subject": data.get("Subject", ""),
            "email_content": data.get("Body", ""),
            "duration_minutes": 30,  # Default, will be updated by LLM
            "timezone": "UTC"
        }
        
        # Use the scheduler agent to process the request
        response = scheduler_agent.schedule(request_data)
        
        # Format the response to match the expected format
        formatted_response = {
            "Request_id": data.get("Request_id", ""),
            "From": data.get("From", ""),
            "To": data.get("To", ""),
            "Subject": data.get("Subject", ""),
            "Body": data.get("Body", ""),
            "EventStart": response.get("scheduled_event", {}).get("start", {}).get("dateTime", ""),
            "EventEnd": response.get("scheduled_event", {}).get("end", {}).get("dateTime", ""),
            "Duration_mins": data.get("Duration_mins", 30),
            "MetaData": response
        }
        
        logger.info(f"Meeting scheduled: {formatted_response.get('EventStart')}")
        return formatted_response
        
    except Exception as e:
        logger.error(f"Error in meeting assistant: {e}")
        logger.exception("Exception details:")
        
        # If there's an error, return a minimal valid response
        response = data.copy()
        
        # Add required fields
        response["EventStart"] = ""
        response["EventEnd"] = ""
        response["Duration_mins"] = ""
        response["MetaData"] = {"error": str(e)}
        
        return response

@app.route('/receive', methods=['POST'])
def receive():
    data = request.get_json()
    print(f"\n Received: {json.dumps(data, indent=2)}")
    print(f"\n\n\n Sending:\n {json.dumps(new_data, indent=2)}")
    return jsonify(new_data)

def run_flask():
    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    # Start Flask in a background thread
    Thread(target=run_flask, daemon=True).start()

    # Keep the program running
    print("Flask server is running on http://0.0.0.0:5000")
    print("Press Ctrl+C to stop the server")

    # This will keep the process running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Server shutting down...")
        sys.exit(0)