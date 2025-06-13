import os
import sys
import datetime
from flask import Flask, send_from_directory, redirect, request
from dotenv import load_dotenv
from flask_migrate import Migrate
import importlib.util
import importlib.machinery

# Load environment variables
load_dotenv()

# Create a main application to serve static files
main_app = Flask(__name__, static_folder='.')

# Set the Python path to include the project directories
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
print(f"Inserted project_root into sys.path: {project_root}") # Diagnostic print

# SkillsTown app setup
skillstown_path = os.path.join(project_root, 'projects/skillstown')
# sys.path.insert(0, skillstown_path) # Removed: project_root is now in sys.path

# Define the paths to ensure they exist before import
os.makedirs(os.path.join(skillstown_path, 'uploads'), exist_ok=True)
os.makedirs(os.path.join(skillstown_path, 'static', 'data'), exist_ok=True)
os.makedirs(os.path.join(skillstown_path, 'static'), exist_ok=True)

# Import SkillsTown app with factory pattern
skillstown_error = None
try:
    # First add the projects directory to the path - This specific insertion is now removed.
    # projects_path = os.path.join(project_root, 'projects') # Definition can be kept if used elsewhere
    # if projects_path not in sys.path: # Removed: project_root is now in sys.path
    #     sys.path.insert(0, projects_path)
    
    from projects.skillstown.app import create_app # Changed to projects.skillstown.app
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
animewatchlist_path = os.path.join(project_root, 'projects/animewatchlist')
# sys.path.insert(0, animewatchlist_path) # Removed: project_root is now in sys.path

# Import the AnimeWatchList app with error handling
try:
    from projects.animewatchlist.app import app as animewatchlist_app, db as animewatchlist_db
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

# Spotify Cover Generator app setup
spotify_path = os.path.join(project_root, 'projects/spotify-cover-generator') # Keep this for reference if needed by other parts, or for AppDispatcher
projects_path = os.path.join(project_root, 'projects') # Ensure this is added to sys.path if not already done earlier for skillstown

# Ensure the 'projects' directory is in sys.path (it should be from skillstown setup)
# Example: if projects_path not in sys.path: sys.path.insert(0, projects_path)
# This is usually done earlier, e.g., before importing skillstown.

has_spotify_app = False
spotify_app = None
print("Attempting Spotify app import using importlib for projects/spotify-cover-generator/app.py")
try:
    spotify_app_path = os.path.join(project_root, 'projects', 'spotify-cover-generator', 'app.py')
    if not os.path.exists(spotify_app_path):
        print(f"❌ Spotify app file not found at {spotify_app_path}")
    else:
        # Use a unique module name for importlib, e.g., 'spotify_cover_generator_app_module'
        module_name = "spotify_cover_generator_app_module"
        spec = importlib.util.spec_from_file_location(module_name, spotify_app_path)
        if spec and spec.loader:
            spotify_module = importlib.util.module_from_spec(spec)
            # Add the 'projects' directory to sys.path temporarily if it helps resolution within the module
            # This is because the spotify app itself might have imports like 'from projects.spotify-cover-generator import ...'
            # which won't work. It more likely has relative imports like 'from . import models'
            # For importlib, the module's __name__ will be `module_name` not `projects.spotify-cover-generator.app`
            # The key is how internal imports within spotify-cover-generator/app.py are handled.
            # Let's ensure the parent directory of 'spotify-cover-generator' is in sys.path
            spotify_project_parent_dir = os.path.join(project_root, 'projects')
            if spotify_project_parent_dir not in sys.path:
                sys.path.insert(0, spotify_project_parent_dir)
            # Also add the actual app's directory to sys.path as it might do 'from . import ...'
            spotify_app_dir = os.path.join(project_root, 'projects', 'spotify-cover-generator')
            if spotify_app_dir not in sys.path:
                sys.path.insert(0, spotify_app_dir)

            # Crucially, for relative imports within the loaded module to work as if it's part of a package,
            # its __name__ should be set as if it's part of 'projects.spotify-cover-generator'
            # However, spec_from_file_location sets __name__ to the first arg.
            # For simplicity now, let's see if direct execution works.
            # If there are issues with relative imports inside spotify_cover_generator/app.py,
            # we might need to adjust its __package__ or __name__ before exec_module.
            # Example: spotify_module.__name__ = 'projects.spotify_cover_generator.app'
            # spotify_module.__package__ = 'projects.spotify_cover_generator'

            setattr(spotify_module, '__package__', module_name) # Or spotify_module.__package__ = module_name
            spec.loader.exec_module(spotify_module)
            if hasattr(spotify_module, 'app'):
                spotify_app = spotify_module.app
                print("✅ Spotify app imported successfully using importlib and 'app' attribute found.")
                has_spotify_app = True
            else:
                print("❌ Spotify app loaded via importlib, but 'app' attribute not found in the module.")
        else:
            print(f"❌ Could not create spec or loader for Spotify app at {spotify_app_path}")
except Exception as e:
    print(f"❌ Error during importlib loading of Spotify app: {e}")
    import traceback
    print(f"Full traceback: {traceback.format_exc()}")
    # Ensure spotify_app is None if it failed
    spotify_app = None
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
            # No more chdir needed here
            return spotify_app(environ, start_response)
            
        # Everything else goes to the main app
        return main_app(environ, start_response)

# Set up the WSGI application with our custom dispatcher
application = AppDispatcher(main_app)

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple('localhost', 5000, application, use_reloader=True)