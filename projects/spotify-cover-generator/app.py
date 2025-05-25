import os
import sys
import random
import json
import datetime
from datetime import timedelta
from flask import Flask, request, render_template, send_from_directory, jsonify, session, redirect, url_for, flash
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
    from config import BASE_DIR, COVERS_DIR, FLASK_SECRET_KEY, SPOTIFY_DB_URL, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
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
        if 'user_id' not in session:
            session_token = request.cookies.get('session_token')
            if session_token:
                user = LoginSession.get_user_from_session(session_token)
                if user:
                    session['user_id'] = user.id
                    session['username'] = user.username or user.display_name
                else:
                    flash("Your session has expired. Please log in again.", "info")
                    return redirect(url_for('login'))
            else:
                flash("Please log in to access this page.", "info")
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get current logged in user"""
    if 'user_id' not in session:
        session_token = request.cookies.get('session_token')
        if session_token:
            user = LoginSession.get_user_from_session(session_token)
            if user:
                session['user_id'] = user.id
                # Optionally, store more user info in session if frequently accessed
                # session['username'] = user.username or user.display_name 
                return user
        return None
    
    # Optimization: Check if user object is already cached in session or g
    # For now, simple DB query
    try:
        return User.query.get(session['user_id'])
    except Exception as e:
        print(f"Error fetching user by ID from session: {e}")
        # Clear potentially invalid session user_id
        session.pop('user_id', None)
        session.pop('username', None)
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
        
        # Update generation results table
        """
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'spotify_generation_results' 
                AND column_name = 'user_id'
            ) THEN
                ALTER TABLE spotify_generation_results 
                ADD COLUMN user_id INTEGER;
            END IF;
        END $$;
        """,
        
        # Add foreign keys after tables exist
        """
        DO $$
        BEGIN
            -- Add foreign key for login_sessions if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints 
                WHERE constraint_name = 'fk_login_sessions_user_id'
            ) THEN
                ALTER TABLE spotify_login_sessions 
                ADD CONSTRAINT fk_login_sessions_user_id 
                FOREIGN KEY (user_id) REFERENCES spotify_users(id) ON DELETE CASCADE;
            END IF;
            
            -- Add foreign key for generation_results if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints 
                WHERE constraint_name = 'fk_generation_results_user_id'
            ) THEN
                ALTER TABLE spotify_generation_results 
                ADD CONSTRAINT fk_generation_results_user_id 
                FOREIGN KEY (user_id) REFERENCES spotify_users(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """,
        
        # Create indexes
        """
        CREATE INDEX IF NOT EXISTS idx_users_email ON spotify_users(email);
        CREATE INDEX IF NOT EXISTS idx_users_spotify_id ON spotify_users(spotify_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_token ON spotify_login_sessions(session_token);
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON spotify_login_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_oauth_state ON spotify_oauth_states(state);
        """
    ]
    
    # Use SQLAlchemy 2.0+ syntax
    with db.engine.connect() as connection:
        for i, sql in enumerate(sql_commands):
            try:
                connection.execute(text(sql))
                connection.commit()
                print(f"✓ SQL command {i+1} executed successfully")
            except Exception as e:
                print(f"❌ SQL command {i+1} failed: {e}")
                raise

def get_or_create_guest_session():
    """Get or create a guest session for anonymous users"""
    if 'guest_session_id' not in session:
        session['guest_session_id'] = str(uuid.uuid4())
        session['guest_created'] = datetime.datetime.utcnow().isoformat()
        session['guest_generations_today'] = 0
        session['guest_last_generation'] = None
    return session['guest_session_id']

def get_guest_generations_today():
    """Get number of generations for guest today"""
    if 'guest_session_id' not in session:
        return 0
    
    # Check if it's a new day
    if 'guest_last_generation' in session and session['guest_last_generation']:
        last_gen = datetime.datetime.fromisoformat(session['guest_last_generation'])
        if last_gen.date() != datetime.datetime.utcnow().date():
            session['guest_generations_today'] = 0
    
    return session.get('guest_generations_today', 0)

def increment_guest_generations():
    """Increment guest generation count"""
    session['guest_generations_today'] = get_guest_generations_today() + 1
    session['guest_last_generation'] = datetime.datetime.utcnow().isoformat()

def can_guest_generate():
    """Check if guest can generate (limit: 1 per day)"""
    return get_guest_generations_today() < 1

# Enhanced guest session cleanup (run periodically)
def cleanup_expired_guest_sessions():
    """Clean up old guest session data (call this periodically)"""
    try:
        # This would be more robust with Redis or database storage
        # For now, sessions auto-expire with Flask's built-in session management
        pass
    except Exception as e:
        print(f"Error cleaning up guest sessions: {e}")

# IP-based rate limiting for guests (alternative approach)
def check_ip_generation_limit(ip_address):
    """Check if IP has exceeded daily generation limit"""
    try:
        import datetime
        from datetime import timedelta
        import json
        from pathlib import Path
        
        # Simple file-based tracking (use Redis in production)
        ip_log_file = Path("ip_generations.json")
        
        today = datetime.datetime.now().date().isoformat()
        
        # Load existing data
        ip_data = {}
        if ip_log_file.exists():
            with open(ip_log_file, 'r') as f:
                ip_data = json.load(f)
        
        # Clean old data
        for ip in list(ip_data.keys()):
            if ip_data[ip].get('date') != today:
                del ip_data[ip]
        
        # Check current IP
        if ip_address not in ip_data:
            ip_data[ip_address] = {'date': today, 'count': 0}
        
        current_count = ip_data[ip_address]['count']
        
        # Save data
        with open(ip_log_file, 'w') as f:
            json.dump(ip_data, f)
        
        return current_count < 3  # Max 3 per IP per day
        
    except Exception as e:
        print(f"Error checking IP limit: {e}")
        return True  # Allow on error

def increment_ip_generation_count(ip_address):
    """Increment generation count for IP"""
    try:
        import json
        from pathlib import Path
        import datetime
        
        ip_log_file = Path("ip_generations.json")
        today = datetime.datetime.now().date().isoformat()
        
        # Load existing data
        ip_data = {}
        if ip_log_file.exists():
            with open(ip_log_file, 'r') as f:
                ip_data = json.load(f)
        
        # Update count
        if ip_address not in ip_data:
            ip_data[ip_address] = {'date': today, 'count': 0}
        
        ip_data[ip_address]['count'] += 1
        
        # Save data
        with open(ip_log_file, 'w') as f:
            json.dump(ip_data, f)
            
    except Exception as e:
        print(f"Error incrementing IP count: {e}")

# Updated get_current_user_or_guest with IP limiting
def get_current_user_or_guest():
    """Get current logged in user or return guest info with IP-based limiting"""
    user = get_current_user()
    if user:
        return {
            'type': 'user',
            'user': user,
            'display_name': user.display_name or user.username,
            'is_premium': user.is_premium_user(),
            'daily_limit': user.get_daily_generation_limit(),
            'generations_today': user.get_generations_today(),
            'can_generate': user.can_generate_today(),
            'can_use_loras': True,
            'can_edit_playlists': bool(user.spotify_access_token),
            'show_upload': user.is_premium_user()
        }
    else:
        # Guest user with combined session + IP limiting
        get_or_create_guest_session()
        ip_address = request.remote_addr or '127.0.0.1'
        
        # Check both session and IP limits
        session_can_generate = can_guest_generate()
        ip_can_generate = check_ip_generation_limit(ip_address)
        
        return {
            'type': 'guest',
            'user': None,
            'display_name': 'Guest',
            'is_premium': False,
            'daily_limit': 1, # Guest session limit
            'generations_today': get_guest_generations_today(),
            'can_generate': session_can_generate and ip_can_generate,
            'can_use_loras': False,
            'can_edit_playlists': False,
            'show_upload': False,
            'ip_address': ip_address
        }

# Enhanced generation tracking for guests
def track_guest_generation():
    """Track generation for both session and IP"""
    try:
        # Session tracking
        increment_guest_generations()
        
        # IP tracking
        ip_address = request.remote_addr or '127.0.0.1'
        increment_ip_generation_count(ip_address)
        
    except Exception as e:
        print(f"Error tracking guest generation: {e}")

# Update the root route
@app.route("/")
def root():
    """Root route - redirect to login if not authenticated, otherwise to main app"""
    user = get_current_user()
    if user:
        return redirect(url_for('generate')) # Fixed: redirect to 'generate'
    else:
        return redirect(url_for('login'))

@app.route("/generate", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"]) # Limit POST requests specifically for this route
def generate(): # Renamed from 'index' to 'generate'
    global initialized
    
    # Get user or guest info
    user_info = get_current_user_or_guest()
    
    if request.method == "POST" and not user_info['can_generate']:
        return render_template(
            "index.html",
            error=f"Daily generation limit reached ({user_info['daily_limit']} per day). " + 
                  ("Try again tomorrow!" if user_info['type'] == 'guest' else "Try again tomorrow or upgrade to premium!"),
            loras=[],
            user_info=user_info
        )
    
    if not initialized:
        if initialize_app():
            print("Application initialized successfully from index route")
        else:
            print("Failed to initialize application from index route")
            return render_template(
                "index.html", 
                error="Application is still initializing or encountered an issue. Please try again in a moment.",
                loras=[],
                user_info=user_info
            )
    
    # Get available loras (only for logged-in users)
    loras = []
    if user_info['can_use_loras']:
        try:
            if 'utils_available' in globals() and utils_available:
                import utils
                loras = utils.get_available_loras()
        except Exception as e:
            print(f"⚠️ Error getting LoRAs: {e}")

    if request.method == "POST":
        try:
            # Check if core generation modules are available
            generation_available = (
                'generator_available' in globals() and generator_available and
                'spotify_client_available' in globals() and spotify_client_available
            )
            
            if not generation_available:
                try:
                    import generator
                    import spotify_client
                    generation_available = True
                    print("✓ Generation modules imported on demand")
                except ImportError as e:
                    print(f"⚠️ Core generation modules not available: {e}")
                    return render_template(
                        "index.html",
                        error="Core generation modules are not available. The system is still starting up - please try again in a moment.",
                        loras=loras,
                        user_info=user_info
                    )
            
            playlist_url = request.form.get("playlist_url")
            user_mood = request.form.get("mood", "").strip()
            negative_prompt = request.form.get("negative_prompt", "").strip()
            lora_name = request.form.get("lora_name", "").strip()
            
            # Restrict LoRA usage for guests
            if user_info['type'] == 'guest' and lora_name and lora_name != "none":
                return render_template(
                    "index.html", 
                    error="LoRA styles are only available for registered users. Please sign up for free to access advanced features!",
                    loras=[],
                    user_info=user_info
                )
            
            lora_input = None
            if lora_name and lora_name != "none" and user_info['can_use_loras']:
                for lora_item in loras:
                    if hasattr(lora_item, 'name') and lora_item.name == lora_name:
                        lora_input = lora_item
                        break
            
            if not playlist_url:
                return render_template(
                    "index.html", 
                    error="Please enter a Spotify playlist or album URL.",
                    loras=loras,
                    user_info=user_info
                )
            
            # Generate the cover
            import generator
            user_id = user_info['user'].id if user_info['type'] == 'user' else None
            result = generator.generate_cover(playlist_url, user_mood, lora_input, 
                                            negative_prompt=negative_prompt, user_id=user_id) 
            
            if "error" in result:
                return render_template(
                    "index.html", 
                    error=result["error"],
                    loras=loras,
                    user_info=user_info
                )
            
            # Increment generation count
            if user_info['type'] == 'guest':
                # Use the new enhanced tracking
                track_guest_generation()
            
            img_filename = os.path.basename(result["output_path"])
            
            # Generate charts with fallback
            genres_chart_data = None
            genre_percentages_data = []
            
            try:
                import chart_generator
                genres_chart_data = chart_generator.generate_genre_chart(result.get("all_genres", []))
            except ImportError:
                print("⚠️ chart_generator not available, skipping genre chart.")
            except Exception as e:
                print(f"⚠️ Error generating genre chart: {e}")

            try:
                if 'utils_available' in globals() and utils_available:
                    import utils
                    genre_percentages_data = utils.calculate_genre_percentages(result.get("all_genres", []))
                else:
                    genre_percentages_data = calculate_genre_percentages(result.get("all_genres", []))
            except Exception as e:
                print(f"⚠️ Error calculating genre percentages: {e}")            # Extract playlist ID with fallback
            playlist_id = None
            try:
                if 'utils_available' in globals() and utils_available:
                    import utils
                    playlist_id = utils.extract_playlist_id(playlist_url) if playlist_url and "playlist/" in playlist_url else None
                else:
                    playlist_id = extract_playlist_id(playlist_url) if playlist_url and "playlist/" in playlist_url else None
            except Exception as e:
                print(f"⚠️ Error extracting playlist ID: {e}")
            
            display_data = {
                "title": result["title"],
                "image_file": img_filename,
                "image_data_base64": result.get("image_data_base64", ""),
                "genres": ", ".join(result.get("genres", [])),
                "mood": result.get("mood", ""),
                "playlist_name": result.get("item_name", "Your Music"),
                "found_genres": bool(result.get("genres", [])),
                "genres_chart": genres_chart_data,
                "genre_percentages": genre_percentages_data,
                "playlist_url": playlist_url,
                "user_mood": user_mood,
                "negative_prompt": negative_prompt,
                "lora_name": result.get("lora_name", ""),
                "lora_type": result.get("lora_type", ""),
                "lora_url": result.get("lora_url", ""),
                "user_info": user_info,
                "user": user_info.get('user'),  # Add user object for template compatibility
                "can_edit_playlist": user_info['can_edit_playlists'],
                "playlist_id": playlist_id
            }
            
            # Record generation if user is logged in
            if user_info['type'] == 'user':
                try:
                    new_generation = GenerationResultDB(
                        title=result["title"],
                        output_path=result["output_path"],
                        item_name=result.get("item_name"),
                        genres=result.get("genres"),
                        all_genres=result.get("all_genres"),
                        mood=user_mood,
                        spotify_url=playlist_url,
                        lora_name=result.get("lora_name"),
                        user_id=user_info['user'].id
                    )
                    db.session.add(new_generation)
                    db.session.commit()
                except Exception as e:
                    print(f"⚠️ Error saving generation result to DB: {e}")

            return render_template("result.html", **display_data)
            
        except Exception as e:
            print(f"❌ Server error processing request: {e}")
            import traceback
            traceback.print_exc()
            return render_template(
                "index.html", 
                error=f"An unexpected error occurred: {str(e)}. Please try again.",
                loras=loras,
                user_info=user_info
            )
    else:
        return render_template("index.html", loras=loras, user_info=user_info)

@app.route('/api/playlist/edit', methods=['POST'])
@login_required
def edit_playlist():
    """Edit Spotify playlist title and description"""
    try:
        user = get_current_user()
        if not user or not user.spotify_access_token:
            return jsonify({"success": False, "error": "Spotify not connected"}), 401
        
        # Refresh token if needed
        if not user.refresh_spotify_token_if_needed():
            return jsonify({"success": False, "error": "Failed to refresh Spotify token"}), 401
        
        data = request.get_json()
        playlist_id = data.get('playlist_id')
        name = data.get('name')
        description = data.get('description', '')
        
        if not playlist_id or not name:
            return jsonify({"success": False, "error": "Missing playlist ID or name"}), 400
        
        # Update playlist using Spotify API
        headers = {'Authorization': f'Bearer {user.spotify_access_token}'}
        url = f'https://api.spotify.com/v1/playlists/{playlist_id}'
        
        payload = {
            'name': name,
            'description': description
        }
        
        response = requests.put(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return jsonify({"success": True, "message": "Playlist updated successfully"})
        else:
            error_msg = "Failed to update playlist"
            if response.status_code == 403:
                error_msg = "You don\'t have permission to edit this playlist"
            elif response.status_code == 404:
                error_msg = "Playlist not found"
            
            return jsonify({"success": False, "error": error_msg}), response.status_code
    
    except Exception as e:
        print(f"Error editing playlist: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@app.route('/api/playlist/cover', methods=['POST']) 
@login_required
def update_playlist_cover():
    """Update Spotify playlist cover image"""
    try:
        user = get_current_user()
        if not user or not user.spotify_access_token:
            return jsonify({"success": False, "error": "Spotify not connected"}), 401
        
        # Refresh token if needed
        if not user.refresh_spotify_token_if_needed():
            return jsonify({"success": False, "error": "Failed to refresh Spotify token"}), 401
        
        data = request.get_json()
        playlist_id = data.get('playlist_id')
        image_data = data.get('image_data')
        
        if not playlist_id or not image_data:
            return jsonify({"success": False, "error": "Missing playlist ID or image data"}), 400
        
        # Extract base64 data from data URL
        if image_data.startswith('data:image'):
            # Remove data URL prefix
            image_data = image_data.split(',')[1]
        
        # Update playlist cover using Spotify API
        headers = {
            'Authorization': f'Bearer {user.spotify_access_token}',
            'Content-Type': 'image/jpeg'
        }
        url = f'https://api.spotify.com/v1/playlists/{playlist_id}/images'
        
        # Decode base64 image
        import base64
        image_bytes = base64.b64decode(image_data)
        
        response = requests.put(url, headers=headers, data=image_bytes)
        
        if response.status_code == 202:  # Spotify returns 202 for successful image upload
            return jsonify({"success": True, "message": "Playlist cover updated successfully"})
        else:
            error_msg = "Failed to update playlist cover"
            if response.status_code == 403:
                error_msg = "You don\'t have permission to edit this playlist"
            elif response.status_code == 404:
                error_msg = "Playlist not found"
            elif response.status_code == 413:
                error_msg = "Image too large (max 256KB)"
            
            return jsonify({"success": False, "error": error_msg}), response.status_code
    
    except Exception as e:
        print(f"Error updating playlist cover: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@app.route('/api/regenerate', methods=['POST'])
@login_required
def regenerate_cover():
    """Regenerate cover with same playlist"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "User not authenticated"}), 401
        
        if not user.can_generate_today():
            return jsonify({"success": False, "error": "Daily generation limit reached"}), 429
        
        data = request.get_json()
        playlist_url = data.get('playlist_url')
        mood = data.get('mood', '')
        negative_prompt = data.get('negative_prompt', '')
        lora_name = data.get('lora_name', '')
        
        if not playlist_url:
            return jsonify({"success": False, "error": "Missing playlist URL"}), 400
        
        # Get LoRA if specified
        lora_input = None
        if lora_name and lora_name != "none":
            try:
                import utils
                loras = utils.get_available_loras()
                for lora_item in loras:
                    if hasattr(lora_item, 'name') and lora_item.name == lora_name:
                        lora_input = lora_item
                        break
            except Exception as e:
                print(f"Error getting LoRA: {e}")
        
        # Generate new cover
        try:
            import generator
            result = generator.generate_cover(
                playlist_url, 
                mood, 
                lora_input, 
                negative_prompt=negative_prompt, 
                user_id=user.id
            )
            
            if "error" in result:
                return jsonify({"success": False, "error": result["error"]}), 400
            
            # Return all relevant data for the frontend to update
            return jsonify({
                "success": True, 
                "message": "Cover regenerated successfully",
                "title": result["title"],
                "image_file": os.path.basename(result["output_path"]),
                "image_data_base64": result.get("image_data_base64", ""),
                "genres": ", ".join(result.get("genres", [])),
                "mood": result.get("mood", ""),
                "playlist_name": result.get("item_name", "Your Music"),
                "found_genres": bool(result.get("genres", [])),
                "lora_name": result.get("lora_name", ""),
                "lora_type": result.get("lora_type", ""),
                "lora_url": result.get("lora_url", "")            })
            
        except Exception as e:
            print(f"Error generating cover: {e}")
            return jsonify({"success": False, "error": "Failed to generate cover"}), 500
            
    except Exception as e:
        print(f"Error in regenerate endpoint: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@app.route('/api/upload_lora', methods=['POST'])
@login_required
@limiter.limit("5 per hour")  # Limit uploads
def upload_lora():
    """Upload LoRA file (Premium users only)"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "User not authenticated"}), 401
        
        # Check if user is premium (only premium users can upload files)
        if not user.is_premium_user():
            return jsonify({"success": False, "error": "File uploads are only available for premium users. Use URL-based LoRAs instead."}), 403
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400
        
        # Validate file extension
        filename = secure_filename(file.filename)
        if not filename.lower().endswith(('.safetensors', '.ckpt', '.pt')):
            return jsonify({"success": False, "error": "Invalid file type. Only .safetensors, .ckpt, and .pt files are allowed."}), 400
        
        # Get name without extension for database
        lora_name = filename.rsplit('.', 1)[0]
        
        # Check if LoRA with this name already exists
        existing = LoraModelDB.query.filter_by(name=lora_name).first()
        if existing:
            return jsonify({"success": False, "error": f"LoRA with name '{lora_name}' already exists"}), 400
        
        # Handle file storage based on environment
        if os.getenv("RENDER"):
            # On Render, files are ephemeral - return error with suggestion
            return jsonify({
                "success": False, 
                "error": "File uploads are not supported on this hosting platform. Please use URL-based LoRAs from Civitai or HuggingFace instead."
            }), 400
        
        # Save file locally (for local development)
        from config import LORA_DIR
        LORA_DIR.mkdir(exist_ok=True)
        
        file_path = LORA_DIR / filename
        file.save(str(file_path))
        
        # Add to database
        new_lora = LoraModelDB(
            name=lora_name,
            source_type="local",
            path=str(file_path),
            url="",
            trigger_words=[],
            strength=0.7
        )
        
        db.session.add(new_lora)
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"LoRA '{lora_name}' uploaded successfully"
        })
        
    except Exception as e:
        print(f"Error uploading LoRA: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@app.route('/api/add_lora_link', methods=['POST'])
@login_required
@limiter.limit("10 per hour")  # Allow more URL-based additions
def add_lora_link():
    """Add LoRA via URL (available for all registered users)"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "User not authenticated"}), 401
        
        data = request.get_json()
        name = data.get('name', '').strip()
        url = data.get('url', '').strip()
        trigger_words = data.get('trigger_words', [])
        strength = float(data.get('strength', 0.7))
        
        if not name or not url:
            return jsonify({"success": False, "error": "Name and URL are required"}), 400
        
        # Use the utility function to add the LoRA
        from utils import add_lora_link
        success, message = add_lora_link(name, url, trigger_words, strength)
        
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"success": False, "error": message}), 400
            
    except Exception as e:
        print(f"Error adding LoRA link: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@app.route("/generated_covers/<path:filename>")
def serve_image(filename):
    return send_from_directory(COVERS_DIR, filename)

# Add this route for checking generation status
@app.route('/api/generation-status')
def generation_status():
    """API endpoint to check generation status"""
    user_info = get_current_user_or_guest()
    
    return jsonify({
        'type': user_info['type'],
        'can_generate': user_info['can_generate'],
        'generations_today': user_info['generations_today'],
        'daily_limit': user_info['daily_limit'],
        'display_name': user_info['display_name']
    })

# Guest conversion tracking
def track_guest_conversion():
    """Track when guests sign up (for analytics)"""
    try:
        if 'guest_session_id' in session:
            guest_id = session['guest_session_id']
            # Log conversion event (implement your analytics here)
            print(f"Guest {guest_id} converted to user account")
            
            # Clear guest session
            session.pop('guest_session_id', None)
            session.pop('guest_generations_today', None)
            session.pop('guest_last_generation', None)
            
    except Exception as e:
        print(f"Error tracking conversion: {e}")

# Update the register route
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Updated register route with conversion tracking"""
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not email or not username or not password:
            flash('All fields are required.', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return redirect(url_for('register'))

        # Create new user
        password_hash = generate_password_hash(password)
        new_user = User(
            email=email, 
            username=username, 
            display_name=username,
            password_hash=password_hash
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            
            # After successful user creation, track conversion
            track_guest_conversion()
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            print(f"Error creating user: {e}")
            flash('Registration failed. Please try again.', 'error')
            return redirect(url_for('register'))
        
    return render_template('register.html', user_info=get_current_user_or_guest())

# Optional: Analytics tracking
def log_generation_analytics(user_info, success=True):
    """Log generation analytics"""
    try:
        analytics_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'user_type': user_info['type'],
            'success': success,
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', '')[:200],  # Truncate
        }
        
        # Add to your analytics system here
        # For now, just log to console
        print(f"Analytics: {analytics_data}")
        
    except Exception as e:
        print(f"Error logging analytics: {e}")

# Add this function to check system health
@app.route('/api/system-status')
def system_status():
    """Check system status and availability"""
    try:
        # Check if core systems are working
        # Ensure config variables are loaded, use os.environ.get as fallback
        SPOTIFY_CLIENT_ID_STATUS = bool(os.environ.get('SPOTIFY_CLIENT_ID') or (globals().get('SPOTIFY_CLIENT_ID')))
        SPOTIFY_CLIENT_SECRET_STATUS = bool(os.environ.get('SPOTIFY_CLIENT_SECRET') or (globals().get('SPOTIFY_CLIENT_SECRET')))
        GEMINI_API_KEY_STATUS = bool(os.environ.get('GEMINI_API_KEY') or (globals().get('GEMINI_API_KEY')))
        STABILITY_API_KEY_STATUS = bool(os.environ.get('STABILITY_API_KEY') or (globals().get('STABILITY_API_KEY')))

        status = {
            'status': 'healthy',
            'spotify_api': SPOTIFY_CLIENT_ID_STATUS and SPOTIFY_CLIENT_SECRET_STATUS,
            'gemini_api': GEMINI_API_KEY_STATUS,
            'stability_api': STABILITY_API_KEY_STATUS,
            'database': False,
            'guest_mode': True # Assuming guest mode is always enabled
        }
        
        # Test database connection
        try:
            with db.engine.connect() as connection:
                connection.execute(text('SELECT 1'))
            status['database'] = True
        except Exception as db_err:
            print(f"Database connection test failed: {db_err}")
            status['database'] = False
        
        # Overall health check
        if not (status['spotify_api'] and status['gemini_api'] and status['stability_api'] and status['database']):
            status['status'] = 'degraded'
            if not status['database']:
                 print("System status degraded: Database connection failed.")
            if not (status['spotify_api'] and status['gemini_api'] and status['stability_api']):
                 print("System status degraded: One or more API keys are missing.")

        return jsonify(status)
        
    except Exception as e:
        print(f"Error in system_status: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login route - handle both form login and Spotify OAuth"""
    if request.method == 'POST':
        # Handle form-based login (if you have username/password)
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username and password:
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password_hash, password):
                # Create session
                session_token = secrets.token_urlsafe(32)
                login_session = LoginSession(
                    user_id=user.id,
                    session_token=session_token,
                    expires_at=datetime.datetime.utcnow() + timedelta(days=30),
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', '')
                )
                db.session.add(login_session)
                user.last_login = datetime.datetime.utcnow()
                db.session.commit()
                
                session['user_session'] = session_token
                flash('Logged in successfully!', 'success')
                return redirect(url_for('generate'))
            else:
                flash('Invalid username or password', 'error')
        else:
            flash('Please enter both username and password', 'error')
    
    # For GET requests or failed login, show login page
    return render_template('login.html', user_info=get_current_user_or_guest())

@app.route('/logout')
def logout():
    """Logout route"""
    if 'user_session' in session:
        # Mark session as inactive
        session_token = session['user_session']
        login_session = LoginSession.query.filter_by(session_token=session_token).first()
        if login_session:
            login_session.is_active = False
            db.session.commit()
        
        session.pop('user_session', None)
    
    # Clear guest session data as well
    session.pop('guest_session_id', None)
    session.pop('guest_created', None) 
    session.pop('guest_generations_today', None)
    session.pop('guest_last_generation', None)
    
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    # Get user statistics
    total_generations = GenerationResultDB.query.filter_by(user_id=user.id).count()
    generations_today = user.get_generations_today()
    daily_limit = user.get_daily_generation_limit()
    
    # Get recent generations
    recent_generations = (GenerationResultDB.query
                         .filter_by(user_id=user.id)
                         .order_by(GenerationResultDB.created_at.desc())
                         .limit(10)
                         .all())
    
    profile_data = {
        'user': user,
        'total_generations': total_generations,
        'generations_today': generations_today,
        'daily_limit': daily_limit,
        'can_generate': user.can_generate_today(),
        'recent_generations': recent_generations,
        'spotify_connected': bool(user.spotify_access_token),
        'is_premium': user.is_premium_user()
    }
    
    return render_template('profile.html', **profile_data, user_info=get_current_user_or_guest())

@app.route('/spotify-login')
def spotify_login():
    """Initiate Spotify OAuth flow"""
    if not SPOTIFY_CLIENT_ID:
        flash('Spotify integration is not configured', 'error')
        return redirect(url_for('generate'))
      # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    oauth_state = SpotifyState(state=state)
    db.session.add(oauth_state)
    db.session.commit()
    
    # Spotify OAuth parameters
    scope = 'playlist-read-private playlist-modify-public playlist-modify-private ugc-image-upload'
    redirect_uri = request.url_root.rstrip('/') + url_for('spotify_callback')
    
    auth_url = (
        'https://accounts.spotify.com/authorize?'
        f'client_id={SPOTIFY_CLIENT_ID}&'
        f'response_type=code&'
        f'redirect_uri={redirect_uri}&'
        f'scope={scope}&'
        f'state={state}'
    )
    
    return redirect(auth_url)

@app.route('/spotify-callback')
def spotify_callback():
    """Handle Spotify OAuth callback"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        if error:
            flash(f'Spotify authorization failed: {error}', 'error')
            return redirect(url_for('generate'))
        
        if not code or not state:
            flash('Invalid Spotify callback', 'error')
            return redirect(url_for('generate'))
          # Verify state
        oauth_state = SpotifyState.query.filter_by(state=state, used=False).first()
        if not oauth_state:
            flash('Invalid state parameter', 'error')
            return redirect(url_for('generate'))
        
        # Mark state as used
        oauth_state.used = True
        db.session.commit()
        
        # Exchange code for tokens
        redirect_uri = request.url_root.rstrip('/') + url_for('spotify_callback')
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': SPOTIFY_CLIENT_ID,
            'client_secret': SPOTIFY_CLIENT_SECRET
        }
        
        response = requests.post('https://accounts.spotify.com/api/token', data=token_data)
        
        if response.status_code != 200:
            flash('Failed to get Spotify tokens', 'error')
            return redirect(url_for('generate'))
        
        tokens = response.json()
        access_token = tokens['access_token']
        refresh_token = tokens.get('refresh_token')
        expires_in = tokens.get('expires_in', 3600)
        
        # Get user info from Spotify
        headers = {'Authorization': f'Bearer {access_token}'}
        user_response = requests.get('https://api.spotify.com/v1/me', headers=headers)
        
        if user_response.status_code != 200:
            flash('Failed to get Spotify user info', 'error')
            return redirect(url_for('generate'))
        
        spotify_user = user_response.json()
        spotify_id = spotify_user['id']
        
        # Find or create user
        user = User.query.filter_by(spotify_id=spotify_id).first()
        
        if not user:
            # Create new user
            user = User(
                spotify_id=spotify_id,
                spotify_username=spotify_user.get('id'),
                display_name=spotify_user.get('display_name', spotify_user.get('id')),
                email=spotify_user.get('email'),
                is_premium=spotify_user.get('product') == 'premium'
            )
            db.session.add(user)
        else:
            # Update existing user
            user.display_name = spotify_user.get('display_name', spotify_user.get('id'))
            user.email = spotify_user.get('email')
            user.is_premium = spotify_user.get('product') == 'premium'
        
        # Update tokens
        user.spotify_access_token = access_token
        user.spotify_refresh_token = refresh_token
        user.spotify_token_expires = datetime.datetime.utcnow() + timedelta(seconds=expires_in)
        user.last_login = datetime.datetime.utcnow()
        
        db.session.commit()
        
        # Create login session
        session_token = secrets.token_urlsafe(32)
        login_session = LoginSession(
            user_id=user.id,
            session_token=session_token,
            expires_at=datetime.datetime.utcnow() + timedelta(days=30),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        db.session.add(login_session)
        db.session.commit()
        
        session['user_session'] = session_token
        flash('Successfully connected to Spotify!', 'success')
        
        # Track conversion if they were a guest
        track_guest_conversion()
        
        return redirect(url_for('generate'))
        
    except Exception as e:
        print(f"Error in Spotify callback: {e}")
        flash('An error occurred during Spotify authorization', 'error')
        return redirect(url_for('generate'))

# Fix the result template reference to 'index'
@app.route('/index')
def index():
    """Redirect /index to /generate for backward compatibility"""
    return redirect(url_for('generate'))

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