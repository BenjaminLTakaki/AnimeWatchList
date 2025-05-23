import os
import sys
import datetime
from flask import Flask, send_from_directory, redirect, request
from dotenv import load_dotenv
from flask_migrate import Migrate  # ADDED

# Load environment variables
load_dotenv()

# Create a main application to serve static files
main_app = Flask(__name__, static_folder='.')

# Set the Python path to include the project directories
project_root = os.path.dirname(os.path.abspath(__file__))

# SkillsTown app setup
skillstown_path = os.path.join(project_root, 'projects/skillstown')
sys.path.insert(0, skillstown_path)

# Define the paths to ensure they exist before import
os.makedirs(os.path.join(skillstown_path, 'uploads'), exist_ok=True)
os.makedirs(os.path.join(skillstown_path, 'static', 'data'), exist_ok=True)
os.makedirs(os.path.join(skillstown_path, 'static'), exist_ok=True)

# Import SkillsTown app with factory pattern
skillstown_error = None
try:
    # First add the projects directory to the path
    projects_path = os.path.join(project_root, 'projects')
    if projects_path not in sys.path:
        sys.path.insert(0, projects_path)
    
    from skillstown.app import create_app
    skillstown_app = create_app('production')
    # db instance is created within create_app and init_auth, need to access it
    # However, Flask-Migrate should be initialized where both app and db are available.
    # It's already initialized in skillstown.app.create_app
    # For wsgi.py, if we need to run flask db commands, we might need a way to access the db instance.
    # For now, assuming the initialization in skillstown.app.create_app is sufficient for Render's context.
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
animewatchlist_path = os.path.join(project_root, 'projects/animewatchlist')
sys.path.insert(0, animewatchlist_path)

# Import the AnimeWatchList app with error handling
try:
    from projects.animewatchlist.app import app as animewatchlist_app, db as animewatchlist_db  # MODIFIED
    Migrate(animewatchlist_app, animewatchlist_db)  # Initialize Flask-Migrate for AnimeWatchList
    print("AnimeWatchList app imported successfully")
    has_animewatchlist_app = True
except Exception as e:
    print(f"Could not import AnimeWatchList app: {e}")
    print("Creating a stub AnimeWatchList app")
    animewatchlist_app = Flask("animewatchlist_stub")
    
    @animewatchlist_app.route('/')
    def animewatchlist_index():
        return "AnimeWatchList is currently unavailable. Database connection issues. Please check your PostgreSQL setup."
    
    has_animewatchlist_app = True  # Keep as True so routing still works

# Spotify Cover Generator app setup
spotify_path = os.path.join(project_root, 'projects/spotify-cover-generator')

# Import Spotify app - add its path first to avoid config conflicts
try:
    # Clear the conflicting paths
    original_sys_path = sys.path.copy()
    sys.path = [p for p in sys.path if 'skillstown' not in p and 'animewatchlist' not in p]
    sys.path.insert(0, spotify_path)
    
    from app import app as spotify_app
    print("Spotify app imported successfully")
    has_spotify_app = True
    
    # Restore original path
    sys.path = original_sys_path
except ImportError as e:
    print(f"Could not import Spotify app: {e}")
    has_spotify_app = False

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
        # Fallback: check if the file exists in the root static folder
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

if has_spotify_app:
    @main_app.route('/spotify/static/<path:filename>')
    def spotify_static(filename):
        print(f"Serving Spotify static file: {filename} from {SPOTIFY_APP_STATIC_DIR}")
        if os.path.exists(os.path.join(SPOTIFY_APP_STATIC_DIR, filename)):
            return send_from_directory(SPOTIFY_APP_STATIC_DIR, filename)
        else:
            print(f"Spotify static file not found: {filename}")
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
            return spotify_app(environ, start_response)
            
        # Everything else goes to the main app
        return main_app(environ, start_response)

# Set up the WSGI application with our custom dispatcher
application = AppDispatcher(main_app)

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    # Set the hostname and port for local development
    run_simple('localhost', 5000, application, use_reloader=True)