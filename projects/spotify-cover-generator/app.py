import os
import sys
import random
import json
import datetime
from datetime import datetime, timedelta
from flask import Flask, request, render_template, send_from_directory, jsonify, session, redirect, url_for, flash
from pathlib import Path
from urllib.parse import urlparse
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import secrets
import requests
import base64
import io
from PIL import Image

# Make sure the current directory is in the path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import app modules
from config import BASE_DIR, COVERS_DIR, FLASK_SECRET_KEY, SPOTIFY_DB_URL
from contextlib import contextmanager

# Initialize Flask app first
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.secret_key = FLASK_SECRET_KEY or ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=24))

# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = SPOTIFY_DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy - we do this only once
from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy(app)

# Define database models for the app
class LoraModelDB(db.Model):
    __tablename__ = 'spotify_lora_models'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    source_type = db.Column(db.String(20), default='local')  # 'local' or 'link'
    path = db.Column(db.String(500), default='')
    url = db.Column(db.String(500), default='')
    trigger_words = db.Column(db.JSON, default=list)
    strength = db.Column(db.Float, default=0.7)
    
    def to_lora_model(self):
        """Convert DB model to LoraModel object"""
        # Import here to avoid circular imports
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
    
    # Add user relationship
    user_id = db.Column(db.Integer, db.ForeignKey('spotify_users.id'), nullable=True)


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationship to generations
    generations = db.relationship('GenerationResultDB', backref='user', lazy=True)
    
    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
    def is_premium_user(self):
        """Check if user has premium access"""
        # Premium access for specific email/spotify account
        return (self.email == 'bentakaki7@gmail.com' or 
                self.spotify_username == 'Benthegamer')
    
    def get_daily_generation_limit(self):
        """Get daily generation limit for user"""
        return 999 if self.is_premium_user() else 2
    
    def can_generate_today(self):
        """Check if user can generate more covers today"""
        today = datetime.utcnow().date()
        today_generations = GenerationResultDB.query.filter(
            GenerationResultDB.user_id == self.id,
            db.func.date(GenerationResultDB.timestamp) == today
        ).count()
        
        return today_generations < self.get_daily_generation_limit()
    
    def get_generations_today(self):
        """Get number of generations made today"""
        today = datetime.utcnow().date()
        return GenerationResultDB.query.filter(
            GenerationResultDB.user_id == self.id,
            db.func.date(GenerationResultDB.timestamp) == today
        ).count()
    
    def refresh_spotify_token_if_needed(self):
        """Refresh Spotify token if it's about to expire"""
        if not self.spotify_refresh_token:
            return False
            
        if (self.spotify_token_expires and 
            self.spotify_token_expires <= datetime.utcnow() + timedelta(minutes=5)):
            # Token expires in less than 5 minutes, refresh it
            return self._refresh_spotify_token()
        
        return True
    
    def _refresh_spotify_token(self):
        """Internal method to refresh Spotify token"""
        from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
        import requests
        import base64
        
        if not self.spotify_refresh_token:
            return False
        
        # Prepare the request
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
                self.spotify_token_expires = datetime.utcnow() + timedelta(
                    seconds=token_data['expires_in']
                )
                
                # Update refresh token if provided
                if 'refresh_token' in token_data:
                    self.spotify_refresh_token = token_data['refresh_token']
                
                db.session.commit()
                return True
        except Exception as e:
            print(f"Error refreshing Spotify token: {e}")
        
        return False
    
    def to_dict(self):
        """Convert user to dictionary"""
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    
    user = db.relationship('User', backref='sessions')
    
    @staticmethod
    def create_session(user_id, ip_address=None, user_agent=None):
        """Create a new login session"""
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=30)  # 30 day sessions
        
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
        """Get user from session token"""
        session = LoginSession.query.filter_by(
            session_token=session_token,
            is_active=True
        ).first()
        
        if not session or session.expires_at <= datetime.utcnow():
            if session:
                session.is_active = False
                db.session.commit()
            return None
        
        return session.user
    
    def invalidate(self):
        """Invalidate this session"""
        self.is_active = False
        db.session.commit()


