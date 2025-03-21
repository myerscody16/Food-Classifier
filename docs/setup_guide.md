# Setup Guide for Food Classification System

## Prerequisites
- Google Cloud Platform (GCP) account with billing enabled
- Google Drive account
- Basic familiarity with command line tools

## Step 1: Create a GCP Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Note your Project ID for later use

## Step 2: Enable Required APIs
In the GCP Console, navigate to "APIs & Services" > "Library" and enable these APIs:
- Cloud Vision API
- Cloud Functions API
- Cloud Storage API
- Firestore API
- Drive API
- Firebase API

## Step 3: Set Up Storage Bucket
1. Navigate to "Cloud Storage" > "Buckets"
2. Click "Create Bucket"
3. Name your bucket: `[PROJECT-ID]-food-images`
4. Choose Region: "us-east5" (or your preferred region)
5. Leave other settings as default and click "Create"
6. Once created, go to the "Permissions" tab and add "allUsers" with "Storage Object Viewer" role to make images public

## Step 4: Set Up Firestore Database
1. Go to "Firestore Database"
2. Click "Create Database"
3. Choose "Native Mode"
4. Select a location close to your other resources
5. Click "Create"
6. Set up security rules under the "Rules" tab:
```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read: if true;
      allow write: if true;  // For testing only
    }
  }
}
```

## Step 5: Create Service Account
1. Go to "IAM & Admin" > "Service Accounts"
2. Click "Create Service Account"
3. Name: "food-classifier-service"
4. Add these roles:
   - Storage Admin
   - Firestore Admin
   - Cloud Vision API User
   - Cloud Functions Invoker
5. Click "Create and Continue" then "Done"
6. Click on the new service account
7. Go to the "Keys" tab
8. Click "Add Key" > "Create new key" > "JSON"
9. Save the key file securely

## Step 6: Share Google Drive Folder
1. Create a folder in Google Drive for image uploads
2. Right-click the folder and select "Share"
3. Add the service account email (looks like `food-classifier-service@[PROJECT-ID].iam.gserviceaccount.com`)
4. Give it "Editor" access
5. Note the folder ID from the URL:
   - From `https://drive.google.com/drive/folders/1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7`
   - The folder ID is `1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7`

## Step 7: Deploy Food Classifier Function
1. Navigate to "Cloud Run"
2. Click "Create Function"
3. Name: "food-classifier"
4. Region: "us-east5" (or match your bucket region)
5. Trigger: HTTP
6. Authentication: Allow unauthenticated invocations
7. Runtime: Python 3.9
8. Entry point: `process_image`
9. For the source code, use the following code for `main.py`:

```python
import os
import json
import datetime
import tempfile
from flask import jsonify
from google.cloud import storage, firestore, vision

# Configuration
PROJECT_ID = os.environ.get('PROJECT_ID')
BUCKET_NAME = os.environ.get('BUCKET_NAME')

def process_image(request):
    """Process an image and classify it with Vision API"""
    # Get the request parameters
    request_json = request.get_json(silent=True)
    
    # Get the file path from the request
    file_path = request_json.get('file_path') if request_json else None
    if not file_path:
        return {"error": "No file path provided"}, 400
    
    # Set up clients
    storage_client = storage.Client()
    db = firestore.Client()
    
    # Generate a unique ID for the file
    file_name = file_path.split('/')[-1]
    file_id = file_name.split('.')[0]
    
    # Check if we've already processed this file
    doc_ref = db.collection('processed_images').document(file_id)
    doc = doc_ref.get()
    
    if doc.exists:
        return {"message": f"File {file_id} already processed", "results": doc.to_dict()}, 200
    
    # Use GCS path for classification
    gcs_uri = f"gs://{BUCKET_NAME}/{file_path}"
    
    # Classify the image
    prediction = detect_labels(gcs_uri)
    
    # Create a public URL
    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{file_path}"
    
    # Save to Firestore with SERVER_TIMESTAMP
    firestore_result = {
        'file_id': file_id,
        'file_name': file_name,
        'timestamp': firestore.SERVER_TIMESTAMP,
        'prediction': prediction,
        'image_url': public_url
    }
    doc_ref.set(firestore_result)
    
    # Return JSON response without the special Firestore value
    result = {
        'file_id': file_id,
        'file_name': file_name,
        'timestamp': datetime.datetime.now().isoformat(),
        'prediction': prediction,
        'image_url': public_url
    }
    
    return result

def detect_labels(image_path):
    """Detects labels in the image using Google Vision API."""
    client = vision.ImageAnnotatorClient()
    
    # Create image object
    image = vision.Image()
    image.source.image_uri = image_path
    
    # Perform label detection
    response = client.label_detection(image=image)
    labels = response.label_annotations
    
    # Filter for food-related labels
    food_categories = [
        'food', 'cuisine', 'dish', 'meal', 'ingredient', 'dessert', 
        'breakfast', 'lunch', 'dinner', 'fruit', 'vegetable', 'meat',
        'baked goods', 'beverage', 'drink'
    ]
    
    # Process and format results
    results = []
    for label in labels:
        is_food = any(food_cat in label.description.lower() for food_cat in food_categories)
        results.append({
            'label': label.description,
            'score': label.score,
            'is_food': is_food
        })
    
    # Sort by score
    results = sorted(results, key=lambda x: x['score'], reverse=True)
    
    return results
```

