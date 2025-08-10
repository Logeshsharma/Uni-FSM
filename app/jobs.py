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
S3_BUCKET = os.getenv("S3_BUCKET")
S3_REGION = os.getenv("S3_REGION")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")

# S3 client
s3 = boto3.client(
    's3',
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name=S3_REGION
)

@app.route('/mapi/job_detail', methods=['GET'])
def api_job_detail():
    job_id = request.args.get('job_id')
    if not job_id:
        return jsonify({"error": "Missing job_id"}), 400

    job_ref = fb_db.collection('jobs').document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists:
        return jsonify({"error": "Job not found"}), 404

    job = job_doc.to_dict()

    created_by_info = {}
    if job.get('created_by'):
        creator_doc = fb_db.collection('users').document(job['created_by']).get()
        if creator_doc.exists:
            creator_data = creator_doc.to_dict()
            created_by_info = {
                "user_id": creator_doc.id,
                "username": creator_data.get('username')
            }

    assigned_to_info = None
    if job.get('assigned_to'):
        tech_doc = fb_db.collection('users').document(job['assigned_to']).get()
        if tech_doc.exists:
            tech_data = tech_doc.to_dict()
            assigned_to_info = {
                "user_id": tech_doc.id,
                "username": tech_data.get('username')
            }

    images = job.get('images', {})
    before_images = images.get('before', [])
    after_images = images.get('after', [])
    before_uploaded = job.get('before_image_uploaded', False)
    after_uploaded = job.get('after_image_uploaded', False)

    return jsonify({
        "job_id": job_id,
        "title": job.get('title'),
        "description": job.get('description'),
        "status": job.get('status', 'N/A'),
        "job_category": job.get('job_category'),
        "job_date": job.get('job_date'),
        "job_time": job.get('job_time'),
        "address": job.get('address'),
        "created_by": created_by_info,
        "assigned_to": assigned_to_info,
        "before_images": before_images,
        "after_images": after_images,
        "before_image_uploaded": before_uploaded,
        "after_image_uploaded": after_uploaded
    }), 200


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
            ExtraArgs={'ContentType': file.content_type or 'application/octet-stream'}
        )

        public_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{unique_filename}"
        uploaded_urls.append(public_url)

    image_field = f"images.{image_type}"
    fb_db.collection('jobs').document(job_id).update({
        image_field: firestore.ArrayUnion(uploaded_urls),
        f"{image_type}_image_uploaded": True
    })

    return jsonify({
        'message': f'{image_type.capitalize()} image(s) uploaded successfully',
        'urls': uploaded_urls
    })


@app.route('/mapi/complete_job', methods=['POST'])
def complete_job():
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
    if not job.get('before_image_uploaded') or not job.get('after_image_uploaded'):
        return jsonify({'error': 'Both before and after images must be uploaded first'}), 400

    job_ref.update({
        'status': 'Completed',
        'completed_at': firestore.SERVER_TIMESTAMP
    })

    return jsonify({'message': 'Job marked as completed'})