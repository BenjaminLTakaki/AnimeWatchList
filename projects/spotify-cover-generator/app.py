import os
import sys
import random
import json
import datetime
from datetime import timedelta
from flask import Flask, request, render_template, send_from_directory, jsonify, session, redirect, url_for, flash, make_response
from pathlib import Path
from urllib.parse import urlparse
from functools import wraps
import requests
import base64
import scipy as sp
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import secrets
from sqlalchemy import text
from collections import Counter
from flask_migrate import Migrate
import uuid
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Get the directory where app.py is located
current_dir = os.path.dirname(os.path.abspath(__file__))

# Add the current directory to Python path if it's not already there
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Also add the parent directory in case modules are there
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

print(f"🔍 Current directory: {current_dir}")
print(f"🔍 Python path: {sys.path[:3]}...")  # Show first 3 paths

# Ensure all required modules can be imported by adding the current directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

print(f"🔍 Current directory: {current_dir}")
print(f"🔍 Directory contents: {os.listdir(current_dir)}")
print(f"🔍 Python path includes current dir: {current_dir in sys.path}")

# Import config first (this should work)
try:
    from config import BASE_DIR, COVERS_DIR, FLASK_SECRET_KEY, SPOTIFY_DB_URL, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI
    print("✓ Config imported successfully")
except ImportError as e:
    print(f"❌ Config import failed: {e}")
    # Fallback - define minimal config
    BASE_DIR = Path(current_dir)
    COVERS_DIR = BASE_DIR / "generated_covers"
    FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-key')
    SPOTIFY_DB_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/test')
    SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
    SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
    SPOTIFY_REDIRECT_URI = os.environ.get('SPOTIFY_REDIRECT_URI', 'http://localhost:5000/spotify-callback')

# Initialize Flask app first
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.secret_key = FLASK_SECRET_KEY or ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=24))

# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = SPOTIFY_DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Add rate limiter (optional - for additional protection)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"],  
    storage_uri="memory://"  
)
limiter.init_app(app)

