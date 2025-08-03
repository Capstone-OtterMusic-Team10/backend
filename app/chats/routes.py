from flask import Blueprint, jsonify, request, make_response, send_file, current_app, redirect, url_for, session
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from ..models import Chat, Messages, Audios, User, delete_prompt_and_audio, delete_audio_files_for_prompt
from .. import db, oauth
from .lyria_demo_test2 import generate_audio
import asyncio
import os
import subprocess
from pathlib import Path
from threading import Thread
from urllib.parse import unquote
import math
from dotenv import load_dotenv
import base64
import logging
load_dotenv()
usevenv = os.getenv("USEVENV")
# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
routes_bp = Blueprint('routes', __name__)
music_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'MusicDownloadFiles'))
"""
Instructions to set up the environment (macOS)
Create the environment for Demucs
conda create -n demucs-env python=3.10 -y
Activate it to install packages
conda activate demucs-env
Install Demucs and its dependencies into the new environment
conda install -c pytorch -c conda-forge demucs ffmpeg -y
Deactivate it when you're done
conda deactivate
"""
if usevenv == "true":
    CONDA_ENV_PATH = "/venv"
else:
    CONDA_ENV_PATH = "/opt/anaconda3/envs/demucs-env"
# Folder Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SEPARATED_DIR = os.path.join(BASE_DIR, "separated_music")
DEMUCS_MODEL_NAME = "htdemucs_ft" # The model used in separator.py
# Ensure the output directory exists at startup
os.makedirs(SEPARATED_DIR, exist_ok=True)
# Use the absolute path to MusicDownloadFiles
music_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'MusicDownloadFiles'))
def commit(new_obj, action="add"):
    if action == "add":
        db.session.add(new_obj)
        db.session.commit()
    elif action == "delete":
        db.session.delete(new_obj)
        db.session.commit()
def create_a_message_and_send_prompt(prompt, chat_id, data, prompt_id, app):
    logger.debug(f"Starting create_a_message_and_send_prompt for prompt: {prompt}, chat_id: {chat_id}, prompt_id: {prompt_id}, data: {data}")
    try:
        logger.debug("Calling asyncio.run(generate_audio)")
        asyncio.run(generate_audio(data["bpm"], data["key"], prompt, chat_id, prompt_id))
        logger.debug("generate_audio completed successfully")
    except Exception as e:
        logger.error(f"Error in create_a_message_and_send_prompt during audio generation: {str(e)}")
        raise
# Google OAuth login
@routes_bp.route('/auth/google')
def auth_google():
    nonce = os.urandom(16).hex()
    session['nonce'] = nonce
    return oauth.google.authorize_redirect(redirect_uri=url_for('routes.auth_google_callback', _external=True), nonce=nonce)
@routes_bp.route('/auth/google/callback')
def auth_google_callback():
    logger.debug("Processing Google OAuth callback")
    try:
        token = oauth.google.authorize_access_token()
        userinfo = oauth.google.parse_id_token(token, nonce=session.get('nonce'))
        email = userinfo['email']
        name = userinfo.get('name', email.split('@')[0])
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(username=name, email=email, password=None)
            db.session.add(user)
            db.session.commit()
            logger.info(f"Created new user: {email}")
        access_token = create_access_token(identity=str(user.id))
        logger.debug(f"Generated JWT token for user {email}: {access_token}")
        if 'nonce' in session:
            del session['nonce']
        return redirect(f"http://localhost:5173/?token={access_token}")
    except Exception as e:
        logger.error(f"Error in Google OAuth callback: {str(e)}")
        return jsonify({"error": str(e)}), 500
# GitHub OAuth login
@routes_bp.route('/auth/github')
def auth_github():
    return oauth.github.authorize_redirect(redirect_uri=url_for('routes.auth_github_callback', _external=True))