class SpotifyState(db.Model):
    __tablename__ = 'spotify_oauth_states'
    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used = db.Column(db.Boolean, default=False)
    
    @staticmethod
    def create_state():
        """Create a new OAuth state"""
        state = secrets.token_urlsafe(32)
        oauth_state = SpotifyState(state=state)
        db.session.add(oauth_state)
        db.session.commit()
        return state
    
    @staticmethod
    def verify_and_use_state(state):
        """Verify and mark state as used"""
        oauth_state = SpotifyState.query.filter_by(state=state, used=False).first()
        if oauth_state and oauth_state.created_at > datetime.utcnow() - timedelta(minutes=10):
            oauth_state.used = True
            db.session.commit()
            return True
        return False

# Global initialization flag
initialized = False

def initialize_app():
    """Initialize the application's dependencies"""
    global initialized
    
    # Create tables if they don't exist
    try:
        with app.app_context():
            db.create_all()
    except Exception as e:
        print(f"Error creating database tables: {e}")
        return False          # Make sure necessary directories exist
    os.makedirs(COVERS_DIR, exist_ok=True)
    
    # Now import modules that might need the database to be configured first
    # Import here to avoid circular imports with db
    try:
        # Add current directory to path to ensure local imports work
        import sys
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
            
        from spotify_client import initialize_spotify
        from models import PlaylistData, GenreAnalysis, LoraModel
        from utils import generate_random_string, get_available_loras
    except ImportError as e:
        print(f"Error importing modules: {e}")
        return False
    
    # Initialize Spotify client
    spotify_initialized = initialize_spotify()
    
    # Check all required environment variables
    from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, GEMINI_API_KEY, STABILITY_API_KEY
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
        print(f"⚠️ Missing environment variables: {', '.join(missing)}")
    
    initialized = spotify_initialized and env_vars_present
    return initialized

def calculate_genre_percentages(genres_list):
    """Calculate percentage distribution of genres"""
    if not genres_list:
        return []
    
    # Import here to avoid circular imports
    from models import GenreAnalysis
    
    # Use GenreAnalysis to calculate percentages
    genre_analysis = GenreAnalysis.from_genre_list(genres_list)
    return genre_analysis.get_percentages(max_genres=5)

