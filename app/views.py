import uuid

from flask import render_template, redirect, url_for, flash, request, jsonify
from google.cloud import firestore
from werkzeug.security import generate_password_hash, check_password_hash

from app import app
from app.models import User, Group, GroupTaskStatus, Task, Message
from app.forms import LoginForm, RegisterForm, TaskForm, ChooseForm
from flask_login import current_user, login_user, logout_user, login_required
from urllib.parse import urlsplit
from app import fb_db


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

    doc_ref = fb_db.collection('users').document()
    doc_ref.set({
        'username': username,
        'email': email,
        'password': password,
        'role': role,
        'tech_available': True if role == 'Technician' else None
    })

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
        'status': 'pending',
        'job_category': job_category,
        'job_date': job_date,
        'job_time': job_time,
        'address': address,
        'created_at': firestore.SERVER_TIMESTAMP
    })

    assign_technician(job_id)

    return jsonify({"message": "Job created", "job_id": job_id})


def assign_technician(job_id):
    job_ref = fb_db.collection('jobs').document(job_id)
    job = job_ref.get()
    if not job.exists:
        return

    available_techs = fb_db.collection('users').where('role', '==', 'Technician').where('tech_available', '==',
                                                                                        True).limit(
        1).stream()

    for tech in available_techs:
        tech_id = tech.id
        job_ref.update({
            'assigned_to': tech_id,
            'status': 'assigned'
        })

        fb_db.collection('users').document(tech_id).update({
            'tech_available': False
        })
        break

@login_required
@app.route('/jobs_list')
def jobs_list():
    jobs_ref = fb_db.collection('jobs')
    docs = jobs_ref.stream()

    jobs = [['Job Id', 'Title', 'Description', 'Created By', 'Job date','status','Assigned']]
    for doc in docs:
        job = doc.to_dict()
        job['job_id'] = doc.id

        # if 'created_at' in job and job['created_at']:
        #     job['created_at'] = job['created_at'].to_datetime().strftime("%Y-%m-%d %H:%M:%S")
        # if 'job_date' in job and job['job_date']:
        #     job['job_date'] = job['job_date'].to_datetime().strftime("%Y-%m-%d %H:%M:%S")

        jobs.append(job)

    return render_template('jobs_list.html', jobs=jobs, title="Jobs")


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
