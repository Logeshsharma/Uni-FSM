import json
import os

from flask import Flask
from config import Config
from jinja2 import StrictUndefined
from flask_login import LoginManager
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


app = Flask(__name__)
app.jinja_env.undefined = StrictUndefined
app.config.from_object(Config)

login = LoginManager(app)
login.init_app(app)
login.login_view = 'login'

# Use a service account.
if os.environ.get('GOOGLE_CREDENTIALS'):
    firebase_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])
    cred = credentials.Certificate(firebase_dict)
else:
    cred = credentials.Certificate('uni-fsm-7b5e1-firebase-adminsdk-fbsvc-4bfb6e8a36.json')

firebase_app = firebase_admin.initialize_app(cred)

fb_db = firestore.client()

from app import views, models, jobs