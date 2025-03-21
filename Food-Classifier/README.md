# Food Classifier Project

A system that automatically classifies food images uploaded to Google Drive using Google Cloud Vision API and displays the results in real-time.

## Architecture

![Architecture Diagram](architecture/flowchart.png)

The system flow:
1. User uploads images to a Google Drive folder
2. Google Drive webhook notifies our Cloud Function
3. Cloud Function transfers the image to Cloud Storage
4. Food Classifier function processes the image with Vision API
5. Results are stored in Firestore
6. Website displays results in real-time

## Components

- **Drive Webhook Function**: Monitors a Google Drive folder and transfers new images to Cloud Storage
- **Food Classifier Function**: Classifies food images using Google Cloud Vision API
- **Firestore Database**: Stores classification results
- **Cloud Storage Bucket**: Stores the actual images
- **Web Interface**: Displays classification results with real-time updates

## Setup Instructions

See [Setup Guide](docs/setup_guide.md) for detailed instructions on how to deploy this project.

## Technologies Used

- Google Cloud Platform
  - Cloud Run
  - Cloud Storage
  - Cloud Vision API
  - Firestore Database
- Google Drive API
- Firebase Hosting
- JavaScript/HTML for the web interface