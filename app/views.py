import uuid

from flask import render_template, redirect, url_for, flash, request, jsonify
from google.cloud import firestore
from werkzeug.security import generate_password_hash, check_password_hash
from app import app
from app.models import User
from app.forms import LoginForm
from flask_login import current_user, login_user, logout_user, login_required
from urllib.parse import urlsplit
from app import fb_db
import numpy as np
import joblib

# Load AI model and encoder at startup
try:
    model, label_encoder = joblib.load("/Users/logeshsharma/Documents/Logesh-UOB/FinalProjects/UniFSM-web/lxk496/app/assign_model.pkl")
    print("✅ AI model and label encoder loaded successfully")
except Exception as e:
    print("❌ Error loading model:", e)
    model = None
    label_encoder = None


# Pending
# Assigned
# On process
# Completed

@app.route("/")
def home():
    return redirect(url_for('jobs_list'))


@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = generate_password_hash(data.get('password'))
    role = data.get('role')
    skills = data.get('skills')
    active_jobs = data.get('active_jobs')

    user = {
        'username': username,
        'email': email,
        'password': password,
        'role': role,
        'tech_available': True if role == 'Technician' else None
    }

    if role == 'Technician':
        if not isinstance(skills, list) or len(skills) == 0:
            return jsonify({'status': 'error', 'message': 'Add your skills'}), 400

        if active_jobs is None:
            return jsonify({'status': 'error', 'message': 'Technicians must include active_jobs'}), 400

        user['tech_available'] = True
        user['skills'] = skills
        user['active_jobs'] = active_jobs

    doc_ref = fb_db.collection('users').document()
    doc_ref.set(user)

    return jsonify({'status': 'User added successfully'}), 200


@app.route('/login', methods=['GET', 'POST'])
def login():
    # View handler for the web app's login page
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data

        user_ref = fb_db.collection('users').where('username', '==', username).limit(1)
        docs = user_ref.stream()
        user_data = next(docs, None)

        if not user_data:
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))

        user_dict = user_data.to_dict()

        if user_dict['role'] != "Admin":
            flash(
                "Only admins can use the online portal. Use the mobile Mix&Meet app for student or technician access.",
                "danger")
            return redirect(url_for('login'))

        if not check_password_hash(user_dict['password'], password):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))

        user = User(
            id=user_data.id,
            username=user_dict['username'],
            role=user_dict['role'],
        )
        login_user(user, remember=form.remember_me.data)

        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('jobs_list')
        return redirect(next_page)

    return render_template('generic_form.html', title='Login', form=form)


@app.route('/create_job', methods=['POST', 'GET'])
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
        'created_at': firestore.SERVER_TIMESTAMP
    })

    assign_technician(job_id)

    return jsonify({"message": "Job created", "job_id": job_id})


