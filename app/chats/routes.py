from flask import Blueprint, jsonify, request, make_response, redirect, url_for, session
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from ..models import Chat, Messages, Audios, User
from .. import db, oauth
from .lyria_demo_test2 import generate_audio
import os
import time
import asyncio
import os
from pathlib import Path
from threading import Thread

routes_bp = Blueprint('routes', __name__)

music_folder = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', '..', 'MusicDownloadFiles'))

def commit(new_obj, action = "add"):
    if action == "add":
        db.session.add(new_obj)
        db.session.commit()
    elif action == "delete":
        db.session.delete(new_obj)
        db.session.commit()


def create_a_message_and_send_prompt(prompt, chat_id, data, prompt_id):
    asyncio.run(generate_audio(data["bpm"], data["key"], prompt, chat_id, prompt_id))
    new_audio = Audios(link=f"lyria_{chat_id}_{prompt_id}", chat=chat_id, prompt=prompt_id)
    commit(new_audio)

# Local login
@routes_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    user = User.query.filter_by(email=email).first()
    if user and user.password == password:  # Plaintext for demo; use hashing in production
        access_token = create_access_token(identity=user.id)
        return jsonify(token=access_token), 200
    return jsonify({'error': 'Invalid credentials'}), 401

# Local signup
@routes_bp.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400
    user = User(username=username, email=email, password=password)  # Plaintext for demo
    db.session.add(user)
    db.session.commit()
    access_token = create_access_token(identity=user.id)
    return jsonify(token=access_token), 200

# Google OAuth login
@routes_bp.route('/auth/google')
def auth_google():
    nonce = os.urandom(16).hex()
    session['nonce'] = nonce
    return oauth.google.authorize_redirect(redirect_uri=url_for('routes.auth_google_callback', _external=True), nonce=nonce)

@routes_bp.route('/auth/google/callback')
def auth_google_callback():
    token = oauth.google.authorize_access_token()
    userinfo = oauth.google.parse_id_token(token, nonce=session.get('nonce'))
    email = userinfo['email']
    name = userinfo.get('name', email.split('@')[0])
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(username=name, email=email, password=None)
        db.session.add(user)
        db.session.commit()
    access_token = create_access_token(identity=user.id)
    if 'nonce' in session:
        del session['nonce']
    return redirect(f"http://localhost:5173/?token={access_token}")  # Changed to root /?token=...

# GitHub OAuth login (setup placeholder)
@routes_bp.route('/auth/github')
def auth_github():
    return oauth.github.authorize_redirect(redirect_uri=url_for('routes.auth_github_callback', _external=True))

@routes_bp.route('/auth/github/callback')
def auth_github_callback():
    token = oauth.github.authorize_access_token()
    user_info = oauth.github.get('user').json()
    email = user_info.get('email') or f"{user_info['login']}@github.com"
    username = user_info['login']
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(username=username, email=email, password=None)
        db.session.add(user)
        db.session.commit()
    access_token = create_access_token(identity=user.id)
    return redirect(f"http://localhost:5173/?token={access_token}")  # Changed to root /?token=...

# User info endpoint
@routes_bp.route('/auth/me', methods=['GET'])
@jwt_required(optional=True)
def get_me():
    user_id = get_jwt_identity()
    if user_id:
        user = User.query.get(user_id)
        if user:
            return jsonify({'id': user.id, 'username': user.username, 'email': user.email}), 200
    return jsonify({'id': None}), 200

# chat functionality
@routes_bp.route('/chat')
@jwt_required()
def get_chats():
    user_id = get_jwt_identity()
    try:
        chats = Chat.query.filter_by(user_id=user_id).all()
        if chats:
            chat_list = [chat.to_dict() for chat in chats]
            return make_response(jsonify(chat_list), 200)

        else:
            return make_response(jsonify({'message': "No chats yet"}), 200)
    except Exception as e:
        return make_response(jsonify({"error": str(e)}), 404)

@routes_bp.route('/chat/<int:id>', methods=["DELETE"])
@jwt_required()
def delete_chat(id):
    user_id = get_jwt_identity()
    try:
        chat = Chat.query.get(id)
        if not chat or chat.user_id != user_id:
            return make_response(jsonify({"message": "Chat not found or unauthorized"}), 404)
        messages = chat.messages

        commit(chat, "delete")
        return '', 204
    except Exception as e:
        return make_response(jsonify({"message": str(e)}), 500)

@routes_bp.route('/chat/<int:id>', methods=["PUT"])
@jwt_required()
def update_chat_name(id):
    user_id = get_jwt_identity()
    try:
        data = request.get_json()
        chat = Chat.query.get(id)
        if not chat or chat.user_id != user_id:
            return make_response(jsonify({"message": "Chat not found or unauthorized"}), 404)
        if 'title' in data:
            chat.title = data['title']
            db.session.commit()

            return make_response(jsonify({"message": "Update successful"}), 200)
        return make_response(jsonify({'message': "No new name identified"}), 400)
    except Exception as e:
        return make_response(jsonify({"message": str(e)}), 500)


# since the new chat will start with the first message sent, then adding a message should be able to add a convo object to db
@routes_bp.route('/talk', methods=['POST'])
@jwt_required()
def post_chats():
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data or 'prompt' not in data:
        return jsonify({"error": "Missing message content"})
    if 'chat' not in data:
        number_of_chats = Chat.query.filter_by(user_id=user_id).count()
        new_chat = Chat(title=f"Chat {number_of_chats}", user_id=user_id)
        commit(new_chat)
        # Here we would have a process that gives us music
        new_exchange = Messages(role="user", content=data["prompt"], convo=new_chat.id)

        commit(new_exchange)


        Thread(target=create_a_message_and_send_prompt, args=(new_exchange.content, new_chat.id, data, new_exchange.id)
               ).start()
        return make_response(jsonify({"new_chat": new_chat.id, "new_message": new_exchange.id}), 200)
    # Here we would have a process that gives us music
    else:
        new_exchange = Messages(role="user", content=data["prompt"], convo=data["chat"])
        commit(new_exchange)

        Thread(target=create_a_message_and_send_prompt, args=(new_exchange.content, data["chat"], data, new_exchange.id)).start()
        return make_response(jsonify({"message": new_exchange.id}), 200)

@routes_bp.route('/get-audio/<int:chat_id>/<int:message_id>')
@jwt_required()
def get_audio(chat_id, message_id):
    user_id = get_jwt_identity()
    chat = Chat.query.get(chat_id)
    if not chat or chat.user_id != user_id:
        return make_response(jsonify({'error': 'Unauthorized'}), 403)
    file_path = f'{music_folder}/lyria_{chat_id}_{message_id}.wav'
    try:
        return send_file(file_path, mimetype='audio/wav')
    except FileNotFoundError:
        return make_response(jsonify({'message': 'No audio available'}), 404)


# getting all audios (will need to be refactred by user-basis once auth is implemented)
@routes_bp.route('/all-audios/<int:user_id>')
@jwt_required()
def get_audios(user_id):
    current_id = get_jwt_identity()
    if current_id != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    my_chats = Chat.query.get()
@routes_bp.route('/getmessages/<int:id>')
@jwt_required()
def get_messages(id):
    user_id = get_jwt_identity()
    try:
        convo = Chat.query.get(id)
        if not convo or convo.user_id != user_id:
            return make_response(jsonify({'error': 'Unauthorized'}), 403)
        messages = convo.messages
        if messages:
            message_list = [msg.to_dict() for msg in messages]
        return make_response(jsonify(message_list), 200)
    except Exception as e:
        return make_response(jsonify({"message": str(e)}), 500)