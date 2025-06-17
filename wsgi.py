import os
import sys
import datetime
from flask import Flask, send_from_directory, redirect
from dotenv import load_dotenv
from flask_migrate import Migrate

# Load environment variables
load_dotenv()

# Create a main application to serve static files
main_app = Flask(__name__, static_folder='.')

# Base path for locating sub‐apps
project_root = os.path.dirname(os.path.abspath(__file__))


# ===================================================================
# SKILLSTOWN APP SETUP (CV Analyzer)
# ===================================================================
skillstown_path = os.path.join(project_root, 'projects/skillstown')
skillstown_system_path = os.path.join(skillstown_path, 'system')

# Ensure upload/static dirs exist
os.makedirs(os.path.join(skillstown_path, 'uploads'), exist_ok=True)
os.makedirs(os.path.join(skillstown_system_path, 'static', 'data'), exist_ok=True)
os.makedirs(os.path.join(skillstown_system_path, 'static'), exist_ok=True)

skillstown_error = None
try:
    if skillstown_system_path not in sys.path:
        sys.path.insert(0, skillstown_system_path)
    from app import create_app as create_skillstown_app
    skillstown_app = create_skillstown_app('production')
    has_skillstown_app = True
    print("✅ SkillsTown app imported successfully")
except Exception as e:
    skillstown_error = str(e)
    has_skillstown_app = False
    print(f"❌ Could not import SkillsTown: {e}")
    skillstown_app = Flask("skillstown_stub")
    @skillstown_app.route('/')
    def skillstown_index():
        return f"SkillsTown unavailable: {skillstown_error}"


# ===================================================================
# ANIMEWATCHLIST APP SETUP
# ===================================================================
animewatchlist_path = os.path.join(project_root, 'projects/animewatchlist')
if animewatchlist_path not in sys.path:
    sys.path.insert(0, animewatchlist_path)

try:
    from projects.animewatchlist.app import app as animewatchlist_app, db as animewatchlist_db
    Migrate(animewatchlist_app, animewatchlist_db)
    has_animewatchlist_app = True
    print("✅ AnimeWatchList app imported successfully")
except Exception as e:
    has_animewatchlist_app = False
    print(f"❌ Could not import AnimeWatchList: {e}")
    animewatchlist_app = Flask("animewatchlist_stub")
    @animewatchlist_app.route('/')
    def animewatchlist_index():
        return "AnimeWatchList unavailable (DB error)"


# ===================================================================
# SPOTIFY COVER GENERATOR APP SETUP
# ===================================================================
spotify_path = os.path.join(project_root, 'projects/spotify-cover-generator')
spotify_error = None

try:
    original_sys_path = sys.path.copy()
    if spotify_path not in sys.path:
        sys.path.insert(0, spotify_path)
    old_cwd = os.getcwd()
    os.chdir(spotify_path)
    from app import app as spotify_app
    has_spotify_app = True
    print("✅ Spotify app imported successfully")
    os.chdir(old_cwd)
except Exception as e:
    spotify_error = str(e)
    has_spotify_app = False
    print(f"❌ Could not import Spotify: {e}")
    os.chdir(old_cwd)
    sys.path = original_sys_path
    spotify_app = Flask("spotify_stub")
    @spotify_app.route('/')
    def spotify_index():
        return f"Spotify unavailable: {spotify_error}"


# ===================================================================
# CONTEXT PROCESSORS & CONFIGURATION
# ===================================================================
def make_injector():
    return {'current_year': datetime.datetime.now().year}

if has_skillstown_app:
    skillstown_app.context_processor(make_injector)
    skillstown_app.config.update({
        'APPLICATION_ROOT': '/skillstown',
        'PREFERRED_URL_SCHEME': 'https',
    })
    skillstown_app.url_map.strict_slashes = False

if has_animewatchlist_app:
    animewatchlist_app.context_processor(make_injector)
    animewatchlist_app.config.update({
        'APPLICATION_ROOT': '/animewatchlist',
        'PREFERRED_URL_SCHEME': 'https',
    })
    animewatchlist_app.url_map.strict_slashes = False

# Always inject and configure Spotify
spotify_app.context_processor(make_injector)
spotify_app.config.update({
    'APPLICATION_ROOT': '/spotify',
    'PREFERRED_URL_SCHEME': 'https',
})
spotify_app.url_map.strict_slashes = False

# Static directories for sub‐apps
if has_skillstown_app:
    SKILLSTOWN_STATIC = os.path.join(skillstown_system_path, 'static')
if has_animewatchlist_app:
    ANIMEWATCHLIST_STATIC = os.path.join(animewatchlist_path, 'static')
SPOTIFY_STATIC = os.path.join(spotify_path, 'static')


