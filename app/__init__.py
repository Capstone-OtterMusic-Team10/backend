from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from .config import Config
from flask_migrate import Migrate
from authlib.integrations.flask_client import OAuth
from flask_jwt_extended import JWTManager

db = SQLAlchemy()
migrate = Migrate()
oauth = OAuth()
jwt = JWTManager()  # Initialize JWTManager globally

def create_app():
    app = Flask(__name__)

    CORS(app, resources={r"/*": {"origins": "*"}})
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    oauth.init_app(app)
    jwt.init_app(app)  # Bind JWTManager to the app

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

    with app.app_context():
        from . import populate_db
        populate_db.add_initial_data()


    return app