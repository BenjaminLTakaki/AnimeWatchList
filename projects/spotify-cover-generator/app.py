import os
import sys
import random
import json
import datetime
from datetime import timezone # Added import
import traceback
import uuid 
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse
from functools import wraps
import hashlib # Added import

import requests
import base64
import secrets
from collections import Counter

from flask import (Flask, request, render_template, send_from_directory, jsonify,
                   session, redirect, url_for, flash, make_response)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from sqlalchemy import text, func # Added func

import spotify_client # Added import

# Monitoring and fault handling imports
try:
    from monitoring_system import (
        setup_monitoring, monitor_performance, monitor_api_calls,
        app_logger, alert_manager, system_monitor
    )
    from fault_handling import (
        fault_tolerant_api_call, GracefulDegradation, db_failover,
        create_user_friendly_error_messages, FaultContext, http_client
    )
    print("✅ Monitoring system imported successfully")
except ImportError as e:
    print(f"⚠️ Monitoring system import failed: {e}")
    # Define dummy decorators as fallback
    def monitor_performance(func):
        return func
    def monitor_api_calls(service_name):
        def decorator(func):
            return func
        return decorator
    def fault_tolerant_api_call(service_name, fallback_func):
        def decorator(func):
            return func
        return decorator

# Configuration imports or fallbacks
try:
    from config import (
        BASE_DIR, COVERS_DIR, FLASK_SECRET_KEY,
        SPOTIFY_DB_URL, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET,
        SPOTIFY_REDIRECT_URI
    )
    print("Config imported successfully")
except ImportError as e:
    print(f"Config import failed: {e}")
    BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
    COVERS_DIR = BASE_DIR / "generated_covers"
    FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-key')
    SPOTIFY_DB_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/test')
    SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
    SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
    SPOTIFY_REDIRECT_URI = os.environ.get('SPOTIFY_REDIRECT_URI', 'http://localhost:5000/spotify-callback')

if os.getenv('RENDER'):
    print("🔧 Render environment detected - running auto-migration...")
    try:
        # Import and run migration
        import subprocess
        result = subprocess.run([sys.executable, 'render_db_fix.py'], 
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("✅ Auto-migration completed successfully")
        else:
            print(f"⚠️ Auto-migration warnings: {result.stderr}")
    except Exception as e:
        print(f"⚠️ Auto-migration failed: {e}")
        
# Flask app initialization
app = Flask(__name__,
            template_folder=str(BASE_DIR / "templates"),
            static_folder=str(BASE_DIR / "static"))
app.secret_key = FLASK_SECRET_KEY or ''.join(random.choices(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=24))

# Configure proxy settings
# When deploying behind a reverse proxy (e.g., Nginx, Heroku, Render),
# this setting is crucial for Flask and extensions like Flask-Limiter
# to correctly identify the client's actual IP address from the
# X-Forwarded-For header. Set to the number of trusted proxies.
app.config['X_FORWARDED_FOR_TRUSTED_HOPS'] = 1 

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = SPOTIFY_DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"],
    storage_uri="memory://"
)
limiter.init_app(app)

# Models definition
class User(db.Model):
    __tablename__ = 'spotify_users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=True)
    password_hash = db.Column(db.String(200), nullable=True)
    spotify_id = db.Column(db.String(100), unique=True, nullable=True)
    spotify_username = db.Column(db.String(100), nullable=True)
    spotify_access_token = db.Column(db.String(500), nullable=True)
    spotify_refresh_token = db.Column(db.String(500), nullable=True)
    spotify_token_expires = db.Column(db.DateTime, nullable=True)
    display_name = db.Column(db.String(100), nullable=True)
    is_premium = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    generations = db.relationship('GenerationResultDB', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash and check_password_hash(self.password_hash, password))

    def is_premium_user(self):
        premium_emails = ['bentakaki7@gmail.com']
        premium_usernames = ['benthegamer']
        if self.email and self.email.lower() in premium_emails:
            return True
        if self.spotify_username and self.spotify_username.lower() in premium_usernames:
            return True
        if self.spotify_id and self.spotify_id.lower() in premium_usernames:
            return True
        return False

    def get_daily_generation_limit(self):
        return 999 if self.is_premium_user() else 2

    def can_generate_today(self):
        today = datetime.datetime.now(timezone.utc).date()
        count = GenerationResultDB.query.filter(
            GenerationResultDB.user_id == self.id,
            db.func.date(GenerationResultDB.timestamp) == today
        ).count()
        return count < self.get_daily_generation_limit()

    def get_generations_today(self):
        today = datetime.datetime.now(timezone.utc).date()
        return GenerationResultDB.query.filter(
            GenerationResultDB.user_id == self.id,
            db.func.date(GenerationResultDB.timestamp) == today
        ).count()

    def refresh_spotify_token_if_needed(self):
        if not self.spotify_refresh_token:
            return False
        if self.spotify_token_expires:
            spotify_token_expires_ts = self.spotify_token_expires
            if spotify_token_expires_ts.tzinfo is None:
                spotify_token_expires_ts = spotify_token_expires_ts.replace(tzinfo=timezone.utc)
            if spotify_token_expires_ts <= datetime.datetime.now(timezone.utc) + timedelta(minutes=5):
                return self._refresh_spotify_token()
        return True

    def _refresh_spotify_token(self):
        if not self.spotify_refresh_token:
            return False
        auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
        headers = {'Authorization': f'Basic {auth_header}', 'Content-Type': 'application/x-www-form-urlencoded'}
        data = {'grant_type': 'refresh_token', 'refresh_token': self.spotify_refresh_token}
        try:
            response = requests.post('https://accounts.spotify.com/api/token', headers=headers, data=data)
            if response.status_code == 200:
                token_data = response.json()
                self.spotify_access_token = token_data['access_token']
                self.spotify_token_expires = datetime.datetime.now(timezone.utc) + timedelta(seconds=token_data['expires_in'])
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
    created_at = db.Column(db.DateTime, default=lambda: datetime.datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    user = db.relationship('User', backref='sessions')

    @staticmethod
    def create_session(user_id, ip_address=None, user_agent=None):
        token = secrets.token_urlsafe(32)
        expires = datetime.datetime.now(timezone.utc) + timedelta(days=30)
        sess = LoginSession(
            user_id=user_id, session_token=token,
            expires_at=expires, ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(sess)
        db.session.commit()
        return token

    @staticmethod
    def get_user_from_session(session_token):
        sess = LoginSession.query.filter_by(session_token=session_token, is_active=True).first()

        if not sess:
            return None

        # Ensure expires_at is timezone-aware for comparison
        # This assumes 'timezone' and 'datetime' are imported, 
        # and 'db' is the SQLAlchemy instance.
        expires_at_aware = sess.expires_at
        if expires_at_aware.tzinfo is None:
            expires_at_aware = expires_at_aware.replace(tzinfo=timezone.utc)

        if expires_at_aware <= datetime.datetime.now(timezone.utc): # Session expired
            sess.is_active = False
            db.session.commit()
            return None
            
        return sess.user 

class SpotifyState(db.Model):
    __tablename__ = 'spotify_oauth_states'
    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.datetime.now(timezone.utc))
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
        if oauth_state:
            created_at_ts = oauth_state.created_at
            if created_at_ts.tzinfo is None:
                created_at_ts = created_at_ts.replace(tzinfo=timezone.utc)
            if created_at_ts > datetime.datetime.now(timezone.utc) - timedelta(minutes=10):
                oauth_state.used = True
                db.session.commit()
                return True
        return False

class LoraModelDB(db.Model):
    __tablename__ = 'spotify_lora_models'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    source_type = db.Column(db.String(20), default='local')  # Only 'local' now
    path = db.Column(db.String(500), default='')
    file_size = db.Column(db.Integer, default=0)  # File size in bytes
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.datetime.now(timezone.utc))
    uploaded_by = db.Column(db.Integer, db.ForeignKey('spotify_users.id'), nullable=True)
    
    def to_lora_model(self):
        from models import LoraModel
        return LoraModel(
            name=self.name,
            source_type=self.source_type,
            path=self.path,
            trigger_words=[],  # Can be extended later
            strength=0.7
        )

