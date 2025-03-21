import os
import json
import tempfile
from flask import jsonify
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.cloud import storage
import requests
import functions_framework

# Configuration from environment variables
PROJECT_ID = os.environ.get('PROJECT_ID')
BUCKET_NAME = os.environ.get('BUCKET_NAME')
DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID')
CLASSIFIER_URL = os.environ.get('CLASSIFIER_URL')

@functions_framework.http
def webhook(request):
    """Handle Drive webhook notifications"""
    try:
        # Log the headers for debugging
        print("Received webhook. Headers:", dict(request.headers))
        
        # For GET requests (verification)
        if request.method == 'GET':
            return "Drive webhook service is running"
        
        # Google Drive webhooks don't send a JSON payload
        # Instead, they send headers with info about what changed
        resource_state = request.headers.get('X-Goog-Resource-State')
        resource_id = request.headers.get('X-Goog-Resource-Id')
        resource_uri = request.headers.get('X-Goog-Resource-Uri')
        
        print(f"Resource state: {resource_state}")
        print(f"Resource ID: {resource_id}")
        print(f"Resource URI: {resource_uri}")
        
        # For change notifications, we need to list files in the folder
        # because the notification only tells us something changed
        if resource_state in ('sync', 'update', 'add'):
            # We need to list files in the folder to find what changed
            result = process_recent_files()
            return jsonify(result)
        
        return jsonify({"status": "notification received", "type": resource_state})
    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        return jsonify({"error": str(e)}), 500

def process_recent_files():
    """Process recently added files in the Drive folder"""
    # Get service account credentials
    creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if not creds_json:
        return {"error": "No credentials found"}
    
    # Parse credentials and build Drive service
    creds_dict = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    drive_service = build('drive', 'v3', credentials=credentials)
    
    # List recent files in the folder
    results = drive_service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType contains 'image/' and trashed=false",
        orderBy="createdTime desc",
        pageSize=5,
        fields="files(id, name, mimeType, createdTime)"
    ).execute()
    
    files = results.get('files', [])
    if not files:
        return {"status": "no files found in folder"}
    
    # Process the most recent file
    most_recent = files[0]
    file_id = most_recent['id']
    file_name = most_recent['name']
    
    # Check if file already exists in bucket
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(file_name)
    
    if blob.exists():
        # Check if we need to process it again
        print(f"File {file_name} already exists in bucket")
        
        # For simplicity, we'll re-process existing files
        # In a production system, you might want to skip them
    
    # Download from Drive
    try:
        request = drive_service.files().get_media(fileId=file_id)
        
        with tempfile.NamedTemporaryFile() as temp:
            downloader = MediaIoBaseDownload(temp, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            # Upload to Cloud Storage
            temp.seek(0)
            blob.upload_from_file(temp)
            
            print(f"Uploaded {file_name} to Cloud Storage")
    except Exception as e:
        return {"status": "error", "error": f"Failed to transfer file: {str(e)}"}
    
    # Call the classifier
    try:
        classifier_response = requests.post(
            CLASSIFIER_URL,
            json={'file_path': file_name},
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"Classifier response: {classifier_response.status_code}")
        
        if classifier_response.status_code != 200:
            return {
                "status": "error", 
                "file_name": file_name,
                "error": f"Classifier error: {classifier_response.text}"
            }
            
        return {
            "status": "success",
            "file_name": file_name,
            "processed": True,
            "classification": classifier_response.json()
        }
    except Exception as e:
        return {"status": "error", "error": f"Failed to classify: {str(e)}"}