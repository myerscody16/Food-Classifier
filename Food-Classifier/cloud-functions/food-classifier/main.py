import os
import tempfile
import json
import datetime
from google.cloud import storage, firestore, vision

# Configure constants
PROJECT_ID = os.environ.get("PROJECT_ID")
BUCKET_NAME = os.environ.get("BUCKET_NAME")

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
    
    # Download the file or use GCS path directly
    gcs_uri = f"gs://{BUCKET_NAME}/{file_path}"
    
    # Classify the image
    prediction = detect_labels(gcs_uri)
    
   # Replace the signed URL section with this
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(file_path)

    # Create a public URL
    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{file_path}"

    # Save to Firestore with SERVER_TIMESTAMP
    firestore_result = {
        'file_id': file_id,
        'file_name': file_name,
        'timestamp': firestore.SERVER_TIMESTAMP,  # Keep for Firestore
        'prediction': prediction,
        'image_url': public_url
    }
    doc_ref.set(firestore_result)

    # Return JSON response without the special Firestore value
    result = {
        'file_id': file_id,
        'file_name': file_name,
        'timestamp': datetime.datetime.now().isoformat(),  # Use string timestamp for JSON
        'prediction': prediction,
        'image_url': public_url
    }
    
    doc_ref.set(result)
    
    print(f"Processed image: {file_name}")
    return {"message": "Image processed successfully", "results": result}, 200

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