# Initialize SQLAlchemy
from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Database Models
class User(db.Model):
    __tablename__ = 'spotify_users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=True)
    password_hash = db.Column(db.String(200), nullable=True)
    
    # Spotify OAuth fields
    spotify_id = db.Column(db.String(100), unique=True, nullable=True)
    spotify_username = db.Column(db.String(100), nullable=True)
    spotify_access_token = db.Column(db.String(500), nullable=True)
    spotify_refresh_token = db.Column(db.String(500), nullable=True)
    spotify_token_expires = db.Column(db.DateTime, nullable=True)
    
    # User info
    display_name = db.Column(db.String(100), nullable=True)
    is_premium = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationship to generations
    generations = db.relationship('GenerationResultDB', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
    def is_premium_user(self):
        return (self.email == 'bentakaki7@gmail.com' or 
                self.spotify_username == 'Benthegamer')
    
    def get_daily_generation_limit(self):
        return 999 if self.is_premium_user() else 2
    
    def can_generate_today(self):
        today = datetime.datetime.utcnow().date()
        today_generations = GenerationResultDB.query.filter(
            GenerationResultDB.user_id == self.id,
            db.func.date(GenerationResultDB.timestamp) == today
        ).count()
        return today_generations < self.get_daily_generation_limit()
    
    def get_generations_today(self):
        today = datetime.datetime.utcnow().date()
        return GenerationResultDB.query.filter(
            GenerationResultDB.user_id == self.id,
            db.func.date(GenerationResultDB.timestamp) == today
        ).count()
    
    def refresh_spotify_token_if_needed(self):
        if not self.spotify_refresh_token:
            return False
            
        if (self.spotify_token_expires and 
            self.spotify_token_expires <= datetime.datetime.utcnow() + timedelta(minutes=5)):
            return self._refresh_spotify_token()
        
        return True
    
    def _refresh_spotify_token(self):
        if not self.spotify_refresh_token:
            return False
        
        auth_header = base64.b64encode(
            f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
        ).decode()
        
        headers = {
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.spotify_refresh_token
        }
        
        try:
            response = requests.post(
                'https://accounts.spotify.com/api/token',
                headers=headers,
                data=data
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.spotify_access_token = token_data['access_token']
                self.spotify_token_expires = datetime.datetime.utcnow() + timedelta(
                    seconds=token_data['expires_in']
                )
                
                if 'refresh_token' in token_data:
                    self.spotify_refresh_token = token_data['refresh_token']
                
                db.session.commit()
                return True
        except Exception as e:
            print(f"Error refreshing Spotify token: {e}")
        
        return False
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'username': self.username,
            'display_name': self.display_name,
            'spotify_username': self.spotify_username,
            'is_premium': self.is_premium_user(),
            'daily_limit': self.get_daily_generation_limit(),
            'generations_today': self.get_generations_today(),
            'can_generate': self.can_generate_today(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class LoginSession(db.Model):
    __tablename__ = 'spotify_login_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('spotify_users.id'), nullable=False)
    session_token = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    
    user = db.relationship('User', backref='sessions')
    
    @staticmethod
    def create_session(user_id, ip_address=None, user_agent=None):
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.datetime.utcnow() + timedelta(days=30)
        
        session = LoginSession(
            user_id=user_id,
            session_token=session_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        db.session.add(session)
        db.session.commit()
        
        return session_token
    
    @staticmethod
    def get_user_from_session(session_token):
        session = LoginSession.query.filter_by(
            session_token=session_token,
            is_active=True
        ).first()
        
        if not session or session.expires_at <= datetime.datetime.utcnow():
            if session:
                session.is_active = False
                db.session.commit()
            return None
        
        return session.user

class SpotifyState(db.Model):
    __tablename__ = 'spotify_oauth_states'
    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    used = db.Column(db.Boolean, default=False)
    
    @staticmethod
    def create_state():
        state = secrets.token_urlsafe(32)
        oauth_state = SpotifyState(state=state)
        db.session.add(oauth_state)
        db.session.commit()
        return state
    
    @staticmethod
    def verify_and_use_state(state):
        oauth_state = SpotifyState.query.filter_by(state=state, used=False).first()
        if oauth_state and oauth_state.created_at > datetime.datetime.utcnow() - timedelta(minutes=10):
            oauth_state.used = True
            db.session.commit()
            return True
        return False

class LoraModelDB(db.Model):
    __tablename__ = 'spotify_lora_models'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    source_type = db.Column(db.String(20), default='local')
    path = db.Column(db.String(500), default='')
    url = db.Column(db.String(500), default='')
    trigger_words = db.Column(db.JSON, default=list)
    strength = db.Column(db.Float, default=0.7)
    
    def to_lora_model(self):
        from models import LoraModel
        return LoraModel(
            name=self.name,
            source_type=self.source_type,
            path=self.path,
            url=self.url,
            trigger_words=self.trigger_words or [],
           
        )

class GenerationResultDB(db.Model):
    __tablename__ = 'spotify_generation_results'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)  # Was 200
    output_path = db.Column(db.String(1000), nullable=False)  # Was 500
    item_name = db.Column(db.String(500))  # Was 200
    genres = db.Column(db.JSON)
    all_genres = db.Column(db.JSON)
    style_elements = db.Column(db.JSON)
    mood = db.Column(db.String(1000))  # Was 50 - THE MAIN FIX!
    energy_level = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    spotify_url = db.Column(db.String(1000))  # Was 500
    lora_name = db.Column(db.String(200))  # Was 100
    lora_type = db.Column(db.String(20))
    lora_url = db.Column(db.String(1000))  # Was 500
    user_id = db.Column(db.Integer, db.ForeignKey('spotify_users.id'), nullable=True)

# HELPER FUNCTIONS - ADD THESE HERE, BEFORE ANY ROUTES
def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            # Try session token from cookie
            session_token = request.cookies.get('session_token')
            if session_token:
                login_session = LoginSession.get_user_from_session(session_token)
                if login_session:
                    session['user_id'] = login_session.id
                    return f(*args, **kwargs)
            
            flash("Please log in to access this page.", "info")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get current logged in user"""
    # Method 1: Check user_id in session (most direct)
    if 'user_id' in session:
        try:
            user = User.query.get(session['user_id'])
            if user:
                return user
        except Exception as e:
            print(f"Error fetching user by ID from session: {e}")
            session.pop('user_id', None)
    
    # Method 2: Check user_session token in session
    if 'user_session' in session:
        try:
            session_token = session['user_session']
            login_session = LoginSession.query.filter_by(
                session_token=session_token, 
                is_active=True
            ).first()
            
            if login_session and login_session.expires_at > datetime.datetime.utcnow():
                user = login_session.user
                if user:
                    # Cache user_id in session for faster future lookups
                    session['user_id'] = user.id
                    return user
            else:
                # Clean up expired session
                session.pop('user_session', None)
        except Exception as e:
            print(f"Error fetching user by session token: {e}")
            session.pop('user_session', None)
    
    # Method 3: Check session_token cookie as fallback
    session_token = request.cookies.get('session_token')
    if session_token:
        try:
            login_session = LoginSession.query.filter_by(
                session_token=session_token, 
                is_active=True
            ).first()
            
            if login_session and login_session.expires_at > datetime.datetime.utcnow():
                user = login_session.user
                if user:
                    # Restore session variables
                    session['user_id'] = user.id
                    session['user_session'] = session_token
                    return user
        except Exception as e:
            print(f"Error fetching user by cookie: {e}")
    
    return None

def calculate_genre_percentages(genres_list):
    """Calculate percentage distribution of genres"""
    if not genres_list:
        return []
    
    try:
        # Attempt to use the more structured GenreAnalysis if available
        from models import GenreAnalysis 
        genre_analysis = GenreAnalysis.from_genre_list(genres_list)
        return genre_analysis.get_percentages(max_genres=5)
    except ImportError:
        # Fallback if models.py or GenreAnalysis is not available
        print("⚠️ models.GenreAnalysis not found, using fallback for calculate_genre_percentages.")
        if not isinstance(genres_list, list): # Ensure it's a list
            return []
            
        genre_counter = Counter(genres_list)
        total_count = sum(genre_counter.values())
        if total_count == 0:
            return []
            
        sorted_genres = genre_counter.most_common(5)
        
        percentages = []
        for genre, count in sorted_genres:
            percentage = round((count / total_count) * 100)
            percentages.append({
                "name": genre,
                "percentage": percentage,
                "count": count  # Keep the count for potential display
            })
        return percentages

def extract_playlist_id(playlist_url):
    """Extract playlist ID from Spotify URL"""
    if not playlist_url or "playlist/" not in playlist_url:
        return None
    try:
        # Example: https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=...
        #          -> 37i9dQZF1DXcBWIGoYBM5M
        path_part = urlparse(playlist_url).path
        if "/playlist/" in path_part:
            return path_part.split("/playlist/")[-1].split("/")[0]
    except Exception as e:
        print(f"Error parsing playlist URL '{playlist_url}': {e}")
    return None

def ensure_tables_exist():
    """Ensure tables exist before any database operation.
       Uses app_context for database operations.
    """
    try:
        with app.app_context(): # Ensure operations are within app context
            # Quick check if a critical table exists
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM spotify_oauth_states LIMIT 1"))
        # print("✓ Tables appear to exist.") # Optional: for debugging
    except Exception: # Broad exception because specific DB errors can vary
        print("⚠️ Tables missing or DB connection issue, attempting to create...")
        try:
            with app.app_context(): # Ensure db.create_all() is in app context
                db.create_all()
                # If you have a manual creation script and want to run it here:
                # create_tables_manually() 
                print("✓ Tables created/verified on-demand.")
        except Exception as e_create:
            print(f"❌ On-demand table creation failed: {e_create}")
            # Depending on the application, you might want to raise this
            # or handle it more gracefully, e.g., by preventing app startup.
            # For now, just printing the error.
            # raise # Uncomment to make table creation failure critical

# Global initialization flag
initialized = False

def initialize_app():
    """Initialize the application's dependencies with better import handling"""
    global initialized
    
    print("🔧 Initializing Spotify Cover Generator...")
    
    # Make sure necessary directories exist first
    try:
        os.makedirs(COVERS_DIR, exist_ok=True)
        print("✓ Created directories")
    except Exception as e:
        print(f"⚠️ Directory creation warning: {e}")
    
    # Database setup (keep your existing database code)
    try:
        with app.app_context():
            print("📊 Setting up database...")
            
            # Test database connection
            try:
                with db.engine.connect() as connection:
                    connection.execute(text('SELECT 1'))
                print("✓ Database connection successful")
            except Exception as e:
                print(f"❌ Database connection failed: {e}")
                return False
            
            # Check and create tables
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            print(f"📋 Existing tables: {existing_tables}")
            
            db.create_all()
            print("✓ db.create_all() executed")
            
            # Verify required tables exist
            new_tables = inspector.get_table_names()
            required_tables = [
                'spotify_users', 
                'spotify_login_sessions', 
                'spotify_oauth_states',
                'spotify_generation_results',
                'spotify_lora_models'
            ]
            
            missing_tables = [t for t in required_tables if t not in new_tables]
            if missing_tables:
                print(f"❌ Still missing tables: {', '.join(missing_tables)}")
                try:
                    create_tables_manually()
                    final_tables = inspector.get_table_names()
                    final_missing = [t for t in required_tables if t not in final_tables]
                    if final_missing:
                        print(f"❌ Manual creation also failed for: {', '.join(final_missing)}")
                        return False
                    else:
                        print("✓ Manual table creation successful for missing tables")
                except Exception as e_manual:
                    print(f"❌ Manual table creation attempt failed: {e_manual}")
                    return False
            else:
                print("✓ All required tables present")
                
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        return False
    
    # Import modules with better error handling - TRY RELATIVE IMPORTS FIRST
    print("📦 Importing modules...")
    
    # Global variables to track what's available
    global spotify_client_available, models_available, utils_available, generator_available
    spotify_client_available = False
    models_available = False
    utils_available = False
    generator_available = False
    
    # Get the current working directory for imports
    original_cwd = os.getcwd()
    # current_dir for os.chdir should be the script's directory, defined globally earlier
    module_level_current_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        # Change to the spotify app directory for imports
        os.chdir(module_level_current_dir)
        
        # Try importing spotify_client
        try:
            import spotify_client
            print("✓ spotify_client imported")
            spotify_client_available = True
        except ImportError as e:
            print(f"⚠️ spotify_client import failed: {e}")
            
        # Try importing models
        try:
            import models
            print("✓ models imported")
            models_available = True
        except ImportError as e:
            print(f"⚠️ models import failed: {e}")
            
        # Try importing utils
        try:
            import utils
            print("✓ utils imported")
            utils_available = True
        except ImportError as e:
            print(f"⚠️ utils import failed: {e}")
        
        # Try importing generator
        try:
            import generator
            print("✓ generator imported")
            generator_available = True
        except ImportError as e:
            print(f"⚠️ generator import failed: {e}")
        
        # Try importing other required modules
        try:
            import title_generator
            import image_generator
            import chart_generator
            print("✓ Additional generation modules imported")
        except ImportError as e:
            print(f"⚠️ Some generation modules unavailable: {e}")
            
    finally:
        # Always restore the original working directory
        os.chdir(original_cwd)
    
    print("✓ Module imports completed (with fallbacks if needed)")
    
    # Initialize Spotify client if available
    if spotify_client_available:
        print("🎵 Initializing Spotify client...")
        try:
            spotify_initialized = spotify_client.initialize_spotify()
            if spotify_initialized:
                print("✓ Spotify client initialized")
            else:
                print("⚠️ Spotify client initialization failed - continuing with limited functionality")
        except Exception as e:
            print(f"⚠️ Spotify initialization error: {e}")
    else:
        print("⚠️ Spotify client not available - skipping initialization")
    
    # Check environment variables
    print("🔑 Checking environment variables...")
    try:
        from config import GEMINI_API_KEY, STABILITY_API_KEY
    except ImportError:
        GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
        STABILITY_API_KEY = os.environ.get('STABILITY_API_KEY')
    
    env_vars_present = all([
        SPOTIFY_CLIENT_ID, 
        SPOTIFY_CLIENT_SECRET, 
        GEMINI_API_KEY, 
        STABILITY_API_KEY
    ])
    
    if not env_vars_present:
        missing = []
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            missing.append("Spotify API credentials")
        if not GEMINI_API_KEY:
            missing.append("Gemini API key")
        if not STABILITY_API_KEY:
            missing.append("Stable Diffusion API key")
        print(f"❌ Missing environment variables: {', '.join(missing)}")
    else:
        print("✓ All environment variables present")
    
    # Set initialization status based on what we have
    initialized = env_vars_present and (spotify_client_available or models_available)
    
    if initialized:
        print("🎉 Application initialized successfully!")
    else:
        print("⚠️ Application initialization completed with limited functionality")
    
    return initialized

def create_tables_manually():
    """Manually create tables using SQLAlchemy 2.0+ compatible syntax"""
    print("🔨 Attempting manual table creation...")
    
    sql_commands = [
        # Users table
        """
        CREATE TABLE IF NOT EXISTS spotify_users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(120) UNIQUE,
            username VARCHAR(80) UNIQUE,
            password_hash VARCHAR(200),
            spotify_id VARCHAR(100) UNIQUE,
            spotify_username VARCHAR(100),
            spotify_access_token VARCHAR(500),
            spotify_refresh_token VARCHAR(500),
            spotify_token_expires TIMESTAMP,
            display_name VARCHAR(100),
            is_premium BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        );
        """,
        
        # Login sessions table
        """
        CREATE TABLE IF NOT EXISTS spotify_login_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            session_token VARCHAR(100) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            ip_address VARCHAR(45),
            user_agent VARCHAR(500)
        );
        """,
        
        # OAuth states table
        """
        CREATE TABLE IF NOT EXISTS spotify_oauth_states (
            id SERIAL PRIMARY KEY,
            state VARCHAR(100) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used BOOLEAN DEFAULT FALSE
        );
        """,
        
        # LoRA models table
        """
        CREATE TABLE IF NOT EXISTS spotify_lora_models (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            source_type VARCHAR(20) DEFAULT 'local',
            path VARCHAR(500) DEFAULT '',
            url VARCHAR(1000) DEFAULT '',
            trigger_words JSON DEFAULT '[]',
            strength FLOAT DEFAULT 0.7
        );
        """,
        
        # Generation results table - WITH CORRECT SIZES FROM THE START!
        """
        CREATE TABLE IF NOT EXISTS spotify_generation_results (
            id SERIAL PRIMARY KEY,
            title VARCHAR(500) NOT NULL,
            output_path VARCHAR(1000) NOT NULL,
            item_name VARCHAR(500),
            genres JSON,
            all_genres JSON,
            style_elements JSON,
            mood VARCHAR(1000),
            energy_level VARCHAR(50),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            spotify_url VARCHAR(1000),
            lora_name VARCHAR(200),
            lora_type VARCHAR(20),
            lora_url VARCHAR(1000),
            user_id INTEGER
        );
        """,
        
        # Add foreign keys
        """
        ALTER TABLE spotify_login_sessions 
        ADD CONSTRAINT fk_login_sessions_user_id 
        FOREIGN KEY (user_id) REFERENCES spotify_users(id) ON DELETE CASCADE;
        """,
        
        """
        ALTER TABLE spotify_generation_results 
        ADD CONSTRAINT fk_generation_results_user_id 
        FOREIGN KEY (user_id) REFERENCES spotify_users(id) ON DELETE SET NULL;
        """,
        
        # Create indexes
        """
        CREATE INDEX IF NOT EXISTS idx_users_email ON spotify_users(email);
        CREATE INDEX IF NOT EXISTS idx_users_spotify_id ON spotify_users(spotify_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_token ON spotify_login_sessions(session_token);
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON spotify_login_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_oauth_state ON spotify_oauth_states(state);
        CREATE INDEX IF NOT EXISTS idx_generation_user_id ON spotify_generation_results(user_id);
        """
    ]
    
    # Use SQLAlchemy 2.0+ syntax
    with db.engine.connect() as connection:
        for i, sql in enumerate(sql_commands):
            try:
                connection.execute(text(sql))
                print(f"✓ SQL command {i+1} executed successfully")
            except Exception as e:
                print(f"❌ SQL command {i+1} failed: {e}")
                # For foreign keys and indexes, failures are often OK (already exist)
                if "foreign key" not in str(e).lower() and "index" not in str(e).lower():
                    raise
        
        connection.commit()
        print("✓ All tables created successfully")

# Fix the result template reference to 'index'
@app.route('/index')
def index():
    """Redirect /index to /generate for backward compatibility"""
    return redirect(url_for('generate'))

@app.route("/admin/nuclear-reset")
def admin_nuclear_reset():
    """NUCLEAR OPTION: Drop and recreate all Spotify tables"""
    try:
        with app.app_context():
            print("💣 NUCLEAR RESET: Dropping all Spotify tables...")
            
            with db.engine.connect() as connection:
                # Drop all Spotify-related tables in correct order (foreign keys first)
                drop_commands = [
                    "DROP TABLE IF EXISTS spotify_generation_results CASCADE;",
                    "DROP TABLE IF EXISTS spotify_login_sessions CASCADE;", 
                    "DROP TABLE IF EXISTS spotify_oauth_states CASCADE;",
                    "DROP TABLE IF EXISTS spotify_lora_models CASCADE;",
                    "DROP TABLE IF EXISTS spotify_users CASCADE;"
                ]
                
                for sql in drop_commands:
                    try:
                        print(f"Executing: {sql}")
                        connection.execute(text(sql))
                    except Exception as e:
                        print(f"⚠️ Drop command failed (table might not exist): {e}")
                
                connection.commit()
                print("✓ All old tables dropped")
            
            # Now recreate with correct sizes
            print("🔨 Creating new tables with correct column sizes...")
            
            # Use the manual creation function with updated sizes
            create_tables_manually_with_correct_sizes()
            
            print("✅ Nuclear reset complete - all tables recreated!")
            
            return jsonify({
                "success": True,
                "message": "Nuclear reset complete! All tables recreated with correct sizes.",
                "warning": "All existing data has been deleted!"
            })
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Nuclear reset error: {e}")
        print(f"Full traceback: {error_details}")
        
        return jsonify({
            "success": False,
            "error": str(e),
            "details": error_details
        }), 500

def create_tables_manually_with_correct_sizes():
    """Create tables with the correct column sizes from the start"""
    print("🔨 Creating tables with correct sizes...")
    
    sql_commands = [
        # Users table
        """
        CREATE TABLE IF NOT EXISTS spotify_users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(120) UNIQUE,
            username VARCHAR(80) UNIQUE,
            password_hash VARCHAR(200),
            spotify_id VARCHAR(100) UNIQUE,
            spotify_username VARCHAR(100),
            spotify_access_token VARCHAR(500),
            spotify_refresh_token VARCHAR(500),
            spotify_token_expires TIMESTAMP,
            display_name VARCHAR(100),
            is_premium BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        );
        """,
        
        # Login sessions table
        """
        CREATE TABLE IF NOT EXISTS spotify_login_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            session_token VARCHAR(100) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            ip_address VARCHAR(45),
            user_agent VARCHAR(500)
        );
        """,
        
        # OAuth states table
        """
        CREATE TABLE IF NOT EXISTS spotify_oauth_states (
            id SERIAL PRIMARY KEY,
            state VARCHAR(100) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used BOOLEAN DEFAULT FALSE
        );
        """,
        
        # LoRA models table
        """
        CREATE TABLE IF NOT EXISTS spotify_lora_models (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            source_type VARCHAR(20) DEFAULT 'local',
            path VARCHAR(500) DEFAULT '',
            url VARCHAR(1000) DEFAULT '',
            trigger_words JSON DEFAULT '[]',
            strength FLOAT DEFAULT 0.7
        );
        """,
        
        # Generation results table - WITH CORRECT SIZES FROM THE START!
        """
        CREATE TABLE IF NOT EXISTS spotify_generation_results (
            id SERIAL PRIMARY KEY,
            title VARCHAR(500) NOT NULL,
            output_path VARCHAR(1000) NOT NULL,
            item_name VARCHAR(500),
            genres JSON,
            all_genres JSON,
            style_elements JSON,
            mood VARCHAR(1000),
            energy_level VARCHAR(50),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            spotify_url VARCHAR(1000),
            lora_name VARCHAR(200),
            lora_type VARCHAR(20),
            lora_url VARCHAR(1000),
            user_id INTEGER
        );
        """,
        
        # Add foreign keys
        """
        ALTER TABLE spotify_login_sessions 
        ADD CONSTRAINT fk_login_sessions_user_id 
        FOREIGN KEY (user_id) REFERENCES spotify_users(id) ON DELETE CASCADE;
        """,
        
        """
        ALTER TABLE spotify_generation_results 
        ADD CONSTRAINT fk_generation_results_user_id 
        FOREIGN KEY (user_id) REFERENCES spotify_users(id) ON DELETE SET NULL;
        """,
        
        # Create indexes
        """
        CREATE INDEX IF NOT EXISTS idx_users_email ON spotify_users(email);
        CREATE INDEX IF NOT EXISTS idx_users_spotify_id ON spotify_users(spotify_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_token ON spotify_login_sessions(session_token);
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON spotify_login_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_oauth_state ON spotify_oauth_states(state);
        CREATE INDEX IF NOT EXISTS idx_generation_user_id ON spotify_generation_results(user_id);
        """
    ]
    
    with db.engine.connect() as connection:
        for i, sql in enumerate(sql_commands):
            try:
                connection.execute(text(sql))
                print(f"✓ SQL command {i+1} executed successfully")
            except Exception as e:
                print(f"❌ SQL command {i+1} failed: {e}")
                # For foreign keys and indexes, failures are often OK (already exist)
                if "foreign key" not in str(e).lower() and "index" not in str(e).lower():
                    raise
        
        connection.commit()
        print("✓ All tables created successfully")

@app.route("/admin/create-tables")
def admin_create_tables():
    """Admin route to manually create tables - SQLAlchemy 2.0+ compatible"""
    try:
        with app.app_context():
            print("🔨 Manual table creation started...")
            
            # Use the updated function with correct sizes
            create_tables_manually_with_correct_sizes()
            
            return jsonify({
                "success": True,
                "message": "Tables created successfully with correct column sizes!"
            })
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Table creation error: {e}")
        print(f"Full traceback: {error_details}")
        
        return jsonify({
            "success": False,
            "error": str(e),
            "details": error_details
        }), 500

if __name__ == '__main__':
    # For Render deployment
    print("🚀 Starting Spotify Cover Generator for Render")
    
    # Initialize the app
    if initialize_app():
        print("✅ Application initialized successfully")
    else:
        print("⚠️ Application initialization had issues, but continuing...")
    
    # Render uses the PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)