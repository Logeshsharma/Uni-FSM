from typing import Optional
from datetime import datetime
import sqlalchemy as sa
import sqlalchemy.orm as so
from flask_login import UserMixin
from flask_sqlalchemy.model import Model
from pyexpat.errors import messages
from sqlalchemy import ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.testing.schema import mapped_column
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login
from dataclasses import dataclass


@dataclass
class User(UserMixin, db.Model):
    # Contains all users in the system.
    __tablename__ = 'users'

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    student_id: so.Mapped[Optional[int]] = so.mapped_column(unique=True, nullable=True)
    username: so.Mapped[str] = so.mapped_column(sa.String(64), index=True, unique=True)
    email: so.Mapped[str] = so.mapped_column(sa.String(120), index=True, unique=True)
    password_hash: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256))
    role: so.Mapped[str] = so.mapped_column(sa.String(10))
    registered: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)

    group_id: so.Mapped[Optional[int]] = mapped_column(ForeignKey('groups.id'), index=True)
    group: so.Mapped['Group'] = relationship(back_populates='users')

    my_message: so.Mapped[list['Message']] = relationship(back_populates='user')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'group_id': self.group_id
        }

    def __repr__(self):
        pwh = 'None' if not self.password_hash else f'...{self.password_hash[-5:]}'
        return f'User(id={self.id}, username={self.username}, email={self.email}, role={self.role}, pwh={pwh})'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


@dataclass
class Group(db.Model):
    # Contains all groups in the system. Each group has 5 member as a list (4 mentors and 1 student)
    __tablename__ = 'groups'

    id: so.Mapped[int] = so.mapped_column(primary_key=True)

    users: so.Mapped[list['User']] = relationship(back_populates='group', cascade='all, delete-orphan')

    taskstatus: so.Mapped[list['GroupTaskStatus']] = relationship(back_populates='group', cascade='all, delete-orphan')

    message: so.Mapped[list['Message']] = relationship(back_populates='group', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'users': [user.to_dict() for user in self.users],
            'taskstatus': [status.to_dict() for status in self.taskstatus]
        }

    def messages_to_dict(self):
        return  {
            'messages': []
        }


@dataclass
class Task(db.Model):
    # Contains all UNIQUE tasks added to the system.
    __tablename__ = 'tasks'

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    title: so.Mapped[str] = so.mapped_column(sa.String(64))
    description: so.Mapped[str] = so.mapped_column(sa.String(1024))
    isUpload: so.Mapped[bool] = so.mapped_column(default=False)
    start_datetime: so.Mapped[datetime] = so.mapped_column(sa.DateTime())
    end_datetime: so.Mapped[datetime] = so.mapped_column(sa.DateTime())
    location: so.Mapped[str] = so.mapped_column(sa.String(128))

    groupstatus: so.Mapped[list['GroupTaskStatus']] = relationship(back_populates='task', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'isUpload': self.isUpload,
            'groupstatus': [status.to_dict() for status in self.groupstatus],
            'start_datetime': self.start_datetime,
            'end_datetime': self.end_datetime,
            'location': self.location
        }


@dataclass
class GroupTaskStatus(db.Model):
    # Tracks a particular group's progress regarding each unique tasks through a combination of group_id and task_id used as foreign ids and primary keys simultaneously.
    __tablename__ = 'groupTaskStatuses'

    status: so.Mapped[str] = so.mapped_column(sa.String(32), default="Inactive")

    group_id: so.Mapped[int] = so.mapped_column(ForeignKey('groups.id'), primary_key=True)
    group: so.Mapped['Group'] = relationship(back_populates='taskstatus')

    task_id: so.Mapped[int] = so.mapped_column(ForeignKey('tasks.id'), primary_key=True)
    task: so.Mapped['Task'] = relationship(back_populates='groupstatus')

    def to_dict(self):
        return {
            'group_id': self.group_id,
            'task_id': self.task_id,
            'status': self.status,
            'task': self.task.to_dict() if self.task else None
        }

@dataclass
class Message(db.Model):
    # Contains every group's messages and their details. Not used in the app as the messaging functionality was not fully implemented.
    __tablename__ = 'messages'

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    sent_time: so.Mapped[datetime] = so.mapped_column(sa.DateTime(), index=True)
    content: so.Mapped[str] = so.mapped_column(sa.String(1024))

    group_id: so.Mapped[int] = so.mapped_column(ForeignKey('groups.id'), index=True)
    group: so.Mapped['Group'] = relationship(back_populates='message')

    user_id: so.Mapped[int] = so.mapped_column(ForeignKey('users.id'))
    user: so.Mapped['User'] = relationship(back_populates='my_message')

    def to_dict(self):
        return {
            'id': self.id,
            'sent_time': self.sent_time,
            'content': self.content,
            'group_id': self.group_id,
            'user_id': self.user_id,
            'username': self.user.username
        }