from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
from .models import User, db
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from .config import Config
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400

    new_user = User(username=username, email=email)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    token = create_access_token(identity=new_user.id)
    return jsonify({'token': token, 'user': new_user.to_dict()}), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        token = create_access_token(identity=user.id)
        return jsonify({'token': token, 'user': user.to_dict()}), 200

    return jsonify({'error': 'Invalid credentials'}), 401

@auth_bp.route('/google', methods=['POST'])
def google_login():
    data = request.get_json()
    token = data.get('id_token')
    try:
        print("Received id_token:", token[:20] + "...")  # Partial log for security
        idinfo = google_id_token.verify_oauth2_token(token, google_requests.Request(), Config.GOOGLE_CLIENT_ID)
        print("Verified token info:", idinfo)  # Full info for debug
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')
        email = idinfo['email']
        name = idinfo.get('name', email.split('@')[0])
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(username=name, email=email)
            db.session.add(user)
            db.session.commit()
        token = create_access_token(identity=user.id)
        return jsonify({'token': token, 'user': user.to_dict()}), 200
    except ValueError as e:
        print("Token verification failed (ValueError):", str(e))  # Debug log
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print("Unexpected error in token verification:", str(e))  # Debug log
        return jsonify({'error': 'Internal error during verification'}), 500

@auth_bp.route('/logout', methods=['POST'])
def logout():
    return jsonify({'message': 'Logged out'}), 200

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if user:
        return jsonify({'user': user.to_dict()}), 200
    return jsonify({'error': 'Not logged in'}), 401