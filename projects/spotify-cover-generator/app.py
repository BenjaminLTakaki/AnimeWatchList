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
from collections import Counter # Added import

# Make sure the current directory is in the path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import app modules
from config import BASE_DIR, COVERS_DIR, FLASK_SECRET_KEY, SPOTIFY_DB_URL, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

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
    
    # Database setup (your existing database code works fine now)
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
                # Attempt manual creation if db.create_all() didn't get them all
                try:
                    create_tables_manually() # Assuming you have this function defined elsewhere
                    final_tables = inspector.get_table_names()
                    final_missing = [t for t in required_tables if t not in final_tables]
                    if final_missing:
                        print(f"❌ Manual creation also failed for: {', '.join(final_missing)}")
                        return False
                    else:
                        print("✓ Manual table creation successful for missing tables")
                except Exception as e_manual:
                    print(f"❌ Manual table creation attempt failed: {e_manual}")
                    return False # Stop if manual creation also fails
            else:
                print("✓ All required tables present")
                
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        return False
    
    # Import modules with better error handling
    try:
        print("📦 Importing modules...")
        
        # Try importing required modules with proper error handling
        try:
            from spotify_client import initialize_spotify
            print("✓ spotify_client imported")
        except ImportError as e:
            print(f"⚠️ spotify_client import failed: {e}")
            print("⚠️ Continuing without Spotify client - will handle this gracefully")
            initialize_spotify = lambda: False  # Dummy function
        
        try:
            from models import PlaylistData, GenreAnalysis, LoraModel
            print("✓ models imported")
        except ImportError as e:
            print(f"⚠️ models import failed: {e}")
            print("⚠️ Continuing without models - basic functionality only")
            # Define dummy classes or skip features if models are critical and missing
            
        try:
            from utils import generate_random_string, get_available_loras, extract_playlist_id, calculate_genre_percentages # Added missing imports
            print("✓ utils imported")
        except ImportError as e:
            print(f"⚠️ utils import failed: {e}")
            print("⚠️ Continuing without utils - limited functionality")
            get_available_loras = lambda: []  # Dummy function
            extract_playlist_id = lambda url: None # Dummy function
            calculate_genre_percentages = lambda genres: [] # Dummy function
            
        print("✓ Module imports completed (with fallbacks if needed)")
        
    except Exception as e:
        print(f"❌ Critical import failure: {e}")
        return False
    
    # Initialize Spotify client
    print("🎵 Initializing Spotify client...")
    try:
        spotify_initialized = initialize_spotify()
        if spotify_initialized:
            print("✓ Spotify client initialized")
        else:
            print("⚠️ Spotify client initialization failed - continuing anyway")
            spotify_initialized = False  # Continue even if Spotify fails
    except Exception as e:
        print(f"⚠️ Spotify initialization error: {e} - continuing anyway")
        spotify_initialized = False
    
    # Check environment variables
    print("🔑 Checking environment variables...")
    from config import GEMINI_API_KEY, STABILITY_API_KEY # Ensure these are imported
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
    
    # Be more lenient with initialization - allow partial success
    initialized = env_vars_present  # Don't require Spotify client for basic functionality
    
    if initialized:
        print("🎉 Application initialized successfully!")
    else:
        print("⚠️ Application initialization completed with issues")
    
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
@app.route('/login/spotify')
def spotify_login():
    """Redirect to Spotify OAuth with table verification"""
    try:
        # Ensure tables exist before creating state
        ensure_tables_exist()
        
        state = SpotifyState.create_state()
        
        auth_url = (
            "https://accounts.spotify.com/authorize"
            f"?client_id={SPOTIFY_CLIENT_ID}"
            "&response_type=code"
            f"&redirect_uri={request.url_root}auth/spotify/callback"
            "&scope=playlist-modify-public playlist-modify-private ugc-image-upload user-read-private user-read-email"
            f"&state={state}"
        )
        
        return redirect(auth_url)
    except Exception as e:
        print(f"❌ Spotify login error: {e}")
        flash('Database setup error. Please try again.', 'error')
        return redirect(url_for('login'))

