from flask import Blueprint, jsonify, request, make_response, send_file
from ..models import Chat, Messages, Audios
from .. import db
from app.chats.lyria_demo_test2 import generate_audio
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

# chat functionality
@routes_bp.route('/chat')
def get_chats():
    
    try:
        chats = Chat.query.all()
        if chats:
            chat_list = [chat.to_dict() for chat in chats]
            return make_response(jsonify(chat_list), 200)
        
        else:
            return make_response(jsonify({'message': "No chats yet"}), 200)
    except Exception as e:
        return make_response(jsonify({"error": str(e)}), 404)

@routes_bp.route('/chat/<int:id>', methods=["DELETE"])
def delete_chat(id):
    try:
        chat = Chat.query.get(id)
        
        if not chat:
            return make_response(jsonify({"message": "Chat is not found"}), 404)
        messages = chat.messages

        commit(chat, "delete")
        return '', 204
    except Exception as e:
        return make_response(jsonify({"message": str(e)}), 500)

@routes_bp.route('/chat/<int:id>', methods=["PUT"])
def update_chat_name(id):
    try:
        data = request.get_json()
        chat = Chat.query.get(id)
        if 'title' in data:
            chat.title = data['title']
            db.session.commit()
            
            return make_response(jsonify({"message": "Update successful"}, 200))
        return make_response(jsonify({'message': "No new name identified"}), 400)
    except Exception as e:
        return make_response(jsonify({"message": str(e)}), 500)


# since the new chat will start with the first message sent, then adding a message should be able to add a convo object to db
@routes_bp.route('/talk', methods=['POST'])
def post_chats():
    data = request.get_json()
    if not data or 'prompt' not in data:
        return jsonify({"error": "Missing message content"})
    if 'chat' not in data:
        number_of_chats = Chat.query.count()
        new_chat = Chat(title=f"Chat {number_of_chats}", user_id = 1)
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
def get_audio(chat_id, message_id):
    file_path = f'{music_folder}/lyria_{chat_id}_{message_id}.wav'
    try:
        return send_file(file_path, mimetype='audio/wav')
    except FileNotFoundError:
        return make_response(jsonify({'message': 'No audio available'}), 404)
   

# getting all audios (will need to be refactred by user-basis once auth is implemented)
@routes_bp.route('/all-audios/<int:user_id>')
def get_audios(user_id):
    my_chats = Chat.query.get()
@routes_bp.route('/getmessages/<int:id>')
def get_messages(id):
    try:
        convo = Chat.query.get(id)
        messages = convo.messages
        if messages:
            message_list = [msg.to_dict() for msg in messages]
        return make_response(jsonify(message_list), 200)
    except Exception as e:
        return make_response(jsonify({"message": str(e)}), 500)