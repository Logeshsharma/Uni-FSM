from flask import request, jsonify
from werkzeug.security import generate_password_hash

from app import app
from app import fb_db


@app.route('/mapi/add_user', methods=['GET', 'POST'])
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


@app.route('/mapi/update_password', methods=['POST'])
def update_password():
    data = request.get_json()

    user_id = data.get('user_id')
    new_password = data.get('new_password')

    if not user_id or not new_password:
        return jsonify({'error': 'user_id and new_password are required'}), 400

    try:
        user_ref = fb_db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({'error': 'User not found'}), 404

        hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')
        user_ref.update({'password': hashed_password})

        return jsonify({'message': 'Password updated successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