# Authentication helpers
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if user is None:
            flash("Please log in to access this page.", "info")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    global initialized
    
    user = get_current_user() # get_current_user should be defined
    if not user: # Should be handled by @login_required, but good for safety
        return redirect(url_for('login'))
    
    if request.method == "POST" and not user.can_generate_today():
        # Ensure get_available_loras is available or has a fallback
        try:
            from utils import get_available_loras
            loras_fallback = get_available_loras()
        except ImportError:
            loras_fallback = []
        return render_template(
            "index.html",
            error=f"Daily generation limit reached ({user.get_daily_generation_limit()} per day). Try again tomorrow!",
            loras=loras_fallback, # Provide loras even in error case
            user=user
        )
    
    if not initialized:
        if initialize_app():
            print("Application initialized successfully from index route")
        else:
            print("Failed to initialize application from index route")
            # Ensure get_available_loras is available or has a fallback
            try:
                from utils import get_available_loras
                loras_fallback_init = get_available_loras()
            except ImportError:
                loras_fallback_init = []
            return render_template(
                "index.html", 
                error="Application is still initializing or encountered an issue. Please try again in a moment.",
                loras=loras_fallback_init, # Provide loras
                user=user
            )
    
    # Import modules with fallback handling
    try:
        from utils import get_available_loras, extract_playlist_id, calculate_genre_percentages # ensure all needed utils are here
        loras = get_available_loras()
    except ImportError:
        print("⚠️ Could not import get_available_loras from utils in index, using empty list")
        loras = []
        # Define dummy functions if these are critical and utils failed to import earlier
        if 'extract_playlist_id' not in globals():
            extract_playlist_id = lambda url: None
        if 'calculate_genre_percentages' not in globals():
            calculate_genre_percentages = lambda genres: []

    if request.method == "POST":
        try:
            # Check if required modules are available
            try:
                from generator import generate_cover
                from chart_generator import generate_genre_chart
            except ImportError as e:
                print(f"⚠️ Core generation modules not available: {e}")
                return render_template(
                    "index.html",
                    error="Core generation modules are not available. Please contact support or try again later.",
                    loras=loras,
                    user=user
                )
            
            playlist_url = request.form.get("playlist_url")
            user_mood = request.form.get("mood", "").strip()
            negative_prompt = request.form.get("negative_prompt", "").strip()
            lora_name = request.form.get("lora_name", "").strip()
            
            lora_input = None
            if lora_name and lora_name != "none":
                for lora_item in loras: # Iterate through lora_item from get_available_loras()
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
            
            # Ensure user_id is passed if your generate_cover expects it
            result = generate_cover(playlist_url, user_mood, lora_input, 
                                  negative_prompt=negative_prompt, user_id=user.id) 
            
            if "error" in result:
                return render_template(
                    "index.html", 
                    error=result["error"],
                    loras=loras,
                    user=user
                )
            
            img_filename = os.path.basename(result["output_path"])
            
            # Ensure chart_generator and calculate_genre_percentages are available
            genres_chart_data = None
            genre_percentages_data = []
            try:
                from chart_generator import generate_genre_chart
                genres_chart_data = generate_genre_chart(result.get("all_genres", []))
            except ImportError:
                print("⚠️ chart_generator not available, skipping genre chart.")
            except Exception as e_chart:
                print(f"⚠️ Error generating genre chart: {e_chart}")

            try:
                # calculate_genre_percentages should be imported from utils
                genre_percentages_data = calculate_genre_percentages(result.get("all_genres", []))
            except NameError: # If utils failed to import it
                 print("⚠️ calculate_genre_percentages not available, skipping percentages.")
            except Exception as e_percent:
                print(f"⚠️ Error calculating genre percentages: {e_percent}")

            
            display_data = {
                "title": result["title"],
                "image_file": img_filename,
                "image_data_base64": result.get("image_data_base64", ""),
                "genres": ", ".join(result.get("genres", [])),
                "mood": result.get("mood", ""),
                "playlist_name": result.get("item_name", "Your Music"),
                "found_genres": bool(result.get("genres", [])),
                "genres_chart": genres_chart_data, # Use the potentially None value
                "genre_percentages": genre_percentages_data, # Use the potentially empty list
                "playlist_url": playlist_url,
                "user_mood": user_mood,
                "negative_prompt": negative_prompt,
                "lora_name": result.get("lora_name", ""),
                "lora_type": result.get("lora_type", ""),
                "lora_url": result.get("lora_url", ""),
                "user": user,
                "can_edit_playlist": bool(user.spotify_access_token and user.refresh_spotify_token_if_needed()), # Check token validity
                "playlist_id": extract_playlist_id(playlist_url) if playlist_url and "playlist/" in playlist_url else None
            }
            
            # Record generation if successful
            try:
                new_generation = GenerationResultDB(
                    title=result["title"],
                    output_path=result["output_path"], # Store relative path or full, ensure consistency
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
            except Exception as e_db_save:
                print(f"⚠️ Error saving generation result to DB: {e_db_save}")
                # Decide if this is critical enough to show an error to the user

            return render_template("result.html", **display_data)
        except Exception as e:
            print(f"❌ Server error processing request in POST: {e}")
            import traceback
            traceback.print_exc()
            return render_template(
                "index.html", 
                error=f"An unexpected error occurred: {str(e)}. Please try again.",
                loras=loras, # Ensure loras is passed
                user=user
            )
    else: # GET request
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