@routes_bp.route('/auth/github/callback')
def auth_github_callback():
    logger.debug("Processing GitHub OAuth callback")
    try:
        token = oauth.github.authorize_access_token()
        user_info = oauth.github.get('user').json()
        email = user_info.get('email') or f"{user_info['login']}@github.com"
        username = user_info['login']
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(username=username, email=email, password=None)
            db.session.add(user)
            db.session.commit()
            logger.info(f"Created new user: {email}")
        access_token = create_access_token(identity=str(user.id))
        logger.debug(f"Generated JWT token for user {email}: {access_token}")
        return redirect(f"http://localhost:5173/?token={access_token}")
    except Exception as e:
        logger.error(f"Error in GitHub OAuth callback: {str(e)}")
        return jsonify({"error": str(e)}), 500
# User info endpoint
@routes_bp.route('/auth/me', methods=['GET'])
@jwt_required(optional=True)
def get_me():
    user_id = get_jwt_identity()
    logger.debug(f"Fetching user info for user_id: {user_id}")
    if user_id:
        user_id = int(user_id)
        user = User.query.get(user_id)
        if user:
            logger.info(f"User found: {user.email}")
            return jsonify({'id': user.id, 'username': user.username, 'email': user.email}), 200
    logger.warning("No user_id found or user not authenticated")
    return jsonify({'id': None}), 200
# Chat functionality
@routes_bp.route('/chat')
@jwt_required()
def get_chats():
    user_id = int(get_jwt_identity())
    logger.debug(f"Fetching chats for user_id: {user_id}, headers: {request.headers}")
    try:
        chats = Chat.query.filter_by(user_id=user_id).all()
        logger.debug(f"Chats retrieved: {len(chats)}")
        if chats:
            chat_list = [chat.to_dict() for chat in chats]
            logger.info(f"Returning {len(chat_list)} chats for user_id: {user_id}")
            return make_response(jsonify(chat_list), 200)
        else:
            logger.info(f"No chats found for user_id: {user_id}")
            return make_response(jsonify({'message': "No chats yet"}), 200)
    except Exception as e:
        logger.error(f"Error fetching chats for user_id {user_id}: {str(e)}")
        return make_response(jsonify({"error": str(e)}), 500)
@routes_bp.route('/chat/<int:id>', methods=["DELETE"])
@jwt_required()
def delete_chat(id):
    user_id = int(get_jwt_identity())
    logger.debug(f"Deleting chat id: {id} for user_id: {user_id}")
    try:
        chat = Chat.query.get(id)
        if not chat or chat.user_id != user_id:
            logger.warning(f"Chat {id} not found or unauthorized for user_id: {user_id}")
            return make_response(jsonify({"message": "Chat not found or unauthorized"}), 404)
        for message in chat.messages[:]:
            delete_audio_files_for_prompt(message.id)
        db.session.delete(chat)
        db.session.commit()
        logger.info(f"Chat {id} deleted successfully")
        return '', 204
    except Exception as e:
        logger.error(f"Error deleting chat {id}: {str(e)}")
        db.session.rollback()
        return make_response(jsonify({"message": str(e)}), 500)
@routes_bp.route('/chat/<int:id>', methods=["PUT"])
@jwt_required()
def update_chat_name(id):
    user_id = int(get_jwt_identity())
    logger.debug(f"Updating chat name for chat id: {id}, user_id: {user_id}, data: {request.get_json()}")
    try:
        data = request.get_json()
        chat = Chat.query.get(id)
        if not chat or chat.user_id != user_id:
            logger.warning(f"Chat {id} not found or unauthorized for user_id: {user_id}")
            return make_response(jsonify({"message": "Chat not found or unauthorized"}), 404)
        if 'title' in data:
            chat.title = data['title']
            db.session.commit()
            logger.info(f"Chat {id} updated successfully to title: {data['title']}")
            return make_response(jsonify({"message": "Update successful"}), 200)
        logger.warning("No new name provided in request")
        return make_response(jsonify({'message': "No new name identified"}), 400)
    except Exception as e:
        logger.error(f"Error updating chat {id}: {str(e)}")
        return make_response(jsonify({"message": str(e)}), 500)
