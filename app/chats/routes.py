from flask import Blueprint, jsonify, request, make_response, send_file
from ..models import Chat, Messages, Audios, delete_prompt_and_audio
from .. import db
from app.chats.lyria_demo_test2 import generate_audio
from flask import Blueprint, jsonify, request, make_response, redirect, url_for, session
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from ..models import Chat, Messages, Audios, User
from .. import db, oauth
from .lyria_demo_test2 import generate_audio
import os
import time
import asyncio
import os
import subprocess
import threading
from flask import send_from_directory
from pathlib import Path
from threading import Thread
from flask import jsonify, send_file, abort, current_app
from urllib.parse import unquote
import math

routes_bp = Blueprint('routes', __name__)

music_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'MusicDownloadFiles'))

"""
# Instructions to set up the environment (macOS)

# Create the environment for Demucs
conda create -n demucs-env python=3.10 -y

# Activate it to install packages
conda activate demucs-env

# Install Demucs and its dependencies into the new environment
conda install -c pytorch -c conda-forge demucs ffmpeg -y

# Deactivate it when you're done
conda deactivate

"""


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
    return redirect(f"http://localhost:5173/?token={access_token}")  # Changed to /?token=...

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
    return redirect(f"http://localhost:5173/?token={access_token}")  # Changed to /?token=...

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

# Delete a prompt (message) and all associated audio files.
@routes_bp.route('/prompt/<int:prompt_id>', methods=['DELETE'])
def delete_prompt_and_audio_route(prompt_id):
    try:
        delete_prompt_and_audio(db.session, prompt_id)
        return make_response(jsonify({"message": f"Prompt {prompt_id} and associated audio files deleted."}), 200)
    except Exception as e:
        return make_response(jsonify({"error": str(e)}), 500)


# List all audio files in the MusicDownloadFiles directory (API version)
@routes_bp.route('/api/music-files', methods=['GET'])
def api_music_files():

    try:
        if not os.path.exists(music_dir):
            return jsonify({"files": []}), 200

        audio_extensions = ('.wav', '.mp3', '.flac', '.m4a', '.ogg')
        files = [
            {"name": f}
            for f in os.listdir(music_dir)
            if f.lower().endswith(audio_extensions) and os.path.isfile(os.path.join(music_dir, f))
        ]
        return jsonify({"files": files}), 200

    except Exception as e:
        print(f"Error listing music files: {e}")
        return jsonify({"error": "Failed to list files"}), 500


# Get mixer data for a file, including separation status
@routes_bp.route('/api/mixer/<filename>', methods=['GET'])
def get_mixer_data(filename):
    try:
        # Get separation status directly
        file_basename = os.path.splitext(filename)[0]
        expected_dir = os.path.join(SEPARATED_DIR, DEMUCS_MODEL_NAME, file_basename)

        if not os.path.isdir(expected_dir):
            status_data = {"status": "not_started", "channels": []}
            message = "Separation not started yet"
        else:
            # Check if all expected channels exist
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

        return jsonify({
            "filename": filename,
            "separation_status": status_data,
            "message": status_data.get("message", "Checking separation status...")
        })
    except Exception as e:
        print(f"Error in get_mixer_data: {e}")
        return jsonify({"error": str(e)}), 500

