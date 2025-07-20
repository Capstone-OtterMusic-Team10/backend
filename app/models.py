from . import db
from datetime import datetime

# user class representing the table in db
class User(db.Model):
    __tablename__ = 'otteruser'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=True)  # Changed to nullable for OAuth users

# conversation - will be the table containing individual conversation (as we might have many tracks per one)
class Chat(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('otteruser.id'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=True)
    messages = db.relationship('Messages', backref='convo_obj', cascade='all, delete-orphan')
    time = db.Column(db.DateTime, default=datetime.now())
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "user_id": self.user_id,
            "folder_id": self.folder_id
        }
# chat table will contian individual messages and the track id that was generated as part of that message
class Messages(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    convo = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    time = db.Column(db.DateTime, default=datetime.now())
    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "convo": self.convo
        }

class Audios(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    link = db.Column(db.String(255), nullable = False)
    chat = db.Column(db.Integer, db.ForeignKey("conversations.id"))
    prompt = db.Column(db.Integer, db.ForeignKey("messages.id"))

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('otteruser.id', ondelete='CASCADE'), nullable=False)