import werkzeug
werkzeug.__version__ = "2.3.8"

import unittest

from werkzeug.security import generate_password_hash

from app import app, db

class RegistrationTestCase(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:test_memory:'
        self.client = app.test_client()

        with app.app_context():
            db.create_all()
            db.session.commit()

    def tearDown(self):
        with app.app_context():
            db.drop_all()

    def test_registration_success(self):
        response = self.client.post('/registration', data={
            'student_id': '12345',
            'email': 'amywong@student.bham.ac.uk',
            'password': generate_password_hash('Amywong1234!'),
            'confirm': generate_password_hash('Amywong1234!')
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

    def test_registration_failure_missing_fields(self):
        response = self.client.post('/registration', data={
            'student_id': '12345',
            'email': '',
            'password': generate_password_hash('Amywong1234!'),
            'confirm': generate_password_hash('Amywong1234!'),
        }, follow_redirects=True)

        self.assertIn('This field is required.', response.data.decode())
        self.assertIn('email', response.data.decode())


    def test_registration_failure_invalid_credentials(self):
        # Try to register with incorrect credentials - student_id or email is wrong
        response = self.client.post('/registration', data={
            'student_id': '99999',  # Invalid student_id - doesn't exist in the database
            'email': 'wrongemail@example.com',  # Invalid email - doesn't match any user
            'password': 'testpass',
            'confirm': 'testpass'
        }, follow_redirects=True)

        # Check that the form validation error for email is shown
        self.assertIn(b'Email must be the student university email ending with', response.data)

        # Check the student ID is invalid
        self.assertIn(b'Student ID must be between 7 and 8 digits', response.data)

        self.assertEqual(response.status_code, 200)
