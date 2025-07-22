import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    JWT_SECRET_KEY = os.getenv('SECRET_KEY')  # Google OAuth
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
    # GitHub OAuth
    GITHUB_CLIENT_ID = os.getenv('GITHUB_CLIENT_ID')
    GITHUB_CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET')