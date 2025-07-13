from flask_login import UserMixin
from app import login, fb_db
from dataclasses import dataclass


@dataclass
class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

    def get_id(self):
        return str(self.id)


@login.user_loader
def load_user(user_id):
    user_doc = fb_db.collection('users').document(user_id).get()
    if user_doc.exists:
        data = user_doc.to_dict()
        return User(id=user_doc.id, username=data['username'], role=data['role'])
    return None