@routes_bp.route('/talk', methods=['POST'])
@jwt_required(optional=True)
def post_chats():
    user_id = get_jwt_identity()
    data = request.get_json()
    logger.debug(f"Received POST /talk for user_id: {user_id}, payload: {data}, headers: {request.headers}")
    if not data:
        logger.error("Missing JSON body")
        return jsonify({"error": "Missing JSON body"}), 422
    prompt = data.get("prompt", "").strip()
    bpm = data.get("bpm")
    key = data.get("key")
    if not prompt:
        logger.error("Missing or empty 'prompt'")
        return jsonify({"error": "Missing or empty 'prompt'"}), 422
    if bpm is None or key is None:
        logger.error(f"Missing 'bpm' ({bpm}) or 'key' ({key})")
        return jsonify({"error": "Missing 'bpm' or 'key'"}), 422
    try:
        app = current_app._get_current_object()
        if user_id:
            user_id = int(user_id)
            if 'chat' not in data:
                number_of_chats = Chat.query.filter_by(user_id=user_id).count()
                new_chat = Chat(title=f"Chat {number_of_chats}", user_id=user_id)
                commit(new_chat)
                new_exchange = Messages(role="user", content=prompt, convo=new_chat.id)
                commit(new_exchange)
                logger.info(f"Created new chat {new_chat.id} with message {new_exchange.id}")
                # Create Audios record immediately
                new_audio = Audios(link=f"lyria_{new_chat.id}_{new_exchange.id}", chat=new_chat.id, prompt=new_exchange.id)
                commit(new_audio)
                logger.info(f"Successfully created and committed Audios record for chat_id: {new_chat.id}, prompt_id: {new_exchange.id}")
                Thread(target=create_a_message_and_send_prompt, args=(new_exchange.content, new_chat.id, data, new_exchange.id, app)).start()
                return jsonify({"new_chat": new_chat.id, "message": new_exchange.id}), 200
            else:
                new_exchange = Messages(role="user", content=prompt, convo=data["chat"])
                commit(new_exchange)
                logger.info(f"Added message {new_exchange.id} to chat {data['chat']}")
                # Create Audios record immediately
                new_audio = Audios(link=f"lyria_{data['chat']}_{new_exchange.id}", chat=data["chat"], prompt=new_exchange.id)
                commit(new_audio)
                logger.info(f"Successfully created and committed Audios record for chat_id: {data['chat']}, prompt_id: {new_exchange.id}")
                Thread(target=create_a_message_and_send_prompt, args=(new_exchange.content, data["chat"], data, new_exchange.id, app)).start()
                return jsonify({"message": new_exchange.id}), 200
        else:
            # Handle non-logged-in users
            # Use a temporary chat_id and prompt_id
            chat_id = "temp"
            prompt_id = f"temp_{hash(prompt + str(bpm) + str(key)) % 1000000}" # Unique temp ID
            Thread(target=create_a_message_and_send_prompt, args=(prompt, chat_id, data, prompt_id, app)).start()
            return jsonify({"message": prompt_id}), 200
    except Exception as e:
        logger.error(f"Internal error in post_chats: {str(e)}")
        return jsonify({"error": f"Internal error: {str(e)}"}), 500
@routes_bp.route('/get-audio/<chat_id>/<message_id>')
@jwt_required(optional=True)
def get_audio(chat_id, message_id):
    user_id = get_jwt_identity()
    logger.debug(f"Fetching audio for chat_id: {chat_id}, message_id: {message_id}, user_id: {user_id}")
    file_path = f'{music_folder}/lyria_{chat_id}_{message_id}.wav'
    try:
        return send_file(file_path, mimetype='audio/wav')
    except FileNotFoundError:
        logger.error(f"Audio file not found: {file_path}")
        return make_response(jsonify({'message': 'No audio available'}), 404)
@routes_bp.route('/all-audios/<int:user_id>')
@jwt_required()
def get_audios(user_id):
    current_id = int(get_jwt_identity())
    logger.debug(f"Fetching audios for user_id: {user_id}, current_id: {current_id}")
    if current_id != user_id:
        logger.warning(f"Unauthorized access attempt: current_id {current_id} != user_id {user_id}")
        return jsonify({'error': 'Unauthorized'}), 403
    audios = Audios.query.join(Chat).filter(Chat.id == Audios.chat, Chat.user_id == user_id).all()
    logger.info(f"Retrieved {len(audios)} audios for user_id: {user_id}")
    return jsonify([{"id": audio.id, "name": f"{audio.link}.wav", "chat": audio.chat, "prompt": audio.prompt} for audio in audios]), 200
