import os
import sys
import random
import json
import datetime
import traceback
import uuid 
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse
from functools import wraps

import requests
import base64
import secrets
from collections import Counter

from flask import (Flask, request, render_template, send_from_directory, jsonify,
                   session, redirect, url_for, flash, make_response)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
# Removed flask_sqlalchemy import, will be handled by extensions
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from sqlalchemy import text

from .extensions import db # Import db from extensions
from .utils import (
    calculate_genre_percentages,
    extract_playlist_id,
    ensure_tables_exist, # Will call create_tables_manually internally
    get_or_create_guest_session,
    get_guest_generations_today,
    increment_guest_generations,
    can_guest_generate,
    track_guest_generation
)

# Monitoring and fault handling imports
from .monitoring_system import (
    setup_monitoring,
    monitor_performance,
    # monitor_api_calls, # Not directly used in app.py
    app_logger,
    alert_manager,
    health_checker # Used in /health route
)
from .fault_handling import (
    FaultContext,
    create_user_friendly_error_messages
    # fault_tolerant_api_call, # Not directly used in app.py
    # GracefulDegradation, db_failover, http_client # Not directly used in app.py
)
print("✅ Successfully imported monitoring and fault_handling modules.")

# Direct configuration import
from .config import (
    BASE_DIR, COVERS_DIR, FLASK_SECRET_KEY,
    SPOTIFY_DB_URL, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI, GEMINI_API_KEY, STABILITY_API_KEY
)
print("Successfully imported configurations from config.py")

# Flask app initialization
app = Flask(__name__,
            template_folder=str(BASE_DIR / "templates"),
            static_folder=str(BASE_DIR / "static"))
app.secret_key = FLASK_SECRET_KEY or ''.join(random.choices(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=24))

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = SPOTIFY_DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize db with app from extensions
db.init_app(app)
migrate = Migrate(app, db)

# Import models after db is initialized and before it's used by other functions or routes
from .database_models import User, LoginSession, SpotifyState, LoraModelDB, GenerationResultDB
# If database_models.py needs db from app.py, you might need to adjust imports
# For example, if database_models.py has `from .app import db` (circular)
# or if you pass `db` to an init_app function in database_models.py.
# Assuming for now that models in database_models.py are defined with their own `db = SQLAlchemy()`
# or correctly pick up this `db` instance upon import.

# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"],
    storage_uri="memory://"
)
limiter.init_app(app)

# HELPER FUNCTIONS
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
            app_logger.error("fetch_user_by_id_session_error", details=str(e), exc_info=True)
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
            app_logger.error("fetch_user_by_session_token_error", details=str(e), exc_info=True)
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
            app_logger.error("fetch_user_by_cookie_error", details=str(e), exc_info=True)
    
    return None

# Global initialization flag
initialized = False
# calculate_genre_percentages, extract_playlist_id, ensure_tables_exist, and create_tables_manually
# have been moved to utils.py
# Guest session functions also moved to utils.py

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
                
                app_logger.info("lora_migration_check", message=f"Existing columns in spotify_lora_models: {existing_columns}")
                
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
                        app_logger.info("lora_migration_executed", migration=migration)
                    except Exception as e:
                        app_logger.warning("lora_migration_skipped", migration=migration, error=str(e), exc_info=True)
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
                    app_logger.info("lora_fk_constraint_verified", constraint="fk_lora_models_uploaded_by")
                except Exception as e:
                    app_logger.warning("lora_fk_constraint_warning", error=str(e), exc_info=True)
                
                app_logger.info("lora_migration_completed", status="success")
                return True
                
    except Exception as e:
        app_logger.error("lora_migration_failed", error=str(e), exc_info=True)
        return False

