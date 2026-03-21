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
<<<<<<< HEAD
    from animewatchlist.app import app as animewatchlist_app, db as animewatchlist_db
=======
    # Import the factory function
    from projects.animewatchlist.app import create_app as create_animewatchlist_app
    
    # Use the main app's config to create the animewatchlist app
    # The create_app function will use environment variables for configuration
    animewatchlist_app, animewatchlist_db = create_animewatchlist_app({
        'SQLALCHEMY_DATABASE_URI': os.environ.get('DATABASE_URL'),
        'SECRET_KEY': os.environ.get('FLASK_SECRET_KEY'),
    })
    
>>>>>>> animewatchlist-fixed
    Migrate(animewatchlist_app, animewatchlist_db)
    print("AnimeWatchList app created successfully using factory")
    has_animewatchlist_app = True
except Exception as e:
    print(f"Could not create AnimeWatchList app from factory: {e}")
    import traceback
    print(f"Full traceback: {traceback.format_exc()}")
    print("Creating a stub AnimeWatchList app")
    animewatchlist_app = Flask("animewatchlist_stub")
    
    @animewatchlist_app.route('/')
    def animewatchlist_index():
        return "AnimeWatchList is currently unavailable. Database connection issues. Please check your PostgreSQL setup."
    
    has_animewatchlist_app = False

# Spotify Cover Generator app setup - FIXED VERSION
spotify_path = os.path.join(projects_dir, 'spotify-cover-generator')

<<<<<<< HEAD
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
=======
# Import Spotify app - FIXED PATH HANDLING
try:
    print(f"Setting up Spotify app from path: {spotify_path}")
    # Store original sys.path and cwd to restore later
    original_sys_path = sys.path.copy()
    original_cwd = os.getcwd()
    # Add the spotify project directory to the path FIRST
    if spotify_path not in sys.path:
        sys.path.insert(0, spotify_path)
    print(f"Added Spotify path to sys.path: {spotify_path}")
    # Change the working directory temporarily for the import
    os.chdir(spotify_path)
    try:
        # Now import the app
        from app import app as spotify_app
        print("✅ Spotify app imported successfully")
        has_spotify_app = True
        # IMPORTANT: Configure the Spotify app for sub-path deployment
        spotify_app.config['APPLICATION_ROOT'] = '/spotify'
        spotify_app.config['PREFERRED_URL_SCHEME'] = 'https'
        # Add context processor
        @spotify_app.context_processor
        def inject_spotify_vars():
            return {'current_year': datetime.datetime.now().year}
    finally:
        # Always restore the working directory
        os.chdir(original_cwd)
except Exception as e:
    print(f"❌ Could not import Spotify app: {e}")
    print(f"Error type: {type(e).__name__}")
    import traceback
    print(f"Full traceback: {traceback.format_exc()}")
    has_spotify_app = False
    # Restore the original path if import failed
    sys.path = original_sys_path
>>>>>>> animewatchlist-fixed

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

@main_app.route('/projects/spotify-cover-generator')
@main_app.route('/projects/spotify-cover-generator/')
def spotify_redirect():
    """Fixed redirect to Spotify app"""
    if has_spotify_app:
        return redirect('/spotify/', code=302)
    else:
        return "Spotify Cover Generator is currently unavailable", 503

# Handle static files from the main app - FIXED STATIC FILE HANDLING
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

<<<<<<< HEAD
# Class to handle routing to the app
=======
if has_spotify_app:
    @main_app.route('/spotify/static/<path:filename>')
    def spotify_static(filename):
        print(f"Serving Spotify static file: {filename} from {SPOTIFY_APP_STATIC_DIR}")
        try:
            full_path = os.path.join(SPOTIFY_APP_STATIC_DIR, filename)
            if os.path.exists(full_path):
                return send_from_directory(SPOTIFY_APP_STATIC_DIR, filename)
            else:
                print(f"Spotify static file not found: {filename}")
                # Try fallback locations
                fallback_paths = [
                    os.path.join(spotify_path, 'templates', filename),
                    os.path.join(project_root, 'static', filename)
                ]
                for fallback_path in fallback_paths:
                    if os.path.exists(fallback_path):
                        return send_from_directory(os.path.dirname(fallback_path), os.path.basename(fallback_path))
                return f"Static file {filename} not found", 404
        except Exception as e:
            print(f"Error serving Spotify static file {filename}: {e}")
            return f"Error serving static file: {e}", 500

# Class to handle routing to the app - OPTIMIZED WITH ERROR HANDLING
>>>>>>> animewatchlist-fixed
class AppDispatcher:
    def __init__(self, app):
        self.app = app
        
    def __call__(self, environ, start_response):
        path_info = environ.get('PATH_INFO', '')
        print(f"🔍 AppDispatcher handling request: {path_info}")
        
        # Clean up double paths (fix for /animewatchlist/animewatchlist/static/)
        if '/animewatchlist/animewatchlist/' in path_info:
            path_info = path_info.replace('/animewatchlist/animewatchlist/', '/animewatchlist/')
            environ['PATH_INFO'] = path_info
            print(f"Fixed double path to: {path_info}")
        
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
            
<<<<<<< HEAD
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
=======
        # Route requests to the appropriate app with error handling
        try:
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
                print("Routing to Spotify app")
                script_name = '/spotify'
                environ['SCRIPT_NAME'] = script_name
                environ['PATH_INFO'] = path_info[len(script_name):]
                # CRITICAL FIX: Set the working directory and sys.path for Spotify app requests
                old_cwd = os.getcwd()
                old_sys_path = sys.path.copy()
                try:
                    os.chdir(spotify_path)
                    if spotify_path not in sys.path:
                        sys.path.insert(0, spotify_path)
                    return spotify_app(environ, start_response)
                finally:
                    os.chdir(old_cwd)
                    sys.path = old_sys_path
>>>>>>> animewatchlist-fixed
            
            print("Routing to main app")
            return main_app(environ, start_response)
            
        except Exception as e:
            print(f"Error in AppDispatcher routing: {e}")
            # Return a 500 error response
            status = '500 Internal Server Error'
            headers = [('Content-Type', 'text/html')]
            start_response(status, headers)
            error_message = f"""
            <html>
            <head><title>Application Error</title></head>
            <body>
            <h1>Application Error</h1>
            <p>There was an error processing your request: {str(e)}</p>
            <p><a href="/">Return to Home</a></p>
            </body>
            </html>
            """.encode('utf-8')
            return [error_message]

# Set up the WSGI application with our custom dispatcher
application = AppDispatcher(main_app)

# Health check endpoint for monitoring
@main_app.route('/health')
def health_check():
    """Simple health check endpoint for monitoring"""
    try:
        # Basic database connectivity test for AnimeWatchList
        if has_animewatchlist_app:
            with animewatchlist_app.app_context():
                # Simple query to test database
                from projects.animewatchlist.auth import User
                user_count = User.query.count()
                return {
                    'status': 'healthy',
                    'users': user_count,
                    'apps': {
                        'skillstown': skillstown_error is None,
                        'animewatchlist': True,
                        'spotify': has_spotify_app
                    }
                }
        else:
            return {'status': 'partial', 'message': 'Some apps unavailable'}
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}, 500

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple('localhost', 5000, application, use_reloader=True)