class GenerationResultDB(db.Model):
    __tablename__ = 'spotify_generation_results'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    output_path = db.Column(db.String(1000), nullable=False)
    item_name = db.Column(db.String(500))
    genres = db.Column(db.JSON)
    all_genres = db.Column(db.JSON)
    style_elements = db.Column(db.JSON)
    mood = db.Column(db.String(1000))
    energy_level = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    spotify_url = db.Column(db.String(1000))
    lora_name = db.Column(db.String(200))
    lora_type = db.Column(db.String(20))
    lora_url = db.Column(db.String(1000))
    user_id = db.Column(db.Integer, db.ForeignKey('spotify_users.id'), nullable=True)

class GuestIPGenerationLog(db.Model):
    __tablename__ = 'spotify_guest_ip_generation_log'
    ip_address_hash = db.Column(db.String(64), primary_key=True) # SHA256 hash
    last_generated_at = db.Column(db.DateTime, nullable=False)

    def __repr__(self):
        return f'<GuestIPGenerationLog {self.ip_address_hash}>'

# HELPER FUNCTIONS
def _hash_ip(ip_address):
    if not ip_address:
        return None
    return hashlib.sha256(ip_address.encode('utf-8')).hexdigest()

def can_guest_generate_by_ip(ip_address):
    hashed_ip = _hash_ip(ip_address)
    if not hashed_ip:
        return False # Or handle error appropriately

    log_entry = GuestIPGenerationLog.query.get(hashed_ip)
    if not log_entry:
        return True # Never generated before from this IP

    # Check if last_generated_at is from today
    # Make last_generated_at aware if it's naive
    last_gen_at_aware = log_entry.last_generated_at
    if last_gen_at_aware.tzinfo is None:
        last_gen_at_aware = last_gen_at_aware.replace(tzinfo=timezone.utc)

    if last_gen_at_aware.date() < datetime.datetime.now(timezone.utc).date():
        return True # Last generation was before today
    return False # Already generated today