@routes_bp.route('/getmessages/<chat_id>')
@jwt_required(optional=True)
def get_messages(chat_id):
    user_id = get_jwt_identity()
    logger.debug(f"Fetching messages for chat id: {chat_id}, user_id: {user_id}")
    try:
        if user_id:
            user_id = int(user_id)
            convo = Chat.query.get(chat_id)
            if not convo or convo.user_id != user_id:
                logger.warning(f"Chat {chat_id} not found or unauthorized for user_id: {user_id}")
                return make_response(jsonify({'error': 'Unauthorized'}), 403)
            messages = convo.messages
            message_list = []
            if messages:
                message_list = [msg.to_dict() for msg in messages]
            logger.info(f"Retrieved {len(message_list)} messages for chat id: {chat_id}")
            return make_response(jsonify(message_list), 200)
        else:
            # Return empty messages for non-logged-in users
            return make_response(jsonify([]), 200)
    except Exception as e:
        logger.error(f"Error fetching messages for chat id {chat_id}: {str(e)}")
        return make_response(jsonify({"message": str(e)}), 500)
@routes_bp.route('/prompt/<int:prompt_id>', methods=['DELETE'])
def delete_prompt_and_audio_route(prompt_id):
    logger.debug(f"Deleting prompt and audio for prompt_id: {prompt_id}")
    try:
        delete_prompt_and_audio(db.session, prompt_id)
        logger.info(f"Prompt {prompt_id} and associated audio files deleted")
        return make_response(jsonify({"message": f"Prompt {prompt_id} and associated audio files deleted."}), 200)
    except Exception as e:
        logger.error(f"Error deleting prompt {prompt_id}: {str(e)}")
        return make_response(jsonify({"error": str(e)}), 500)
@routes_bp.route('/api/music-files', methods=['GET'])
@jwt_required()
def api_music_files():
    user_id = int(get_jwt_identity())
    logger.debug(f"Fetching music files for user_id: {user_id}")
    try:
        return get_audios(user_id)
    except Exception as e:
        logger.error(f"Error listing music files for user_id {user_id}: {str(e)}")
        return jsonify({"error": "Failed to list files"}), 500
@routes_bp.route('/api/mixer/<filename>', methods=['GET'])
def get_mixer_data(filename):
    logger.debug(f"Fetching mixer data for filename: {filename}")
    try:
        file_basename = os.path.splitext(filename)[0]
        expected_dir = os.path.join(SEPARATED_DIR, DEMUCS_MODEL_NAME, file_basename)
        if not os.path.isdir(expected_dir):
            logger.info(f"Separation not started for {filename}")
            status_data = {"status": "not_started", "channels": []}
            message = "Separation not started yet"
        else:
            expected_channels = ['drums', 'bass', 'other', 'vocals']
            available_channels = []
            for channel in expected_channels:
                channel_file = os.path.join(expected_dir, f"{channel}.mp3")
                if os.path.exists(channel_file):
                    available_channels.append(channel)
            if len(available_channels) == len(expected_channels):
                status_data = {
                    "status": "complete",
                    "channels": available_channels,
                    "message": "Separation complete and ready for mixing"
                }
            else:
                status_data = {
                    "status": "processing",
                    "channels": available_channels,
                    "message": f"Processing... {len(available_channels)}/{len(expected_channels)} channels ready"
                }
        logger.info(f"Mixer data for {filename}: {status_data}")
        return jsonify({
            "filename": filename,
            "separation_status": status_data,
            "message": status_data.get("message", "Checking separation status...")
        })
    except Exception as e:
        logger.error(f"Error in get_mixer_data for {filename}: {str(e)}")
        return jsonify({"error": str(e)}), 500