10. Create a `requirements.txt` file with:
```
google-cloud-storage==2.7.0
google-cloud-firestore==2.10.0
google-cloud-vision==2.7.3
flask==2.0.1
```

11. Add environment variables:
    - PROJECT_ID: Your GCP project ID
    - BUCKET_NAME: Your storage bucket name

## Step 8: Deploy Drive Webhook Function
1. Navigate to "Cloud Run"
2. Click "Create Function"
3. Name: "drive-to-storage-sync"
4. Region: "us-east5" (or match your bucket region)
5. Trigger: HTTP
6. Authentication: Allow unauthenticated invocations
7. Runtime: Python 3.9
8. Entry point: `webhook`
9. For the source code, use the following code for `main.py`:

```python
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
```

10. Create a `requirements.txt` file with:
```
functions-framework==3.0.0
google-cloud-storage==2.7.0
google-api-python-client==2.86.0
google-auth==2.17.3
requests==2.28.1
flask==2.0.1
werkzeug==2.0.1
```

11. Add environment variables:
    - PROJECT_ID: Your GCP project ID
    - BUCKET_NAME: Your storage bucket name
    - DRIVE_FOLDER_ID: Your Google Drive folder ID
    - CLASSIFIER_URL: URL of your food-classifier function
    - GOOGLE_APPLICATION_CREDENTIALS_JSON: Your service account key JSON (entire contents)

## Step 9: Register Webhook with Google Drive
1. Save the following code as `register_webhook.py`:

```python
import os
import time
import uuid
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration
DRIVE_FOLDER_ID = "YOUR_DRIVE_FOLDER_ID"  # Your Google Drive folder ID
WEBHOOK_URL = "YOUR_CLOUD_RUN_URL/webhook"  # Your Cloud Run webhook URL
SERVICE_ACCOUNT_FILE = "service-account-key.json"  # Path to your service account key file

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
```

2. Update the configuration variables in the script:
   - DRIVE_FOLDER_ID: Your Drive folder ID
   - WEBHOOK_URL: Your drive-to-storage-sync function URL + "/webhook"
   - SERVICE_ACCOUNT_FILE: Path to your service account key file
3. Run the script:
   ```bash
   python register_webhook.py
   ```
4. Verify the webhook was registered successfully

