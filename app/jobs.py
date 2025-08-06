import os
import uuid

from flask import request, jsonify
from google.cloud import firestore

from app import app
from app import fb_db
import boto3

# JOB status
# Pending
# Assigned
# OnProcess
# Completed

# === AWS S3 Config ===
S3_BUCKET = ''
S3_REGION = ''
S3_ACCESS_KEY = ''
S3_SECRET_KEY = ''

# S3 client
s3 = boto3.client(
    's3',
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name=S3_REGION
)

@app.route('/mapi/upload_image', methods=['POST'])
def upload_image():
    job_id = request.form.get('job_id')
    image_type = request.form.get('type')  # 'before' or 'after'
    technician_id = request.form.get('technician_id')  # Optional
    files = request.files.getlist('image')

    if image_type not in ['before', 'after']:
        return jsonify({'error': 'Invalid image type'}), 400

    if not job_id or not files:
        return jsonify({'error': 'Missing job_id or image'}), 400

    job_ref = fb_db.collection('jobs').document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists:
        return jsonify({'error': 'Job not found'}), 404

    job_data = job_doc.to_dict()
    if technician_id and job_data.get('assigned_to') != technician_id:
        return jsonify({'error': 'Unauthorized'}), 403

    uploaded_urls = []

    for file in files:
        ext = os.path.splitext(file.filename)[1]
        unique_filename = f"jobs/{job_id}/{image_type}/{uuid.uuid4()}{ext}"

        s3.upload_fileobj(
            file,
            S3_BUCKET,
            unique_filename,
            ExtraArgs={'ContentType': file.content_type,}
        )

        public_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{unique_filename}"
        uploaded_urls.append(public_url)

    # Update Firestore
    image_field = f"images.{image_type}"
    fb_db.collection('jobs').document(job_id).update({
        image_field: firestore.ArrayUnion(uploaded_urls),
        f"{image_type}_image_uploaded": True
    })

    return jsonify({
        'message': f'{image_type.capitalize()} image(s) uploaded successfully',
        'urls': uploaded_urls
    })


@app.route('/mapi/start_job', methods=['POST'])
def start_job():
    data = request.json
    job_id = data.get('job_id')
    technician_id = data.get('technician_id')

    if not job_id or not technician_id:
        return jsonify({'error': 'Missing job_id or technician_id'}), 400

    job_ref = fb_db.collection('jobs').document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists:
        return jsonify({'error': 'Job not found'}), 404

    job = job_doc.to_dict()
    if job.get('assigned_to') != technician_id:
        return jsonify({'error': 'Unauthorized'}), 403

    job_ref.update({
        'status': 'OnProcess',
        'started_at': firestore.SERVER_TIMESTAMP,
        'before_image_uploaded': False,
        'after_image_uploaded': False
    })

    return jsonify({'message': 'Job started successfully'})