# Create a placeholder image once at startup
def create_static_placeholder():
    """Create a static placeholder image if it doesn't exist"""
    from PIL import Image, ImageDraw, ImageFont
    
    placeholder_path = os.path.join(app.static_folder, "images", "image-placeholder.png")
    if not os.path.exists(placeholder_path):
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(placeholder_path), exist_ok=True)
        
        # Create a simple placeholder image
        image = Image.new('RGB', (512, 512), color='#1E1E1E')
        draw = ImageDraw.Draw(image)
        
        # Draw a border
        border_width = 5
        border_color = "#333333"
        draw.rectangle(
            [(border_width//2, border_width//2), (512-border_width//2, 512-border_width//2)],
            outline=border_color,
            width=border_width
        )
        
        # Try to use a font
        try:
            font = ImageFont.truetype("arial.ttf", 28)
            small_font = ImageFont.truetype("arial.ttf", 16)
        except:
            # Use default if truetype not available
            font = ImageFont.load_default()
            small_font = font
            
        # Draw text
        text = "Image Not Found"
        draw.text((100, 240), text, fill="#1DB954", font=font)
        draw.text((90, 280), "Click Generate Again", fill="#FFFFFF", font=small_font)
        
        # Save the image
        image.save(placeholder_path)
        print(f"Created placeholder image at {placeholder_path}")
    
    return placeholder_path

# Create placeholder on startup
create_static_placeholder()

# Authentication decorator
def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # Check for session token in cookies
            session_token = request.cookies.get('session_token')
            if session_token:
                user = LoginSession.get_user_from_session(session_token)
                if user:
                    session['user_id'] = user.id
                    session['username'] = user.username or user.display_name
                else:
                    return redirect(url_for('login'))
            else:
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
                return user
        return None
    
    return User.query.get(session['user_id'])

def extract_playlist_id(playlist_url):
    """Extract playlist ID from Spotify URL"""
    if "playlist/" in playlist_url:
        return playlist_url.split("playlist/")[-1].split("?")[0].split("/")[0]
    return None

def save_generation_data_with_user(data, user_id, output_path=None):
    """Save generation data to database with user tracking"""
    try:
        # Import here to avoid circular imports
        from config import DATA_DIR
        
        with app.app_context():
            # Create a new generation result record
            new_result = GenerationResultDB(
                title=data.get("title", "New Album"),
                output_path=data.get("output_path", ""),
                item_name=data.get("item_name", ""),
                genres=data.get("genres", []),
                all_genres=data.get("all_genres", []),
                style_elements=data.get("style_elements", []),
                mood=data.get("mood", ""),
                energy_level=data.get("energy_level", ""),
                spotify_url=data.get("spotify_url", ""),
                lora_name=data.get("lora_name", ""),
                lora_type=data.get("lora_type", ""),
                lora_url=data.get("lora_url", ""),
                user_id=user_id  # Add user tracking
            )
            
            db.session.add(new_result)
            db.session.commit()
            
            # Return the ID as a string
            return str(new_result.id)
    except Exception as e:
        print(f"Error saving data to database: {e}")
        
        # Fall back to saving to a JSON file if database fails
        try:
            # Create a unique filename based on timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = "".join(c for c in data.get("item_name", "") if c.isalnum() or c in [' ', '-', '_']).strip()
            safe_name = safe_name.replace(' ', '_')
            json_filename = f"{timestamp}_{safe_name}.json"
            
            with open(DATA_DIR / json_filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"Data saved to file {DATA_DIR / json_filename} (database failed)")
            
            return str(DATA_DIR / json_filename)
        except Exception as file_error:
            print(f"Error saving data to file: {file_error}")
            return None

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page with both regular and Spotify login"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Please fill in all fields', 'error')
            return render_template('auth/login.html')
        
        # Find user by email or username
        user = User.query.filter(
            (User.email == email) | (User.username == email)
        ).first()
        
        if user and user.check_password(password):
            # Create session
            session_token = LoginSession.create_session(
                user.id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            # Update last login
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Set session and cookie
            session['user_id'] = user.id
            session['username'] = user.username or user.display_name
            
            response = redirect(url_for('index'))
            response.set_cookie('session_token', session_token, max_age=30*24*60*60)  # 30 days
            
            flash(f'Welcome back, {user.display_name or user.username}!', 'success')
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
            flash('Password must be at least 6 characters long', 'error')
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
        
        # Auto-login after registration
        session_token = LoginSession.create_session(
            user.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        session['user_id'] = user.id
        session['username'] = user.username
        
        response = redirect(url_for('index'))
        response.set_cookie('session_token', session_token, max_age=30*24*60*60)
        
        flash(f'Registration successful! Welcome, {user.username}!', 'success')
        return response
    
    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    """Logout user"""
    # Invalidate session token
    session_token = request.cookies.get('session_token')
    if session_token:
        login_session = LoginSession.query.filter_by(session_token=session_token).first()
        if login_session:
            login_session.invalidate()
    
    # Clear session
    session.clear()
    
    response = redirect(url_for('login'))
    response.set_cookie('session_token', '', expires=0)
    
    flash('You have been logged out', 'info')
    return response

# Spotify OAuth Routes
@app.route('/login/spotify')
def spotify_login():
    """Redirect to Spotify OAuth"""
    from config import SPOTIFY_CLIENT_ID
    
    # Create OAuth state for security
    state = SpotifyState.create_state()
    
    # Spotify OAuth URL
    auth_url = (
        "https://accounts.spotify.com/authorize"
        f"?client_id={SPOTIFY_CLIENT_ID}"
        "&response_type=code"
        f"&redirect_uri={request.url_root}auth/spotify/callback"
        "&scope=playlist-modify-public playlist-modify-private ugc-image-upload user-read-private user-read-email"
        f"&state={state}"
    )
    
    return redirect(auth_url)

@app.route('/auth/spotify/callback')
def spotify_callback():
    """Handle Spotify OAuth callback"""
    from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
    
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    if error:
        flash(f'Spotify login error: {error}', 'error')
        return redirect(url_for('login'))
    
    if not code or not state:
        flash('Invalid Spotify callback', 'error')
        return redirect(url_for('login'))
    
    # Verify state
    if not SpotifyState.verify_and_use_state(state):
        flash('Invalid OAuth state', 'error')
        return redirect(url_for('login'))
    
    # Exchange code for tokens
    auth_header = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    
    token_data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': f"{request.url_root}auth/spotify/callback"
    }
    
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        # Get access token
        token_response = requests.post(
            'https://accounts.spotify.com/api/token',
            data=token_data,
            headers=headers
        )
        
        if token_response.status_code != 200:
            flash('Failed to get Spotify access token', 'error')
            return redirect(url_for('login'))
        
        tokens = token_response.json()
        access_token = tokens['access_token']
        refresh_token = tokens.get('refresh_token')
        expires_in = tokens.get('expires_in', 3600)
        
        # Get user info from Spotify
        user_headers = {'Authorization': f'Bearer {access_token}'}
        user_response = requests.get(
            'https://api.spotify.com/v1/me',
            headers=user_headers
        )
        
        if user_response.status_code != 200:
            flash('Failed to get Spotify user info', 'error')
            return redirect(url_for('login'))
        
        spotify_user = user_response.json()
        
        # Find or create user
        user = User.query.filter_by(spotify_id=spotify_user['id']).first()
        
        if not user:
            # Check if user exists with same email
            email = spotify_user.get('email')
            if email:
                user = User.query.filter_by(email=email).first()
            
            if not user:
                # Create new user
                user = User(
                    spotify_id=spotify_user['id'],
                    spotify_username=spotify_user.get('display_name', spotify_user['id']),
                    email=spotify_user.get('email'),
                    display_name=spotify_user.get('display_name', spotify_user['id'])
                )
                db.session.add(user)
            else:
                # Link Spotify to existing account
                user.spotify_id = spotify_user['id']
                user.spotify_username = spotify_user.get('display_name', spotify_user['id'])
        
        # Update Spotify tokens
        user.spotify_access_token = access_token
        user.spotify_refresh_token = refresh_token
        user.spotify_token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
        user.last_login = datetime.utcnow()
        
        db.session.commit()
        
        # Create session
        session_token = LoginSession.create_session(
            user.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        session['user_id'] = user.id
        session['username'] = user.display_name or user.username
        
        response = redirect(url_for('index'))
        response.set_cookie('session_token', session_token, max_age=30*24*60*60)
        
        flash(f'Welcome, {user.display_name}! Logged in with Spotify.', 'success')
        return response
        
    except Exception as e:
        print(f"Spotify OAuth error: {e}")
        flash('Error during Spotify login', 'error')
        return redirect(url_for('login'))

# User Profile and Dashboard
@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    # Get user's recent generations
    recent_generations = GenerationResultDB.query.filter_by(
        user_id=user.id
    ).order_by(GenerationResultDB.timestamp.desc()).limit(10).all()
    
    return render_template('auth/profile.html', user=user, generations=recent_generations)

@app.route('/api/user/status')
@login_required
def user_status():
    """API endpoint for user status"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    
    return jsonify(user.to_dict())

# Spotify Playlist Editing Routes
@app.route('/api/playlist/edit', methods=['POST'])
@login_required
def edit_playlist():
    """Edit playlist title and description"""
    user = get_current_user()
    if not user or not user.spotify_access_token:
        return jsonify({'error': 'Spotify authentication required'}), 401
    
    data = request.json
    playlist_id = data.get('playlist_id')
    new_name = data.get('name')
    new_description = data.get('description')
    
    if not playlist_id:
        return jsonify({'error': 'Playlist ID required'}), 400
    
    # Refresh token if needed
    if not user.refresh_spotify_token_if_needed():
        return jsonify({'error': 'Failed to refresh Spotify token'}), 401
    
    # Prepare the request
    headers = {
        'Authorization': f'Bearer {user.spotify_access_token}',
        'Content-Type': 'application/json'
    }
    
    update_data = {}
    if new_name:
        update_data['name'] = new_name
    if new_description:
        update_data['description'] = new_description
    
    if not update_data:
        return jsonify({'error': 'No updates provided'}), 400
    
    try:
        response = requests.put(
            f'https://api.spotify.com/v1/playlists/{playlist_id}',
            headers=headers,
            json=update_data
        )
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'Playlist updated successfully'})
        elif response.status_code == 403:
            return jsonify({'error': 'You do not have permission to edit this playlist'}), 403
        else:
            return jsonify({'error': f'Spotify API error: {response.status_code}'}), 400
            
    except Exception as e:
        print(f"Error editing playlist: {e}")
        return jsonify({'error': 'Failed to update playlist'}), 500

@app.route('/api/playlist/cover', methods=['POST'])
@login_required
def update_playlist_cover():
    """Update playlist cover image"""
    user = get_current_user()
    if not user or not user.spotify_access_token:
        return jsonify({'error': 'Spotify authentication required'}), 401
    
    data = request.json
    playlist_id = data.get('playlist_id')
    image_data_base64 = data.get('image_data')
    
    if not playlist_id or not image_data_base64:
        return jsonify({'error': 'Playlist ID and image data required'}), 400
    
    # Refresh token if needed
    if not user.refresh_spotify_token_if_needed():
        return jsonify({'error': 'Failed to refresh Spotify token'}), 401
    
    try:
        # Process the image data
        if image_data_base64.startswith('data:image'):
            # Remove data URL prefix
            image_data_base64 = image_data_base64.split(',')[1]
        
        # Decode base64 image
        image_bytes = base64.b64decode(image_data_base64)
        
        # Convert to PIL Image to ensure it's JPEG and within size limits
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize if too large (Spotify requirement: max 256KB)
        max_size = 256 * 1024  # 256KB
        quality = 90
        
        while True:
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=quality)
            if len(output.getvalue()) <= max_size or quality <= 10:
                break
            quality -= 10
        
        # Get final JPEG data
        jpeg_data = output.getvalue()
        jpeg_base64 = base64.b64encode(jpeg_data).decode('utf-8')
        
        # Upload to Spotify
        headers = {
            'Authorization': f'Bearer {user.spotify_access_token}',
            'Content-Type': 'image/jpeg'
        }
        
        response = requests.put(
            f'https://api.spotify.com/v1/playlists/{playlist_id}/images',
            headers=headers,
            data=jpeg_data
        )
        
        if response.status_code == 202:  # Spotify returns 202 for successful image upload
            return jsonify({'success': True, 'message': 'Playlist cover updated successfully'})
        elif response.status_code == 403:
            return jsonify({'error': 'You do not have permission to edit this playlist'}), 403
        else:
            print(f"Spotify cover upload error: {response.status_code} - {response.text}")
            return jsonify({'error': f'Spotify API error: {response.status_code}'}), 400
            
    except Exception as e:
        print(f"Error updating playlist cover: {e}")
        return jsonify({'error': 'Failed to update playlist cover'}), 500

@app.route('/api/playlist/info/<playlist_id>')
@login_required
def get_playlist_info(playlist_id):
    """Get playlist information"""
    user = get_current_user()
    if not user or not user.spotify_access_token:
        return jsonify({'error': 'Spotify authentication required'}), 401
    
    # Refresh token if needed
    if not user.refresh_spotify_token_if_needed():
        return jsonify({'error': 'Failed to refresh Spotify token'}), 401
    
    headers = {
        'Authorization': f'Bearer {user.spotify_access_token}'
    }
    
    try:
        response = requests.get(
            f'https://api.spotify.com/v1/playlists/{playlist_id}',
            headers=headers
        )
        
        if response.status_code == 200:
            playlist_data = response.json()
            return jsonify({
                'id': playlist_data['id'],
                'name': playlist_data['name'],
                'description': playlist_data.get('description', ''),
                'owner': playlist_data['owner']['display_name'],
                'owner_id': playlist_data['owner']['id'],
                'can_edit': playlist_data['owner']['id'] == user.spotify_id,
                'public': playlist_data['public'],
                'collaborative': playlist_data['collaborative'],
                'tracks_total': playlist_data['tracks']['total']
            })
        else:
            return jsonify({'error': 'Playlist not found or access denied'}), 404
            
    except Exception as e:
        print(f"Error getting playlist info: {e}")
        return jsonify({'error': 'Failed to get playlist information'}), 500

# Routes
@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Main route for the application - now requires login"""
    global initialized
    
    # Get current user
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    # Check generation limit
    if request.method == "POST" and not user.can_generate_today():
        from utils import get_available_loras
        return render_template(
            "index.html",
            error=f"Daily generation limit reached ({user.get_daily_generation_limit()} per day). Try again tomorrow!",
            loras=get_available_loras(),
            user=user
        )
    
    # Ensure app is initialized
    if not initialized:
        if initialize_app():
            print("Application initialized successfully")
        else:
            print("Failed to initialize application")
            return render_template(
                "index.html", 
                error="Failed to initialize application. Check server logs for details.",
                loras=[],
                user=user
            )
    
    # Import here to avoid circular imports
    from utils import get_available_loras
    from generator import generate_cover
    from chart_generator import generate_genre_chart
    
    # Get available LoRAs
    loras = get_available_loras()
    
    if request.method == "POST":
        try:
            playlist_url = request.form.get("playlist_url")
            user_mood = request.form.get("mood", "").strip()
            negative_prompt = request.form.get("negative_prompt", "").strip()
            
            # Handle LoRA selection - only from dropdown now
            lora_name = request.form.get("lora_name", "").strip()
            
            # Determine which LoRA to use
            lora_input = None
            if lora_name and lora_name != "none":
                # Using a saved LoRA from the dropdown
                for lora in loras:
                    if lora.name == lora_name:
                        lora_input = lora
                        break
            
            if not playlist_url:
                return render_template(
                    "index.html", 
                    error="Please enter a Spotify playlist or album URL.",
                    loras=loras,
                    user=user
                )
            
            # Generate cover with user context
            result = generate_cover(playlist_url, user_mood, lora_input, 
                                  negative_prompt=negative_prompt, user_id=user.id)
            
            # Handle errors
            if "error" in result:
                return render_template(
                    "index.html", 
                    error=result["error"],
                    loras=loras,
                    user=user
                )
            
            # Get the filename part from the full path
            img_filename = os.path.basename(result["output_path"])
            
            # Generate genre chart
            genres_chart = generate_genre_chart(result.get("all_genres", []))
            
            # Calculate genre percentages for visualization
            genre_percentages = calculate_genre_percentages(result.get("all_genres", []))
            
            # Log the base64 data length to see if it was generated
            if "image_data_base64" in result:
                base64_length = len(result["image_data_base64"])
                print(f"Base64 image data generated, length: {base64_length}")
            else:
                print("No base64 image data in result")
            
            # Data for display
            display_data = {
                "title": result["title"],
                "image_file": img_filename,
                "image_data_base64": result.get("image_data_base64", ""),
                "genres": ", ".join(result.get("genres", [])),
                "mood": result.get("mood", ""),
                "playlist_name": result.get("item_name", "Your Music"),
                "found_genres": bool(result.get("genres", [])),
                "genres_chart": genres_chart,
                "genre_percentages": genre_percentages,
                "playlist_url": playlist_url,
                "user_mood": user_mood,
                "negative_prompt": negative_prompt,
                "lora_name": result.get("lora_name", ""),
                "lora_type": result.get("lora_type", ""),
                "lora_url": result.get("lora_url", ""),
                "user": user,
                "can_edit_playlist": bool(user.spotify_access_token),  # Can edit if has Spotify token
                "playlist_id": extract_playlist_id(playlist_url) if "playlist/" in playlist_url else None
            }
            
            return render_template("result.html", **display_data)
        except Exception as e:
            print(f"Server error processing request: {e}")
            return render_template(
                "index.html", 
                error=f"An error occurred: {str(e)}",
                loras=loras,
                user=user
            )
    else:
        return render_template("index.html", loras=loras, user=user)

@app.route("/generated_covers/<path:filename>")
def serve_image(filename):
    """Serve generated images"""
    try:
        print(f"Attempting to serve image: {filename} from {COVERS_DIR}")
        
        # Create an absolute path to the file
        file_path = os.path.join(COVERS_DIR, filename)
        
        # Check if file exists
        if os.path.exists(file_path):
            return send_from_directory(COVERS_DIR, filename)
        else:
            print(f"Image file not found: {file_path}")
            # Return a placeholder image
            return send_from_directory(os.path.join(app.static_folder, "images"), "image-placeholder.png")
    except Exception as e:
        print(f"Error serving image {filename}: {e}")
        # Return a placeholder in case of error
        return send_from_directory(os.path.join(app.static_folder, "images"), "image-placeholder.png")

@app.route("/status")
def status():
    """API endpoint to check system status"""
    # Check if Spotify is initialized
    from spotify_client import sp
    from utils import get_available_loras
    
    return jsonify({
        "initialized": initialized,
        "spotify_working": sp is not None,
        "loras_available": len(get_available_loras())
    })

@app.route("/api/generate", methods=["POST"])
@login_required
def api_generate():
    """API endpoint to generate covers programmatically - now requires login"""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    
    # Check generation limit
    if not user.can_generate_today():
        return jsonify({
            "error": f"Daily generation limit reached ({user.get_daily_generation_limit()} per day). Try again tomorrow!"
        }), 429
    
    try:
        data = request.json
        if not data or "spotify_url" not in data:
            return jsonify({"error": "Missing spotify_url in request"}), 400
            
        spotify_url = data.get("spotify_url")
        user_mood = data.get("mood", "")
        negative_prompt = data.get("negative_prompt", "")
        
        # Import here to avoid circular imports
        from utils import get_available_loras
        from generator import generate_cover
        
        # Handle LoRA - simplified to only use name
        lora_name = data.get("lora_name", "")
        
        # Determine which LoRA to use
        lora_input = None
        if lora_name:
            # Try to find in available LoRAs
            loras = get_available_loras()
            for lora in loras:
                if lora.name == lora_name:
                    lora_input = lora
                    break
        
        # Generate the cover with user tracking
        result = generate_cover(spotify_url, user_mood, lora_input, 
                              negative_prompt=negative_prompt, user_id=user.id)
        
        if "error" in result:
            return jsonify({"error": result["error"]}), 400
            
        # Return result data, including base64 data for direct use
        return jsonify({
            "success": True,
            "title": result["title"],
            "image_path": result["output_path"],
            "image_url": f"/generated_covers/{os.path.basename(result['output_path'])}",
            "image_data_base64": result.get("image_data_base64", ""),
            "data_file": result.get("data_file"),
            "genres": result.get("genres", []),
            "mood": result.get("mood", ""),
            "playlist_name": result.get("item_name", ""),
            "lora_name": result.get("lora_name", ""),
            "lora_type": result.get("lora_type", ""),
            "user": user.to_dict()        })
    except Exception as e:
        print(f"API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/regenerate", methods=["POST"])
@login_required
def api_regenerate():
    """API endpoint to regenerate cover art with the same playlist - now requires login"""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    
    # Check generation limit
    if not user.can_generate_today():
        return jsonify({
            "error": f"Daily generation limit reached ({user.get_daily_generation_limit()} per day). Try again tomorrow!"
        }), 429
    
    try:
        data = request.json
        if not data or "playlist_url" not in data:
            return jsonify({"error": "Missing playlist_url in request"}), 400
            
        # Import here to avoid circular imports
        from utils import get_available_loras
        from generator import generate_cover
        
        spotify_url = data.get("playlist_url")
        user_mood = data.get("mood", "")
        negative_prompt = data.get("negative_prompt", "")
        
        # Handle LoRA - simplified to only use name
        lora_name = data.get("lora_name", "")
        
        # Determine which LoRA to use
        lora_input = None
        if lora_name:
            # Try to find in available LoRAs
            loras = get_available_loras()
            for lora in loras:
                if lora.name == lora_name:
                    lora_input = lora
                    break
          # Generate a new seed to ensure variation
        random_seed = random.randint(1, 1000000)
        
        # Generate the cover with user tracking
        result = generate_cover(spotify_url, user_mood, lora_input, 
                              negative_prompt=negative_prompt, user_id=user.id)
        
        if "error" in result:
            return jsonify({"error": result["error"]}), 400
            
        # Return result data
        return jsonify({
            "success": True,
            "title": result["title"],
            "image_path": result["output_path"],
            "image_url": f"/generated_covers/{os.path.basename(result['output_path'])}",
            "image_data_base64": result.get("image_data_base64", ""),
            "data_file": result.get("data_file", ""),
            "lora_name": result.get("lora_name", ""),
            "lora_type": result.get("lora_type", ""),
            "user": user.to_dict()
        })
    except Exception as e:
        print(f"API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/loras", methods=["GET"])
def api_loras():
    """API endpoint to get available LoRAs"""
    from utils import get_available_loras
    loras = get_available_loras()
    return jsonify({
        "loras": [lora.to_dict() for lora in loras]
    })

@app.route("/api/upload_lora", methods=["POST"])
def api_upload_lora():
    """API endpoint to upload a new LoRA file"""
    try:
        from utils import get_available_loras
        from config import LORA_DIR
        
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
            
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
            
        # Check file extension
        allowed_extensions = {'.safetensors', '.ckpt', '.pt'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        if file_ext not in allowed_extensions:
            return jsonify({"error": f"File must be one of: {', '.join(allowed_extensions)}"}), 400
            
        # Save the file
        filename = os.path.basename(file.filename)
        file.save(os.path.join(LORA_DIR, filename))
        
        return jsonify({
            "success": True,
            "message": f"LoRA file {filename} uploaded successfully",
            "loras": [lora.to_dict() for lora in get_available_loras()]
        })
    except Exception as e:
        print(f"API error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import sys
    
    # Check if running in CLI mode
    if len(sys.argv) > 1:
        if sys.argv[1] == "--generate" and len(sys.argv) >= 3:
            print(f"Starting Spotify Cover Generator in CLI mode")
            
            initialize_app()
            
            # Import here to avoid circular imports
            from models import LoraModel
            from generator import generate_cover
            from utils import get_available_loras
            
            spotify_url = sys.argv[2]
            mood = sys.argv[3] if len(sys.argv) >= 4 else None
            
            # Handle LoRA from command line - simplified to only use name
            lora_input = None
            if len(sys.argv) >= 5:
                lora_arg = sys.argv[4]
                # Try to find in available LoRAs
                loras = get_available_loras()
                for lora in loras:
                    if lora.name == lora_arg:
                        lora_input = lora
                        break
                
                # If not found, just use the name
                if not lora_input:
                    lora_input = lora_arg
            
            print(f"Generating cover for: {spotify_url}")
            if mood:
                print(f"Using mood: {mood}")
            if lora_input:
                if isinstance(lora_input, LoraModel):
                    print(f"Using LoRA: {lora_input.name} ({lora_input.source_type})")
                else:
                    print(f"Using LoRA: {lora_input}")
                
            result = generate_cover(spotify_url, mood, lora_input)
            
            if "error" in result:
                print(f"Error: {result['error']}")
                sys.exit(1)
                
            print(f"\nGeneration complete!")
            print(f"Title: {result['title']}")
            print(f"Image saved to: {result['output_path']}")
            print(f"Data saved to: {result.get('data_file', 'Not saved')}")
            sys.exit(0)
            
        elif sys.argv[1] == "--help":
            print("Spotify Cover Generator CLI Usage:")
            print("  Generate a cover: python app.py --generate <spotify_url> [mood] [lora_name]")
            print("  Start web server: python app.py")
            print("  Show this help:   python app.py --help")
            sys.exit(0)
    
    # Default to web server mode
    print(f"Starting Spotify Cover Generator")
    
    initialize_app()
    app.run(debug=False, host="0.0.0.0", port=50)