## Step 10: Deploy Website
1. Create the following `index.html` file:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Food Classification Results</title>
    <script src="https://www.gstatic.com/firebasejs/8.10.1/firebase-app.js"></script>
    <script src="https://www.gstatic.com/firebasejs/8.10.1/firebase-firestore.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }
        .result-card {
            background-color: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 25px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .result-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 15px;
            align-items: center;
        }
        .result-image {
            max-width: 100%;
            max-height: 300px;
            border-radius: 8px;
            margin-bottom: 15px;
            display: block;
        }
        .prediction {
            display: flex;
            align-items: center;
            margin-bottom: 10px;
        }
        .prediction-label {
            font-weight: bold;
            min-width: 150px;
        }
        .prediction-bar {
            height: 24px;
            background-color: #4285f4;
            border-radius: 4px;
            margin-right: 10px;
        }
        .prediction-score {
            min-width: 60px;
            text-align: right;
        }
        .is-food {
            background-color: #34a853;
        }
        .not-food {
            background-color: #ea4335;
        }
        .time {
            color: #666;
            font-size: 0.9em;
        }
        .loading {
            text-align: center;
            padding: 30px;
            color: #666;
        }
        .empty-message {
            text-align: center;
            padding: 40px 20px;
            color: #666;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .upload-info {
            text-align: center;
            margin-bottom: 30px;
            padding: 15px;
            background-color: #e8f0fe;
            border-radius: 8px;
        }
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            background-color: #4285f4;
            color: white;
            padding: 15px 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            z-index: 1000;
            animation: slide-in 0.5s ease-out;
        }
        .fade-out {
            opacity: 0;
            transition: opacity 0.5s ease-out;
        }
        @keyframes slide-in {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        .auto-update-indicator {
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 20px;
            color: #4285f4;
            font-size: 0.9em;
        }
        .pulse {
            width: 10px;
            height: 10px;
            background-color: #34a853;
            border-radius: 50%;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.4; }
            100% { opacity: 1; }
        }
    </style>
