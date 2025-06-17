"""
WSGI Configuration for Portfolio Website Multi-App Deployment

This WSGI file serves multiple Flask applications:
1. SkillsTown CV Analyzer (from projects/skillstown/system/)
2. AnimeWatchList (from projects/animewatchlist/) 
3. Spotify Cover Generator (from projects/spotify-cover-generator/)
4. Main Portfolio Site (static files and navigation)

Each app is conditionally loaded with error handling and fallback stubs.
The AppDispatcher class routes requests to the appropriate sub-application.

Path structure:
- /skillstown/* -> SkillsTown app
- /animewatchlist/* -> AnimeWatchList app  
- /spotify/* -> Spotify Cover Generator app
- /* -> Main portfolio site

Updated: June 2025 - Refactored to match new workspace structure
"""

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

# ===================================================================
# SKILLSTOWN APP SETUP (CV Analyzer)
# ===================================================================
# SkillsTown app setup
skillstown_path = os.path.join(project_root, 'projects/skillstown')
skillstown_system_path = os.path.join(skillstown_path, 'system')

# Define the paths to ensure they exist before import
os.makedirs(os.path.join(skillstown_path, 'uploads'), exist_ok=True)
os.makedirs(os.path.join(skillstown_system_path, 'static', 'data'), exist_ok=True)
os.makedirs(os.path.join(skillstown_system_path, 'static'), exist_ok=True)

# Import SkillsTown app - it's in the system directory
skillstown_error = None
try:
    # Add the skillstown system directory to the path
    if skillstown_system_path not in sys.path:
        sys.path.insert(0, skillstown_system_path)
      # Import the create_app function from the skillstown system
    from app import create_app
    skillstown_app = create_app('production')
    print("✅ SkillsTown app imported successfully")
    has_skillstown_app = True
except Exception as e:
    skillstown_error = str(e)
    print(f"❌ Could not import SkillsTown app: {skillstown_error}")
    print(f"Error type: {type(e).__name__}")
    import traceback
    print(f"Full traceback: {traceback.format_exc()}")
    print("Creating a stub SkillsTown app")
    skillstown_app = Flask("skillstown_stub")
    has_skillstown_app = False
    
    @skillstown_app.route('/')
    def skillstown_index():
        return f"SkillsTown is currently unavailable. Error: {skillstown_error}"

# ===================================================================
# ANIMEWATCHLIST APP SETUP
# ===================================================================
# AnimeWatchList app setup
animewatchlist_path = os.path.join(project_root, 'projects/animewatchlist')
sys.path.insert(0, animewatchlist_path)

# Import the AnimeWatchList app with error handling
try:
    from projects.animewatchlist.app import app as animewatchlist_app, db as animewatchlist_db
    Migrate(animewatchlist_app, animewatchlist_db)
    print("✅ AnimeWatchList app imported successfully")
    has_animewatchlist_app = True
except Exception as e:
    print(f"❌ Could not import AnimeWatchList app: {e}")
    print(f"Error type: {type(e).__name__}")
    import traceback
    print(f"Full traceback: {traceback.format_exc()}")
    print("Creating a stub AnimeWatchList app")
    animewatchlist_app = Flask("animewatchlist_stub")
    has_animewatchlist_app = False
    
    @animewatchlist_app.route('/')
    def animewatchlist_index():        return "AnimeWatchList is currently unavailable. Database connection issues. Please check your PostgreSQL setup."

# ===================================================================
# SPOTIFY COVER GENERATOR APP SETUP  
# ===================================================================
# Spotify Cover Generator app setup
spotify_path = os.path.join(project_root, 'projects/spotify-cover-generator')

# Import Spotify app - FIXED PATH HANDLING
try:
    print(f"Setting up Spotify app from path: {spotify_path}")
    
    # Store original sys.path to restore later
    original_sys_path = sys.path.copy()
    
    # Add the spotify project directory to the path FIRST
    # This ensures all imports within the spotify app work correctly
    if spotify_path not in sys.path:
        sys.path.insert(0, spotify_path)
    
    print(f"Added Spotify path to sys.path: {spotify_path}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Spotify directory contents: {os.listdir(spotify_path) if os.path.exists(spotify_path) else 'Directory not found'}")
    
    # Change the working directory temporarily for the import
    old_cwd = os.getcwd()
    os.chdir(spotify_path)
    
    try:
        from app import app as spotify_app
        print("✅ Spotify app imported successfully")
        has_spotify_app = True
    finally:
        # Always restore the working directory
        os.chdir(old_cwd)
        
