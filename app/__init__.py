import json
import os

from flask import Flask
from config import Config
from jinja2 import StrictUndefined
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import sqlalchemy as sa
import sqlalchemy.orm as so
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


app = Flask(__name__)
app.jinja_env.undefined = StrictUndefined
app.config.from_object(Config)
db = SQLAlchemy(app)

login = LoginManager(app)
login.login_view = 'login'

# Use a service account.
if os.environ.get('FLASK_ENV') == 'production':
    firebase_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])
    cred = credentials.Certificate(firebase_dict)
else:
    cred = credentials.Certificate('uni-fsm-7b5e1-firebase-adminsdk-fbsvc-7d190e7da4.json')

firebase_app = firebase_admin.initialize_app(cred)

fb_db = firestore.client()

from app import views, models
from app.debug_utils import reset_db

@app.shell_context_processor
def make_shell_context():
    return dict(db=db, sa=sa, so=so, reset_db=reset_db)