</head>
<body>
    <h1>Food Classification Results</h1>
    
    <div class="upload-info">
        <p>Upload images to your Google Drive folder to classify them.</p>
        <p>Bucket: <strong>YOUR_BUCKET_NAME</strong></p>
    </div>
    
    <div class="auto-update-indicator">
        <div class="pulse"></div>
        <span>Auto-updating in real-time</span>
    </div>
    
    <div id="results-container" class="loading">Loading results...</div>

    <script>
        // Firebase configuration - Replace with your project values
        const firebaseConfig = {
            apiKey: "YOUR_API_KEY",
            authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
            projectId: "YOUR_PROJECT_ID",
            storageBucket: "YOUR_BUCKET_NAME",
            messagingSenderId: "YOUR_MESSAGING_SENDER_ID",
            appId: "YOUR_APP_ID"
        };
        
        // Initialize Firebase
        firebase.initializeApp(firebaseConfig);
        const db = firebase.firestore();
        
        function formatTimestamp(timestamp) {
            if (!timestamp) return 'Unknown';
            
            try {
                // Handle Firestore timestamp objects
                if (timestamp.toDate) {
                    return timestamp.toDate().toLocaleString();
                }
                // Handle ISO strings
                if (typeof timestamp === 'string' && timestamp.includes('T')) {
                    return new Date(timestamp).toLocaleString();
                }
                return timestamp;
            } catch (e) {
                return timestamp;
            }
        }
        
        function setupRealtimeUpdates() {
            const resultsContainer = document.getElementById('results-container');
            resultsContainer.innerHTML = '<div class="loading">Loading results...</div>';
            
            // Listen for real-time updates
            db.collection('processed_images')
                .orderBy('timestamp', 'desc')
                .limit(10)
                .onSnapshot((snapshot) => {
                    if (snapshot.empty) {
                        resultsContainer.innerHTML = '<div class="empty-message">No classification results found. Upload an image to the storage bucket to get started!</div>';
                        return;
                    }
                    
                    // Check if this is the initial load or an update
                    const isInitialLoad = !resultsContainer.querySelector('.result-card');
                    
                    // If this isn't the initial load, and something changed, show notification
                    if (!isInitialLoad && snapshot.docChanges().length > 0) {
                        const newImages = snapshot.docChanges()
                            .filter(change => change.type === 'added')
                            .map(change => change.doc.data().file_name);
                            
                        if (newImages.length > 0) {
                            showNotification(`New classification: ${newImages[0]}${newImages.length > 1 ? ` and ${newImages.length - 1} more` : ''}`);
                        }
                    }
                    
                    // Clear container for refresh
                    resultsContainer.innerHTML = '';
                    
                    // Display all results
                    snapshot.forEach((doc) => {
                        displayResultCard(doc.data(), resultsContainer);
                    });
                }, (error) => {
                    console.error("Error watching collection: ", error);
                    resultsContainer.innerHTML = `<div class="error">Error loading results: ${error.message}</div>`;
                });
        }
        
        // Helper function to display a result card
        function displayResultCard(data, container) {
            const card = document.createElement('div');
            card.className = 'result-card';
            
            // Create header with filename and timestamp
            const header = document.createElement('div');
            header.className = 'result-header';
            const fileName = document.createElement('h2');
            fileName.textContent = data.file_name;
            const time = document.createElement('span');
            time.className = 'time';
            time.textContent = formatTimestamp(data.timestamp);
            header.appendChild(fileName);
            header.appendChild(time);
            card.appendChild(header);
            
            // Add image if available
            if (data.image_url) {
                const img = document.createElement('img');
                img.src = data.image_url;
                img.alt = data.file_name;
                img.className = 'result-image';
                card.appendChild(img);
            }
            
            // Add predictions
            const predictions = data.prediction || [];
            if (predictions && predictions.length > 0) {
                // Sort predictions by score, highest first
                const sortedPredictions = [...predictions].sort((a, b) => b.score - a.score);
                
                // Take top 5
                sortedPredictions.slice(0, 5).forEach(prediction => {
                    const predDiv = document.createElement('div');
                    predDiv.className = 'prediction';
                    
                    const label = document.createElement('div');
                    label.className = 'prediction-label';
                    label.textContent = prediction.label;
                    
                    const barWidth = Math.round(prediction.score * 100);
                    const bar = document.createElement('div');
                    bar.className = `prediction-bar ${prediction.is_food ? 'is-food' : 'not-food'}`;
                    bar.style.width = `${barWidth * 3}px`; // Scale for better visualization
                    
                    const score = document.createElement('div');
                    score.className = 'prediction-score';
                    score.textContent = `${barWidth}%`;
                    
                    predDiv.appendChild(label);
                    predDiv.appendChild(bar);
                    predDiv.appendChild(score);
                    
                    card.appendChild(predDiv);
                });
            } else {
                const noResults = document.createElement('p');
                noResults.textContent = 'No predictions found for this image.';
                card.appendChild(noResults);
            }
            
            container.appendChild(card);
        }
        
        // Notification function
        function showNotification(message) {
            const notification = document.createElement('div');
            notification.className = 'notification';
            notification.textContent = message;
            document.body.appendChild(notification);
            
            // Remove after 3 seconds
            setTimeout(() => {
                notification.classList.add('fade-out');
                setTimeout(() => notification.remove(), 500);
            }, 3000);
        }
        
        // Start real-time updates when the page loads
        document.addEventListener('DOMContentLoaded', function() {
            setupRealtimeUpdates();
        });
    </script>
</body>
</html>
```

2. Update the following in the HTML:
   - Replace `YOUR_BUCKET_NAME` with your bucket name
   - Update the Firebase config with your project values
3. Navigate to your Cloud Storage bucket
4. Create a folder named "website"
5. Upload the `index.html` file to this directory
6. Make the file publicly accessible
7. Note the public URL of the file, which should be something like:
   ```
   https://storage.googleapis.com/[PROJECT-ID]-food-images/website/index.html
   ```

## Step 11: Test the System
1. Upload a food image to your Google Drive folder
2. Wait a few seconds
3. Visit your website URL
4. Verify that the image appears with its classification results

## Troubleshooting
- **Webhook not working**: Re-register the webhook as they expire after 7 days
- **Images not appearing in the bucket**: Check the Cloud Function logs for errors
- **Classification not working**: Verify the Vision API is enabled and the classifier function is working
- **Website not updating**: Check Firestore security rules and browser console for errors

## Decommissioning Steps
To properly shut down the project:
1. Delete the Cloud Functions
2. Delete the Cloud Storage bucket
3. Delete the Firestore database
4. Disable all APIs
5. Delete the service account
6. Unregister the webhook (optional, it will expire automatically)
7. Verify in the Billing section that there are no more active resources