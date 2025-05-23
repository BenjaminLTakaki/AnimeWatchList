import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Base configuration class."""
    # App configuration
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "skillstown_secret_key_change_this")
    
    # Database configuration - Try multiple environment variable names
    database_url = os.environ.get('DATABASE_URL') or os.environ.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///skillstown.db')
    
    # Fix Render PostgreSQL URLs (postgres:// -> postgresql://)
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
    COURSE_CATALOG_PATH = os.path.join(STATIC_FOLDER, 'data', 'course_catalog.json')
    
    # API Keys
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    
    # Create required directories
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(STATIC_FOLDER, 'data'), exist_ok=True)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}