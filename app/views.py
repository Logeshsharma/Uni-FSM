from flask import render_template, redirect, url_for, flash, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms.validators import email

from app import app
from app.models import User, Group, GroupTaskStatus, Task, Message
from app.forms import LoginForm, RegisterForm, TaskForm, ChooseForm
from flask_login import current_user, login_user, logout_user, login_required
import sqlalchemy as sa
from app import db
from urllib.parse import urlsplit
import random
from app import fb_db


@app.route("/")
def home():
    return render_template('home.html', title="")



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

        print('user_data ', user_data)

        if not user_data:
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))

        user_dict = user_data.to_dict()

        if user_dict['role'] != "Admin":
            flash(
                "Only admins can use the online portal. Use the mobile Mix&Meet app for student or technician access.",
                "danger")
            return redirect(url_for('login'))

        print("check_password_hash(user_dict['password'], password) ",
              check_password_hash(user_dict['password'], password))

        if not check_password_hash(user_dict['password'], password):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))

        user = User(
            id=user_data.id,
            username=user_dict['username'],
            role=user_dict['role']
        )
        login_user(user, remember=form.remember_me.data)

        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('home')
        return redirect(next_page)

    return render_template('generic_form.html', title='Login', form=form)


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
        "id": user_doc.id,
        "username": user['username'],
        "email": user['email'],
        "role": user['role']
    }), 200


@app.route('/get_group_mobile/<int:group_id>')
def get_group_mobile(group_id):
    # API for retrieving a group's information and users by the mobile app.
    try:
        group = db.session.get(Group, group_id)
        group_response = {
            'group_id': group.id,
            'users': [user.to_dict() for user in group.users]
        }
        if group is None:
            return jsonify({'id': -1}), 200
    except Exception:
        return jsonify({'id': -1}), 200

    return jsonify(group_response), 200


@app.route('/get_tasks_mobile/<int:group_id>')
def get_tasks_mobile(group_id):
    # API for retrieving a group's list of associated tasks, their details and completion status.
    try:
        q = db.select(Group).where(Group.id == group_id)
        group = db.session.scalar(q)
        if not group:
            return jsonify({'message': 'No Group'}), 404
        group_response = {
            'group_id': group.id,
            'tasks': []
        }
        for task_status in group.taskstatus:
            task = {
                'id': task_status.task.id,
                'title': task_status.task.title,
                'desc': task_status.task.description,
                'isUpload': task_status.task.isUpload,
                'status': task_status.status,
                'start_datetime': task_status.task.start_datetime,
                'end_datetime': task_status.task.end_datetime,
                'location': task_status.task.location
            }
            group_response['tasks'].append(task)
    except Exception:
        return jsonify({'tasks': []}), 200

    return jsonify(group_response), 200


@app.route('/get_group_messages/<int:group_id>/<int:number_of_messages>')
def get_group_messages(group_id, number_of_messages):
    # API for retrieving an x groups's y last messages. Not used anywhere in the mobile app as we didn't have enough time to implement, but still here just in case.
    try:
        messages = db.session.scalars(db.select(Message)
                                      .where(Message.group_id == group_id)
                                      .order_by(Message.sent_time.desc())
                                      .limit(number_of_messages)).all()
        messages_dict = {
            'messages': [message.to_dict() for message in messages[::-1]]
        }
    except Exception:
        return jsonify({'message_id': -1}), 200
    return jsonify(messages_dict)


@app.route('/create_task', methods=['GET', 'POST'])
@login_required
def create_task():
    # View handler containing a form and logic that can be filled out to create a new task for all groups.
    if current_user.role != "Admin":
        flash("Only admin users are allowed on that page", "danger")
        return redirect(url_for("home"))
    form = TaskForm()
    if form.validate_on_submit():
        task = Task(title=form.title.data, description=form.description.data, isUpload=form.isUpload.data,
                    start_datetime=form.start_datetime.data, end_datetime=form.end_datetime.data,
                    location=form.location.data)
        db.session.add(task)
        db.session.flush()
        all_group_ids = db.session.scalars(db.select(Group.id)).all()
        for group_id in all_group_ids:
            db.session.add(GroupTaskStatus(task_id=task.id, group_id=group_id))
        db.session.commit()
        flash("Task created successfully", 'success')
        return redirect(url_for('create_task'))
    return render_template('create_task.html', title="", form=form)


