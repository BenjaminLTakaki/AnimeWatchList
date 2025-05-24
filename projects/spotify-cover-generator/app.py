import os
import sys
import random
import json
import datetime
from flask import Flask, request, render_template, send_from_directory, jsonify, session, redirect, url_for, flash
from pathlib import Path
from urllib.parse import urlparse
from functools import wraps
import requests
import base64
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from sqlalchemy import text
from collections import Counter

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

# Initialize SQLAlchemy
from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy(app)

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
            self.spotify_token_expires <= datetime.datetime.utcnow() + datetime.timedelta(minutes=5)):
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
                self.spotify_token_expires = datetime.datetime.utcnow() + datetime.timedelta(
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
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        
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
        if oauth_state and oauth_state.created_at > datetime.datetime.utcnow() - datetime.timedelta(minutes=10):
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
            strength=self.strength
        )

class GenerationResultDB(db.Model):
    __tablename__ = 'spotify_generation_results'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    output_path = db.Column(db.String(500), nullable=False)
    item_name = db.Column(db.String(200))
    genres = db.Column(db.JSON)
    all_genres = db.Column(db.JSON)
    style_elements = db.Column(db.JSON)
    mood = db.Column(db.String(50))
    energy_level = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    spotify_url = db.Column(db.String(500))
    lora_name = db.Column(db.String(100))
    lora_type = db.Column(db.String(20))
    lora_url = db.Column(db.String(500))
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
    
    # Import modules with better error handling and absolute imports
    print("📦 Importing modules...")
    
    # Global variables to track what's available
    global spotify_client_available, models_available, utils_available, generator_available
    spotify_client_available = False
    models_available = False
    utils_available = False
    generator_available = False
    
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

