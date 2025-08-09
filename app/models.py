from . import db
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import Session

class User(db.Model):
    __tablename__ = 'otteruser'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email
        }

class Chat(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('otteruser.id'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=True)
    messages = db.relationship('Messages', backref='convo_obj', cascade='all, delete-orphan')
    time = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "user_id": self.user_id,
            "folder_id": self.folder_id,
            "time": self.time.isoformat()
        }

class Messages(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    convo = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    time = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "convo": self.convo,
            "time": self.time.isoformat()
        }

class Audios(db.Model):
    __tablename__ = 'audios'
    id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String(255), nullable=False)
    chat = db.Column(db.Integer, db.ForeignKey("conversations.id"))
    prompt = db.Column(db.Integer, db.ForeignKey("messages.id"))
    chat_rel = db.relationship("Chat", backref="audios")
    prompt_rel = db.relationship("Messages", backref="audios")

class Folder(db.Model):
    __tablename__ = 'folder'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('otteruser.id', ondelete='CASCADE'), nullable=False)

def delete_audio_files_for_prompt(prompt_id: int, audio_dir="MusicDownloadFiles"):
    deleted = 0
    for filename in os.listdir(audio_dir):
        if filename.endswith(f"_{prompt_id}.wav"):
            file_path = os.path.join(audio_dir, filename)
            os.remove(file_path)
            print(f"Deleted audio file: {file_path}")
            deleted += 1
    if deleted == 0:
        print(f"No audio files found for prompt {prompt_id}")
    return deleted

def delete_prompt_from_db(db: Session, prompt_id: int):
    prompt = db.query(Messages).filter(Messages.id == prompt_id).first()
    if prompt:
        db.delete(prompt)
        db.commit()
        print(f"Deleted prompt {prompt_id} from database")
        return True
    else:
        print(f"Prompt {prompt_id} not found in database")
        return False

def delete_prompt_and_audio(db: Session, prompt_id: int):
    if delete_prompt_from_db(db, prompt_id):
        delete_audio_files_for_prompt(prompt_id)