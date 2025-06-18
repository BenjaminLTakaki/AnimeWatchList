import os
import sys
import random
import datetime
import uuid
from pathlib import Path
from flask import Flask, session, request, current_app, render_template, jsonify, redirect, url_for, flash, make_response # Added more flask imports
from sqlalchemy import text # For health check db.session.execute
from werkzeug.security import generate_password_hash, check_password_hash

get_current_user_or_guest_global_ref = None

def monitor_performance(f):
    """Basic performance monitoring decorator (placeholder)."""
    import functools
    import time
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        result = f(*args, **kwargs)
        end_time = time.time()
        print(f"PERF: {f.__name__} took {end_time - start_time:.4f} seconds.")
        return result
    return decorated_function

def get_current_user_or_guest_factory_func(auth_utils_module, models_module, app_module_for_session_fns):
    """
    Factory to create get_current_user_or_guest function.
    Dependencies are passed to avoid circular imports at module level.
    """
    # Ensure models are loaded for User methods like get_generations_today
    User = models_module.User
    GenerationResultDB = models_module.GenerationResultDB

    def _get_current_user_or_guest():
        user = auth_utils_module.get_current_user()
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
            if 'guest_session_id' not in session:
                session['guest_session_id'] = str(uuid.uuid4())
                session['guest_created'] = datetime.datetime.utcnow().isoformat()
                session['guest_generations_today'] = 0
                session['guest_last_generation'] = None

            guest_generations_today = session.get('guest_generations_today', 0)
            if session.get('guest_last_generation'):
                try:
                    last_gen_date = datetime.datetime.fromisoformat(session['guest_last_generation']).date()
                    if last_gen_date != datetime.datetime.utcnow().date():
                        guest_generations_today = 0
                        session['guest_generations_today'] = 0
                except ValueError:
                     guest_generations_today = 0
                     session['guest_generations_today'] = 0

            daily_guest_limit = 1
            can_guest_gen = guest_generations_today < daily_guest_limit

            return {
                'type': 'guest',
                'user': None,
                'display_name': 'Guest',
                'is_premium': False,
                'daily_limit': daily_guest_limit,
                'generations_today': guest_generations_today,
                'can_generate': can_guest_gen,
                'can_use_loras': False,
                'can_edit_playlists': False,
                'show_upload': False
            }
    return _get_current_user_or_guest

def initialize_database_safely(app_instance, db_instance):
    """Safely initialize database within app context."""
    try:
        with app_instance.app_context():
            db_instance.create_all()
            print("✅ Database tables created successfully via factory's initialize_database_safely.")
    except Exception as e:
        print(f"❌ Database initialization failed in factory: {e}")

def create_app(test_config_dict=None): # Modified signature
    """Application factory function."""
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

    app.config.update(
        SECRET_KEY=os.environ.get('FLASK_SECRET_KEY', 'dev-key-' + uuid.uuid4().hex),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "app.db"}'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SPOTIFY_CLIENT_ID=os.environ.get('SPOTIFY_CLIENT_ID'),
        SPOTIFY_CLIENT_SECRET=os.environ.get('SPOTIFY_CLIENT_SECRET'),
        SPOTIFY_REDIRECT_URI=os.environ.get('SPOTIFY_REDIRECT_URI', 'http://localhost:5000/spotify-callback'),
        COVERS_DIR=BASE_DIR / "generated_covers",
        LORA_DIR=BASE_DIR / "loras", # Default LORA_DIR
        BASE_DIR=BASE_DIR,
        MONITORING_AVAILABLE=False,
        FAULT_HANDLING_AVAILABLE=False,
        MAX_LORAS_NON_PREMIUM=2 # Default for get_upload_info
    )

    if os.path.exists(BASE_DIR / "config.py"):
        try:
            # Store current LORA_DIR before loading from_pyfile, in case it's not in config.py
            default_lora_dir = app.config['LORA_DIR']
            app.config.from_pyfile(BASE_DIR / "config.py")
            # If LORA_DIR was not in config.py, from_pyfile might have removed it if it was a default
            # This ensures LORA_DIR is preserved if not explicitly set in config.py
            if 'LORA_DIR' not in app.config:
                app.config['LORA_DIR'] = default_lora_dir
            print("✅ Loaded configuration from config.py")
        except Exception as e:
            print(f"⚠️ Could not load from config.py: {e}")

    # Ensure LORA_DIR is created (it might have been updated by config.py)
    # This logic was in config.py but safer to have it here after all config is loaded.
    lora_dir_to_create = Path(app.config.get('LORA_DIR'))
    try:
        lora_dir_to_create.mkdir(parents=True, exist_ok=True)
        print(f"✅ Ensured LORA_DIR exists: {lora_dir_to_create}")
    except Exception as e:
        print(f"⚠️ Could not create LORA_DIR {lora_dir_to_create}: {e}. Check permissions or path.")
        # Fallback or error further if LORA_DIR is critical and couldn't be made

    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
        app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)

    if not os.path.exists(app.config['COVERS_DIR']):
        os.makedirs(app.config['COVERS_DIR'])

    from .extensions import db, migrate, limiter
    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    from . import models
    from . import auth_utils

    global get_current_user_or_guest_global_ref
    get_current_user_or_guest_global_ref = get_current_user_or_guest_factory_func(auth_utils, models, None)

    initialize_database_safely(app, db)

    @app.context_processor
    def inject_template_vars():
        return {
            'current_year': datetime.datetime.now().year,
            'user_info': get_current_user_or_guest_global_ref()
        }

    try:
        from .monitoring_system import setup_monitoring
        setup_monitoring(app)
        app.config['MONITORING_AVAILABLE'] = True
        print("✅ Monitoring system setup in factory")
    except ImportError:
        print("⚠️ Monitoring system import failed in factory (Not an error if optional)")
        if not hasattr(app, 'logger_instance'):
            class DummyLogger:
                def log_structured(self, *args, **kwargs): pass
            app.logger_instance = DummyLogger()

    try:
        app.config['FAULT_HANDLING_AVAILABLE'] = True
        print("✅ Fault handling assumed available/configured in factory")
    except ImportError:
        print("⚠️ Fault handling import failed in factory (Not an error if optional)")

    # Placeholder for blueprint registration
    from .main import bp as main_bp
    app.register_blueprint(main_bp)

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp) # No prefix for /login, /register, etc.

    from .spotify_routes import bp as spotify_routes_bp
    # Prefix for spotify routes already in their definitions, e.g. /spotify/api/loras
    # So, no url_prefix here, or ensure it matches if routes are /api/loras etc.
    app.register_blueprint(spotify_routes_bp)

    # Apply test configuration if provided
    if test_config_dict:
        app.config.from_mapping(test_config_dict)

    return app