def initialize_app():
    """Initialize the application's dependencies with better import handling"""
    global initialized
    
    print("🔧 Initializing Spotify Cover Generator...")
    
    # Make sure necessary directories exist first
    try:
        os.makedirs(COVERS_DIR, exist_ok=True)
        # Create LoRA directory for file uploads
        lora_dir = BASE_DIR / "loras"
        os.makedirs(lora_dir, exist_ok=True)
        app_logger.info("directory_creation_success", directories=[str(COVERS_DIR), str(lora_dir)])
    except Exception as e:
        app_logger.warning("directory_creation_warning", error=str(e), exc_info=True)
    
    # Database setup
    try:
        with app.app_context():
            print("📊 Setting up database...")
            
            # Test database connection
            try:
                with db.engine.connect() as connection:
                    connection.execute(text('SELECT 1'))
                app_logger.info("database_connection_success")
            except Exception as e:
                app_logger.error("database_connection_failed", error=str(e), exc_info=True)
                return False
            
            # Check and create tables
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            app_logger.info("db_setup_existing_tables", tables=existing_tables)
            
            db.create_all() # This needs to be within app_context, which it is.
            app_logger.info("db_create_all_executed")
            
            # Run LoRA table migration
            migrate_lora_table()
            
            # Ensure all tables exist using the utility function
            # This function (now in utils.py) handles db.create_all() and manual creation if needed.
            ensure_tables_exist()

            # Verify required tables exist (optional, as ensure_tables_exist should handle it)
            # For robustness, a light check can remain or be added to ensure_tables_exist
            inspector = db.inspect(db.engine) # Re-inspect after ensure_tables_exist
            final_tables = inspector.get_table_names()
            required_tables = [
                'spotify_users', 
                'spotify_login_sessions', 
                'spotify_oauth_states',
                'spotify_generation_results',
                'spotify_lora_models'
            ]
            missing_after_ensure = [t for t in required_tables if t not in final_tables]
            if missing_after_ensure:
                app_logger.critical("db_setup_missing_tables_after_ensure", missing_tables=missing_after_ensure)
                # This would indicate a problem with ensure_tables_exist or db setup.
                return False # Hard fail if tables are still not there.
            else:
                app_logger.info("db_setup_all_tables_confirmed")
                
    except Exception as e:
        app_logger.error("database_setup_failed", error=str(e), exc_info=True)
        return False
    
    # Import modules with better error handling
    app_logger.info("module_import_start")
    
    # Global variables to track what's available
    global spotify_client_available, models_available, utils_available, generator_available
    global title_generator_available, image_generator_available, chart_generator_available # Add for more granular checks if needed
    spotify_client_available = False
    models_available = False
    utils_available = False # This will track the import of the 'utils' module as a whole
    generator_available = False
    title_generator_available = False
    image_generator_available = False
    chart_generator_available = False

    # Try importing modules using relative imports
    try:
        from . import spotify_client
        app_logger.info("module_import_success", module="spotify_client")
        spotify_client_available = True
    except ImportError as e:
        app_logger.warning("module_import_failed", module="spotify_client", error=str(e))
        
    try:
        from . import models
        app_logger.info("module_import_success", module="models")
        models_available = True
    except ImportError as e:
        app_logger.warning("module_import_failed", module="models", error=str(e))
        
    try:
        # Attempt to import the utils module itself. Specific functions are already imported at the top.
        # This is for checking availability of the module if it's used like 'utils.some_function()'
        from . import utils as initialize_app_utils # Use an alias to avoid conflict if 'utils' name is used elsewhere
        app_logger.info("module_import_success", module="utils")
        utils_available = True # Flag that the utils module (aliased) is available
    except ImportError as e:
        app_logger.warning("module_import_failed", module="utils", error=str(e))
    
    try:
        from . import generator
        app_logger.info("module_import_success", module="generator")
        generator_available = True
    except ImportError as e:
        app_logger.warning("module_import_failed", module="generator", error=str(e))

    try:
        from . import title_generator
        app_logger.info("module_import_success", module="title_generator")
        title_generator_available = True
    except ImportError as e:
        app_logger.warning("module_import_failed", module="title_generator", error=str(e))

    try:
        from . import image_generator
        app_logger.info("module_import_success", module="image_generator")
        image_generator_available = True
    except ImportError as e:
        app_logger.warning("module_import_failed", module="image_generator", error=str(e))

    try:
        from . import chart_generator
        app_logger.info("module_import_success", module="chart_generator")
        chart_generator_available = True
    except ImportError as e:
        app_logger.warning("module_import_failed", module="chart_generator", error=str(e))

    app_logger.info("module_import_completed")
    
    # Initialize Spotify client if available
    if spotify_client_available:
        app_logger.info("spotify_client_initialization_start")
        try:
            spotify_initialized = spotify_client.initialize_spotify()
            if spotify_initialized:
                app_logger.info("spotify_client_initialization_success")
            else:
                app_logger.warning("spotify_client_initialization_failed_functional")
        except Exception as e:
            app_logger.error("spotify_client_initialization_error", error=str(e), exc_info=True)
    else:
        app_logger.warning("spotify_client_unavailable_for_initialization")
    
    # Check environment variables (values are now directly imported from config)
    app_logger.info("env_variable_check_start")
    # GEMINI_API_KEY and STABILITY_API_KEY are already imported directly from config.
    
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
        app_logger.error("missing_env_variables", missing_keys=missing) if missing else app_logger.info("all_env_variables_present")
    
    # Set initialization status
    initialized = env_vars_present and (spotify_client_available or models_available)
    
    if initialized:
        app_logger.info("application_initialization_status", status="success")
    else:
        app_logger.warning("application_initialization_status", status="limited_functionality")
    
    return initialized