def record_guest_generation_by_ip(ip_address):
    hashed_ip = _hash_ip(ip_address)
    if not hashed_ip:
        return # Or handle error

    log_entry = GuestIPGenerationLog.query.get(hashed_ip)
    now_utc = datetime.datetime.now(timezone.utc)
    if log_entry:
        log_entry.last_generated_at = now_utc
    else:
        log_entry = GuestIPGenerationLog(ip_address_hash=hashed_ip, last_generated_at=now_utc)
        db.session.add(log_entry)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error recording guest IP generation: {e}")
        # Potentially re-raise or handle more gracefully

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
    """Fixed get current logged in user function"""
    if 'user_id' in session:
        try:
            user = User.query.get(session['user_id'])
            if user and user.is_active:
                return user
        except Exception as e:
            print(f"Error fetching user by ID from session: {e}")
            session.pop('user_id', None)
    if 'user_session' in session:
        try:
            session_token = session['user_session']
            login_session = LoginSession.query.filter_by(
                session_token=session_token, 
                is_active=True
            ).first()
            if login_session:
                expires_at_ts = login_session.expires_at
                if expires_at_ts.tzinfo is None:
                    expires_at_ts = expires_at_ts.replace(tzinfo=timezone.utc)
                if expires_at_ts > datetime.datetime.now(timezone.utc):
                    user = login_session.user
                    if user and user.is_active:
                        session['user_id'] = user.id
                        return user
                else:
                    session.pop('user_session', None)
        except Exception as e:
            print(f"Error fetching user by session token: {e}")
            session.pop('user_session', None)
    session_token = request.cookies.get('session_token')
    if session_token:
        try:
            login_session = LoginSession.query.filter_by(
                session_token=session_token, 
                is_active=True
            ).first()
            if login_session:
                expires_at_ts = login_session.expires_at
                if expires_at_ts.tzinfo is None:
                    expires_at_ts = expires_at_ts.replace(tzinfo=timezone.utc)
                if expires_at_ts > datetime.datetime.now(timezone.utc):
                    user = login_session.user
                    if user and user.is_active:
                        session['user_id'] = user.id
                    return user
            else:
                session.pop('user_session', None)
        except Exception as e:
            print(f"Error fetching user by session token: {e}")
            session.pop('user_session', None)
    session_token = request.cookies.get('session_token')
    if session_token:
        try:
            login_session = LoginSession.query.filter_by(
                session_token=session_token, 
                is_active=True
            ).first()
            if login_session: # Check if login_session exists before accessing attributes
                expires_at_ts = login_session.expires_at
                if expires_at_ts.tzinfo is None:
                    expires_at_ts = expires_at_ts.replace(tzinfo=timezone.utc)
                if expires_at_ts > datetime.datetime.now(timezone.utc):
                    user = login_session.user
                    if user and user.is_active: # Check if user exists and is active
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
        if not isinstance(genres_list, list):
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
                "count": count
            })
        return percentages

def extract_playlist_id(playlist_url):
    """Extract playlist ID from Spotify URL"""
    if not playlist_url or "playlist/" not in playlist_url:
        return None
    try:
        path_part = urlparse(playlist_url).path
        if "/playlist/" in path_part:
            return path_part.split("/playlist/")[-1].split("/")[0]
    except Exception as e:
        print(f"Error parsing playlist URL '{playlist_url}': {e}")
    return None

def ensure_tables_exist():
    """Ensure tables exist before any database operation."""
    try:
        with app.app_context():
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM spotify_oauth_states LIMIT 1"))
    except Exception:
        print("⚠️ Tables missing or DB connection issue, attempting to create...")
        try:
            with app.app_context():
                db.create_all()
                print("✓ Tables created/verified on-demand.")
        except Exception as e_create:
            print(f"❌ On-demand table creation failed: {e_create}")

# Global initialization flag
initialized = False

