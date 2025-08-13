from urllib.parse import urlsplit

from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.security import check_password_hash

from app import app
from app import fb_db
from app.forms import LoginForm
from app.models import User


@app.route("/")
def home():
    return redirect(url_for('jobs_list'))


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

        suggestions = job.get('assignment_suggestions', [])

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
            'job_category': job.get('job_category'),
            'description': job.get('description'),
            'created_by': created_by_name,
            'job_date': job_date,
            'status': job.get('status', 'N/A'),
            'assigned_to': assigned_to,
            'suggestions': enhanced_suggestions
        })

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

    job['before_image_uploaded'] = job.get('before_image_uploaded', False)
    job['after_image_uploaded'] = job.get('after_image_uploaded', False)
    job['before_images'] = job.get('images', {}).get('before', [])
    job['after_images'] = job.get('images', {}).get('after', [])

    created_by = "N/A"
    if job.get('created_by'):
        user_doc = fb_db.collection('users').document(job['created_by']).get()
        if user_doc.exists:
            created_by = user_doc.to_dict().get('username')

    # Get assigned technician username
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


@app.route('/logout')
def logout():
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