@app.route('/update_task_status', methods=['GET', 'POST'])
def update_task_status():
    # API for mobile app that can be used to update a particular group's particular task's status in the database.
    try:
        if request.method == 'POST':
            group_id = request.json.get('group_id')
            task_id = request.json.get('task_id')
            status = request.json.get('status')
            task_status = db.session.get(GroupTaskStatus, (group_id, task_id))
            task_status.status = status
            db.session.commit()
    except Exception:
        return jsonify({'status': 'failed'}), 404

    return jsonify({'status': 'Updated'}), 200


@app.route("/tasks", methods=["GET"])
@login_required
def view_tasks():
    # View handler for displaying a table with all unique tasks in the web app's database.
    try:
        tasks = db.session.scalars(db.select(Task)).all()
        return render_template("view_tasks.html", tasks=tasks, title="")
    except Exception as e:
        app.logger.error(f"Error in view_tasks: {str(e)}")
        return render_template("errors/500.html", title="Error"), 500


@app.route("/task/<int:task_id>", methods=["GET"])
@login_required
def task_details(task_id):
    try:
        task = db.session.get(Task, task_id)

        if task is None:
            flash("Task not found", "danger")
            return redirect(url_for("view_tasks"))

        task_statuses = db.session.scalars(db.select(GroupTaskStatus).where(GroupTaskStatus.task_id == task_id)).all()

        return render_template("task_details.html", task=task, task_statuses=task_statuses, title="")

    except Exception as e:
        app.logger.error(f"Error in task_details: {str(e)}")
        return render_template("errors/500.html", title="Error"), 500


@app.route('/admin_account', methods=['GET', 'POST'])
@login_required
def admin_account():
    # View handler for displaying the logged in admin's details as well as a complete list of the system's users and their details.
    # Additionally, the "Group Generation" button is rendered, allowing to redirect to /group_generation and perform group formation.
    form = ChooseForm
    if current_user.is_authenticated and current_user.role == 'Admin':
        q = sa.select(User)
        all_users = db.session.scalars(q).all()
        regist_status = {0: 'Not Registered', 1: 'Registered'}
        return render_template('admin_account.html', title='', all_users=all_users, regist_status=regist_status,
                               form=form)
    else:
        flash(f'Web portal features are accessible by admins only. Access denied', 'danger')
    return redirect(url_for('home'))


@app.route('/group_generation', methods=['GET', 'POST'])
@login_required
def group_generation():
    # Endpoint containing logic for generating as many groups of 4students+1mentor in the database as possible.
    # If the database already has existing groups, does not change them, but form groups from other/new users if possible.
    # Creates individual status tracking for every newly created group by adding a unique combination of task_id and group_id + task_status in the database's 'groupTaskStatuses' table.
    eligible_users = User.query.filter(User.registered == 1, User.role != 'Admin', User.group_id == None).all()
    students = [user for user in eligible_users if user.role == 'Student']
    mentors = [user for user in eligible_users if user.role == 'Mentor']
    if len(mentors) < 1 and len(students) < 4:
        flash('Not enough students and mentors to form new groups.', 'danger')
        return redirect(url_for('admin_account'))
    elif len(mentors) < 1:
        flash(f'Not enough mentors to form new groups.', 'danger')
        return redirect(url_for('admin_account'))
    elif len(students) < 4:
        flash(f'Not enough students to form new groups.', 'danger')
        return redirect(url_for('admin_account'))
    num_groups = min(len(students) // 4, len(mentors))
    random.shuffle(students)
    random.shuffle(mentors)
    selected_mentor = random.sample(mentors, num_groups)
    for i in range(num_groups):
        selected_students = random.sample(students, 4)
        group = Group()
        mentor = random.choice(selected_mentor)
        group.users.clear()
        group.users.append(mentor)
        group.users.extend(selected_students)
        db.session.add(group)
        db.session.commit()
        selected_mentor.remove(mentor)
        for student in selected_students:
            students.remove(student)
        tasks = db.session.scalars(db.select(Task))
        for task in tasks:
            db.session.add(GroupTaskStatus(status="Inactive", group_id=group.id, task_id=task.id))
        db.session.commit()

    flash(f'{num_groups} Group(s) Successfully Generated. {len(students)} unassigned student(s) remaining.', 'success')
    return redirect(url_for('groups'))


@app.route('/groups', methods=['GET'])
@login_required
def groups():
    # View handler for displaying a table with all groups and their members in the system.
    q = sa.select(Group)
    all_groups = db.session.scalars(q).all()
    for group in all_groups:
        group.users.sort(key=lambda user: 0 if user.role == 'Mentor' else 1)
    return render_template('groups.html', title='', all_groups=all_groups)


@app.route('/logout')
def logout():
    # Endpoint for logging the current user out
    logout_user()
    return redirect(url_for('home'))


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