# ===================================================================
# MAIN APP ROUTES & STATIC FILE SERVING
# ===================================================================
@main_app.route('/')
def index():
    return send_from_directory('.', 'index.html')


# Project shortcuts
if has_skillstown_app:
    @main_app.route('/projects/skillstown')
    @main_app.route('/projects/skillstown/')
    def proj_skillstown():
        return redirect('/skillstown/')

if has_animewatchlist_app:
    @main_app.route('/projects/animewatchlist')
    @main_app.route('/projects/animewatchlist/')
    def proj_animewatchlist():
        return redirect('/animewatchlist/')

@main_app.route('/projects/spotify-cover-generator')
@main_app.route('/projects/spotify-cover-generator/')
def proj_spotify():
    return redirect('/spotify/')


@main_app.route('/<path:path>')
def serve_static(path):
    # Handle project shortcuts
    if path.startswith('projects/skillstown'):
        return redirect('/skillstown/')
    if path.startswith('projects/animewatchlist'):
        return redirect('/animewatchlist/')
    if path.startswith('projects/spotify-cover-generator'):
        return redirect('/spotify/')
    # Serve file if it exists
    if os.path.exists(path):
        return send_from_directory('.', path)
    return "File not found", 404


# Static asset routes for sub‐apps
if has_skillstown_app:
    @main_app.route('/skillstown/static/<path:filename>')
    def skillstown_static(filename):
        full = os.path.join(SKILLSTOWN_STATIC, filename)
        if os.path.exists(full):
            return send_from_directory(SKILLSTOWN_STATIC, filename)
        return "SkillsTown static not found", 404

if has_animewatchlist_app:
    @main_app.route('/animewatchlist/static/<path:filename>')
    def animewatchlist_static(filename):
        full = os.path.join(ANIMEWATCHLIST_STATIC, filename)
        if os.path.exists(full):
            return send_from_directory(ANIMEWATCHLIST_STATIC, filename)
        return "AnimeWatchList static not found", 404

@main_app.route('/spotify/static/<path:filename>')
def spotify_static(filename):
    full = os.path.join(SPOTIFY_STATIC, filename)
    if os.path.exists(full):
        return send_from_directory(SPOTIFY_STATIC, filename)
    return "Spotify static not found", 404


@main_app.route('/debug/apps')
def debug_apps():
    return (
        f"<h2>App Status</h2>"
        f"<ul>"
        f"<li>SkillsTown: {'✅' if has_skillstown_app else '❌'}</li>"
        f"<li>AnimeWatchList: {'✅' if has_animewatchlist_app else '❌'}</li>"
        f"<li>Spotify: {'✅' if has_spotify_app else '❌'}</li>"
        f"</ul>"
        f"<pre>Spotify error: {spotify_error or 'None'}</pre>"
        f"<pre>SkillsTown error: {skillstown_error or 'None'}</pre>"
    )


# ===================================================================
# WSGI APPLICATION DISPATCHER
# ===================================================================
class AppDispatcher:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        print(f"Routing: {path}")

        # 1) Static files for sub‐apps
        if has_skillstown_app and path.startswith('/skillstown/static/'):
            return main_app(environ, start_response)
        if has_animewatchlist_app and path.startswith('/animewatchlist/static/'):
            return main_app(environ, start_response)
        if path.startswith('/spotify/static/'):
            return main_app(environ, start_response)

        # 2) Sub‐app routes
        if path == '/spotify' or path.startswith('/spotify/'):
            if has_spotify_app:
                environ['SCRIPT_NAME'] = '/spotify'
                environ['PATH_INFO'] = path[len('/spotify'): ] or '/'
                old = os.getcwd()
                os.chdir(spotify_path)
                try:
                    return spotify_app(environ, start_response)
                finally:
                    os.chdir(old)
            return spotify_app(environ, start_response)

        if has_skillstown_app and (path == '/skillstown' or path.startswith('/skillstown/')):
            environ['SCRIPT_NAME'] = '/skillstown'
            environ['PATH_INFO'] = path[len('/skillstown'): ] or '/'
            return skillstown_app(environ, start_response)

        if has_animewatchlist_app and (path == '/animewatchlist' or path.startswith('/animewatchlist/')):
            environ['SCRIPT_NAME'] = '/animewatchlist'
            environ['PATH_INFO'] = path[len('/animewatchlist'): ] or '/'
            return animewatchlist_app(environ, start_response)

        # 3) Fallback to main
        return main_app(environ, start_response)


# Expose WSGI app
application = AppDispatcher(main_app)


# Development server
if __name__ == '__main__':
    from werkzeug.serving import run_simple
    run_simple('localhost', 5000, application, use_reloader=True)