@routes_bp.route('/api/mix-and-download', methods=['POST'])
def mix_and_download():
    data = request.get_json()
    logger.debug(f"Mixing audio with data: {data}")
    filename = data.get('filename')
    track_volumes = data.get('trackVolumes', {})
    if not filename:
        logger.error("Filename is required")
        return jsonify({"error": "Filename is required"}), 400
    try:
        file_basename = os.path.splitext(filename)[0]
        separated_dir = os.path.join(SEPARATED_DIR, DEMUCS_MODEL_NAME, file_basename)
        if not os.path.exists(separated_dir):
            logger.error(f"Separated tracks not found for {filename}")
            return jsonify({"error": "Separated tracks not found"}), 404
        output_filename = f"{file_basename}_mixed.wav"
        output_path = os.path.join(SEPARATED_DIR, output_filename)
        non_vocal_channels = ['drums', 'bass', 'other']
        input_files = []
        volume_filters = []
        for i, channel in enumerate(non_vocal_channels):
            channel_file = os.path.join(separated_dir, f"{channel}.mp3")
            if os.path.exists(channel_file):
                input_files.append(f"-i {channel_file}")
                volume = track_volumes.get(channel, 1.0)
                if volume > 0:
                    volume_db = 20 * math.log10(volume)
                    volume_filters.append(f"[{i}:a]volume={volume_db}dB[a{i}]")
                else:
                    volume_filters.append(f"[{i}:a]volume=0dB[a{i}]")
        if not input_files:
            logger.error("No tracks found to mix")
            return jsonify({"error": "No tracks found to mix"}), 404
        filter_complex = ";".join(volume_filters)
        if len(input_files) > 1:
            mix_inputs = "".join([f"[a{i}]" for i in range(len(input_files))])
            filter_complex += f";{mix_inputs}amix=inputs={len(input_files)}:duration=longest[out]"
        else:
            filter_complex += ";[a0]copy[out]"
        input_args = " ".join(input_files)
        ffmpeg_cmd = f'ffmpeg {input_args} -filter_complex "{filter_complex}" -map "[out]" -y "{output_path}"'
        logger.debug(f"Running FFmpeg command: {ffmpeg_cmd}")
        result = subprocess.run(ffmpeg_cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            return jsonify({"error": f"FFmpeg mixing failed: {result.stderr}"}), 500
        if not os.path.exists(output_path):
            logger.error("Failed to create mixed audio file")
            return jsonify({"error": "Failed to create mixed audio file"}), 500
        logger.info(f"Successfully mixed audio: {output_filename}")
        return send_file(
            output_path,
            mimetype='audio/wav',
            as_attachment=True,
            download_name=output_filename
        )
    except Exception as e:
        logger.error(f"Error mixing audio: {str(e)}")
        return jsonify({"error": str(e)}), 500
@routes_bp.after_request
def after_request(response):
    logger.debug(f"Response headers: {response.headers}")
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response
def run_demucs_in_background(input_path, output_path):
    python_executable = os.path.join(CONDA_ENV_PATH, "bin/python")
    script_path = os.path.join(BASE_DIR, "separator.py")
    if not os.path.exists(python_executable):
        logger.error(f"FATAL ERROR: Conda python executable not found at {python_executable}")
        return
    command = [python_executable, script_path, input_path, output_path]
    logger.debug(f"Starting background process: {' '.join(command)}")
    subprocess.Popen(command)
    logger.info("Background process started.")
@routes_bp.route('/api/separated-channels/<filename>', methods=['GET'])
def get_separated_channels(filename):
    file_basename = os.path.splitext(filename)[0]
    expected_dir = os.path.join(SEPARATED_DIR, DEMUCS_MODEL_NAME, file_basename)
    if not os.path.isdir(expected_dir):
        return jsonify({"status": "processing", "channels": []}), 202
    try:
        channels = [os.path.splitext(f)[0] for f in os.listdir(expected_dir) if f.endswith('.mp3')]
        return jsonify({"status": "complete", "channels": channels})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@routes_bp.route('/api/stream-channel/<filename>/<channel>', methods=['GET'])
def stream_channel(filename, channel):
    file_basename = os.path.splitext(filename)[0]
    channel_filename = f"{channel}.mp3"
    directory = os.path.join(SEPARATED_DIR, DEMUCS_MODEL_NAME, file_basename)
    if not os.path.exists(os.path.join(directory, channel_filename)):
        return jsonify({"error": "Channel not found"}), 404
    return send_from_directory(directory, channel_filename, mimetype='audio/mpeg')