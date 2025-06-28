from flask import Blueprint, jsonify, request, make_response, send_file
from ..models import Chat, Messages
from .. import db

routes_bp = Blueprint('routes', __name__)

def commit(new_obj, action = "add"):   
    if action == "add":
        db.session.add(new_obj)
        db.session.commit()
    elif action == "delete":
        db.session.delete(new_obj)
        db.session.commit()


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
@routes_bp.route('/talk/', methods=['POST'])
def post_chats():
    file_path = '../static/testtest.mp3'
    data = request.get_json()
    
    if not data or 'content' not in data:
        return jsonify({"error": "Missing message content"})
    if 'chat' not in data:
        number_of_chats = Chat.query.count()
        new_convo = Chat(title=f"Chat {number_of_chats}", user_id = 1)
        commit(new_convo)
        # Here we would have a process that gives us music
        new_exchange = Messages(role="user", content=data["content"], convo=new_convo.id)
        
        commit(new_exchange)
        return make_response(jsonify({"new_convo": new_convo.id}), 200)
    # Here we would have a process that gives us music
    else:
        new_exchange = Messages(role="user", content=data["content"], convo=data["chat"])
        commit(new_exchange)
        return make_response(jsonify({"message": "New message created"}), 200)
    
@routes_bp.route('/get-audio')
def get_audio():
    file_path = '../static/testtest.mp3'
    return send_file(file_path)

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