def assign_technician(job_id):
    print(f"🔧 Assigning technician for job_id: {job_id}")

    job_ref = fb_db.collection("jobs").document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists:
        print("❌ Job not found.")
        return

    job_data = job_doc.to_dict()
    category = job_data.get("job_category")

    if not category:
        print("⚠️ No job category provided.")
        return

    category_encoded = label_encoder.transform([category])[0]

    tech_docs = fb_db.collection("users").where("role", "==", "Technician").stream()

    best_score = -1
    best_tech = None
    fallback_options = []

    for tech_doc in tech_docs:
        tech_data = tech_doc.to_dict()
        tech_id = tech_doc.id
        skills = tech_data.get("skills", [])
        active_jobs = tech_data.get("active_jobs", 0)
        skill_match = 1 if category in skills else 0

        print(
            f"🔍 Checking tech {tech_data.get('username')} | Skills: {skills} | Active Jobs: {active_jobs} | Skill Match: {skill_match}")

        features = np.array([[category_encoded, skill_match, active_jobs]])
        assign_prob = model.predict_proba(features)[0][1]
        print(f"➡️ Predicted probability: {assign_prob:.2f}")

        fallback_options.append({
            "technician_id": tech_id,
            "username": tech_data.get("username"),
            "score": round(assign_prob, 2),
            "active_jobs": active_jobs,
            "skills": skills
        })

        if skill_match and active_jobs < 3 and assign_prob > best_score:
            best_score = assign_prob
            best_tech = tech_id

    # tech_docs = fb_db.collection("users") \
    #     .where("role", "==", "Technician") \
    #     .stream()
    #
    # best_score = -1
    # best_tech = None
    # fallback_options = []
    #
    # for tech_doc in tech_docs:
    #     tech_data = tech_doc.to_dict()
    #     tech_id = tech_doc.id
    #     skills = tech_data.get("skills", [])
    #     active_jobs = tech_data.get("active_jobs", 0)
    #     skill_match = 1 if category in skills else 0
    #
    #     features = np.array([[category_encoded, skill_match, active_jobs]])
    #     assign_prob = model.predict_proba(features)[0][1]
    #
    #     fallback_options.append({
    #         "technician_id": tech_id,
    #         "username": tech_data.get("username"),
    #         "score": round(assign_prob, 2),
    #         "active_jobs": active_jobs,
    #         "skills": skills
    #     })
    #
    #     if skill_match and active_jobs < 3 and assign_prob > best_score:
    #         best_score = assign_prob
    #         best_tech = tech_id

    if best_tech:
        print(f"✅ Assigned to technician: {best_tech}")
        job_ref.update({
            "assigned_to": best_tech,
            "status": "Assigned"
        })
        fb_db.collection("users").document(best_tech).update({
            "tech_available": False
        })
    else:
        fallback_options = sorted(fallback_options, key=lambda x: x["score"], reverse=True)[:3]
        print("⚠️ No technician assigned, saving fallback suggestions:")
        print(fallback_options)
        job_ref.update({
            "assignment_suggestions": fallback_options,
            "status": "Pending"
        })


# def assign_technician(job_id):
#     job_ref = fb_db.collection('jobs').document(job_id)
#     job = job_ref.get()
#     if not job.exists:
#         return
#
#     available_techs = fb_db.collection('users').where('role', '==', 'Technician').where('tech_available', '==',
#                                                                                         True).limit(
#         1).stream()
#
#     for tech in available_techs:
#         tech_id = tech.id
#         job_ref.update({
#             'assigned_to': tech_id,
#             'status': 'Assigned'
#         })
#
#         fb_db.collection('users').document(tech_id).update({
#             'tech_available': False
#         })
#         break


@app.route('/jobs_list')
@login_required
def jobs_list():
    last_job_id = request.args.get('last_job_id')

    jobs_ref = fb_db.collection('jobs').order_by('created_at', direction='DESCENDING')

    if last_job_id:
        last_doc = fb_db.collection('jobs').document(last_job_id).get()
        if last_doc.exists:
            jobs_ref = jobs_ref.start_after(last_doc)

    docs = list(jobs_ref.stream())

    active_jobs = fb_db.collection('jobs').where('status', 'in', ['Pending', 'Assigned']).stream()
    busy_tech_ids = {doc.to_dict().get('assigned_to') for doc in active_jobs}

    tech_docs = fb_db.collection('users').where('role', '==', 'Technician').stream()
    available_technicians_map = {}
    for tech in tech_docs:
        data = tech.to_dict()
        tech_id = tech.id
        is_busy = tech_id in busy_tech_ids
        status_label = "Busy" if is_busy else "Available"
        available_technicians_map[tech_id] = {
            'id': tech_id,
            'name': data.get('username', data.get('email')),
            'status_label': status_label
        }

    jobs = []
    for doc in docs:
        job = doc.to_dict()
        job_id = doc.id

        created_by_id = job.get('created_by')
        created_by_name = "N/A"
        if created_by_id:
            user_doc = fb_db.collection('users').document(created_by_id).get()
            if user_doc.exists:
                created_by_name = user_doc.to_dict().get('username')

        assigned_to_id = job.get('assigned_to')
        assigned_to = available_technicians_map.get(assigned_to_id) if assigned_to_id else None

        job_date = job.get('job_date') or 'N/A'

        # ✅ Check for AI suggestions
        suggestions = job.get('assignment_suggestions', [])

        # Optional: enhance suggestions with technician name
        enhanced_suggestions = []
        for s in suggestions:
            tech_id = s.get('technician_id')
            tech_name = available_technicians_map.get(tech_id, {}).get('name', "Unknown")
            enhanced_suggestions.append({
                'technician_id': tech_id,
                'technician_name': tech_name,
                'score': s.get('score'),
                'active_jobs': s.get('active_jobs'),
                'skills': s.get('skills')
            })

        jobs.append({
            'job_id': job_id,
            'title': job.get('title'),
            'description': job.get('description'),
            'created_by': created_by_name,
            'job_date': job_date,
            'status': job.get('status', 'N/A'),
            'assigned_to': assigned_to,
            'suggestions': enhanced_suggestions  # ✅ Add to context
        })

    # for doc in docs:
    #     job = doc.to_dict()
    #     job_id = doc.id
    #
    #     created_by_id = job.get('created_by')
    #     created_by_name = "N/A"
    #     if created_by_id:
    #         user_doc = fb_db.collection('users').document(created_by_id).get()
    #         if user_doc.exists:
    #             created_by_name = user_doc.to_dict().get('username')
    #
    #     assigned_to_id = job.get('assigned_to')
    #     assigned_to = available_technicians_map.get(assigned_to_id) if assigned_to_id else None
    #
    #     job_date = job.get('job_date') or 'N/A'
    #
    #     jobs.append({
    #         'job_id': job_id,
    #         'title': job.get('title'),
    #         'description': job.get('description'),
    #         'created_by': created_by_name,
    #         'job_date': job_date,
    #         'status': job.get('status', 'N/A'),
    #         'assigned_to': assigned_to
    #     })

    return render_template(
        'jobs_list.html',
        jobs=jobs,
        title="Jobs",
        available_technicians=list(available_technicians_map.values()),
    )