except Exception as e:
    print(f"❌ Could not import Spotify app: {e}")
    print(f"Error type: {type(e).__name__}")
    import traceback
    print(f"Full traceback: {traceback.format_exc()}")
    has_spotify_app = False    # Restore the original path if import failed
    sys.path = original_sys_path

# ===================================================================
# FLASK APP CONFIGURATION
# ===================================================================
# Configure context processors
if has_skillstown_app:
    @skillstown_app.context_processor
    def inject_skillstown_vars():
        return {
            'current_year': datetime.datetime.now().year
        }

if has_animewatchlist_app:
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
if has_skillstown_app:
    skillstown_app.config['APPLICATION_ROOT'] = '/skillstown'
    skillstown_app.config['PREFERRED_URL_SCHEME'] = 'https'

if has_animewatchlist_app:
    animewatchlist_app.config['APPLICATION_ROOT'] = '/animewatchlist'
    animewatchlist_app.config['PREFERRED_URL_SCHEME'] = 'https'

if has_spotify_app:
    spotify_app.config['APPLICATION_ROOT'] = '/spotify'
    spotify_app.config['PREFERRED_URL_SCHEME'] = 'https'

# Define static folders explicitly
if has_skillstown_app:
    SKILLSTOWN_APP_STATIC_DIR = os.path.join(skillstown_system_path, 'static')
if has_animewatchlist_app:
    ANIMEWATCHLIST_APP_STATIC_DIR = os.path.join(animewatchlist_path, 'static')
if has_spotify_app:
    SPOTIFY_APP_STATIC_DIR = os.path.join(spotify_path, 'static')

# ===================================================================
# MAIN APP ROUTES AND STATIC FILE SERVING
# ===================================================================
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
if has_skillstown_app:
    @main_app.route('/projects/skillstown')
    @main_app.route('/projects/skillstown/')
    def skillstown_redirect():
        return redirect('/skillstown/')

if has_animewatchlist_app:
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
if has_skillstown_app:
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

if has_animewatchlist_app:
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

# ===================================================================
# WSGI APPLICATION DISPATCHER
# ===================================================================
# Class to handle routing to the app
class AppDispatcher:
    def __init__(self, app):
        self.app = app
        
    def __call__(self, environ, start_response):
        # Get the request path
        path_info = environ.get('PATH_INFO', '')        # Handle static file requests
        if has_skillstown_app and path_info.startswith('/skillstown/static/'):
            environ['PATH_INFO'] = path_info
            return main_app(environ, start_response)
        elif has_animewatchlist_app and path_info.startswith('/animewatchlist/static/'):
            environ['PATH_INFO'] = path_info
            return main_app(environ, start_response)
        elif has_spotify_app and path_info.startswith('/spotify/static/'):
            environ['PATH_INFO'] = path_info
            return main_app(environ, start_response)
            
        # Route requests to the appropriate app
        if has_skillstown_app and path_info.startswith('/skillstown'):
            script_name = '/skillstown'
            environ['SCRIPT_NAME'] = script_name
            environ['PATH_INFO'] = path_info[len(script_name):]
            return skillstown_app(environ, start_response)
        elif has_animewatchlist_app and path_info.startswith('/animewatchlist'):
            script_name = '/animewatchlist'
            environ['SCRIPT_NAME'] = script_name
            environ['PATH_INFO'] = path_info[len(script_name):]
            return animewatchlist_app(environ, start_response)
        elif has_spotify_app and path_info.startswith('/spotify'):
            script_name = '/spotify'
            environ['SCRIPT_NAME'] = script_name
            environ['PATH_INFO'] = path_info[len(script_name):]
            # IMPORTANT: Set the working directory for Spotify app requests
            old_cwd = os.getcwd()
            try:
                os.chdir(spotify_path)
                return spotify_app(environ, start_response)
            finally:
                os.chdir(old_cwd)
            
        # Everything else goes to the main app
        return main_app(environ, start_response)

# Set up the WSGI application with our custom dispatcher
application = AppDispatcher(main_app)

# ===================================================================
# DEVELOPMENT SERVER
# ===================================================================
if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple('localhost', 5000, application, use_reloader=True)

# ===================================================================
# REFACTORING NOTES (June 2025)
# ===================================================================
# Key changes made to match new workspace structure:
# 1. SkillsTown app moved from projects/skillstown/app.py to projects/skillstown/system/app.py
# 2. Added proper error handling and conditional loading for all apps
# 3. Fixed static file paths to match actual directory structure
# 4. Added has_*_app flags to prevent errors when apps fail to load
# 5. Improved logging with ✅/❌ indicators for better debugging
# 6. Maintained backward compatibility with existing routes
# ===================================================================