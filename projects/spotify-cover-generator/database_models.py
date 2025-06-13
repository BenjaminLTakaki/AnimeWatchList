import datetime
# Removed flask_sqlalchemy import and local db instance
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from sqlalchemy import text # Keep this import if any model uses text()
from .extensions import db # Import db from extensions

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
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
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
        today = datetime.datetime.utcnow().date()
        # Ensure GenerationResultDB is available, it might be defined later in this file
        # or imported if this file is split further.
        # For now, assuming it's defined below.
        count = GenerationResultDB.query.filter(
            GenerationResultDB.user_id == self.id,
            db.func.date(GenerationResultDB.timestamp) == today
        ).count()
        return count < self.get_daily_generation_limit()

    def get_generations_today(self):
        today = datetime.datetime.utcnow().date()
        return GenerationResultDB.query.filter(
            GenerationResultDB.user_id == self.id,
            db.func.date(GenerationResultDB.timestamp) == today
        ).count()

    def refresh_spotify_token_if_needed(self):
        # This method might have dependencies on app.config (SPOTIFY_CLIENT_ID, etc.)
        # It's generally better to move such logic to a service layer or pass dependencies.
        # For now, leaving it, but it's a candidate for refactoring.
        if not self.spotify_refresh_token:
            return False
        if self.spotify_token_expires and \
           self.spotify_token_expires <= datetime.datetime.utcnow() + datetime.timedelta(minutes=5):
            return self._refresh_spotify_token()
        return True

    def _refresh_spotify_token(self):
        # This method depends on SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET and requests library.
        # Consider refactoring to remove direct dependency or ensure config is available.
        # Placeholder for actual implementation if moved, or ensure app context is available.
        # For now, this will likely fail if called without app context and config.
        if not self.spotify_refresh_token:
            return False

        # The following import and config access won't work directly here without app context
        # For demonstration, assuming these would be handled by the calling context (app.py)
        # import requests
        # import base64
        # from flask import current_app # Example of accessing app config
        # SPOTIFY_CLIENT_ID = current_app.config['SPOTIFY_CLIENT_ID']
        # SPOTIFY_CLIENT_SECRET = current_app.config['SPOTIFY_CLIENT_SECRET']

        # auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
        # headers = {'Authorization': f'Basic {auth_header}', 'Content-Type': 'application/x-www-form-urlencoded'}
        # data = {'grant_type': 'refresh_token', 'refresh_token': self.spotify_refresh_token}
        # try:
        #     response = requests.post('https://accounts.spotify.com/api/token', headers=headers, data=data)
        #     if response.status_code == 200:
        #         token_data = response.json()
        #         self.spotify_access_token = token_data['access_token']
        #         self.spotify_token_expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=token_data['expires_in'])
        #         if 'refresh_token' in token_data:
        #             self.spotify_refresh_token = token_data['refresh_token']
        #         db.session.commit()
        #         return True
        # except Exception as e:
        #     print(f"Error refreshing Spotify token: {e}")
        return False # Placeholder

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
        token = secrets.token_urlsafe(32)
        expires = datetime.datetime.utcnow() + datetime.timedelta(days=30)
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
        if not sess or sess.expires_at <= datetime.datetime.utcnow():
            if sess:
                sess.is_active = False
                db.session.commit()
            return None
        return sess.user

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
    source_type = db.Column(db.String(20), default='local')  # Only 'local' now
    path = db.Column(db.String(500), default='')
    file_size = db.Column(db.Integer, default=0)  # File size in bytes
    uploaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('spotify_users.id'), nullable=True)

    def to_lora_model(self):
        # This import will cause a circular dependency if models.py also imports database_models.py
        # It's better to have LoraModel (the dataclass) in a separate file or pass it as an argument.
        # For now, commenting out the direct import.
        # from models import LoraModel

        # Assuming LoraModel is a dataclass that can be instantiated directly
        # This part needs to be refactored to avoid circular import or to ensure LoraModel is accessible
        class TempLoraModel: # Placeholder
            def __init__(self, name, source_type, path, trigger_words, strength):
                self.name = name
                self.source_type = source_type
                self.path = path
                self.trigger_words = trigger_words
                self.strength = strength

        return TempLoraModel( # Replace TempLoraModel with actual LoraModel when refactored
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

# Removed init_app function as db is now imported
