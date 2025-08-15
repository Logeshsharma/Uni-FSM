import os
import uuid

import boto3
from flask import jsonify
from flask import request
from google.cloud import firestore
from werkzeug.security import check_password_hash

from app import app
from app import fb_db

# JOB status
# Pending
# Assigned
# OnProcess
# Completed
# Closed

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


@app.route('/mapi/login', methods=['POST'])
def login_mobile():
    username = request.json.get('username')
    password = request.json.get('password')

    user_ref = fb_db.collection('users').where('username', '==', username).limit(1)
    docs = user_ref.stream()
    user_doc = next(docs, None)

    if not user_doc:
        return jsonify({"message": "Login failed. Invalid username or password", "status": "error"}), 401

    user = user_doc.to_dict()

    if not check_password_hash(user['password'], password):
        return jsonify({"message": "Login failed. Invalid username or password", "status": "error"}), 401

    return jsonify({
        "message": "Login successful",
        "status": "success",
        "user_id": user_doc.id,
        "username": user['username'],
        "email": user['email'],
        "role": user['role']
    }), 200


@app.route('/mapi/jobs_list', methods=['GET'])
def jobs_list_client():
    user_id = request.args.get('user_id')
    role = request.args.get('role')

    jobs_query = fb_db.collection('jobs')

    if user_id and role == 'Student':
        jobs_query = jobs_query.where('created_by', '==', user_id)
    elif user_id and role == 'Technician':
        jobs_query = jobs_query.where('assigned_to', '==', user_id)

    docs = jobs_query.stream()

    jobs = []
    for doc in docs:
        job = doc.to_dict()
        job['job_id'] = doc.id

        created_by_id = job.get('created_by')
        created_by_user = {}
        if created_by_id:
            user_doc = fb_db.collection('users').document(created_by_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                created_by_user = {
                    "user_id": created_by_id,
                    "username": user_data.get('username', user_data.get('username'))  # fallback to email
                }

        assigned_to_id = job.get('assigned_to')
        assigned_to_user = None
        if assigned_to_id:
            tech_doc = fb_db.collection('users').document(assigned_to_id).get()
            if tech_doc.exists:
                tech_data = tech_doc.to_dict()
                assigned_to_user = {
                    "user_id": assigned_to_id,
                    "username": tech_data.get('username', tech_data.get('username'))  # fallback to email
                }

        job['created_by'] = created_by_user
        job['assigned_to'] = assigned_to_user

        jobs.append(job)

    return jsonify(jobs)


@app.route('/mapi/job_detail', methods=['GET'])
def job_detail_client():
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
    tech_complete = job.get('tech_complete', False)

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
        "after_image_uploaded": after_uploaded,
        "tech_complete": tech_complete,
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
        'tech_complete': True,
        'completed_at': firestore.SERVER_TIMESTAMP
    })

    return jsonify({'message': 'Job marked as completed'})


@app.route('/mapi/close_job', methods=['POST'])
def close_job():
    data = request.json
    job_id = data.get('job_id')
    student_id = data.get('student_id')

    if not job_id or not student_id:
        return jsonify({"error": "Missing job_id or student_id"}), 400

    job_ref = fb_db.collection('jobs').document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists:
        return jsonify({"error": "Job not found"}), 404

    job_data = job_doc.to_dict()

    if job_data.get('created_by') != student_id:
        return jsonify({"error": "Unauthorized"}), 403

    if not job_data.get('tech_complete'):
        return jsonify({"error": "Technician has not completed the job yet"}), 400

    job_ref.update({
        "student_closed": True,
        "status": "Closed",
        "closed_at": firestore.SERVER_TIMESTAMP
    })

    return jsonify({"message": "Job closed successfully"}), 200
