import os
import uuid

from flask import request, jsonify
from google.cloud import firestore

from app import app
from app import fb_db


# JOB status
# Pending
# Assigned
# OnProcess
# Completed

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


