from flask import Blueprint, jsonify, request, make_response
from .models import Convos, Chat
from . import db

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
        chats = Convos.query.all()
        if chats:
            chat_list = [chat.to_dict() for chat in chats]
            return make_response(jsonify(chat_list), 200)
        else:
            return make_response(jsonify({'message': "No chats yet"}), 204)
    except Exception as e:
        return make_response(jsonify({"error": str(e)}), 404)

@routes_bp.route('/chat/<int:id>', methods=["DELETE"])
def delete_chat(id):
    try:
        chat = Convos.query.get(id)
        if not chat:
            return make_response(jsonify({"message": "Chat is not found"}), 404)
        commit(chat, "delete")
        return '', 204
    except Exception as e:
        return make_response(jsonify({"message": str(e)}), 500)

@routes_bp.route('/talk', methods=['POST'])
def post_chats():
    data = request.get_json()

    if not data or 'content' not in data:
        return jsonify({"error": "Missing message content"})
    if 'chat' not in data:
        number_convos = Convos.query.count()
        new_convo = Convos(title=f"Chat {number_convos}", user_id = 1)
        commit(new_convo)
        # Here we would have a process that gives us music
        new_exchange = Chat(role="user", content=data["content"], convo=new_convo.id)
        commit(new_exchange)
        return make_response(jsonify({"new_convo": new_convo.id}), 200)
    # Here we would have a process that gives us music
    else:
        new_exchange = Chat(role="user", content=data["content"], convo=data["chat"])
        commit(new_exchange)
        return make_response(jsonify({"message": "New message created"}), 200)
