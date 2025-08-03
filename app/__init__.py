from flask import Flask, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from .config import Config
from flask_migrate import Migrate
from authlib.integrations.flask_client import OAuth
from flask_jwt_extended import JWTManager

db = SQLAlchemy()
migrate = Migrate()
oauth = OAuth()
jwt = JWTManager() # Initialize JWTManager globally

def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": "http://localhost:5173"}})
    app.config.from_object(Config)
    db.init_app(app)
    migrate.init_app(app, db)
    oauth.init_app(app)
    jwt.init_app(app) # Bind JWTManager to the app

    # Custom JWT error handlers for logging
    @jwt.unauthorized_loader
    def unauthorized_callback(reason):
        app.logger.error(f"Unauthorized access: {reason}")
        return jsonify({"msg": "Missing or invalid Authorization header", "error": reason}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        app.logger.error(f"Invalid JWT token: {error}")
        return jsonify({"msg": "Invalid token", "error": str(error)}), 422

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        app.logger.error(f"Expired JWT token: {jwt_payload}")
        return jsonify({"msg": "Token has expired", "error": "Expired token"}), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        app.logger.error(f"Revoked JWT token: {jwt_payload}")
        return jsonify({"msg": "Token has been revoked", "error": "Revoked token"}), 401

    @jwt.needs_fresh_token_loader
    def needs_fresh_token_callback(jwt_header, jwt_payload):
        app.logger.error(f"Fresh token required: {jwt_payload}")
        return jsonify({"msg": "Fresh token required", "error": "Fresh token needed"}), 401

    @jwt.user_lookup_error_loader
    def user_lookup_error_callback(jwt_header, jwt_payload):
        app.logger.error(f"User lookup error for token: {jwt_payload}")
        return jsonify({"msg": "User not found", "error": "User lookup failed"}), 401

    # Google OAuth
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )

    # GitHub OAuth (setup, but callback will indicate it's prepared)
    oauth.register(
        name='github',
        client_id=app.config['GITHUB_CLIENT_ID'],
        client_secret=app.config['GITHUB_CLIENT_SECRET'],
        authorize_url='https://github.com/login/oauth/authorize',
        access_token_url='https://github.com/login/oauth/access_token',
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'user:email'}
    )

    from app.chats.routes import routes_bp
    app.register_blueprint(routes_bp)

    from .auth_routes import auth_bp
    app.register_blueprint(auth_bp)

    with app.app_context():
        from . import populate_db
        populate_db.add_initial_data()

    return app