import os
import uuid

import joblib
import numpy as np
from flask import request, jsonify
from google.cloud import firestore

from app import app
from app import fb_db

# Load AI model and encoder at startup
try:
    current_dir = os.path.dirname(__file__)
    model_path = os.path.join(current_dir, "ai", "assign_model.pkl")
    model, label_encoder = joblib.load(model_path)
    print("AI model and label encoder loaded successfully")
except Exception as e:
    print(" Error loading model:", e)
    model = None
    label_encoder = None



@app.route('/mapi/create_job', methods=['POST', 'GET'])
def create_job():
    user_id = request.json.get('user_id')
    title = request.json.get('title')
    description = request.json.get('description')
    job_category = request.json.get('job_category')
    job_date = request.json.get('job_date')
    job_time = request.json.get('job_time')
    address = request.json.get('address')

    user_doc = fb_db.collection('users').document(user_id).get()
    if not user_doc.exists:
        return jsonify({"error": "Invalid user"}), 404

    user = user_doc.to_dict()
    if user.get('role') != 'Student':
        return jsonify({"error": "Only students can create jobs"}), 403

    job_id = str(uuid.uuid4())
    fb_db.collection('jobs').document(job_id).set({
        'title': title,
        'description': description,
        'created_by': user_id,
        'assigned_to': None,
        'status': 'Pending',
        'job_category': job_category,
        'job_date': job_date,
        'job_time': job_time,
        'address': address,
        'tech_complete': False,
        'student_closed': False,
        'created_at': firestore.SERVER_TIMESTAMP,
        "closed_at": None,
    })

    assign_technician(job_id)

    return jsonify({"message": "Job created", "job_id": job_id})


def assign_technician(job_id):
    MAX_ACTIVE_JOBS = 2

    job_ref = fb_db.collection("jobs").document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists:
        # Job not found.
        return

    job_data = job_doc.to_dict()
    category = job_data.get("job_category")

    if not category:
        # No job category provided.
        return

    category_encoded = label_encoder.transform([category])[0]

    tech_docs = fb_db.collection("users").where("role", "==", "Technician").stream()

    best_score = -1
    best_tech = None
    best_tech_data = None
    fallback_options = []

    for tech_doc in tech_docs:
        tech_data = tech_doc.to_dict()
        tech_id = tech_doc.id
        skills = tech_data.get("skills", [])
        active_jobs = tech_data.get("active_jobs", 0)
        skill_match = 1 if category in skills else 0

        features = np.array([[category_encoded, skill_match, active_jobs]])
        assign_prob = model.predict_proba(features)[0][1]

        if skill_match:
            fallback_options.append({
                "technician_id": tech_id,
                "username": tech_data.get("username"),
                "score": round(assign_prob, 2),
                "active_jobs": active_jobs,
                "skills": skills
            })

        if skill_match and active_jobs < MAX_ACTIVE_JOBS and assign_prob > best_score:
            best_score = assign_prob
            best_tech = tech_id
            best_tech_data = tech_data

    if best_tech:
        fresh_doc = fb_db.collection("users").document(best_tech).get()
        fresh_data = fresh_doc.to_dict()
        fresh_active_jobs = fresh_data.get("active_jobs", 0)

        if fresh_active_jobs >= MAX_ACTIVE_JOBS:
            best_tech = None  # Clear the assignment

    if best_tech:

        # Update job
        job_ref.update({
            "assigned_to": best_tech,
            "status": "Assigned"
        })

        # Update technician
        new_active_jobs = best_tech_data.get("active_jobs", 0) + 1
        update_data = {
            "active_jobs": new_active_jobs
        }

        if new_active_jobs >= MAX_ACTIVE_JOBS:
            update_data["tech_available"] = False

        fb_db.collection("users").document(best_tech).update(update_data)

    else:
        fallback_options = sorted(fallback_options, key=lambda x: x["score"], reverse=True)[:3]
        print(fallback_options)
        job_ref.update({
            "assignment_suggestions": fallback_options,
            "status": "Pending"
        })