def migrate_lora_table():
    """Migrate LoRA table to add missing columns"""
    try:
        with app.app_context():
            with db.engine.connect() as connection:
                # Check if columns exist first
                result = connection.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'spotify_lora_models'
                """))
                existing_columns = [row[0] for row in result]
                
                print(f"Existing columns in spotify_lora_models: {existing_columns}")
                
                # Add missing columns if they don't exist
                migrations = []
                
                if 'file_size' not in existing_columns:
                    migrations.append("ALTER TABLE spotify_lora_models ADD COLUMN file_size INTEGER DEFAULT 0")
                    
                if 'uploaded_at' not in existing_columns:
                    migrations.append("ALTER TABLE spotify_lora_models ADD COLUMN uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                    
                if 'uploaded_by' not in existing_columns:
                    migrations.append("ALTER TABLE spotify_lora_models ADD COLUMN uploaded_by INTEGER")
                
                # Remove old URL-related columns if they exist
                if 'url' in existing_columns:
                    migrations.append("ALTER TABLE spotify_lora_models DROP COLUMN IF EXISTS url CASCADE")
                    
                if 'trigger_words' in existing_columns:
                    migrations.append("ALTER TABLE spotify_lora_models DROP COLUMN IF EXISTS trigger_words CASCADE")
                    
                if 'strength' in existing_columns:
                    migrations.append("ALTER TABLE spotify_lora_models DROP COLUMN IF EXISTS strength CASCADE")
                
                # Execute migrations
                for migration in migrations:
                    try:
                        connection.execute(text(migration))
                        connection.commit()
                        print(f"✓ Executed: {migration}")
                    except Exception as e:
                        print(f"⚠️ Migration failed (might already exist): {migration} - {e}")
                          # Add foreign key constraint if it doesn't exist
                try:
                    # Check if constraint exists
                    constraint_exists = connection.execute(text("""
                        SELECT 1 FROM information_schema.table_constraints 
                        WHERE constraint_name = 'fk_lora_models_uploaded_by'
                    """)).fetchone()
                    
                    # Add constraint if it doesn't exist
                    if not constraint_exists:
                        connection.execute(text("""
                            ALTER TABLE spotify_lora_models 
                            ADD CONSTRAINT fk_lora_models_uploaded_by 
                            FOREIGN KEY (uploaded_by) REFERENCES spotify_users(id) ON DELETE SET NULL
                        """))
                        connection.commit()
                    print("✓ Foreign key constraint added/verified")                
                except Exception as e:
                    print(f"⚠️ Foreign key constraint warning: {e}")
                
                print("✅ LoRA table migration completed")
                return True
                
    except Exception as e:
        print(f"❌ LoRA table migration failed: {e}")
        return False

def initialize_app():
    """Initialize the application's dependencies (Render-optimized)"""
    global initialized

    print("🔧 Initializing Spotify Cover Generator on Render...")
    
    # Make sure necessary directories exist
    try:
        os.makedirs(COVERS_DIR, exist_ok=True)
        # For Render, use /tmp for temporary files
        if os.getenv('RENDER'):
            lora_dir = Path("/tmp/loras")
        else:
            lora_dir = BASE_DIR / "loras"
        os.makedirs(lora_dir, exist_ok=True)
        print("✓ Created directories")
    except Exception as e:
        print(f"⚠️ Directory creation warning: {e}")

    # Database setup
    try:
        with app.app_context():
            print("📊 Testing database connection...")
            
            # Test database connection
            try:
                with db.engine.connect() as connection:
                    connection.execute(text('SELECT 1'))
                print("✓ Database connection successful")
            except Exception as e:
                print(f"❌ Database connection failed: {e}")
                # On Render, try to continue anyway
                if os.getenv('RENDER'):
                    print("⚠️ Continuing on Render despite database warning...")
                else:
                    return False

            # Quick table check
            try:
                inspector = db.inspect(db.engine)
                existing_tables = inspector.get_table_names()
                required_tables = [
                    'spotify_users', 'spotify_login_sessions', 'spotify_oauth_states',
                    'spotify_generation_results', 'spotify_lora_models'
                ]
                missing_tables = [t for t in required_tables if t not in existing_tables]
                
                if missing_tables:
                    print(f"⚠️ Missing tables: {', '.join(missing_tables)}")
                    if os.getenv('RENDER'):
                        print("🔧 Running emergency table creation...")
                        # Try to create tables inline
                        try:
                            db.create_all()
                            print("✓ Emergency table creation completed")
                        except Exception as e:
                            print(f"⚠️ Emergency table creation failed: {e}")
                else:
                    print("✓ All required tables present")

            except Exception as e:
                print(f"⚠️ Table check warning: {e}")

    except Exception as e:
        print(f"⚠️ Database setup warning: {e}")
        # On Render, continue anyway
        if not os.getenv('RENDER'):
            return False

    # Continue with module imports...
    print("📦 Importing modules...")
    
    # Global variables to track what's available
    global spotify_client_available, models_available, utils_available, generator_available
    spotify_client_available = False
    models_available = False
    utils_available = False
    generator_available = False
    
    # Get the current working directory for imports
    original_cwd = os.getcwd()
    module_level_current_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        # Change to the spotify app directory for imports
        os.chdir(module_level_current_dir)
        
        # Try importing modules
        try:
            import spotify_client
            print("✓ spotify_client imported")
            spotify_client_available = True
        except ImportError as e:
            print(f"⚠️ spotify_client import failed: {e}")
            
        try:
            import models
            print("✓ models imported")
            models_available = True
        except ImportError as e:
            print(f"⚠️ models import failed: {e}")
            
        try:
            import utils
            print("✓ utils imported")
            utils_available = True
        except ImportError as e:
            print(f"⚠️ utils import failed: {e}")
        
        try:
            import generator
            print("✓ generator imported")
            generator_available = True
        except ImportError as e:
            print(f"⚠️ generator import failed: {e}")
        
        try:
            import title_generator
            import image_generator
            import chart_generator
            print("✓ Additional generation modules imported")
        except ImportError as e:
            print(f"⚠️ Some generation modules unavailable: {e}")
            
    finally:
        os.chdir(original_cwd)
    
    print("✓ Module imports completed")
    
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
    
    # Set initialization status - be more lenient on Render
    initialized = True  # On Render, we'll try to start even with warnings

    if initialized:
        print("🎉 Application initialized for Render!")
    else:
        print("⚠️ Application initialization completed with warnings")

    return True

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
        
        # LoRA models table (UPDATED for file uploads only)
        """
        CREATE TABLE IF NOT EXISTS spotify_lora_models (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            source_type VARCHAR(20) DEFAULT 'local',
            path VARCHAR(500) DEFAULT '',
            file_size INTEGER DEFAULT 0,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            uploaded_by INTEGER
        );
        """,
        
        # Generation results table
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
          # Add foreign keys (simplified for better PostgreSQL compatibility)
        """
        ALTER TABLE spotify_login_sessions 
        ADD CONSTRAINT IF NOT EXISTS fk_login_sessions_user_id 
        FOREIGN KEY (user_id) REFERENCES spotify_users(id) ON DELETE CASCADE;
        """,
        """
        ALTER TABLE spotify_generation_results 
        ADD CONSTRAINT IF NOT EXISTS fk_generation_results_user_id 
        FOREIGN KEY (user_id) REFERENCES spotify_users(id) ON DELETE SET NULL;
        """,
        """
        ALTER TABLE spotify_lora_models 
        ADD CONSTRAINT IF NOT EXISTS fk_lora_models_uploaded_by 
        FOREIGN KEY (uploaded_by) REFERENCES spotify_users(id) ON DELETE SET NULL;
        """,
        
        # Create indexes
        """
        CREATE INDEX IF NOT EXISTS idx_users_email ON spotify_users(email);
        CREATE INDEX IF NOT EXISTS idx_users_spotify_id ON spotify_users(spotify_id);
        CREATE INDEX IF NOT EXISTS idx_users_spotify_username ON spotify_users(spotify_username);
        CREATE INDEX IF NOT EXISTS idx_sessions_token ON spotify_login_sessions(session_token);
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON spotify_login_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_oauth_state ON spotify_oauth_states(state);
        """
    ]
    
    with db.engine.connect() as connection:
        for i, sql in enumerate(sql_commands):
            try:
                connection.execute(text(sql))
                connection.commit()
                print(f"✓ SQL command {i+1} executed successfully")
            except Exception as e:
                print(f"❌ SQL command {i+1} failed: {e}")
                raise

def get_current_user_or_guest():
    """Get current logged in user or return guest info"""
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
        # Guest logic using IP address
        # request.remote_addr should provide the IP
        ip_address = request.remote_addr 
        can_generate_today = can_guest_generate_by_ip(ip_address)
        return {
            'type': 'guest',
            'user': None,
            'display_name': 'Guest',
            'is_premium': False,
            'daily_limit': 1, # Guest daily limit is 1
            'generations_today': 0 if can_generate_today else 1, # Simplified: 0 if can still gen, 1 if already gen'd
            'can_generate': can_generate_today,
            'can_use_loras': False,
            'can_edit_playlists': False,
            'show_upload': False
        }

