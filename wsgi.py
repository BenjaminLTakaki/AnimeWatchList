import os
import sys
import datetime
from flask import Flask, send_from_directory, redirect, request
from dotenv import load_dotenv
from flask_migrate import Migrate

# Load environment variables
load_dotenv()

# Create a main application to serve static files
main_app = Flask(__name__, static_folder='.')

# Set the Python path to include the project directories
project_root = os.path.dirname(os.path.abspath(__file__))
projects_dir = os.path.join(project_root, 'projects')
if projects_dir not in sys.path:
    sys.path.insert(0, projects_dir)

# SkillsTown app setup
skillstown_path = os.path.join(projects_dir, 'skillstown')

# Define the paths to ensure they exist before import
os.makedirs(os.path.join(skillstown_path, 'uploads'), exist_ok=True)
os.makedirs(os.path.join(skillstown_path, 'static', 'data'), exist_ok=True)
os.makedirs(os.path.join(skillstown_path, 'static'), exist_ok=True)

# Import SkillsTown app with factory pattern
skillstown_error = None
try:
    # projects_dir is already in sys.path
    from skillstown.app import create_app
    skillstown_app = create_app('production')
    print("SkillsTown app imported successfully")
except Exception as e:
    skillstown_error = str(e)
    print(f"Could not import SkillsTown app: {skillstown_error}")
    print(f"Current sys.path: {sys.path}")
    print("Creating a stub SkillsTown app")
    skillstown_app = Flask("skillstown_stub")
    
    @skillstown_app.route('/')
    def skillstown_index():
        return f"SkillsTown is currently unavailable. Error: {skillstown_error}"

# AnimeWatchList app setup
animewatchlist_path = os.path.join(projects_dir, 'animewatchlist')

# Import the AnimeWatchList app with error handling
try:
    from animewatchlist.app import app as animewatchlist_app, db as animewatchlist_db
    Migrate(animewatchlist_app, animewatchlist_db)
    print("AnimeWatchList app imported successfully")
    has_animewatchlist_app = True
except Exception as e:
    print(f"Could not import AnimeWatchList app: {e}")
    print("Creating a stub AnimeWatchList app")
    animewatchlist_app = Flask("animewatchlist_stub")
    
    @animewatchlist_app.route('/')
    def animewatchlist_index():
        return "AnimeWatchList is currently unavailable. Database connection issues. Please check your PostgreSQL setup."
    
    has_animewatchlist_app = True

# Spotify Cover Generator app setup - FIXED VERSION
spotify_path = os.path.join(projects_dir, 'spotify-cover-generator')

def import_spotify_app():
    """Safely import the Spotify app with proper error handling"""
    try:
        print(f"Setting up Spotify app from path: {spotify_path}")
        
        if not os.path.exists(spotify_path):
            print(f"❌ Spotify path does not exist: {spotify_path}")
            return None, False
        
        try:
            # Add spotify-cover-generator to Python path
            if spotify_path not in sys.path:
                sys.path.insert(0, spotify_path)
            
            print(f"Attempting Spotify import. sys.path: {sys.path}")
            
            # Import directly from app.py in the spotify-cover-generator directory
            from app import app as spotify_app
            
            # Test basic app functionality
            with spotify_app.app_context():
                try:
                    from extensions import db
                    db.session.execute(db.text('SELECT 1'))
                    print("✓ Spotify app database connection verified")
                except Exception as db_error:
                    print(f"⚠️ Spotify database issue: {db_error}")
            
            print("✅ Spotify app imported successfully")
            return spotify_app, True
            
        except ImportError as import_error:
            print(f"❌ Spotify app import failed: {import_error}")
            print("Creating stub Spotify app")
            
            stub_app = Flask("spotify_stub")
            
            @stub_app.route('/')
            @stub_app.route('/<path:path>')
            def spotify_error(path=None):
                return f"""
                <h1>Spotify Cover Generator - Temporarily Unavailable</h1>
                <p>The Spotify Cover Generator is experiencing technical difficulties.</p>
                <p>Error: {import_error}</p>
                <p><a href=\"/\">Return to main site</a></p>
                """
            
            return stub_app, False
            
        except Exception as e:
            print(f"❌ Unexpected error importing Spotify app: {e}")
            import traceback
            print(f"Full traceback: {traceback.format_exc()}")
            return None, False
            
    except Exception as e:
        print(f"❌ Critical error in Spotify app setup: {e}")
        return None, False

# Use the safe import function
spotify_app, has_spotify_app = import_spotify_app()

# Configure Spotify app if it was imported successfully
if has_spotify_app and spotify_app:
    try:
        spotify_app.config['APPLICATION_ROOT'] = '/spotify'
        spotify_app.config['PREFERRED_URL_SCHEME'] = 'https'
        
        @spotify_app.context_processor
        def inject_spotify_vars():
            return {
                'current_year': datetime.datetime.now().year
            }
        
        print("✓ Spotify app configured successfully")
    except Exception as config_error:
        print(f"⚠️ Spotify app configuration warning: {config_error}")
else:
    print("⚠️ Spotify app not available")

