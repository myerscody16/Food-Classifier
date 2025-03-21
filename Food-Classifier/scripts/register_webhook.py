import os
import time
import uuid
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration
DRIVE_FOLDER_ID = ""  # Your Google Drive folder ID
WEBHOOK_URL = ""  # Your Cloud Run webhook URL
SERVICE_ACCOUNT_FILE = ""  # Path to your service account key file

def register_webhook():
    """Register a webhook to monitor Drive folder changes"""
    # Load service account key
    with open(SERVICE_ACCOUNT_FILE, 'r') as f:
        credentials_info = json.load(f)
    
    # Create credentials
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    
    # Build Drive API service
    drive_service = build('drive', 'v3', credentials=credentials)
    
    # Create a unique channel ID
    channel_id = str(uuid.uuid4())
    
    # Calculate expiration time (1 week from now in milliseconds)
    expiration = int((time.time() + 604800) * 1000)
    
    # Create the webhook request
    body = {
        'id': channel_id,
        'type': 'web_hook',
        'address': WEBHOOK_URL,
        'expiration': expiration
    }
    
    # Register the webhook
    try:
        response = drive_service.files().watch(
            fileId=DRIVE_FOLDER_ID,
            body=body
        ).execute()
        
        print("Webhook successfully registered!")
        print(f"Channel ID: {response['id']}")
        print(f"Resource ID: {response['resourceId']}")
        print(f"Expiration: {response['expiration']} (about 1 week)")
        
        return response
    except Exception as e:
        print(f"Error registering webhook: {str(e)}")
        return None

if __name__ == "__main__":
    register_webhook()