@app.route('/reassign-technician', methods=['POST'])
@login_required
def reassign_technician():
    if current_user.role != 'Admin':
        return "Forbidden", 403

    job_id = request.form.get('job_id')
    new_tech_id = request.form.get('assigned_to')

    if job_id and new_tech_id:
        fb_db.collection('jobs').document(job_id).update({
            'assigned_to': new_tech_id,
            'status': 'Assigned'
        })
        fb_db.collection('users').document(new_tech_id).update({
            'tech_available': False
        })
        flash('Technician reassigned successfully', 'success')

    return redirect(url_for('jobs_list'))


@app.route('/job/<job_id>')
@login_required
def job_details(job_id):
    job_doc = fb_db.collection('jobs').document(job_id).get()
    if not job_doc.exists:
        return render_template('errors/404.html'), 404

    job = job_doc.to_dict()
    job['job_id'] = job_id

    created_by = "N/A"
    if job.get('created_by'):
        user_doc = fb_db.collection('users').document(job['created_by']).get()
        if user_doc.exists:
            created_by = user_doc.to_dict().get('username')

    assigned_to = "Unassigned"
    if job.get('assigned_to'):
        tech_doc = fb_db.collection('users').document(job['assigned_to']).get()
        if tech_doc.exists:
            assigned_to = tech_doc.to_dict().get('username')

    return render_template(
        'job_details.html',
        title="Job Details",
        job=job,
        created_by=created_by,
        assigned_to=assigned_to
    )


@app.route('/jobs_list_client', methods=['GET'])
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
        job['assigned_to'] = assigned_to_user  # could be None

        jobs.append(job)

    return jsonify(jobs)


@app.route('/login_mobile', methods=['POST'])
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


@app.route('/logout')
def logout():
    # Endpoint for logging the current user out
    logout_user()
    return redirect(url_for('login'))


# Error handlers
# See: https://en.wikipedia.org/wiki/List_of_HTTP_status_codes

# Error handler for 403 Forbidden
@app.errorhandler(403)
def error_403(error):
    return render_template('errors/403.html', title='Error 403'), 403


# Handler for 404 Not Found
@app.errorhandler(404)
def error_404(error):
    return render_template('errors/404.html', title='Error 404'), 404


@app.errorhandler(413)
def error_413(error):
    return render_template('errors/413.html', title='Error 413'), 413


# 500 Internal Server Error
@app.errorhandler(500)
def error_500(error):
    return render_template('errors/500.html', title='Error 500'), 500