# create_tables_manually function has been moved to utils.py

# Guest session functions are now in utils.py:
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

# Guest session functions are now in utils.py:
# get_or_create_guest_session, get_guest_generations_today,
# increment_guest_generations, can_guest_generate, track_guest_generation
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
            'show_upload': user.is_premium_user()  # ONLY premium users can upload files
        }
    else:
        # Uses utils.get_or_create_guest_session, utils.get_guest_generations_today, utils.can_guest_generate
        get_or_create_guest_session()
        return {
            'type': 'guest',
            'user': None,
            'display_name': 'Guest',
            'is_premium': False,
            'daily_limit': 1, # This could be current_app.config.get('GUEST_DAILY_LIMIT', 1)
            'generations_today': get_guest_generations_today(),
            'can_generate': can_guest_generate(),
            'can_use_loras': False,
            'can_edit_playlists': False,
            'show_upload': False
        }

# track_guest_generation moved to utils.py

# Context processor to inject common template variables
@app.context_processor
def inject_template_vars():
    """Inject common variables into all templates"""
    return {
        'current_year': datetime.datetime.now().year,
        'user_info': get_current_user_or_guest()
    }

# ROUTES
@app.route("/")
def root():
    """Root route - redirect to login if not authenticated, otherwise to main app"""
    user = get_current_user()
    if user:
        return redirect(url_for('generate'))
    else:
        return redirect(url_for('login'))