# Context processor to inject common template variables
@app.context_processor
def inject_template_vars():
    """Inject common variables into all templates"""
    return {
        'current_year': datetime.datetime.now(timezone.utc).year,
        'user_info': get_current_user_or_guest()
    }

# ROUTES
@app.route("/")
def root():
    """Root route - show main page instead of redirecting"""
    return redirect(url_for('generate'))

@app.route("/generate", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
@monitor_performance
def generate():
    """Main generation route"""
    global initialized
    
    user_info = get_current_user_or_guest()
    
    if request.method == "POST" and not user_info['can_generate']:
        return render_template(
            "index.html",
            error=f"Daily generation limit reached ({user_info['daily_limit']} per day). " + 
                  ("Try again tomorrow!" if user_info['type'] == 'guest' else "Try again tomorrow or upgrade to premium!"),
            loras=[]
        )
    
    if not initialized:
        if initialize_app():
            print("Application initialized successfully from generate route")
        else:
            print("Failed to initialize application from generate route")
            return render_template(
                "index.html", 
                error="Application is still initializing or encountered an issue. Please try again in a moment.",
                loras=[]
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
                        loras=loras
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
                    loras=[]
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
                    loras=loras
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
                    loras=loras
                )
            
            # Increment generation count
            if user_info['type'] == 'guest':
                record_guest_generation_by_ip(request.remote_addr) # New call
            
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
                "user_info": user_info,
                "user": user_info.get('user'),
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
                loras=loras
            )
    else:
        return render_template("index.html", loras=loras)