# Update the static file serving for Spotify
if has_spotify_app:
    SPOTIFY_APP_STATIC_DIR = os.path.join(spotify_path, 'static')
    
    @main_app.route('/spotify/static/<path:filename>')
    def spotify_static(filename):
        try:
            if os.path.exists(os.path.join(SPOTIFY_APP_STATIC_DIR, filename)):
                return send_from_directory(SPOTIFY_APP_STATIC_DIR, filename)
            else:
                return f"Static file {filename} not found", 404
        except Exception as e:
            print(f"Error serving Spotify static file {filename}: {e}")
            return "Error serving file", 500

# Configure context processors
@skillstown_app.context_processor
def inject_skillstown_vars():
    return {
        'current_year': datetime.datetime.now().year
    }

@animewatchlist_app.context_processor
def inject_animewatchlist_vars():
    return {
        'current_year': datetime.datetime.now().year
    }

if has_spotify_app:
    @spotify_app.context_processor
    def inject_spotify_vars():
        return {
            'current_year': datetime.datetime.now().year
        }

# Configure app roots
skillstown_app.config['APPLICATION_ROOT'] = '/skillstown'
skillstown_app.config['PREFERRED_URL_SCHEME'] = 'https'

animewatchlist_app.config['APPLICATION_ROOT'] = '/animewatchlist'
animewatchlist_app.config['PREFERRED_URL_SCHEME'] = 'https'

if has_spotify_app:
    spotify_app.config['APPLICATION_ROOT'] = '/spotify'
    spotify_app.config['PREFERRED_URL_SCHEME'] = 'https'

# Define static folders explicitly
SKILLSTOWN_APP_STATIC_DIR = os.path.join(skillstown_path, 'static')
ANIMEWATCHLIST_APP_STATIC_DIR = os.path.join(animewatchlist_path, 'static')
if has_spotify_app:
    SPOTIFY_APP_STATIC_DIR = os.path.join(spotify_path, 'static')

# Set up routes for the main application to serve static files
@main_app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@main_app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(path):
        return send_from_directory('.', path)
    return "File not found", 404

# Create direct routes to the apps
@main_app.route('/projects/skillstown')
@main_app.route('/projects/skillstown/')
def skillstown_redirect():
    return redirect('/skillstown/')

@main_app.route('/projects/animewatchlist')
@main_app.route('/projects/animewatchlist/')
def animewatchlist_redirect():
    return redirect('/animewatchlist/')

if has_spotify_app:
    @main_app.route('/projects/spotify-cover-generator')
    @main_app.route('/projects/spotify-cover-generator/')
    def spotify_redirect():
        return redirect('/spotify/')

# Handle static files from the main app
@main_app.route('/skillstown/static/<path:filename>')
def skillstown_static(filename):
    print(f"Serving SkillsTown static file: {filename} from {SKILLSTOWN_APP_STATIC_DIR}")
    if os.path.exists(os.path.join(SKILLSTOWN_APP_STATIC_DIR, filename)):
        return send_from_directory(SKILLSTOWN_APP_STATIC_DIR, filename)
    else:
        print(f"SkillsTown static file not found: {filename}")
        if os.path.exists(os.path.join('static', filename)):
            return send_from_directory('static', filename)
        return f"Static file {filename} not found", 404

@main_app.route('/animewatchlist/static/<path:filename>')
def animewatchlist_static(filename):
    print(f"Serving AnimeWatchList static file: {filename} from {ANIMEWATCHLIST_APP_STATIC_DIR}")
    if os.path.exists(os.path.join(ANIMEWATCHLIST_APP_STATIC_DIR, filename)):
        return send_from_directory(ANIMEWATCHLIST_APP_STATIC_DIR, filename)
    else:
        print(f"AnimeWatchList static file not found: {filename}")
        return f"Static file {filename} not found", 404

# Class to handle routing to the app
class AppDispatcher:
    def __init__(self, app):
        self.app = app
        
    def __call__(self, environ, start_response):
        # Get the request path
        path_info = environ.get('PATH_INFO', '')
        
        # Handle static file requests
        if path_info.startswith('/skillstown/static/'):
            environ['PATH_INFO'] = path_info
            return main_app(environ, start_response)
        elif path_info.startswith('/animewatchlist/static/'):
            environ['PATH_INFO'] = path_info
            return main_app(environ, start_response)
        elif has_spotify_app and path_info.startswith('/spotify/static/'):
            environ['PATH_INFO'] = path_info
            return main_app(environ, start_response)
            
        # Route requests to the appropriate app
        if path_info.startswith('/skillstown'):
            script_name = '/skillstown'
            environ['SCRIPT_NAME'] = script_name
            environ['PATH_INFO'] = path_info[len(script_name):]
            return skillstown_app(environ, start_response)
        elif path_info.startswith('/animewatchlist'):
            script_name = '/animewatchlist'
            environ['SCRIPT_NAME'] = script_name
            environ['PATH_INFO'] = path_info[len(script_name):]
            return animewatchlist_app(environ, start_response)
        elif has_spotify_app and path_info.startswith('/spotify'):
            script_name = '/spotify'
            environ['SCRIPT_NAME'] = script_name
            environ['PATH_INFO'] = path_info[len(script_name):]
            return spotify_app(environ, start_response) # <-- Simplified call
            
        # Everything else goes to the main app
        return main_app(environ, start_response)

# Set up the WSGI application with our custom dispatcher
application = AppDispatcher(main_app)

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple('localhost', 5000, application, use_reloader=True)