@app.route("/generate", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"]) # Keep limiter for specific routes
@monitor_performance # Apply performance monitoring
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
        if initialize_app(): # This is the app.py initialize_app
            app_logger.info("app_initialization_from_route", route="generate", status="success")
        else:
            app_logger.error("app_initialization_from_route_failed", route="generate")
            return render_template(
                "index.html", 
                error="Application is still initializing or encountered an issue. Please try again in a moment.", # User-friendly
                loras=[]
            )
    
    # Get available loras (only for logged-in users)
    loras = []
    if user_info['can_use_loras']:
        try:
            # utils_available is set in initialize_app based on 'from . import utils as initialize_app_utils'
            # Specific utils functions are imported at the top of app.py
            # If get_available_loras is a function in utils.py, we use the alias.
            if 'utils_available' in globals() and utils_available:
                # If initialize_app_utils.get_available_loras() is how it's meant to be called:
                # from . import utils as initialize_app_utils # This is in initialize_app()
                # loras = initialize_app_utils.get_available_loras()
                # However, if get_available_loras is not part of the top-level utils imports,
                # and initialize_app makes 'utils' (the module) available, this is how it would be called.
                # Let's assume initialize_app makes 'utils' (the module) available via 'initialize_app_utils'
                # And 'get_available_loras' is a function within that module.
                # The alias 'initialize_app_utils' is defined in 'initialize_app'
                # For this to work here, initialize_app_utils must be global or passed around.
                # Simpler: if 'utils_available' is True, it means 'from . import utils as initialize_app_utils' succeeded.
                # We need to ensure 'initialize_app_utils' is accessible here or change how 'get_available_loras' is called.
                # For now, let's assume 'initialize_app_utils' is made global from initialize_app, or this part needs a direct import.
                # Given the current structure, it's better if initialize_app sets a global alias or generate() imports it.
                # To ensure utils.get_available_loras() works, 'utils' module itself needs to be imported.
                # The top level has 'from .utils import ... specific functions ...'
                # Let's ensure 'utils' module is imported in 'initialize_app' and made available,
                # e.g. by 'global initialize_app_utils' and then using 'initialize_app_utils.get_available_loras()'
                # For now, will try to import it directly here if utils_available is true.
                if utils_available: # utils_available is set by initialize_app
                    from . import utils as route_utils # Import utils for this route's scope
                    loras = route_utils.get_available_loras()
        except ImportError as e:
            app_logger.warning("get_loras_import_failed_in_route", error=str(e), exc_info=True)
        except Exception as e:
            app_logger.warning("get_loras_failed", error=str(e), exc_info=True)

    if request.method == "POST":
        try:
            # Check if core generation modules are available
            # These globals (generator_available, etc.) are set by initialize_app()
            if not (generator_available and spotify_client_available):
                app_logger.warning("generation_modules_unavailable_on_post",
                                   generator_available=generator_available,
                                   spotify_client_available=spotify_client_available)
                # Attempt re-import or fail gracefully
                try:
                    # Use relative imports for on-demand re-import
                    from . import generator
                    from . import spotify_client
                    # Re-set global flags if successful, though ideally initialize_app handles this.
                    # This is a fallback.
                    global generator_available, spotify_client_available
                    generator_available = True # Mark as available if re-import succeeds
                    spotify_client_available = True # Mark as available
                    app_logger.info("generation_modules_reimported_on_demand_relatively")
                except ImportError as import_e:
                    app_logger.error("core_generation_modules_reimport_failed_relatively", error=str(import_e))
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
            # generator module should be available if generator_available is True
            from . import generator # Ensure it's imported for this scope
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
                track_guest_generation()
            
            img_filename = os.path.basename(result["output_path"])
            
            # Generate charts with fallback
            genres_chart_data = None
            genre_percentages_data = []
            
            try:
                # chart_generator module should be available if chart_generator_available is True from initialize_app
                if chart_generator_available:
                    from . import chart_generator # Ensure it's imported for this scope
                    genres_chart_data = chart_generator.generate_genre_chart(result.get("all_genres", []))
                else:
                    app_logger.warning("chart_generator_module_not_available_for_chart")
                    genres_chart_data = None
            except ImportError: # Fallback if direct import fails
                app_logger.warning("chart_generator_unavailable_on_import_in_route")
            except Exception as e:
                app_logger.error("genre_chart_generation_failed", error=str(e), exc_info=True)

            try:
                # utils.calculate_genre_percentages is now imported at the top
                genre_percentages_data = calculate_genre_percentages(result.get("all_genres", []))
            except Exception as e:
                app_logger.error("genre_percentages_calculation_failed", error=str(e), exc_info=True)
            
            # Extract playlist ID with fallback
            playlist_id = None
            try:
                # utils.extract_playlist_id is now imported at the top
                playlist_id = extract_playlist_id(playlist_url) if playlist_url and "playlist/" in playlist_url else None
            except Exception as e:
                app_logger.error("extract_playlist_id_failed", error=str(e), exc_info=True)
            
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
                    app_logger.error("save_generation_to_db_failed", error=str(e), exc_info=True)

            return render_template("result.html", **display_data)
        except Exception as e:
            app_logger.error("generate_post_request_failed", error=str(e), exc_info=True)
            # No need for traceback.print_exc() as app_logger with exc_info=True handles it.
            return render_template(
                "index.html", 
                error=f"An unexpected error occurred: {str(e)}. Please try again.",
                loras=loras
            )
    else:
        return render_template("index.html", loras=loras)

# LoRA UPLOAD ROUTE (FIXED FOR FILE UPLOADS ONLY)
@app.route('/spotify/api/upload_lora', methods=['POST'])
@login_required
@limiter.limit("5 per hour") # Keep specific limiter
@monitor_performance # Apply performance monitoring
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
        app_logger.error("upload_lora_failed", error=str(e), exc_info=True)
        return jsonify({"success": False, "error": "Internal server error"}), 500

# Add new LoRA management and upload info routes
@app.route('/spotify/api/delete_lora', methods=['DELETE'])
@login_required
@limiter.limit("10 per hour") # Keep specific limiter
@monitor_performance # Apply performance monitoring
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
                app_logger.info("lora_file_deleted_fs", path=lora_record.path)
            except Exception as e:
                app_logger.error("lora_file_delete_fs_failed", path=lora_record.path, error=str(e), exc_info=True)
        db.session.delete(lora_record)
        db.session.commit()
        return jsonify({"success": True, "message": f"LoRA '{lora_name}' deleted successfully"})
    except Exception as e:
        app_logger.error("delete_lora_db_failed", lora_name=lora_name, error=str(e), exc_info=True)
        return jsonify({"success": False, "error": "Internal server error"}), 500


def get_user_lora_upload_info(user):
    """Get user's LoRA upload info"""
    if not user:
        return {"can_upload": False, "current_count": 0, "limit": 0}
    current_count = LoraModelDB.query.filter_by(source_type="local", uploaded_by=user.id).count()
    if user.is_premium_user():
        return {"can_upload": True, "current_count": current_count, "limit": "unlimited", "is_premium": True}
    return {"can_upload": current_count < 2, "current_count": current_count, "limit": 2, "is_premium": False}

@app.route('/spotify/api/upload_info')
@login_required
def get_upload_info():
    """Get user's upload information"""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(get_user_lora_upload_info(user))

@app.route('/spotify/api/loras')
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
        app_logger.error("get_loras_api_failed", error=str(e), exc_info=True)
        return jsonify({"loras": []})

# SPOTIFY AUTH ROUTES (FIXED)
@app.route('/spotify-login')
@monitor_performance # Apply performance monitoring
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
    scope = 'playlist-read-private playlist-modify-public playlist-modify-private ugc-image-upload user-read-email user-read-private'
    redirect_uri = SPOTIFY_REDIRECT_URI
    
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
@monitor_performance # Apply performance monitoring
def spotify_callback():
    """Handle Spotify OAuth callback - FIXED PREMIUM DETECTION"""
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
        if not SpotifyState.verify_and_use_state(state):
            flash('Invalid state parameter', 'error')
            return redirect(url_for('generate'))
        
        # Exchange code for tokens
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': SPOTIFY_REDIRECT_URI,
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
        
        app_logger.debug("spotify_user_auth_data", data=spotify_user)
        
        # Find or create user
        user = User.query.filter_by(spotify_id=spotify_id).first()
        
        if not user:
            # Create new user
            user = User(
                spotify_id=spotify_id,
                spotify_username=spotify_user.get('id'), # Often same as id
                display_name=spotify_user.get('display_name', spotify_user.get('id')),
                email=spotify_user.get('email'), # May be null
                is_premium=False
            )
            db.session.add(user)
            app_logger.info("new_user_created_from_spotify_auth", spotify_id=spotify_id, email=user.email)
        else:
            # Update existing user
            user.display_name = spotify_user.get('display_name', user.display_name) # Keep old if new is null
            user.email = spotify_user.get('email') or user.email # Keep old if new is null
            app_logger.info("existing_user_updated_from_spotify_auth", spotify_id=spotify_id, email=user.email)
        
        # Update tokens
        user.spotify_access_token = access_token
        user.spotify_refresh_token = refresh_token
        user.spotify_token_expires = datetime.datetime.utcnow() + timedelta(seconds=expires_in)
        user.last_login = datetime.datetime.utcnow()
        
        db.session.commit()
        
        # Check if user is premium AFTER saving to database
        is_premium = user.is_premium_user() # This method itself contains logic for premium check
        app_logger.info("user_premium_check_result",
                        spotify_id=user.spotify_id,
                        is_premium=is_premium,
                        email=user.email,
                        spotify_username=user.spotify_username)
        
        # Create login session
        session_token = LoginSession.create_session(
            user.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        
        # Set session variables
        session['user_id'] = user.id
        session['user_session'] = session_token
        session['username'] = user.display_name or user.username
        
        # Create response with cookie
        resp = make_response(redirect(url_for('generate')))
        resp.set_cookie('session_token', session_token, max_age=30*24*60*60)  # 30 days
        
        # Show different flash messages based on premium status
        if is_premium:
            flash('🌟 Welcome back, Premium user! You have unlimited generations and file upload access.', 'success')
        else:
            flash('Successfully connected to Spotify! You have 2 daily generations.', 'success')
        
        return resp
        
    except Exception as e:
        app_logger.error("spotify_callback_failed", error=str(e), exc_info=True)
        flash('An error occurred during Spotify authorization. Please try again.', 'error')
        return redirect(url_for('generate'))

# OTHER ROUTES (login, logout, profile, etc. - keep existing)
@app.route('/login', methods=['GET', 'POST'])
@monitor_performance # Apply performance monitoring
def login():
    """Login route - handle both form login and Spotify OAuth"""
    if request.method == 'POST':
        # Handle form-based login
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
    
    return render_template('login.html')

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
    
    # clear all session data
    session.clear()
    
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
@monitor_performance # Apply performance monitoring
def register():
    """Register route"""
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
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            app_logger.error("user_registration_failed", email=email, username=username, error=str(e), exc_info=True)
            flash('Registration failed. Please try again.', 'error')
            return redirect(url_for('register'))
        
    return render_template('register.html')

@app.route('/profile')
@login_required
@monitor_performance # Apply performance monitoring
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

@app.route("/generated_covers/<path:filename>")
def serve_image(filename):
    return send_from_directory(COVERS_DIR, filename)

if not any(rule.endpoint == 'health_check' for rule in app.url_map.iter_rules()):
    @app.route('/health')
    def health_check():
        """Health check endpoint for monitoring"""
        try:
        # health_checker imported at the top
            health_results = health_checker.run_all_checks()
            all_healthy = all(result.healthy for result in health_results.values())
            
            response_data = {
                "status": "healthy" if all_healthy else "degraded",
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "services": {name: {
                    "healthy": result.healthy,
                    "response_time_ms": result.response_time_ms,
                    "error": result.error
                } for name, result in health_results.items()}
            }
            return jsonify(response_data), 200 if all_healthy else 503
        except Exception as e: # Catch if health_checker itself fails
            app_logger.critical("health_check_endpoint_failed", error=str(e), exc_info=True)
            return jsonify({
                "status": "error", 
                "error": "Health check system failed", # Generic error message
                "details": str(e), # Specific error details for logging/debugging
                "timestamp": datetime.datetime.utcnow().isoformat()
            }), 500

@app.route('/metrics')
def metrics_endpoint():
    """Metrics endpoint for performance monitoring"""
    try:
        # app_logger imported at the top
        metrics_data = {
            "performance": app_logger.get_performance_summary(), # Assuming this method exists on app_logger
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
        return jsonify(metrics_data), 200
    except Exception as e:
        # Log this error, as the metrics endpoint itself failing is an issue
        try: # Nested try to ensure app_logger is available
            app_logger.error("metrics_endpoint_failed", error=str(e), exc_info=True)
        except: # Fallback if app_logger is not even available
            print(f"CRITICAL: Metrics endpoint failed and app_logger unavailable: {e}")

        return jsonify({
            "error": "Metrics not available",
            "message": str(e), # Potentially sensitive, consider generic message in prod
            "timestamp": datetime.datetime.utcnow().isoformat()
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
        
        # FaultContext and create_user_friendly_error_messages are imported at the top of the file
        # from .fault_handling import FaultContext, create_user_friendly_error_messages
        # No need to re-import here if top-level import is successful and they are in scope.
        try:
            # from fault_handling import FaultContext, create_user_friendly_error_messages # This line is removed
            context = FaultContext( # This should work if top-level import was successful
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

# Set up monitoring when app starts - this block is already correct from previous steps.
# The try-except around setup_monitoring with setup_basic_monitoring as fallback is good.
# No changes needed to this specific block below based on current instructions.

if __name__ == '__main__':
    print("Initializing application...")
    # Application startup logic
    # Call the local initialize_app function (defined in this file, app.py)
    if initialize_app(): # This is app.initialize_app()
        print("Application initialized successfully")
    else:
        print("Application initialization had issues; CRITICAL. Check logs.")
        # Depending on severity, you might want to sys.exit(1) here
        # For now, it will continue as per original logic.
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)