# LoRA UPLOAD ROUTE (FIXED FOR FILE UPLOADS ONLY)
@app.route('/api/upload_lora', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def upload_lora():
    """Upload LoRA file (Premium users only)"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "User not authenticated"}), 401
        
        # Check if user is premium (only premium users can upload files)
        if not user.is_premium_user():
            return jsonify({
                "success": False, 
                "error": "File uploads are only available for premium users. Premium access is granted to bentakaki7@gmail.com and Spotify user 'benthegamer'."
            }), 403
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400
        
        # Validate file extension
        filename = secure_filename(file.filename)
        if not filename.lower().endswith(('.safetensors', '.ckpt', '.pt')):
            return jsonify({
                "success": False, 
                "error": "Invalid file type. Only .safetensors, .ckpt, and .pt files are allowed."
            }), 400
        
        # Get name without extension for database
        lora_name = filename.rsplit('.', 1)[0]
        
        # Check if LoRA with this name already exists
        existing = LoraModelDB.query.filter_by(name=lora_name).first()
        if existing:
            return jsonify({
                "success": False, 
                "error": f"LoRA with name '{lora_name}' already exists"
            }), 400
        
        # Create LoRA directory if it doesn't exist
        lora_dir = BASE_DIR / "loras"
        lora_dir.mkdir(exist_ok=True)
        
        # Save file
        file_path = lora_dir / filename
        file.save(str(file_path))
        
        # Get file size
        file_size = os.path.getsize(str(file_path))
        
        # Add to database
        new_lora = LoraModelDB(
            name=lora_name,
            source_type="local",
            path=str(file_path),
            file_size=file_size,
            uploaded_by=user.id
        )
        
        db.session.add(new_lora)
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"LoRA '{lora_name}' uploaded successfully ({file_size} bytes)"
        })
        
    except Exception as e:
        print(f"Error uploading LoRA: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

# Add new LoRA management and upload info routes
@app.route('/api/delete_lora', methods=['DELETE'])
@login_required
@limiter.limit("10 per hour")
def delete_lora():
    """Delete LoRA file (All users can delete their own uploads)"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "User not authenticated"}), 401
        data = request.get_json()
        lora_name = data.get('name', '').strip()
        if not lora_name:
            return jsonify({"success": False, "error": "LoRA name is required"}), 400
        lora_record = LoraModelDB.query.filter_by(name=lora_name).first()
        if not lora_record:
            return jsonify({"success": False, "error": "LoRA not found"}), 404
        if not user.is_premium_user() and lora_record.uploaded_by != user.id:
            return jsonify({"success": False, "error": "You can only delete LoRAs you uploaded"}), 403
        if lora_record.path and os.path.exists(lora_record.path):
            try:
                os.remove(lora_record.path)
                print(f"Deleted LoRA file: {lora_record.path}")
            except Exception as e:
                print(f"Could not delete file {lora_record.path}: {e}")
        db.session.delete(lora_record)
        db.session.commit()
        return jsonify({"success": True, "message": f"LoRA '{lora_name}' deleted successfully"})
    except Exception as e:
        print(f"Error deleting LoRA: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


def get_user_lora_upload_info(user):
    """Get user's LoRA upload info"""
    if not user:
        return {"can_upload": False, "current_count": 0, "limit": 0}
    current_count = LoraModelDB.query.filter_by(source_type="local", uploaded_by=user.id).count()
    if user.is_premium_user():
        return {"can_upload": True, "current_count": current_count, "limit": "unlimited", "is_premium": True}
    return {"can_upload": current_count < 2, "current_count": current_count, "limit": 2, "is_premium": False}

@app.route('/api/upload_info')
@login_required
def get_upload_info():
    """Get user's upload information"""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(get_user_lora_upload_info(user))

@app.route('/api/loras')
def get_loras():
    """Get list of available LoRAs (file uploads only) with ownership info"""
    try:
        user = get_current_user()
        
        loras = []
        db_loras = LoraModelDB.query.filter_by(source_type="local").all()
        
        for db_lora in db_loras:
            # Check if file still exists
            if db_lora.path and os.path.exists(db_lora.path):
                lora_data = {
                    "name": db_lora.name,
                    "source_type": "local",
                    "file_size": db_lora.file_size or 0,
                    "uploaded_at": db_lora.uploaded_at.isoformat() if db_lora.uploaded_at else None,
                    "can_delete": False,
                    "uploaded_by_current_user": False
                }
                
                # Add ownership info if user is logged in
                if user:
                    lora_data["uploaded_by_current_user"] = (db_lora.uploaded_by == user.id)
                    # User can delete if: they uploaded it, or they're premium
                    lora_data["can_delete"] = (
                        db_lora.uploaded_by == user.id or 
                        user.is_premium_user()
                    )
                
                loras.append(lora_data)
        
        return jsonify({"loras": loras})
        
    except Exception as e:
        print(f"Error getting LoRAs: {e}")
        return jsonify({"loras": []})

# SPOTIFY PLAYLIST EDIT ROUTES
@app.route('/api/playlist/edit', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
@monitor_api_calls(service_name="spotify_playlist_edit")
def edit_playlist_details():
    """Edit Spotify playlist details (name, description)"""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "User not authenticated"}), 401

    if not user.spotify_access_token:
        return jsonify({"success": False, "error": "Spotify account not connected or token missing"}), 403

    if not user.refresh_spotify_token_if_needed():
        return jsonify({"success": False, "error": "Failed to refresh Spotify token"}), 500

    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

        playlist_id = data.get('playlist_id')
        name = data.get('name')
        description = data.get('description')

        if not playlist_id:
            return jsonify({"success": False, "error": "playlist_id is required"}), 400
        
        # Name and description can be empty strings to clear them, but should exist
        if name is None or description is None:
            return jsonify({"success": False, "error": "name and description are required (can be empty strings)"}), 400

        # Call the (yet to be created) spotify_client function
        # For now, this will likely error out as spotify_client.update_playlist_details doesn't exist
        # We'll assume it returns True on success, or raises an exception on failure
        spotify_client.update_playlist_details(
            user.spotify_access_token,
            playlist_id,
            name,
            description
        )
        
        return jsonify({"success": True})

    except AttributeError as ae: # Catch if update_playlist_details doesn't exist
        print(f"AttributeError in edit_playlist_details: {ae}")
        return jsonify({"success": False, "error": "Playlist editing function not yet implemented."}), 501
    except Exception as e:
        print(f"Error editing playlist details: {e}")
        traceback.print_exc()
        # Attempt to create a user-friendly message
        try:
            from fault_handling import FaultContext, create_user_friendly_error_messages
            context = FaultContext(
                function_name="edit_playlist_details",
                error=e,
                user_id=str(user.id) if user else None
            )
            user_message = create_user_friendly_error_messages(e, context)
        except (ImportError, Exception):
            user_message = "An unexpected error occurred while editing playlist details."
        return jsonify({"success": False, "error": user_message}), 500

@app.route('/api/playlist/cover', methods=['POST'])
@login_required
@limiter.limit("5 per minute")
@monitor_api_calls(service_name="spotify_playlist_cover")
def update_playlist_cover():
    """Update Spotify playlist cover image"""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "User not authenticated"}), 401

    if not user.spotify_access_token:
        return jsonify({"success": False, "error": "Spotify account not connected or token missing"}), 403

    if not user.refresh_spotify_token_if_needed():
        return jsonify({"success": False, "error": "Failed to refresh Spotify token"}), 500

    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

        playlist_id = data.get('playlist_id')
        image_data_url = data.get('image_data') # Expects data:image/jpeg;base64,actual_base64_string

        if not playlist_id:
            return jsonify({"success": False, "error": "playlist_id is required"}), 400
        if not image_data_url:
            return jsonify({"success": False, "error": "image_data is required"}), 400

        # Extract actual base64 string
        # Format: data:[<mediatype>][;base64],<data>
        try:
            header, actual_base64_string = image_data_url.split(',', 1)
            if not header.startswith("data:image") or ";base64" not in header:
                raise ValueError("Invalid image data URL format")
        except ValueError:
            return jsonify({"success": False, "error": "Invalid image_data format. Expected data URL (e.g., data:image/jpeg;base64,...)"}), 400
        
        # Call the (yet to be created) spotify_client function
        # For now, this will likely error out
        spotify_client.update_playlist_cover_image(
            user.spotify_access_token,
            playlist_id,
            actual_base64_string
        )
        
        return jsonify({"success": True})

    except AttributeError as ae: # Catch if update_playlist_cover_image doesn't exist
        print(f"AttributeError in update_playlist_cover: {ae}")
        return jsonify({"success": False, "error": "Playlist cover update function not yet implemented."}), 501
    except Exception as e:
        print(f"Error updating playlist cover: {e}")
        traceback.print_exc()
        # Attempt to create a user-friendly message
        try:
            from fault_handling import FaultContext, create_user_friendly_error_messages
            context = FaultContext(
                function_name="update_playlist_cover",
                error=e,
                user_id=str(user.id) if user else None
            )
            user_message = create_user_friendly_error_messages(e, context)
        except (ImportError, Exception):
            user_message = "An unexpected error occurred while updating playlist cover."
        return jsonify({"success": False, "error": user_message}), 500

# SPOTIFY AUTH ROUTES (FIXED)
@app.route('/spotify-login')
@app.route('/spotify_login')  # Add this alias
def spotify_login():
    """Initiate Spotify OAuth flow - with both URL patterns"""
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        flash('Spotify integration is not configured', 'error')
        return redirect(url_for('login'))
    
    # Generate state for CSRF protection
    try:
        state = SpotifyState.create_state()
    except Exception as e:
        print(f"Error creating OAuth state: {e}")
        flash('Error initiating Spotify login. Please try again.', 'error')
        return redirect(url_for('login'))
    
    scope = " ".join([
        "user-read-private", "user-read-email", "playlist-read-private",
        "playlist-modify-public", "playlist-modify-private",
        "ugc-image-upload"
    ])
    
    auth_url = (
        f"https://accounts.spotify.com/authorize?response_type=code"
        f"&client_id={SPOTIFY_CLIENT_ID}&scope={scope}"
        f"&redirect_uri={SPOTIFY_REDIRECT_URI}&state={state}"
    )
    return redirect(auth_url)