# Mixes the separated tracks using FFmpeg and returns the mixed audio file
@routes_bp.route('/api/mix-and-download', methods=['POST'])
def mix_and_download():
    data = request.get_json()
    filename = data.get('filename')
    track_volumes = data.get('trackVolumes', {})

    if not filename:
        return jsonify({"error": "Filename is required"}), 400

    try:
        # Get the separated tracks directory
        file_basename = os.path.splitext(filename)[0]
        separated_dir = os.path.join(SEPARATED_DIR, DEMUCS_MODEL_NAME, file_basename)

        if not os.path.exists(separated_dir):
            return jsonify({"error": "Separated tracks not found"}), 404

        # Create a temporary output file
        output_filename = f"{file_basename}_mixed.wav"
        output_path = os.path.join(SEPARATED_DIR, output_filename)

        # Build FFmpeg command for mixing.
        # mix drums, bass, and other (excluding vocals)
        non_vocal_channels = ['drums', 'bass', 'other']
        input_files = []
        volume_filters = []

        for i, channel in enumerate(non_vocal_channels):
            channel_file = os.path.join(separated_dir, f"{channel}.mp3")
            if os.path.exists(channel_file):
                input_files.append(f"-i {channel_file}")
                # Apply volume (convert from 0-1 to dB)
                volume = track_volumes.get(channel, 1.0)
                if volume > 0:
                    volume_db = 20 * math.log10(volume)
                    volume_filters.append(f"[{i}:a]volume={volume_db}dB[a{i}]")
                else:
                    volume_filters.append(f"[{i}:a]volume=0dB[a{i}]")

        if not input_files:
            return jsonify({"error": "No tracks found to mix"}), 404

        # Build the FFmpeg filter complex
        filter_complex = ";".join(volume_filters)
        if len(input_files) > 1:
            # Mix multiple tracks
            mix_inputs = "".join([f"[a{i}]" for i in range(len(input_files))])
            filter_complex += f";{mix_inputs}amix=inputs={len(input_files)}:duration=longest[out]"
        else:
            # Single track
            filter_complex += ";[a0]copy[out]"

        # Construct the full FFmpeg command
        input_args = " ".join(input_files)
        ffmpeg_cmd = f'ffmpeg {input_args} -filter_complex "{filter_complex}" -map "[out]" -y "{output_path}"'

        print(f"Running FFmpeg command: {ffmpeg_cmd}")

        # Execute FFmpeg command
        result = subprocess.run(ffmpeg_cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            return jsonify({"error": f"FFmpeg mixing failed: {result.stderr}"}), 500

        if not os.path.exists(output_path):
            return jsonify({"error": "Failed to create mixed audio file"}), 500

        # Return the mixed file
        return send_file(
            output_path,
            mimetype='audio/wav',
            as_attachment=True,
            download_name=output_filename
        )

    except Exception as e:
        print(f"Error mixing audio: {e}")
        return jsonify({"error": str(e)}), 500

# CORS headers for all routes
@routes_bp.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


# Helper Function to run Demucs in a background thread to avoid blocking the API
def run_demucs_in_background(input_path, output_path):

    python_executable = os.path.join(CONDA_ENV_PATH, "bin/python")
    # Make sure separator.py is in rooot
    script_path = os.path.join(BASE_DIR, "separator.py")

    if not os.path.exists(python_executable):
        print(f"FATAL ERROR: Conda python executable not found at {python_executable}")
        return

    command = [python_executable, script_path, input_path, output_path]

    print(f"Starting background process: {' '.join(command)}")
    # Use Popen to run the command in the background
    subprocess.Popen(command)
    print("Background process started.")

# Demucs separation routes

# # Starts the Demucs separation process for a given file.
# @routes_bp.route('/api/separate-audio', methods=['POST'])
# def separate_audio_endpoint():
#     data = request.get_json()
#     filename = data.get('filename')
#
#     if not filename:
#         return jsonify({"error": "Filename is required"}), 400
#
#     input_file_path = os.path.join(music_folder, filename)
#
#     if not os.path.exists(input_file_path):
#         return jsonify({"error": f"File not found: {filename}"}), 404
#
#     thread = threading.Thread(target=run_demucs_in_background, args=(input_file_path, SEPARATED_DIR))
#     thread.start()
#
#     return jsonify({
#         "success": True,
#         "message": f"Separation started for {filename}. This may take a few minutes."
#     }), 200

# Checks for and returns the available separated channels for a file.
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

# Streams a specific audio channel for playback.
@routes_bp.route('/api/stream-channel/<filename>/<channel>', methods=['GET'])
def stream_channel(filename, channel):
    file_basename = os.path.splitext(filename)[0]
    channel_filename = f"{channel}.mp3"
    directory = os.path.join(SEPARATED_DIR, DEMUCS_MODEL_NAME, file_basename)

    if not os.path.exists(os.path.join(directory, channel_filename)):
        return jsonify({"error": "Channel not found"}), 404

    return send_from_directory(directory, channel_filename, mimetype='audio/mpeg')