# Also add this route to manually trigger table creation for debugging
@app.route("/admin/create-tables")
def admin_create_tables():
    """Admin route to manually create tables - SQLAlchemy 2.0+ compatible"""
    try:
        with app.app_context():
            print("🔧 Admin: Creating tables...")
            
            # Try SQLAlchemy first
            db.create_all()
            
            # Try manual creation
            create_tables_manually()
            
            # Verify
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            return jsonify({
                "success": True,
                "message": "Tables created successfully",
                "tables": tables
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Update your spotify_login route to ensure tables exist
@app.route('/login/spotify') # This is the route for initiating Spotify login
def spotify_login(): # Renamed from spotify_login_initiate to avoid confusion
    """Redirect to Spotify OAuth with table verification"""
    try:
        ensure_tables_exist() # Ensure tables are there before we create a state
        state = SpotifyState.create_state()
        scope = 'user-read-email user-read-private playlist-read-private playlist-modify-public playlist-modify-private ugc-image-upload'
        
        auth_url = (
            f"https://accounts.spotify.com/authorize?"
            f"client_id={SPOTIFY_CLIENT_ID}&"
            f"response_type=code&"
            f"redirect_uri={url_for('spotify_callback', _external=True)}&"
            f"state={state}&"
            f"scope={scope}"
        )
        return redirect(auth_url)
    except Exception as e:
        print(f"Error during Spotify login initiation: {e}")
        flash("Could not connect to Spotify. Please try again later.", "error")
        return redirect(url_for('login'))

# NEW AUTHENTICATION AND USER ROUTES
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Please fill in all fields', 'error')
            return render_template('auth/login.html')
        
        # Try to find user by email or username
        user = User.query.filter(
            (User.email == email) | (User.username == email)
        ).first()
        
        if user and user.check_password(password):
            # Create login session
            session_token = LoginSession.create_session(
                user.id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            # Set session
            session['user_id'] = user.id
            session['username'] = user.username or user.display_name
            
            # Set cookie for persistent login
            response = redirect(request.args.get('next') or url_for('index')) # Should redirect to new 'index' (now 'generate') or 'root'
            response.set_cookie('session_token', session_token, max_age=30*24*3600)  # 30 days
            
            # Update last login
            user.last_login = datetime.datetime.utcnow()
            db.session.commit()
            
            flash('Welcome back!', 'success')
            return response
        else:
            flash('Invalid email/username or password', 'error')
    
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page"""
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not all([email, username, password, confirm_password]):
            flash('Please fill in all fields', 'error')
            return render_template('auth/register.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return render_template('auth/register.html')
        
        if len(username) < 3:
            flash('Username must be at least 3 characters', 'error')
            return render_template('auth/register.html')
        
        # Check if user already exists
        existing_user = User.query.filter(
            (User.email == email) | (User.username == username)
        ).first()
        
        if existing_user:
            flash('Email or username already exists', 'error')
            return render_template('auth/register.html')
        
        # Create new user
        user = User(
            email=email,
            username=username,
            display_name=username
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Auto-login the user
        session_token = LoginSession.create_session(
            user.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        session['user_id'] = user.id
        session['username'] = user.username
        
        response = redirect(url_for('index')) # Should redirect to new 'index' (now 'generate') or 'root'
        response.set_cookie('session_token', session_token, max_age=30*24*3600)
        
        flash('Account created successfully! Welcome!', 'success')
        return response
    
    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    """Logout user"""
    # Clear session
    user_id = session.get('user_id')
    session.clear()
    
    # Invalidate session token
    session_token = request.cookies.get('session_token')
    if session_token:
        login_session = LoginSession.query.filter_by(session_token=session_token).first()
        if login_session:
            login_session.is_active = False
            db.session.commit()
    
    response = redirect(url_for('login'))
    response.set_cookie('session_token', '', expires=0)
    
    flash('You have been logged out', 'info')
    return response

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    user = get_current_user()
    if not user: # Should be caught by @login_required, but as a safeguard
        return redirect(url_for('login'))
    
    # Get user's recent generations
    recent_generations = GenerationResultDB.query.filter_by(
        user_id=user.id
    ).order_by(GenerationResultDB.timestamp.desc()).limit(10).all()
    
    return render_template('auth/profile.html', user=user, generations=recent_generations)

@app.route('/auth/spotify/callback')
def spotify_callback():
    """Handle Spotify OAuth callback"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        if error:
            flash(f'Spotify authorization failed: {error}', 'error')
            return redirect(url_for('login'))
        
        if not code or not state:
            flash('Missing authorization code or state', 'error')
            return redirect(url_for('login'))
        
        # Verify state
        if not SpotifyState.verify_and_use_state(state):
            flash('Invalid or expired authorization state', 'error')
            return redirect(url_for('login'))
        
        # Exchange code for access token
        auth_header = base64.b64encode(
            f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
        ).decode()
        
        headers = {
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': url_for('spotify_callback', _external=True) # Ensure this matches exactly what Spotify expects
        }
        
        response = requests.post(
            'https://accounts.spotify.com/api/token',
            headers=headers,
            data=data
        )
        
        if response.status_code != 200:
            flash(f'Failed to get Spotify access token. Status: {response.status_code}, Response: {response.text}', 'error')
            return redirect(url_for('login'))
        
        token_data = response.json()
        access_token = token_data['access_token']
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)
        
        # Get user info from Spotify
        user_info_headers = {'Authorization': f'Bearer {access_token}'}
        user_response = requests.get('https://api.spotify.com/v1/me', headers=user_info_headers)
        
        if user_response.status_code != 200:
            flash('Failed to get Spotify user info', 'error')
            return redirect(url_for('login'))
        
        spotify_user_data = user_response.json()
        spotify_id = spotify_user_data['id']
        display_name = spotify_user_data.get('display_name', spotify_id)
        email = spotify_user_data.get('email') # Email might not always be provided
        
        # Find or create user
        user = User.query.filter_by(spotify_id=spotify_id).first()
        
        if not user:
            # Check if user exists with same email, if email is provided by Spotify
            if email:
                user = User.query.filter_by(email=email).first()
                if user: # User with this email exists, link Spotify ID
                    user.spotify_id = spotify_id
                    user.spotify_username = spotify_id # Or display_name
            
            if not user: # Still no user, create a new one
                user = User(
                    spotify_id=spotify_id,
                    spotify_username=spotify_id, # Or display_name
                    display_name=display_name,
                    email=email # This might be None
                )
                db.session.add(user)
        
        # Update Spotify tokens and last login for the user
        user.spotify_access_token = access_token
        if refresh_token: # Spotify might not always return a new refresh token
            user.spotify_refresh_token = refresh_token
        user.spotify_token_expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)
        user.last_login = datetime.datetime.utcnow()
        if not user.display_name: # If display name was missing initially
            user.display_name = display_name
        if email and not user.email: # If email was missing initially
             user.email = email

        db.session.commit()
        
        # Create login session
        session_token = LoginSession.create_session(
            user.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        session['user_id'] = user.id
        session['username'] = user.display_name or user.spotify_username
        
        response = redirect(url_for('index')) # Should redirect to new 'index' (now 'generate') or 'root'
        response.set_cookie('session_token', session_token, max_age=30*24*3600)
        
        flash(f'Welcome, {display_name}!', 'success')
        return response
        
    except Exception as e:
        import traceback
        print(f"Spotify callback error: {e}\n{traceback.format_exc()}")
        flash('An error occurred during Spotify login. Please try again.', 'error')
        return redirect(url_for('login'))

# Add this route before your existing index route
@app.route("/")
def root():
    """Root route - redirect to login if not authenticated, otherwise to main app"""
    user = get_current_user()
    if user:
        return redirect(url_for('index')) # This should point to the main app page, now 'generate'
    else:
        return redirect(url_for('login'))

@app.route("/generate", methods=["GET", "POST"])
@login_required
def index():
    global initialized
    
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    if request.method == "POST" and not user.can_generate_today():
        return render_template(
            "index.html",
            error=f"Daily generation limit reached ({user.get_daily_generation_limit()} per day). Try again tomorrow!",
            loras=[],
            user=user
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
                user=user
            )
    
    # Get available loras with fallback
    loras = []
    try:
        if 'utils_available' in globals() and utils_available:
            import utils
            loras = utils.get_available_loras()
        else:
            print("⚠️ Utils not available - using empty LoRA list")
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
                # Try to import them again
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
                        user=user
                    )
            
            playlist_url = request.form.get("playlist_url")
            user_mood = request.form.get("mood", "").strip()
            negative_prompt = request.form.get("negative_prompt", "").strip()
            lora_name = request.form.get("lora_name", "").strip()
            
            lora_input = None
            if lora_name and lora_name != "none":
                for lora_item in loras:
                    if hasattr(lora_item, 'name') and lora_item.name == lora_name:
                        lora_input = lora_item
                        break
            
            if not playlist_url:
                return render_template(
                    "index.html", 
                    error="Please enter a Spotify playlist or album URL.",
                    loras=loras,
                    user=user
                )
            
            # Generate the cover
            import generator
            result = generator.generate_cover(playlist_url, user_mood, lora_input, 
                                            negative_prompt=negative_prompt, user_id=user.id) 
            
            if "error" in result:
                return render_template(
                    "index.html", 
                    error=result["error"],
                    loras=loras,
                    user=user
                )
            
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
                    # Fallback calculation
                    genre_percentages_data = calculate_genre_percentages(result.get("all_genres", []))
            except Exception as e:
                print(f"⚠️ Error calculating genre percentages: {e}")

            # Extract playlist ID with fallback
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
                "user": user,
                "can_edit_playlist": bool(user.spotify_access_token and user.refresh_spotify_token_if_needed()),
                "playlist_id": playlist_id
            }
            
            # Record generation if successful
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
                    user_id=user.id
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
                user=user
            )
    else:
        return render_template("index.html", loras=loras, user=user)

@app.route("/generated_covers/<path:filename>")
def serve_image(filename):
    try:
        print(f"Attempting to serve image: {filename} from {COVERS_DIR}")
        
        file_path = os.path.join(COVERS_DIR, filename)
        
        if os.path.exists(file_path):
            return send_from_directory(COVERS_DIR, filename)
        else:
            print(f"Image file not found: {file_path}")
            return send_from_directory(os.path.join(app.static_folder, "images"), "image-placeholder.png")
    except Exception as e:
        print(f"Error serving image {filename}: {e}")
        return send_from_directory(os.path.join(app.static_folder, "images"), "image-placeholder.png")

@app.route("/status")
def status():
    from spotify_client import sp
    from utils import get_available_loras
    
    return jsonify({
        "initialized": initialized,
        "spotify_working": sp is not None,
        "loras_available": len(get_available_loras())
    })

if __name__ == "__main__":
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