@app.route('/spotify-callback')
def spotify_callback():
    """Fixed Spotify OAuth callback"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        if error:
            flash(f'Spotify authorization failed: {error}', 'error')
            return redirect(url_for('login'))
        if not code or not state:
            flash('Invalid Spotify callback - missing parameters', 'error')
            return redirect(url_for('login'))
        if not SpotifyState.verify_and_use_state(state):
            flash('Invalid state parameter - possible CSRF attack', 'error')
            return redirect(url_for('login'))
        if os.getenv('RENDER'):
            redirect_uri = 'https://www.benjamintakaki.com/spotify/spotify-callback'
        else:
            redirect_uri = 'http://localhost:5000/spotify/spotify-callback'
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': SPOTIFY_CLIENT_ID,
            'client_secret': SPOTIFY_CLIENT_SECRET
        }
        response = requests.post('https://accounts.spotify.com/api/token', data=token_data, timeout=30)
        if response.status_code != 200:
            print(f"Token exchange failed: {response.status_code} - {response.text}")
            flash('Failed to get Spotify tokens. Please try again.', 'error')
            return redirect(url_for('login'))
        tokens = response.json()
        access_token = tokens['access_token']
        refresh_token = tokens.get('refresh_token')
        expires_in = tokens.get('expires_in', 3600)
        headers = {'Authorization': f'Bearer {access_token}'}
        user_response = requests.get('https://api.spotify.com/v1/me', headers=headers, timeout=30)
        if user_response.status_code != 200:
            print(f"User info fetch failed: {user_response.status_code} - {user_response.text}")
            flash('Failed to get Spotify user info. Please try again.', 'error')
            return redirect(url_for('login'))
        spotify_user = user_response.json()
        spotify_id = spotify_user['id']
        print(f"🔍 Spotify user data: {spotify_user}")
        user = User.query.filter_by(spotify_id=spotify_id).first()
        if not user:
            user = User(
                spotify_id=spotify_id,
                spotify_username=spotify_user.get('id'),
                display_name=spotify_user.get('display_name', spotify_user.get('id')),
                email=spotify_user.get('email'),
                is_premium=False
            )
            db.session.add(user)
            print(f"✓ Created new user with email: {user.email}")
        else:
            user.display_name = spotify_user.get('display_name', spotify_user.get('id'))
            user.email = spotify_user.get('email')
            print(f"✓ Updated existing user")
        user.spotify_access_token = access_token
        user.spotify_refresh_token = refresh_token
        user.spotify_token_expires = datetime.datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        user.last_login = datetime.datetime.now(timezone.utc)
        db.session.commit()
        session_token = LoginSession.create_session(
            user.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        session['user_id'] = user.id
        session['user_session'] = session_token
        resp = make_response(redirect(url_for('generate')))
        resp.set_cookie('session_token', session_token, max_age=30*24*60*60)
        is_premium = user.is_premium_user()
        if is_premium:
            flash('🌟 Welcome back, Premium user! You have unlimited generations and file upload access.', 'success')
        else:
            flash('Successfully connected to Spotify! You have 2 daily generations.', 'success')
        return resp
    except Exception as e:
        print(f"Error in Spotify callback: {e}")
        import traceback
        traceback.print_exc()
        flash('An error occurred during Spotify authorization. Please try again.', 'error')
        return redirect(url_for('login'))

# OTHER ROUTES (login, logout, profile, etc. - keep existing)
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Fixed login route"""
    user = get_current_user()
    if user:
        return redirect(url_for('generate'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username and password:
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                session_token = LoginSession.create_session(
                    user.id,
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', '')
                )
                user.last_login = datetime.datetime.now(timezone.utc)
                db.session.commit()
                session['user_id'] = user.id
                session['user_session'] = session_token
                resp = make_response(redirect(url_for('generate')))
                resp.set_cookie('session_token', session_token, max_age=30*24*60*60)
                flash('Logged in successfully!', 'success')
                return resp
            else:
                flash('Invalid username or password', 'error')
        else:
            flash('Please enter both username and password', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Fixed logout route"""
    user_id = session.get('user_id')
    if 'user_session' in session:
        try:
            session_token = session['user_session']
            login_session = LoginSession.query.filter_by(session_token=session_token).first()
            if login_session:
                login_session.is_active = False
                db.session.commit()
        except Exception as e:
            print(f"Error marking session inactive: {e}")
    session.clear()
    resp = make_response(redirect(url_for('login')))
    resp.set_cookie('session_token', '', expires=0)
    flash('You have been logged out successfully', 'info')
    return resp

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
                         .order_by(GenerationResultDB.timestamp.desc())
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
    
    return render_template('profile.html', **profile_data)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register route"""
    # If user is already logged in, redirect to generate
    user = get_current_user()
    if user:
        return redirect(url_for('generate'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not email or not username or not password:
            flash('All fields are required.', 'error')
            return render_template('register.html')

        # Check for existing users
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return render_template('register.html')

        # Create new user
        try:
            new_user = User(
                email=email, 
                username=username, 
                display_name=username
            )
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            print(f"Error creating user: {e}")
            flash('Registration failed. Please try again.', 'error')
            return render_template('register.html')
        
    return render_template('register.html')

# Add this debug route to check what routes exist
@app.route('/debug/routes')
def debug_routes():
    """Debug route to see all available routes"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'rule': rule.rule
        })
    
    from flask import jsonify
    return jsonify({'routes': routes})

# Make sure spotify_login route exists (rename from spotify-login)
# This is now handled by the alias, so we can remove the duplicate route definition.


if not any(rule.endpoint == 'health_check' for rule in app.url_map.iter_rules()):
    @app.route('/health')
    def health_check():
        """Health check endpoint for monitoring"""
        try:
            from monitoring_system import health_checker
            health_results = health_checker.run_all_checks()
            all_healthy = all(result.healthy for result in health_results.values())
            
            response_data = {
                "status": "healthy" if all_healthy else "degraded",
                "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
                "services": {name: {
                    "healthy": result.healthy,
                    "response_time_ms": result.response_time_ms,
                    "error": result.error
                } for name, result in health_results.items()}
            }
            
            return jsonify(response_data), 200 if all_healthy else 503
            
        except ImportError:
            # Fallback health check if monitoring system not available
            return jsonify({
                "status": "healthy",
                "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
                "message": "Basic health check - monitoring system not available"
            }), 200
        except Exception as e:
            return jsonify({
                "status": "error", 
                "error": str(e),
                "timestamp": datetime.datetime.now(timezone.utc).isoformat()
            }), 500

@app.route('/metrics')
def metrics_endpoint():
    """Metrics endpoint for performance monitoring"""
    try:
        from monitoring_system import app_logger
        
        metrics_data = {
            "performance": app_logger.get_performance_summary(),
            "timestamp": datetime.datetime.now(timezone.utc).isoformat()
        }
        
        return jsonify(metrics_data), 200
        
    except ImportError:
        # Fallback metrics
        return jsonify({
            "status": "monitoring_unavailable",
            "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
            "message": "Monitoring system not available"
        }), 200
    except Exception as e:
        return jsonify({
            "error": "Metrics not available",
            "message": str(e),
            "timestamp": datetime.datetime.now(timezone.utc).isoformat()
        }), 500

# 5. FIX monitoring_system.py initialization
"""
In your app.py, around the end of the file, UPDATE this section:

FIND:
try:
    setup_monitoring(app)
    print("✅ Monitoring system setup complete")
except Exception as e:
    print(f"⚠️ Monitoring setup failed: {e}")

REPLACE with:
"""

def setup_basic_monitoring(app):
    """Setup basic monitoring if full system unavailable"""
    @app.before_request
    def log_request():
        request.start_time = time.time()
    
    @app.after_request  
    def log_response(response):
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            print(f"REQUEST: {request.method} {request.path} - {response.status_code} ({duration:.3f}s)")
        return response

try:
    from monitoring_system import setup_monitoring
    setup_monitoring(app)
    print("✅ Full monitoring system setup complete")
except ImportError as e:
    print(f"⚠️ Full monitoring not available: {e}")
    setup_basic_monitoring(app)
    print("✅ Basic monitoring setup complete")
except Exception as e:
    print(f"⚠️ Monitoring setup failed: {e}")
    setup_basic_monitoring(app)
    print("✅ Fallback monitoring setup complete")

# Enhanced error handlers with monitoring
@app.errorhandler(404)
def handle_404_error(e):
    try:
        app_logger.log_structured(
            "info",
            "page_not_found",
            path=request.path,
            method=request.method,
            user_agent=request.headers.get('User-Agent', '')
        )
    except:
        pass  # Fallback if monitoring not available
    return "Page not found", 404

@app.errorhandler(403)
def handle_403_error(e):
    try:
        app_logger.log_structured(
            "warning",
            "access_forbidden", 
            path=request.path,
            method=request.method,
            user_id=session.get('user_id')
        )
    except:
        pass  # Fallback if monitoring not available
    return "Access forbidden", 403

@app.errorhandler(Exception)
def handle_generic_error(e):
    """Enhanced error handler with user-friendly messages"""
    try:
        # Log the error
        app_logger.log_structured(
            "error",
            "unhandled_exception",
            error=str(e),
            error_type=type(e).__name__,
            path=request.path,
            method=request.method,
            user_id=session.get('user_id'),
            traceback=traceback.format_exc()
        )
        
        # Alert on critical errors
        alert_manager.alert(
            "unhandled_exception",
            f"Unhandled exception on {request.method} {request.path}: {str(e)}",
            severity="critical"
        )
        
        # Create user-friendly error message
        user_info = get_current_user_or_guest()
        
        # Import FaultContext here to avoid import issues
        try:
            from fault_handling import FaultContext, create_user_friendly_error_messages
            context = FaultContext(
                function_name="web_request",
                attempt_number=1,
                error=e,
                user_id=str(user_info.get('user', {}).get('id', '')),
                is_guest=user_info.get('type') == 'guest'
            )
            user_message = create_user_friendly_error_messages(e, context)
        except (ImportError, Exception):
            user_message = "An unexpected error occurred. Please try again or contact support if the problem persists."
        
        return render_template('error.html', 
                             error_message=user_message,
                             show_retry=True), 500
    except Exception as fallback_error:
        # Ultimate fallback if everything fails
        print(f"Error in error handler: {fallback_error}")
        return "An error occurred. Please try again.", 500

# Set up monitoring when app starts
try:
    setup_monitoring(app)
    print("✅ Monitoring system setup complete")
except Exception as e:
    print(f"⚠️ Monitoring setup failed: {e}")

if os.getenv('RENDER'):
    try:
        with app.app_context():
            db.create_all()
            print("✅ Final table creation check completed")
    except Exception as e:
        print(f"⚠️ Final table creation warning: {e}")
        
if __name__ == '__main__':
    print("Initializing application...")
    # Application startup logic
    from models import initialize_app
    if initialize_app():
        print("Application initialized successfully")
    else:
        print("Application initialization had issues; continuing...")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)